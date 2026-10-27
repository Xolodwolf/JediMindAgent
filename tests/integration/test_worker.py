"""The RAG worker and the pgvector store against the Django tables on PostgreSQL; only the model and PDF parsing are fakes.

Needs both the web and the RAG dependencies and a PostgreSQL DATABASE_URL with the pgvector extension available:
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
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    from rag_service import store
    from rag_service import worker as worker_module
    from rag_service.schemas import PageText
except ImportError:  # the web image has no RAG dependencies
    worker_module = None

from jedi_mind_agent.knowledge.models import Book, BookStatus, chunk_store_stats

PAGES = [
    PageText(page_number=1, text="Введение. " * 200),
    PageText(page_number=2, text="6.1. Первый уровень. Все горит\n" + "Практика. " * 200),
    PageText(page_number=3, text="6.2. Второй уровень. Ночь простоять\n" + "Список задач. " * 150),
]


def unit(index: int) -> list[float]:
    vector = [0.0] * 384
    vector[index] = 1.0
    return vector


class FakeEmbeddings:
    """Every text gets the same unit vector; the query vector decides the distance."""

    on_embed = None

    def embed(self, texts):
        if self.on_embed:
            self.on_embed()
        return [unit(0) for _ in texts]


@unittest.skipIf(worker_module is None, "RAG dependencies are not installed")
@unittest.skipUnless(connection.vendor == "postgresql", "pgvector needs PostgreSQL")
class BookWorkerTest(TransactionTestCase):
    # With available_apps the flush between tests uses TRUNCATE ... CASCADE, which also empties rag_chunks.
    available_apps = ["jedi_mind_agent.knowledge"]

    def setUp(self) -> None:
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.media = Path(media.name)
        override = self.settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)

        for target, value in (("MEDIA_ROOT", self.media), ("DELETE_PDF_AFTER_INDEXING", False)):
            patcher = mock.patch.object(worker_module, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        pages = mock.patch("rag_service.ingest.extract_pdf_pages", return_value=PAGES)
        pages.start()
        self.addCleanup(pages.stop)

        db = connection.settings_dict
        dsn = f"postgresql://{db['USER']}:{db['PASSWORD']}@{db['HOST']}:{db['PORT'] or 5432}/{db['NAME']}"
        self.pool = ConnectionPool(dsn, min_size=1, max_size=2, kwargs={"autocommit": True, "row_factory": dict_row})
        self.addCleanup(self.pool.close)

        self.embeddings = FakeEmbeddings()
        self.worker = worker_module.BookWorker(self.embeddings, pool=self.pool)

    def queue_book(self, slug: str = "jedi-path") -> Book:
        book = Book(title="Путь джедая", slug=slug)
        book.file.save(f"{slug}.pdf", ContentFile(b"%PDF-1.4 fake"), save=False)
        book.enqueue()
        return book

    def search(self, **kwargs):
        with self.pool.connection() as conn:
            return store.query(conn, query_embedding=unit(0), top_k=50, **kwargs)

    def test_empty_queue(self):
        self.assertFalse(self.worker.process_next())

    def test_ingest_writes_chunks_with_levels(self):
        book = self.queue_book()
        self.assertTrue(self.worker.process_next())

        book.refresh_from_db()
        self.assertEqual(book.status, BookStatus.READY)
        self.assertEqual(book.page_count, 3)
        self.assertEqual(set(book.chunks_by_level), {"0", "1", "2"})
        self.assertEqual(chunk_store_stats()["count"], book.chunk_count)
        self.assertFalse(self.worker.process_next())

    def test_search_respects_the_level_ceiling(self):
        self.queue_book()
        self.worker.process_next()

        self.assertEqual({r.level for r in self.search()}, {0, 1, 2})
        self.assertEqual({r.level for r in self.search(max_level=1)}, {0, 1})
        results = self.search(max_level=0)
        self.assertTrue(results)
        self.assertAlmostEqual(results[0].score, 0.0, places=5)  # identical unit vectors
        self.assertEqual(results[0].source_title, "Путь джедая")

    def test_reindex_replaces_chunks(self):
        book = self.queue_book()
        self.worker.process_next()
        before = chunk_store_stats()["count"]

        Book.enqueue_many(Book.objects.filter(pk=book.pk))
        self.worker.process_next()

        self.assertEqual(chunk_store_stats()["count"], before)

    def test_book_requeued_during_processing_is_processed_again(self):
        book = self.queue_book()
        self.embeddings.on_embed = lambda: Book.enqueue_many(Book.objects.filter(pk=book.pk))
        self.worker.process_next()

        book.refresh_from_db()
        self.assertEqual((book.status, book.revision), (BookStatus.PENDING, 2))
        self.assertEqual(chunk_store_stats()["count"], 0)  # nothing of the stale revision was written

        self.embeddings.on_embed = None
        self.worker.process_next()
        book.refresh_from_db()
        self.assertEqual((book.status, book.revision), (BookStatus.READY, 2))

    def test_book_deleted_during_processing_is_skipped(self):
        book = self.queue_book()
        self.embeddings.on_embed = lambda: Book.objects.filter(pk=book.pk).delete()
        self.worker.process_next()

        self.assertFalse(Book.objects.exists())
        self.assertEqual(chunk_store_stats()["count"], 0)

    def test_deleting_a_book_removes_its_chunks(self):
        book = self.queue_book()
        self.worker.process_next()
        other = self.queue_book(slug="other-book")
        self.worker.process_next()

        book.delete()

        self.assertEqual({r.source_slug for r in self.search()}, {"other-book"})
        other.refresh_from_db()
        self.assertEqual(chunk_store_stats()["count"], other.chunk_count)

    def test_missing_file_fails_the_job(self):
        book = self.queue_book()
        (self.media / book.file.name).unlink()
        self.worker.process_next()

        book.refresh_from_db()
        self.assertEqual(book.status, BookStatus.FAILED)
        self.assertIn("Загрузите файл заново", book.error)

    def test_pdf_can_be_removed_after_indexing(self):
        book = self.queue_book()
        with mock.patch.object(worker_module, "DELETE_PDF_AFTER_INDEXING", True):
            self.worker.process_next()

        book.refresh_from_db()
        self.assertEqual(book.status, BookStatus.READY)
        self.assertFalse((self.media / book.file.name).exists())
