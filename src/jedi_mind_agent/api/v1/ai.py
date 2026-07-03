from fastapi import APIRouter

from jedi_mind_agent.ai.schemas import ChatRequest, ChatResponse
from jedi_mind_agent.ai.service import OpenAIChatService
from jedi_mind_agent.core.config import get_settings

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    settings = get_settings()
    service = OpenAIChatService(settings)
    answer, used_fallback = await service.respond(request.message)

    return ChatResponse(answer=answer, model=settings.openai_chat_model, used_fallback=used_fallback)
