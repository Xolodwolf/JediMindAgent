from functools import lru_cache

from jedi_mind_agent.rag.config import EMBEDDING_MODEL


class LocalEmbeddingService:
    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        model = _get_model()
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [vector.tolist() for vector in vectors]


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL)
