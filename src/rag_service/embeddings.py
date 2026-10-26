import threading
from functools import lru_cache

from rag_service.config import EMBEDDING_BATCH_SIZE, EMBEDDING_MODEL

# One model instance is shared by the API and the worker thread; encode() calls are serialized.
_lock = threading.Lock()


class LocalEmbeddingService:
    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        model = _get_model()
        with _lock:
            vectors = model.encode(
                texts, batch_size=EMBEDDING_BATCH_SIZE, normalize_embeddings=True, show_progress_bar=False
            )
        return [vector.tolist() for vector in vectors]

    @property
    def dimensions(self) -> int:
        return _get_model().get_sentence_embedding_dimension()


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL)
