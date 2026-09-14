from jedi_mind_agent.rag.config import RAG_TOP_K
from jedi_mind_agent.rag.chroma import ChromaRagStore
from jedi_mind_agent.rag.embeddings import LocalEmbeddingService
from jedi_mind_agent.rag.schemas import RetrievalResult


class RagRetrievalService:
    def __init__(self) -> None:
        self._embeddings = LocalEmbeddingService()
        self._store = ChromaRagStore()

    def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        source_slug: str | None = None,
    ) -> list[RetrievalResult]:
        [query_embedding] = self._embeddings.embed([query])
        return self._store.query(
            query_embedding=query_embedding,
            top_k=top_k or RAG_TOP_K,
            source_slug=source_slug,
        )
