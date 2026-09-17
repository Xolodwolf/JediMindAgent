from functools import lru_cache

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
        max_level: int | None = None,
    ) -> list[RetrievalResult]:
        [query_embedding] = self._embeddings.embed([query])
        return self._store.query(
            query_embedding=query_embedding,
            top_k=top_k or RAG_TOP_K,
            source_slug=source_slug,
            max_level=max_level,
        )


@lru_cache(maxsize=1)
def get_retrieval_service() -> RagRetrievalService:
    return RagRetrievalService()


def format_rag_context(results: list[RetrievalResult]) -> str:
    blocks = []
    for index, result in enumerate(results, start=1):
        source = f"{result.source_title or result.source_filename}, стр. {result.page_start}–{result.page_end}"
        blocks.append(f"[{index}] Источник: {source}\n{result.text}")
    return "\n\n".join(blocks)
