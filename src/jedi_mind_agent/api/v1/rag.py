from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from jedi_mind_agent.rag.retrieval import RagRetrievalService
from jedi_mind_agent.rag.schemas import RetrievalResult, RetrieveRequest, RetrieveResponse

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(request: RetrieveRequest) -> RetrieveResponse:
    try:
        results = await run_in_threadpool(
            _retrieve,
            request,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"RAG retrieval is unavailable: {exc.__class__.__name__}") from exc

    return RetrieveResponse(query=request.query, results=results)


def _retrieve(request: RetrieveRequest) -> list[RetrievalResult]:
    return RagRetrievalService().retrieve(
        request.query,
        top_k=request.top_k,
        source_slug=request.source_slug,
        max_level=request.max_level,
    )
