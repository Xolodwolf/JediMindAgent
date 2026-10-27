import uuid

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import connection, models
from django.db.models import F
from django.utils.text import slugify

MAX_BOOK_SIZE = 200 * 1024 * 1024


class RagSettings(models.Model):
    """Single row: where the RAG service is and how many book chunks the agent gets."""

    SINGLETON_ID = 1

    rag_service_url = models.URLField(
        "URL RAG-сервиса", default="http://rag:8001", help_text="Сервис эмбеддингов и поиска (FastAPI)."
    )
    request_timeout_seconds = models.PositiveSmallIntegerField(
        "таймаут запроса к RAG-сервису, с", default=30, validators=[MinValueValidator(1), MaxValueValidator(300)]
    )
    top_k = models.PositiveSmallIntegerField(
        "фрагментов в контексте агента", default=5, validators=[MinValueValidator(1), MaxValueValidator(20)]
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "настройки RAG"
        verbose_name_plural = "настройки RAG"

    def __str__(self) -> str:
        return "Настройки RAG"

    def save(self, *args, **kwargs) -> None:
        self.pk = self.SINGLETON_ID
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "RagSettings":
        settings, _ = cls.objects.get_or_create(pk=cls.SINGLETON_ID)
        return settings



def validate_pdf(file) -> None:
    if file.size > MAX_BOOK_SIZE:
        raise ValidationError(f"Файл больше {MAX_BOOK_SIZE // (1024 * 1024)} МБ.")
    position = file.tell()
    file.seek(0)
    header = file.read(5)
    file.seek(position)
    if header != b"%PDF-":
        raise ValidationError("Это не PDF-файл.")


class BookStatus(models.TextChoices):
    PENDING = "pending", "в очереди"
    PROCESSING = "processing", "обрабатывается"
    READY = "ready", "загружена"
    FAILED = "failed", "ошибка"


class Book(models.Model):
    """A PDF book of the knowledge base.

    Django only records the request; the RAG worker parses the PDF, computes embeddings and writes the chunks
    to `rag_chunks` (pgvector). The worker works with the tables directly, so their names and the columns it uses
    are a contract with `rag_service/worker.py` and `rag_service/store.py`: it claims PENDING rows and finishes a
    job only if `revision` is unchanged, so a book re-queued while it is being processed is processed again.
    Chunks reference the book with ON DELETE CASCADE: deleting a book removes them.
    """

    title = models.CharField("название", max_length=300)
    slug = models.SlugField(
        "идентификатор источника",
        max_length=120,
        unique=True,
        blank=True,
        help_text="Латиница, цифры, дефисы. Пусто — сгенерируется из названия. После создания не меняется.",
    )
    file = models.FileField(
        "PDF-файл",
        upload_to="books/",
        validators=[FileExtensionValidator(["pdf"]), validate_pdf],
    )
    status = models.CharField("статус", max_length=20, choices=BookStatus.choices, default=BookStatus.PENDING)
    error = models.TextField("ошибка", blank=True)
    revision = models.PositiveIntegerField("ревизия", default=0)
    page_count = models.PositiveIntegerField("страниц", null=True, blank=True)
    chunk_count = models.PositiveIntegerField("фрагментов", null=True, blank=True)
    chunks_by_level = models.JSONField("фрагментов по уровням", null=True, blank=True)
    file_hash = models.CharField("SHA-256 файла", max_length=64, blank=True)
    embedding_model = models.CharField("модель эмбеддингов", max_length=200, blank=True)
    created_at = models.DateTimeField("создана", auto_now_add=True)
    updated_at = models.DateTimeField("изменена", auto_now=True)
    started_at = models.DateTimeField("обработка начата", null=True, blank=True)
    processed_at = models.DateTimeField("обработана", null=True, blank=True)

    class Meta:
        db_table = "rag_books"
        verbose_name = "книга"
        verbose_name_plural = "книги"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "updated_at"], name="rag_books_status_updated")]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def enqueue(self) -> None:
        """Queue (re-)indexing. Saves the whole row."""
        self.status = BookStatus.PENDING
        self.error = ""
        self.revision += 1
        self.save()

    @classmethod
    def enqueue_many(cls, queryset: models.QuerySet) -> int:
        return queryset.update(status=BookStatus.PENDING, error="", revision=F("revision") + 1)

    def _unique_slug(self) -> str:
        stem = self.file.name.rsplit("/", 1)[-1].rsplit(".", 1)[0] if self.file else ""
        base = (slugify(self.title) or slugify(stem) or f"book-{uuid.uuid4().hex[:8]}")[:100]
        slug, suffix = base, 2
        while Book.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug, suffix = f"{base}-{suffix}", suffix + 1
        return slug


def chunk_store_stats() -> dict:
    """pgvector version and the number of stored chunks, read by Django from the shared database."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM rag_chunks")
        count = cursor.fetchone()[0]
        version = None
        if connection.vendor == "postgresql":
            cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            row = cursor.fetchone()
            version = row[0] if row else None
    return {"pgvector": version, "count": count}
