"""Local embeddings with fastembed (ONNX Runtime): the same model as sentence-transformers, without PyTorch."""

import threading
from functools import lru_cache

import numpy as np

from rag_service.config import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_CACHE_DIR,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_THREADS,
)

# One model instance is shared by the API and the worker thread; embed() calls are serialized to bound memory.
_lock = threading.Lock()


class LocalEmbeddingService:
    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        model = _get_model()
        with _lock:
            vectors = np.asarray(list(model.embed(texts, batch_size=EMBEDDING_BATCH_SIZE)), dtype=np.float32)
        if vectors.shape[1] != EMBEDDING_DIMENSIONS:
            raise ValueError(f"Model returns {vectors.shape[1]}-dimensional vectors, expected {EMBEDDING_DIMENSIONS}.")
        # fastembed returns mean-pooled vectors for this model; search uses cosine distance on unit vectors.
        vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        return vectors.tolist()

    def load(self) -> None:
        _get_model()


@lru_cache(maxsize=1)
def _get_model():
    from fastembed import TextEmbedding

    return TextEmbedding(EMBEDDING_MODEL, cache_dir=EMBEDDING_CACHE_DIR, threads=EMBEDDING_THREADS)
