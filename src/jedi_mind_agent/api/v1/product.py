"""Product JSON API for the web interface. The current user always comes from `get_current_user`."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from jedi_mind_agent.ai.agent import JediAgent, get_agent
from jedi_mind_agent.api.deps import CurrentUser, SessionDep
from jedi_mind_agent.api.v1.schemas import (
    ChatMessageIn,
    ChatTurnOut,
    ExerciseOut,
    ExercisePatchIn,
    LevelTestStartIn,
    MessageOut,
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
    return StateResponse(state=StateOut.from_model(await service.get_state(session, user.id)))


@router.get("/me/messages", response_model=list[MessageOut])
async def list_messages(session: SessionDep, user: CurrentUser) -> list[MessageOut]:
    return [MessageOut.from_model(message) for message in await service.list_user_messages(session, user.id)]


@router.post("/me/level-test", response_model=ChatTurnOut)
async def start_level_test(body: LevelTestStartIn, session: SessionDep, user: CurrentUser) -> ChatTurnOut:
    return _turn_out(await service.start_level_test(session, user_id=user.id, restart=body.restart))


@router.post("/me/reset", response_model=StateResponse)
async def reset_memory(session: SessionDep, user: CurrentUser) -> StateResponse:
    return StateResponse(state=StateOut.from_model(await service.reset_user(session, user.id)))


@router.post("/chat/messages", response_model=ChatTurnOut)
async def send_message(body: ChatMessageIn, session: SessionDep, user: CurrentUser, agent: Agent) -> ChatTurnOut:
    turn = await service.handle_chat_message(
        session,
        user_id=user.id,
        text=body.message,
        agent=agent,
        retrieve=_retrieve if body.use_rag else None,
    )
    return _turn_out(turn)


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


@router.delete("/exercises/{exercise_id}", status_code=204)
async def delete_exercise(exercise_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Response:
    try:
        await service.delete_exercise(session, user_id=user.id, exercise_id=exercise_id)
    except service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


def _turn_out(turn: service.ChatTurn) -> ChatTurnOut:
    return ChatTurnOut(
        messages=[MessageOut.from_model(message) for message in turn.messages],
        state=StateOut.from_model(turn.state),
        exercises_changed=[ExerciseOut.from_model(exercise) for exercise in turn.new_exercises],
    )


def _retrieve(query: str) -> list[RetrievalResult]:
    return get_retrieval_service().retrieve(query)
