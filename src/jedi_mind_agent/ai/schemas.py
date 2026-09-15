from pydantic import BaseModel, Field

from jedi_mind_agent.rag.schemas import RagUsage


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    use_rag: bool = False


class ChatResponse(BaseModel):
    answer: str
    model: str
    used_fallback: bool = False
    rag: RagUsage = Field(default_factory=lambda: RagUsage(used=False))
