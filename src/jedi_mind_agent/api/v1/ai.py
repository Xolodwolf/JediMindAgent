from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from jedi_mind_agent.ai.schemas import ChatRequest, ChatResponse
from jedi_mind_agent.ai.service import OpenAIChatService
from jedi_mind_agent.core.config import get_settings
from jedi_mind_agent.rag.retrieval import RagRetrievalService
from jedi_mind_agent.rag.schemas import RagSource, RagUsage, RetrievalResult

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    settings = get_settings()
    service = OpenAIChatService(settings)
    rag_results: list[RetrievalResult] = []

    if request.use_rag:
        try:
            rag_results = await run_in_threadpool(_retrieve_for_chat, request.message)
        except Exception:
            rag_results = []

    answer, used_fallback = await service.respond(
        request.message,
        rag_context=_format_rag_context(rag_results) if rag_results else None,
    )

    return ChatResponse(
        answer=answer,
        model=settings.openai_chat_model,
        used_fallback=used_fallback,
        rag=RagUsage(used=bool(rag_results), sources=[_to_source(result) for result in rag_results]),
    )


def _format_rag_context(results: list[RetrievalResult]) -> str:
    blocks = []
    for index, result in enumerate(results, start=1):
        source = f"{result.source_title or result.source_filename}, pages {result.page_start}-{result.page_end}"
        blocks.append(f"[{index}] Source: {source}\n{result.text}")
    return "\n\n".join(blocks)


def _retrieve_for_chat(message: str) -> list[RetrievalResult]:
    return RagRetrievalService().retrieve(message)


def _to_source(result: RetrievalResult) -> RagSource:
    return RagSource(
        chunk_id=result.chunk_id,
        source_slug=result.source_slug,
        source_title=result.source_title,
        source_filename=result.source_filename,
        page_start=result.page_start,
        page_end=result.page_end,
        score=result.score,
    )
