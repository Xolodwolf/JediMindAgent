"""Client of the RAG service. The web container has no ML dependencies: embeddings and ChromaDB queries run there."""

import httpx
from pydantic import BaseModel

from jedi_mind_agent.knowledge.models import RagSettings


class RagServiceError(Exception):
    pass


class RetrievalResult(BaseModel):
    chunk_id: str
    text: str
    score: float | None = None
    source_slug: str
    source_title: str
    source_filename: str
    page_start: int
    page_end: int
    level: int = 0


def retrieve(query: str, *, max_level: int, settings: RagSettings | None = None) -> list[RetrievalResult]:
    """Book chunks with level <= max_level, most relevant first."""
    settings = settings or RagSettings.load()
    data = _post(
        settings,
        "/retrieve",
        {"query": query, "top_k": settings.top_k, "max_level": max_level, "chroma": settings.chroma_config()},
    )
    return [RetrievalResult.model_validate(item) for item in data["results"]]


def check_health(settings: RagSettings) -> dict:
    """State of the RAG service, its worker and the configured ChromaDB collection."""
    return _post(settings, "/health/chroma", {"chroma": settings.chroma_config()})


def format_rag_context(results: list[RetrievalResult]) -> str:
    blocks = []
    for index, result in enumerate(results, start=1):
        source = f"{result.source_title or result.source_filename}, стр. {result.page_start}–{result.page_end}"
        blocks.append(f"[{index}] Источник: {source}\n{result.text}")
    return "\n\n".join(blocks)


def _post(settings: RagSettings, path: str, payload: dict) -> dict:
    url = settings.rag_service_url.rstrip("/") + path
    try:
        response = httpx.post(url, json=payload, timeout=settings.request_timeout_seconds)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300]
        raise RagServiceError(f"RAG-сервис ответил {exc.response.status_code}: {detail}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise RagServiceError(f"RAG-сервис недоступен ({url}): {exc.__class__.__name__}") from exc
