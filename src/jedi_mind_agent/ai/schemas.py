from pydantic import BaseModel, Field

from jedi_mind_agent.product.enums import ReadinessResult, UserLevel
from jedi_mind_agent.rag.schemas import RagUsage


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    use_rag: bool = False


class ChatResponse(BaseModel):
    answer: str
    model: str
    used_fallback: bool = False
    rag: RagUsage = Field(default_factory=lambda: RagUsage(used=False))


# Structured outputs of the product agent. Value ranges are deliberately not enforced here:
# an out-of-range number must not discard the whole reply, the domain service drops it instead.


class DiagnosticUpdate(BaseModel):
    level: UserLevel | None = Field(default=None, description="User level, only when the evidence is sufficient.")
    energy_level: int | None = Field(default=None, description="Mental fuel ('мыслетопливо'), 1-10.")
    focus_level: int | None = Field(default=None, description="Ability to focus, 1-10.")
    main_problem: str | None = Field(default=None, description="The user's main problem, one short sentence.")
    time_limit_minutes: int | None = Field(default=None, description="Minutes per day the user can spend on practice.")


class ExerciseProposal(BaseModel):
    title: str = Field(description="Short exercise title.")
    description: str = Field(description="Why it helps, numbered steps, expected result. Adapted to the user.")
    estimated_minutes: int | None = Field(default=None, description="Approximate duration in minutes.")


class AgentReply(BaseModel):
    answer: str = Field(description="Message shown to the user.")
    diagnostic: DiagnosticUpdate | None = Field(default=None, description="New facts about the user's state.")
    exercise: ExerciseProposal | None = Field(default=None, description="One exercise to suggest, if appropriate.")


class ReadinessAssessment(BaseModel):
    result: ReadinessResult
    summary: str = Field(description="2-4 sentences for the user: the result and what to do next.")
