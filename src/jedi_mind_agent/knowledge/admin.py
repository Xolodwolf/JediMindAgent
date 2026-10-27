from django.conf import settings as django_settings
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from jedi_mind_agent.knowledge.models import Book, BookStatus, RagSettings, chunk_store_stats
from jedi_mind_agent.knowledge.rag import RagServiceError, check_health


@admin.register(RagSettings)
class RagSettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        ("RAG-сервис", {"fields": ["rag_service_url", "request_timeout_seconds", "top_k"]}),
        ("Состояние", {"fields": ["service_status", "database_info"]}),
    ]
    readonly_fields = ["service_status", "database_info"]

    def changelist_view(self, request, extra_context=None):
        # A single row: the list page goes straight to its form.
        settings = RagSettings.load()
        return redirect(reverse("admin:knowledge_ragsettings_change", args=[settings.pk]))

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    @admin.display(description="RAG-сервис")
    def service_status(self, obj: RagSettings) -> str:
        try:
            health = check_health(obj)
        except RagServiceError as exc:
            return format_html('<span style="color:#ba2121">{}</span>', str(exc))
        database = health.get("database", {})
        rows = [
            ("RAG-сервис", "доступен"),
            ("Модель эмбеддингов", health.get("embedding_model", "—")),
            ("Воркер загрузки книг", "работает" if health.get("worker_running") else "не запущен"),
            ("База из RAG-сервиса", "доступна" if database.get("ok") else f"недоступна: {database.get('error', '')}"),
        ]
        return format_html("<table>{}</table>", format_html_join("", "<tr><td>{}</td><td>{}</td></tr>", rows))

    @admin.display(description="PostgreSQL и pgvector")
    def database_info(self, obj: RagSettings) -> str:
        db = django_settings.DATABASES["default"]
        stats = chunk_store_stats()
        return format_html(
            "подключена: {} {}:{}<br>pgvector: {}, фрагментов книг: {}<br><span style='color:#666'>"
            "Подключение задаётся переменной DATABASE_URL: через админку его не поменять, админка сама работает "
            "на этой базе.</span>",
            db.get("NAME"),
            db.get("HOST") or "local",
            db.get("PORT") or "-",
            stats["pgvector"] or "не установлен",
            stats["count"],
        )


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ["title", "slug", "status_badge", "chunk_count", "page_count", "processed_at", "updated_at"]
    list_filter = ["status"]
    search_fields = ["title", "slug"]
    actions = ["reindex"]
    readonly_fields = [
        "status_badge",
        "error",
        "page_count",
        "chunk_count",
        "levels_table",
        "file_hash",
        "embedding_model",
        "revision",
        "created_at",
        "started_at",
        "processed_at",
    ]

    def get_fields(self, request, obj=None):
        if obj is None:
            return ["title", "slug", "file"]
        return ["title", "slug", "file", *self.readonly_fields]

    def get_readonly_fields(self, request, obj=None):
        # The slug is stored with the book's chunks, so it is fixed after creation.
        return [*self.readonly_fields, "slug"] if obj else []

    def save_model(self, request, obj: Book, form, change: bool) -> None:
        if change and not form.has_changed():
            return
        if change and "file" in form.changed_data:
            old = Book.objects.get(pk=obj.pk)
            if old.file and old.file.name != obj.file.name:
                old.file.delete(save=False)
        # A new file or a new title changes the stored chunks, so the book is indexed again.
        obj.enqueue()
        self.message_user(
            request,
            f"«{obj.title}» поставлена в очередь. Воркер RAG-сервиса проиндексирует её; обновите страницу, "
            "чтобы увидеть статус.",
            messages.INFO,
        )

    @admin.action(description="Проиндексировать заново")
    def reindex(self, request, queryset) -> None:
        count = Book.enqueue_many(queryset)
        self.message_user(request, f"Поставлено в очередь книг: {count}.", messages.SUCCESS)

    @admin.display(description="статус", ordering="status")
    def status_badge(self, obj: Book) -> str:
        colors = {
            BookStatus.READY: "#2f7d4a",
            BookStatus.FAILED: "#ba2121",
            BookStatus.PROCESSING: "#b07a00",
        }
        return format_html('<b style="color:{}">{}</b>', colors.get(obj.status, "#417690"), obj.get_status_display())

    @admin.display(description="фрагментов по уровням")
    def levels_table(self, obj: Book) -> str:
        if not obj.chunks_by_level:
            return "—"
        rows = sorted(obj.chunks_by_level.items(), key=lambda item: int(item[0]))
        return format_html_join(
            ", ", "{}: {}", ((("общие" if str(level) == "0" else f"уровень {level}"), count) for level, count in rows)
        )
