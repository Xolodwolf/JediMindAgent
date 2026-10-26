"""RAG service settings from environment variables. ChromaDB coordinates come with each request or job from Django."""

import os
from pathlib import Path

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# The same PostgreSQL as Django: the worker takes book jobs from the `rag_books` table.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
# The volume with books uploaded through the Django admin (Django's MEDIA_ROOT).
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/app/media"))

WORKER_ENABLED = os.environ.get("RAG_WORKER_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
WORKER_POLL_SECONDS = float(os.environ.get("RAG_WORKER_POLL_SECONDS", "3"))
# A job in "processing" longer than this is considered abandoned by a crashed worker and is taken again.
WORKER_STALE_MINUTES = int(os.environ.get("RAG_WORKER_STALE_MINUTES", "30"))

EMBEDDING_BATCH_SIZE = 64
CHUNK_TARGET_CHARS = 1400
CHUNK_OVERLAP_CHARS = 200
