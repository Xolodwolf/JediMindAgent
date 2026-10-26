"""The RAG worker against the Django `rag_books` table on PostgreSQL, with ChromaDB and the model replaced by fakes.

Needs both the web and the RAG dependencies (chromadb-client, pypdf) and a PostgreSQL DATABASE_URL:
    DATABASE_URL=postgresql://... python manage.py test tests.integration
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from django.core.files.base import ContentFile
from django.db import connection
from django.test import TransactionTestCase

try:
    from rag_service import worker as worker_module
    from rag_service.schemas import PageText
except ImportError:  # the web image has no RAG dependencies
    worker_module = None

from jedi_mind_agent.knowledge.models import Book, BookStatus, RagSettings

PAGES = [
    PageText(page_number=1, text="Введение. " * 200),
    PageText(page_number=2, text="6.1. Первый уровень. Все горит\n" + "Практика. " * 200),
]


class FakeStore:
    """In-memory ChromaDB: {collection: {slug: chunk count}}."""

    data: dict[str, dict[str, int]] = {}

    def __init__(self, config) -> None:
        self.collection_name = config.collection
        self._chunks = FakeStore.data.setdefault(config.collection, {})

    def delete_source(self, slug: str) -> None:
        self._chunks.pop(slug, None)

    def upsert_chunks(self, *, chunks, source_slug, **_) -> None:
        self._chunks[source_slug] = len(chunks)


class FakeEmbeddings:
    on_embed = None

    def embed(self, texts):
        if self.on_embed:
            self.on_embed()
        return [[0.1, 0.2, 0.3] for _ in texts]


@unittest.skipIf(worker_module is None, "RAG dependencies are not installed")
@unittest.skipUnless(connection.vendor == "postgresql", "the worker uses PostgreSQL-only SQL")
class BookWorkerTest(TransactionTestCase):
    def setUp(self) -> None:
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.media = Path(media.name)
        override = self.settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)

        FakeStore.data = {}
        self.embeddings = FakeEmbeddings()
        for target, value in (
            ("ChromaRagStore", FakeStore),
            ("MEDIA_ROOT", self.media),
            ("WORKER_STALE_MINUTES", 30),
        ):
            patcher = mock.patch.object(worker_module, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        pages = mock.patch("rag_service.ingest.extract_pdf_pages", return_value=PAGES)
        pages.start()
        self.addCleanup(pages.stop)

        db = connection.settings_dict
        dsn = f"postgresql://{db['USER']}:{db['PASSWORD']}@{db['HOST']}:{db['PORT'] or 5432}/{db['NAME']}"
        self.worker = worker_module.BookWorker(self.embeddings, database_url=dsn)

    def queue_book(self, title: str = "Путь джедая") -> Book:
        book = Book(title=title, slug="jedi-path")
        book.file.save("jedi-path.pdf", ContentFile(b"%PDF-1.4 fake"), save=False)
        book.enqueue()
        return book

    def test_empty_queue(self):
        self.assertFalse(self.worker.process_next())

    def test_ingest(self):
        book = self.queue_book()
        self.assertTrue(self.worker.process_next())

        book.refresh_from_db()
        self.assertEqual(book.status, BookStatus.READY)
        self.assertEqual(book.page_count, 2)
        self.assertEqual(set(book.chunks_by_level), {"0", "1"})  # the introduction and the first level
        self.assertEqual(sum(book.chunks_by_level.values()), book.chunk_count)
        self.assertEqual(book.indexed_config, book.ingest_config)
        self.assertEqual(FakeStore.data["jedi_mind_agent_chunks"], {"jedi-path": book.chunk_count})
        self.assertFalse(self.worker.process_next())

    def test_reindex_after_chroma_settings_change_moves_the_chunks(self):
        book = self.queue_book()
        self.worker.process_next()

        settings = RagSettings.load()
        settings.chroma_collection = "books_v2"
        settings.save()
        Book.enqueue_many(Book.objects.filter(pk=book.pk))
        self.worker.process_next()

        self.assertEqual(FakeStore.data["jedi_mind_agent_chunks"], {})
        self.assertIn("jedi-path", FakeStore.data["books_v2"])

    def test_book_requeued_during_processing_is_processed_again(self):
        book = self.queue_book()
        self.embeddings.on_embed = lambda: Book.enqueue_many(Book.objects.filter(pk=book.pk))
        self.worker.process_next()

        book.refresh_from_db()
        self.assertEqual((book.status, book.revision), (BookStatus.PENDING, 2))

        self.embeddings.on_embed = None
        self.worker.process_next()
        book.refresh_from_db()
        self.assertEqual((book.status, book.revision), (BookStatus.READY, 2))

    def test_missing_file_fails_the_job(self):
        book = self.queue_book()
        (self.media / book.file.name).unlink()
        self.worker.process_next()

        book.refresh_from_db()
        self.assertEqual(book.status, BookStatus.FAILED)
        self.assertIn("FileNotFoundError", book.error)

    def test_deletion_removes_chunks_file_and_row(self):
        book = self.queue_book()
        self.worker.process_next()
        path = self.media / book.file.name

        Book.request_deletion(Book.objects.filter(pk=book.pk))
        self.assertTrue(self.worker.process_next())

        self.assertFalse(Book.objects.filter(pk=book.pk).exists())
        self.assertEqual(FakeStore.data["jedi_mind_agent_chunks"], {})
        self.assertFalse(path.exists())
