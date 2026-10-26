import uuid

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F
from django.utils.text import slugify

MAX_BOOK_SIZE = 200 * 1024 * 1024


class RagSettings(models.Model):
    """Single row: where the RAG service and ChromaDB are and how many book chunks the agent gets."""

    SINGLETON_ID = 1

    rag_service_url = models.URLField(
        "URL RAG-сервиса", default="http://rag:8001", help_text="Сервис эмбеддингов и поиска (FastAPI)."
    )
    request_timeout_seconds = models.PositiveSmallIntegerField(
        "таймаут запроса к RAG-сервису, с", default=30, validators=[MinValueValidator(1), MaxValueValidator(300)]
    )
    chroma_host = models.CharField("хост ChromaDB", max_length=200, default="chroma")
    chroma_port = models.PositiveIntegerField(
        "порт ChromaDB", default=8000, validators=[MinValueValidator(1), MaxValueValidator(65535)]
    )
    chroma_collection = models.CharField("коллекция ChromaDB", max_length=200, default="jedi_mind_agent_chunks")
    top_k = models.PositiveSmallIntegerField(
        "фрагментов в контексте агента", default=5, validators=[MinValueValidator(1), MaxValueValidator(20)]
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "настройки RAG и ChromaDB"
        verbose_name_plural = "настройки RAG и ChromaDB"

    def __str__(self) -> str:
        return "Настройки RAG и ChromaDB"

    def save(self, *args, **kwargs) -> None:
        self.pk = self.SINGLETON_ID
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "RagSettings":
        settings, _ = cls.objects.get_or_create(pk=cls.SINGLETON_ID)
        return settings

    def chroma_config(self) -> dict:
        return {"host": self.chroma_host, "port": self.chroma_port, "collection": self.chroma_collection}


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
    DELETING = "deleting", "удаляется"


class Book(models.Model):
    """A PDF book of the knowledge base.

    Django only records the request; the RAG worker parses the PDF, computes embeddings and writes ChromaDB.
    The worker works with the table directly, so its name and the columns it uses are a contract with
    `rag_service/worker.py`: it claims rows in PENDING or DELETING status and finishes a job only if `revision`
    is unchanged, so a book re-queued while it is being processed is processed again.
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
    # ChromaDB settings at the time of queueing: where the worker writes this book.
    ingest_config = models.JSONField("куда загружать", default=dict, blank=True)
    # Where the book's chunks currently are; the worker clears them from here on re-indexing and deletion.
    indexed_config = models.JSONField("где лежат фрагменты", null=True, blank=True)
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
        """Queue (re-)indexing with the current ChromaDB settings. Saves the whole row."""
        self.status = BookStatus.PENDING
        self.error = ""
        self.revision += 1
        self.ingest_config = RagSettings.load().chroma_config()
        self.save()

    @classmethod
    def enqueue_many(cls, queryset: models.QuerySet) -> int:
        return queryset.exclude(status=BookStatus.DELETING).update(
            status=BookStatus.PENDING,
            error="",
            revision=F("revision") + 1,
            ingest_config=RagSettings.load().chroma_config(),
        )

    @classmethod
    def request_deletion(cls, queryset: models.QuerySet) -> int:
        """The worker removes the chunks from ChromaDB, then the file and the row."""
        return queryset.update(status=BookStatus.DELETING, revision=F("revision") + 1, started_at=None)

    def _unique_slug(self) -> str:
        stem = self.file.name.rsplit("/", 1)[-1].rsplit(".", 1)[0] if self.file else ""
        base = (slugify(self.title) or slugify(stem) or f"book-{uuid.uuid4().hex[:8]}")[:100]
        slug, suffix = base, 2
        while Book.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug, suffix = f"{base}-{suffix}", suffix + 1
        return slug
