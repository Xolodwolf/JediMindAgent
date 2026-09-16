"""Product JSON API for the web interface. The current user always comes from `get_current_user`."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from jedi_mind_agent.ai.agent import JediAgent, get_agent
from jedi_mind_agent.api.deps import CurrentUser, SessionDep
from jedi_mind_agent.api.v1.schemas import (
    ChatMessageIn,
    ChatTurnOut,
    ExerciseOut,
    ExercisePatchIn,
    MessageOut,
    ReadinessCheckOut,
    ReadinessOut,
    StateOut,
    StateResponse,
)
from jedi_mind_agent.product import service
from jedi_mind_agent.rag.retrieval import get_retrieval_service
from jedi_mind_agent.rag.schemas import RetrievalResult

router = APIRouter(prefix="/api/v1", tags=["product"])

Agent = Annotated[JediAgent, Depends(get_agent)]


@router.get("/me/state", response_model=StateResponse)
async def get_state(session: SessionDep, user: CurrentUser) -> StateResponse:
    state = await service.get_state(session, user.id)
    check = await service.last_readiness_check(session, user.id)
    return StateResponse(state=StateOut.from_model(state), last_check=ReadinessCheckOut.from_model(check))


@router.get("/me/messages", response_model=list[MessageOut])
async def list_messages(session: SessionDep, user: CurrentUser) -> list[MessageOut]:
    return [MessageOut.from_model(message) for message in await service.list_user_messages(session, user.id)]


@router.post("/me/readiness", response_model=ReadinessOut)
async def check_readiness(session: SessionDep, user: CurrentUser, agent: Agent) -> ReadinessOut:
    outcome = await service.run_readiness_check(session, user_id=user.id, agent=agent)
    return ReadinessOut(
        message=MessageOut.from_model(outcome.message),
        state=StateOut.from_model(outcome.state),
        check=ReadinessCheckOut.from_model(outcome.check),
    )


@router.post("/me/reset", response_model=StateResponse)
async def reset_memory(session: SessionDep, user: CurrentUser) -> StateResponse:
    state = await service.reset_user(session, user.id)
    return StateResponse(state=StateOut.from_model(state), last_check=None)


@router.post("/chat/messages", response_model=ChatTurnOut)
async def send_message(body: ChatMessageIn, session: SessionDep, user: CurrentUser, agent: Agent) -> ChatTurnOut:
    turn = await service.handle_chat_message(
        session,
        user_id=user.id,
        text=body.message,
        agent=agent,
        retrieve=_retrieve if body.use_rag else None,
    )
    return ChatTurnOut(
        user_message=MessageOut.from_model(turn.user_message),
        assistant_message=MessageOut.from_model(turn.assistant_message),
        state=StateOut.from_model(turn.state),
        exercises_changed=[ExerciseOut.from_model(exercise) for exercise in turn.new_exercises],
    )


@router.get("/exercises", response_model=list[ExerciseOut])
async def list_exercises(session: SessionDep, user: CurrentUser) -> list[ExerciseOut]:
    return [ExerciseOut.from_model(exercise) for exercise in await service.list_exercises(session, user.id)]


@router.patch("/exercises/{exercise_id}", response_model=ExerciseOut)
async def update_exercise(
    exercise_id: uuid.UUID, body: ExercisePatchIn, session: SessionDep, user: CurrentUser
) -> ExerciseOut:
    try:
        exercise = await service.change_exercise_status(
            session, user_id=user.id, exercise_id=exercise_id, target=body.status
        )
    except service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.DomainError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ExerciseOut.from_model(exercise)


def _retrieve(query: str) -> list[RetrievalResult]:
    return get_retrieval_service().retrieve(query)
