"""RAG service settings from environment variables."""

import os
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
# Must match the vector(N) column created by the Django migration knowledge.0003_rag_chunks.
EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "384"))
# The Docker image downloads the model here at build time, so a cold start needs no network.
EMBEDDING_CACHE_DIR = os.environ.get("EMBEDDING_CACHE_DIR") or None
EMBEDDING_THREADS = int(os.environ["EMBEDDING_THREADS"]) if os.environ.get("EMBEDDING_THREADS") else None
# Smaller batches keep peak memory low while a book is indexed.
EMBEDDING_BATCH_SIZE = int(os.environ.get("EMBEDDING_BATCH_SIZE", "16"))

# The same PostgreSQL as Django: book jobs in `rag_books`, chunks with vectors in `rag_chunks` (pgvector).
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DB_POOL_MAX_SIZE = int(os.environ.get("RAG_DB_POOL_MAX_SIZE", "4"))
# The volume with books uploaded through the Django admin (Django's MEDIA_ROOT).
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/app/media"))

WORKER_ENABLED = _bool("RAG_WORKER_ENABLED", True)
WORKER_POLL_SECONDS = float(os.environ.get("RAG_WORKER_POLL_SECONDS", "3"))
# A job in "processing" longer than this is considered abandoned by a crashed worker and is taken again.
WORKER_STALE_MINUTES = int(os.environ.get("RAG_WORKER_STALE_MINUTES", "30"))
# For hosts without a persistent disk: the chunks are in PostgreSQL, the PDF is not needed after indexing.
DELETE_PDF_AFTER_INDEXING = _bool("RAG_DELETE_PDF_AFTER_INDEXING", False)

CHUNK_TARGET_CHARS = 1400
CHUNK_OVERLAP_CHARS = 200
