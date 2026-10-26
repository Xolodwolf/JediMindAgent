"""Book worker: loads books queued in the Django admin into ChromaDB.

Jobs are rows of the Django table `rag_books` (model `knowledge.Book`), so no message broker is needed:
the worker claims a row with `FOR UPDATE SKIP LOCKED`, several workers never take the same job, and a job
survives restarts of both services. A job is finished only if the row's `revision` is still the claimed one:
a book re-queued or deleted while it was processed is simply processed again.

Runs as a thread of the RAG service (shares the embedding model) or standalone: `python -m rag_service.worker`.
"""

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from rag_service.chroma import ChromaRagStore
from rag_service.config import DATABASE_URL, MEDIA_ROOT, WORKER_POLL_SECONDS, WORKER_STALE_MINUTES
from rag_service.embeddings import LocalEmbeddingService
from rag_service.ingest import ingest_pdf
from rag_service.schemas import ChromaConfig

logger = logging.getLogger(__name__)

# Statuses of knowledge.BookStatus.
PENDING, PROCESSING, READY, FAILED, DELETING = "pending", "processing", "ready", "failed", "deleting"

CLAIM_SQL = """
UPDATE rag_books
SET status = CASE WHEN status = 'deleting' THEN 'deleting' ELSE 'processing' END,
    started_at = now(),
    updated_at = now()
WHERE id = (
    SELECT id FROM rag_books
    WHERE status = 'pending'
       OR (status IN ('processing', 'deleting')
           AND (started_at IS NULL OR started_at < now() - make_interval(mins => %(stale)s)))
    ORDER BY updated_at
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING id, status, revision, slug, title, file, ingest_config, indexed_config
"""


@dataclass(frozen=True)
class Job:
    id: int
    status: str
    revision: int
    slug: str
    title: str
    file: str
    ingest_config: dict[str, Any] | None
    indexed_config: dict[str, Any] | None


class BookWorker:
    def __init__(self, embeddings: LocalEmbeddingService, database_url: str = DATABASE_URL) -> None:
        if not database_url:
            raise RuntimeError("DATABASE_URL is not set: the worker takes its jobs from PostgreSQL.")
        # Django-style URLs may carry a driver suffix (postgresql+psycopg://); libpq wants the bare scheme.
        scheme, rest = database_url.split("://", 1)
        self._dsn = f"{scheme.split('+')[0]}://{rest}"
        self._embeddings = embeddings
        self.running = False

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
                    # The table appears when the web container applies Django migrations.
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
        with psycopg.connect(self._dsn, autocommit=True, row_factory=dict_row) as conn:
            row = conn.execute(CLAIM_SQL, {"stale": WORKER_STALE_MINUTES}).fetchone()
            if row is None:
                return False
            job = Job(**row)
            if job.status == DELETING:
                self._delete(conn, job)
            else:
                self._ingest(conn, job)
            return True

    def _ingest(self, conn: psycopg.Connection, job: Job) -> None:
        logger.info("Ingesting book %s (%s), revision %s", job.id, job.slug, job.revision)
        try:
            target = ChromaConfig.model_validate(job.ingest_config or {})
            store = ChromaRagStore(target)
            previous = _config(job.indexed_config)
            if previous is not None and previous != target:
                # ChromaDB settings changed since the last indexing: the old copy must not stay searchable.
                ChromaRagStore(previous).delete_source(job.slug)
            summary = ingest_pdf(
                _media_path(job.file),
                source_slug=job.slug,
                source_title=job.title,
                store=store,
                embeddings=self._embeddings,
            )
        except Exception as exc:
            logger.exception("Book %s ingestion failed", job.id)
            self._finish(conn, job, status=FAILED, error=f"{exc.__class__.__name__}: {exc}"[:2000])
            return

        self._finish(
            conn,
            job,
            status=READY,
            error="",
            page_count=summary.page_count,
            chunk_count=summary.chunk_count,
            chunks_by_level=Jsonb({str(level): count for level, count in summary.chunks_by_level.items()}),
            file_hash=summary.file_hash,
            embedding_model=summary.embedding_model,
            indexed_config=Jsonb(target.model_dump()),
        )
        logger.info("Book %s ingested: %s chunks in %s", job.id, summary.chunk_count, summary.collection)

    def _delete(self, conn: psycopg.Connection, job: Job) -> None:
        logger.info("Deleting book %s (%s)", job.id, job.slug)
        try:
            # Chunks may be in the collection of the last successful indexing and in the one of an unfinished job.
            for config in {c for c in (_config(job.indexed_config), _config(job.ingest_config)) if c is not None}:
                ChromaRagStore(config).delete_source(job.slug)
        except Exception as exc:
            # The row stays in "deleting" and is retried once the claim goes stale.
            logger.exception("Book %s deletion failed", job.id)
            conn.execute(
                "UPDATE rag_books SET error = %s WHERE id = %s AND revision = %s",
                (f"Не удалось удалить из ChromaDB: {exc.__class__.__name__}: {exc}"[:2000], job.id, job.revision),
            )
            return

        deleted = conn.execute("DELETE FROM rag_books WHERE id = %s AND revision = %s", (job.id, job.revision)).rowcount
        if deleted and job.file:
            try:
                _media_path(job.file).unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove file of deleted book %s: %s", job.id, job.file, exc_info=True)
        logger.info("Book %s deleted", job.id)

    @staticmethod
    def _finish(conn: psycopg.Connection, job: Job, **fields: Any) -> None:
        assignments = ", ".join(f"{name} = %({name})s" for name in fields)
        updated = conn.execute(
            f"UPDATE rag_books SET {assignments}, processed_at = now(), updated_at = now() "
            "WHERE id = %(id)s AND revision = %(revision)s AND status = 'processing'",
            {**fields, "id": job.id, "revision": job.revision},
        ).rowcount
        if not updated:
            logger.info("Book %s changed while it was processed; the result of revision %s is dropped", job.id, job.revision)


def _config(value: dict[str, Any] | None) -> ChromaConfig | None:
    return ChromaConfig.model_validate(value) if value else None


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
