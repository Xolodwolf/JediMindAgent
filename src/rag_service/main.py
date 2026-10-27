"""RAG service: the only process with ML dependencies.

Serves query embeddings + pgvector search for the Django app and runs the book worker in a background thread,
so the API and the worker share one copy of the embedding model. Internal service: not published outside Docker.
"""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from rag_service import store
from rag_service.config import DATABASE_URL, EMBEDDING_MODEL, WORKER_ENABLED
from rag_service.db import get_pool
from rag_service.embeddings import LocalEmbeddingService
from rag_service.schemas import RetrieveRequest, RetrieveResponse
from rag_service.worker import BookWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

embeddings = LocalEmbeddingService()
worker: BookWorker | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global worker
    stop = threading.Event()
    # Load the model in the background: the first query would otherwise wait for it.
    threading.Thread(target=embeddings.load, name="model-preload", daemon=True).start()

    thread = None
    if WORKER_ENABLED and DATABASE_URL:
        worker = BookWorker(embeddings)
        thread = threading.Thread(target=worker.run_forever, args=(stop,), name="book-worker", daemon=True)
        thread.start()
    else:
        logger.warning("Book worker is disabled (RAG_WORKER_ENABLED=false or DATABASE_URL is empty)")
    yield
    stop.set()
    if thread is not None:
        thread.join(timeout=10)


app = FastAPI(title="JediMindAgent RAG service", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    try:
        with get_pool().connection() as conn:
            database = {"ok": True, **store.stats(conn)}
    except Exception as exc:
        database = {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"[:300]}
    return {
        "status": "ok",
        "embedding_model": EMBEDDING_MODEL,
        "worker_running": bool(worker and worker.running),
        "database": database,
    }


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve(request: RetrieveRequest) -> RetrieveResponse:
    try:
        [query_embedding] = embeddings.embed([request.query])
        with get_pool().connection() as conn:
            results = store.query(
                conn,
                query_embedding=query_embedding,
                top_k=request.top_k,
                max_level=request.max_level,
                source_slug=request.source_slug,
            )
    except Exception as exc:
        logger.exception("Retrieval failed")
        raise HTTPException(status_code=503, detail=f"RAG retrieval is unavailable: {exc.__class__.__name__}") from exc
    return RetrieveResponse(query=request.query, results=results)
