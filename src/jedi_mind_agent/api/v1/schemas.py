"""Response and request models of the product JSON API."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from jedi_mind_agent.product.enums import (
    EXERCISE_TRANSITIONS,
    LEVEL_RANK,
    LEVEL_TITLES,
    ChatRole,
    ExerciseStatus,
    ReadinessResult,
    UserLevel,
)
from jedi_mind_agent.product.models import ChatMessage, ReadinessCheck, UserExercise, UserState


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
            level_rank=LEVEL_RANK[state.level],
            level_title=LEVEL_TITLES[state.level],
            energy_level=state.energy_level,
            focus_level=state.focus_level,
            main_problem=state.main_problem,
            time_limit_minutes=state.time_limit_minutes,
        )


class ReadinessCheckOut(BaseModel):
    result: ReadinessResult
    summary: str
    from_level: UserLevel
    target_level: UserLevel | None
    created_at: datetime

    @classmethod
    def from_model(cls, check: ReadinessCheck | None) -> "ReadinessCheckOut | None":
        if check is None:
            return None
        return cls(
            result=check.result,
            summary=check.summary,
            from_level=check.from_level,
            target_level=check.target_level,
            created_at=check.created_at,
        )


class StateResponse(BaseModel):
    state: StateOut
    last_check: ReadinessCheckOut | None


class SourceOut(BaseModel):
    source_title: str
    page_start: int
    page_end: int


class MessageOut(BaseModel):
    id: uuid.UUID
    role: ChatRole
    content: str
    created_at: datetime
    used_fallback: bool
    sources: list[SourceOut]

    @classmethod
    def from_model(cls, message: ChatMessage) -> "MessageOut":
        meta = message.meta or {}
        return cls(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            used_fallback=bool(meta.get("used_fallback")),
            sources=[SourceOut.model_validate(source) for source in meta.get("sources", [])],
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
            level_rank=LEVEL_RANK[exercise.level],
            status=exercise.status,
            estimated_minutes=exercise.estimated_minutes,
            actions=list(EXERCISE_TRANSITIONS.get(exercise.status, ())),
            updated_at=exercise.updated_at,
        )


class ChatMessageIn(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    use_rag: bool = True


class ChatTurnOut(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    state: StateOut
    exercises_changed: list[ExerciseOut]


class ExercisePatchIn(BaseModel):
    status: ExerciseStatus


class ReadinessOut(BaseModel):
    message: MessageOut
    state: StateOut
    check: ReadinessCheckOut | None
