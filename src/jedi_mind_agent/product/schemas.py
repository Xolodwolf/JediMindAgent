"""Response and request models of the product JSON API. Validated with pydantic, rendered by Django views."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from jedi_mind_agent.product.enums import EXERCISE_TRANSITIONS, LEVEL_RANK, LEVEL_TITLES, ChatRole, ExerciseStatus, UserLevel
from jedi_mind_agent.product.models import ChatMessage, UserExercise, UserState


class StateOut(BaseModel):
    level: UserLevel
    level_rank: int
    level_title: str
    energy_level: int | None
    focus_level: int | None
    main_problem: str | None
    time_limit_minutes: int | None

    @classmethod
    def from_model(cls, state: UserState) -> "StateOut":
        return cls(
            level=state.level,
            level_rank=LEVEL_RANK[UserLevel(state.level)],
            level_title=LEVEL_TITLES[UserLevel(state.level)],
            energy_level=state.energy_level,
            focus_level=state.focus_level,
            main_problem=state.main_problem,
            time_limit_minutes=state.time_limit_minutes,
        )


class StateResponse(BaseModel):
    state: StateOut


class SourceOut(BaseModel):
    source_title: str
    page_start: int
    page_end: int


class TestPromptOut(BaseModel):
    """A level test question: the UI renders its choices as buttons under the latest message."""

    test_id: uuid.UUID
    step: int
    total: int
    kind: Literal["choice", "scale"]
    choices: list[str]


class MessageOut(BaseModel):
    id: uuid.UUID
    role: ChatRole
    content: str
    created_at: datetime
    used_fallback: bool
    sources: list[SourceOut]
    test: TestPromptOut | None

    @classmethod
    def from_model(cls, message: ChatMessage) -> "MessageOut":
        meta = message.meta or {}
        test = meta.get("test")
        return cls(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            used_fallback=bool(meta.get("used_fallback")),
            sources=[SourceOut.model_validate(source) for source in meta.get("sources", [])],
            # Only questions carry choices; answers are marked as test messages without them.
            test=TestPromptOut.model_validate(test) if test and "choices" in test else None,
        )


class ExerciseOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    level: UserLevel
    level_rank: int
    status: ExerciseStatus
    estimated_minutes: int | None
    # Statuses the exercise may move to. The server is the authority; the UI only renders these.
    actions: list[ExerciseStatus]
    updated_at: datetime

    @classmethod
    def from_model(cls, exercise: UserExercise) -> "ExerciseOut":
        return cls(
            id=exercise.id,
            title=exercise.title,
            description=exercise.description,
            level=exercise.level,
            level_rank=LEVEL_RANK[UserLevel(exercise.level)],
            status=exercise.status,
            estimated_minutes=exercise.estimated_minutes,
            actions=list(EXERCISE_TRANSITIONS.get(ExerciseStatus(exercise.status), ())),
            updated_at=exercise.updated_at,
        )


class ChatMessageIn(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    use_rag: bool = True


class LevelTestStartIn(BaseModel):
    # False resumes an unfinished test instead of starting over.
    restart: bool = False


class ChatTurnOut(BaseModel):
    # New messages in chronological order: the user's message (if any) and the replies.
    messages: list[MessageOut]
    state: StateOut
    exercises_changed: list[ExerciseOut]


class ExercisePatchIn(BaseModel):
    status: ExerciseStatus
