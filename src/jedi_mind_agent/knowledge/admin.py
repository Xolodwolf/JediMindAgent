from django.conf import settings as django_settings
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from jedi_mind_agent.knowledge.models import Book, BookStatus, RagSettings
from jedi_mind_agent.knowledge.rag import RagServiceError, check_health


@admin.register(RagSettings)
class RagSettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        ("RAG-сервис", {"fields": ["rag_service_url", "request_timeout_seconds", "top_k"]}),
        ("ChromaDB", {"fields": ["chroma_host", "chroma_port", "chroma_collection"]}),
        ("Состояние", {"fields": ["connection_status", "database_info"]}),
    ]
    readonly_fields = ["connection_status", "database_info"]

    def changelist_view(self, request, extra_context=None):
        # A single row: the list page goes straight to its form.
        settings = RagSettings.load()
        return redirect(reverse("admin:knowledge_ragsettings_change", args=[settings.pk]))

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    @admin.display(description="RAG-сервис и ChromaDB")
    def connection_status(self, obj: RagSettings) -> str:
        try:
            health = check_health(obj)
        except RagServiceError as exc:
            return format_html('<span style="color:#ba2121">{}</span>', str(exc))
        chroma = health.get("chroma", {})
        rows = [
            ("RAG-сервис", "доступен"),
            ("Модель эмбеддингов", health.get("embedding_model", "—")),
            ("Воркер загрузки книг", "работает" if health.get("worker_running") else "не запущен"),
            ("ChromaDB", "доступна" if chroma.get("ok") else f"недоступна: {chroma.get('error', '')}"),
        ]
        if chroma.get("ok"):
            rows.append(("Фрагментов в коллекции", chroma.get("count", 0)))
        return format_html("<table>{}</table>", format_html_join("", "<tr><td>{}</td><td>{}</td></tr>", rows))

    @admin.display(description="PostgreSQL")
    def database_info(self, obj: RagSettings) -> str:
        db = django_settings.DATABASES["default"]
        return format_html(
            "подключена: {} {}:{}<br><span style='color:#666'>Подключение задаётся переменной DATABASE_URL: "
            "через админку его не поменять, админка сама работает на этой базе.</span>",
            db.get("NAME"),
            db.get("HOST") or "local",
            db.get("PORT") or "-",
        )


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ["title", "slug", "status_badge", "chunk_count", "page_count", "processed_at", "updated_at"]
    list_filter = ["status"]
    search_fields = ["title", "slug"]
    actions = ["reindex", "remove"]
    readonly_fields = [
        "status_badge",
        "error",
        "page_count",
        "chunk_count",
        "levels_table",
        "file_hash",
        "embedding_model",
        "ingest_config",
        "indexed_config",
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
        # The slug names the book's chunks in ChromaDB, so it is fixed after creation.
        return [*self.readonly_fields, "slug"] if obj else []

    def has_delete_permission(self, request, obj=None) -> bool:
        # Deleting the row would leave its chunks in ChromaDB: books are removed by the worker via the action.
        return False

    def save_model(self, request, obj: Book, form, change: bool) -> None:
        if change and not form.has_changed():
            return
        if change and "file" in form.changed_data:
            old = Book.objects.get(pk=obj.pk)
            if old.file and old.file.name != obj.file.name:
                old.file.delete(save=False)
        # A new file or a new title changes what is stored in ChromaDB, so the book is indexed again.
        obj.enqueue()
        self.message_user(
            request,
            f"«{obj.title}» поставлена в очередь. Воркер RAG-сервиса загрузит её в ChromaDB; обновите страницу, "
            "чтобы увидеть статус.",
            messages.INFO,
        )

    @admin.action(description="Загрузить в ChromaDB заново")
    def reindex(self, request, queryset) -> None:
        count = Book.enqueue_many(queryset)
        self.message_user(request, f"Поставлено в очередь книг: {count}.", messages.SUCCESS)

    @admin.action(description="Удалить книги и их фрагменты из ChromaDB")
    def remove(self, request, queryset) -> None:
        count = Book.request_deletion(queryset)
        self.message_user(request, f"Воркер удалит книг: {count}.", messages.SUCCESS)

    @admin.display(description="статус", ordering="status")
    def status_badge(self, obj: Book) -> str:
        colors = {
            BookStatus.READY: "#2f7d4a",
            BookStatus.FAILED: "#ba2121",
            BookStatus.PROCESSING: "#b07a00",
            BookStatus.DELETING: "#666",
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
