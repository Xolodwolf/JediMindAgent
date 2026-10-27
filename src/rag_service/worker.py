"""Book worker: indexes books queued in the Django admin into PostgreSQL + pgvector.

Jobs are rows of the Django table `rag_books` (model `knowledge.Book`), so no message broker is needed:
the worker claims a row with `FOR UPDATE SKIP LOCKED`, several workers never take the same job, and a job
survives restarts of both services. Parsing and embedding run outside any transaction; the chunks and the
result are then written in one transaction, only if the row still has the claimed `revision`. A book re-queued
while it was processed is simply processed again; a book deleted meanwhile is skipped.

Runs as a thread of the RAG service (shares the embedding model) or standalone: `python -m rag_service.worker`.
"""

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from rag_service import store
from rag_service.config import (
    DELETE_PDF_AFTER_INDEXING,
    EMBEDDING_MODEL,
    MEDIA_ROOT,
    WORKER_POLL_SECONDS,
    WORKER_STALE_MINUTES,
)
from rag_service.db import get_pool
from rag_service.embeddings import LocalEmbeddingService
from rag_service.ingest import prepare_pdf

logger = logging.getLogger(__name__)

CLAIM_SQL = """
UPDATE rag_books
SET status = 'processing', started_at = now(), updated_at = now()
WHERE id = (
    SELECT id FROM rag_books
    WHERE status = 'pending'
       OR (status = 'processing' AND started_at < now() - make_interval(mins => %(stale)s))
    ORDER BY updated_at
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING id, revision, slug, title, file
"""

# Locks the row for the final write and checks that the job is still current.
LOCK_SQL = "SELECT 1 FROM rag_books WHERE id = %s AND revision = %s AND status = 'processing' FOR UPDATE"


@dataclass(frozen=True)
class Job:
    id: int
    revision: int
    slug: str
    title: str
    file: str


class BookWorker:
    def __init__(self, embeddings: LocalEmbeddingService, pool: ConnectionPool | None = None) -> None:
        self._embeddings = embeddings
        self._pool = pool
        self.running = False

    @property
    def pool(self) -> ConnectionPool:
        return self._pool or get_pool()

    def run_forever(self, stop: threading.Event) -> None:
        self.running = True
        logger.info("Book worker started")
        waiting_for_schema = False
        try:
            while not stop.is_set():
                try:
                    worked = self.process_next()
                    waiting_for_schema = False
                except psycopg.errors.UndefinedTable:
                    # The tables appear when the web container applies Django migrations.
                    if not waiting_for_schema:
                        logger.warning("Table rag_books does not exist yet; waiting for Django migrations")
                    waiting_for_schema = True
                    worked = False
                except Exception:
                    logger.exception("Book worker iteration failed")
                    worked = False
                if not worked:
                    stop.wait(WORKER_POLL_SECONDS)
        finally:
            self.running = False
            logger.info("Book worker stopped")

    def process_next(self) -> bool:
        """Process one job; False when the queue is empty."""
        with self.pool.connection() as conn:
            row = conn.execute(CLAIM_SQL, {"stale": WORKER_STALE_MINUTES}).fetchone()
        if row is None:
            return False
        self._ingest(Job(**row))
        return True

    def _ingest(self, job: Job) -> None:
        logger.info("Indexing book %s (%s), revision %s", job.id, job.slug, job.revision)
        try:
            path = _media_path(job.file)
            book = prepare_pdf(path, embeddings=self._embeddings)
            with self.pool.connection() as conn, conn.transaction():
                if conn.execute(LOCK_SQL, (job.id, job.revision)).fetchone() is None:
                    logger.info("Book %s changed or was deleted during indexing; revision %s dropped", job.id, job.revision)
                    return
                store.replace_book_chunks(
                    conn,
                    book_id=job.id,
                    source_slug=job.slug,
                    source_title=job.title,
                    source_filename=path.name,
                    file_hash=book.file_hash,
                    embedding_model=EMBEDDING_MODEL,
                    chunks=book.chunks,
                    embeddings=book.embeddings,
                )
                conn.execute(
                    """
                    UPDATE rag_books
                    SET status = 'ready', error = '', page_count = %(page_count)s, chunk_count = %(chunk_count)s,
                        chunks_by_level = %(chunks_by_level)s, file_hash = %(file_hash)s,
                        embedding_model = %(embedding_model)s, processed_at = now(), updated_at = now()
                    WHERE id = %(id)s
                    """,
                    {
                        "id": job.id,
                        "page_count": book.page_count,
                        "chunk_count": len(book.chunks),
                        "chunks_by_level": Jsonb({str(level): count for level, count in book.chunks_by_level.items()}),
                        "file_hash": book.file_hash,
                        "embedding_model": EMBEDDING_MODEL,
                    },
                )
        except Exception as exc:
            logger.exception("Book %s indexing failed", job.id)
            self._fail(job, f"{exc.__class__.__name__}: {exc}"[:2000])
            return

        logger.info("Book %s indexed: %s chunks", job.id, len(book.chunks))
        if DELETE_PDF_AFTER_INDEXING:
            path.unlink(missing_ok=True)

    def _fail(self, job: Job, error: str) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "UPDATE rag_books SET status = 'failed', error = %s, processed_at = now(), updated_at = now() "
                "WHERE id = %s AND revision = %s AND status = 'processing'",
                (error, job.id, job.revision),
            )


def _media_path(name: str) -> Path:
    path = (MEDIA_ROOT / name).resolve()
    if not path.is_relative_to(MEDIA_ROOT.resolve()):
        raise ValueError(f"Book file is outside MEDIA_ROOT: {name}")
    return path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        BookWorker(LocalEmbeddingService()).run_forever(threading.Event())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
