"""Server-rendered test UI: Jinja2 templates and plain HTML forms, no JavaScript.

Every action is a POST form followed by a 303 redirect back to the page (Post/Redirect/Get),
so refreshing the page never resubmits a message.
"""

import uuid
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from jedi_mind_agent.ai.agent import JediAgent, get_agent
from jedi_mind_agent.db.session import get_session
from jedi_mind_agent.product import service
from jedi_mind_agent.product.enums import (
    ACTIVE_EXERCISE_STATUSES,
    EXERCISE_TRANSITIONS,
    LEVEL_RANK,
    ExerciseStatus,
    ReadinessResult,
    UserLevel,
)
from jedi_mind_agent.rag.retrieval import get_retrieval_service
from jedi_mind_agent.rag.schemas import RetrievalResult

WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"

templates = Jinja2Templates(directory=WEB_DIR / "templates")
router = APIRouter(include_in_schema=False)

Session = Annotated[AsyncSession, Depends(get_session)]
Agent = Annotated[JediAgent, Depends(get_agent)]

USERNAME_MAX = 50
MESSAGE_MAX = 4000

LEVEL_LABELS = {
    UserLevel.UNKNOWN: "не определён",
    UserLevel.LEVEL_1: "1 · Все горит",
    UserLevel.LEVEL_2: "2 · Ночь простоять да день продержаться",
    UserLevel.LEVEL_3: "3 · Есть свет в конце тоннеля",
    UserLevel.LEVEL_4: "4 · Планомерно к намеченным целям",
    UserLevel.LEVEL_5: "5 · Естественно, спонтанно и все во благо",
}
STATUS_LABELS = {
    ExerciseStatus.SUGGESTED: "предложено",
    ExerciseStatus.ACCEPTED: "принято",
    ExerciseStatus.IN_PROGRESS: "выполняю",
    ExerciseStatus.COMPLETED: "выполнено",
    ExerciseStatus.SKIPPED: "пропущено",
    ExerciseStatus.NOT_SUITABLE: "не подошло",
    ExerciseStatus.CANCELLED: "отменено",
}
ACTION_LABELS = {
    ExerciseStatus.ACCEPTED: "Принять",
    ExerciseStatus.IN_PROGRESS: "Начать",
    ExerciseStatus.COMPLETED: "Выполнено",
    ExerciseStatus.SKIPPED: "Пропустить",
    ExerciseStatus.NOT_SUITABLE: "Не подошло",
    ExerciseStatus.CANCELLED: "Отменить",
}
READINESS_LABELS = {
    ReadinessResult.READY: "готов",
    ReadinessResult.PARTIALLY_READY: "частично готов",
    ReadinessResult.NOT_READY: "пока не готов",
}


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    session: Session,
    user_id: uuid.UUID | None = None,
    error: str | None = None,
    rag: bool = True,
) -> HTMLResponse:
    context: dict = {
        "users": await service.list_users(session),
        "user": None,
        "error": error,
        "rag": rag,
        "level_labels": LEVEL_LABELS,
        "level_rank": LEVEL_RANK,
        "status_labels": STATUS_LABELS,
        "readiness_labels": READINESS_LABELS,
        "actions": {status: [(t, ACTION_LABELS[t]) for t in targets] for status, targets in EXERCISE_TRANSITIONS.items()},
    }

    user = await service.get_user(session, user_id) if user_id else None
    if user_id and user is None:
        context["error"] = "Пользователь не найден."

    if user is not None:
        exercises = await service.list_exercises(session, user.id)
        chat = await service.find_chat_session(session, user.id)
        context.update(
            user=user,
            state=await service.get_state(session, user.id),
            messages=await service.list_messages(session, chat.id) if chat else [],
            active_exercises=[e for e in exercises if e.status in ACTIVE_EXERCISE_STATUSES],
            closed_exercises=[e for e in exercises if e.status not in ACTIVE_EXERCISE_STATUSES],
            last_check=await service.last_readiness_check(session, user.id),
        )

    return templates.TemplateResponse(request, "index.html", context)


@router.post("/users")
async def create_user(session: Session, username: Annotated[str, Form()] = "") -> RedirectResponse:
    username = username.strip()
    if not username or len(username) > USERNAME_MAX:
        return _redirect(error=f"Имя пользователя: от 1 до {USERNAME_MAX} символов.")

    user = await service.get_or_create_user(session, username)
    return _redirect(user.id)


@router.post("/users/{user_id}/chat")
async def send_message(
    user_id: uuid.UUID,
    session: Session,
    agent: Agent,
    message: Annotated[str, Form()] = "",
    use_rag: Annotated[bool, Form()] = False,
) -> RedirectResponse:
    text = message.strip()
    if not text or len(text) > MESSAGE_MAX:
        return _redirect(user_id, error=f"Сообщение: от 1 до {MESSAGE_MAX} символов.", rag=use_rag)
    if await service.get_user(session, user_id) is None:
        return _redirect(error="Пользователь не найден.")

    await service.handle_chat_message(
        session, user_id=user_id, text=text, agent=agent, retrieve=_retrieve if use_rag else None
    )
    return _redirect(user_id, rag=use_rag)


@router.post("/users/{user_id}/exercises/{exercise_id}/status")
async def update_exercise_status(
    user_id: uuid.UUID,
    exercise_id: uuid.UUID,
    session: Session,
    status: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        target = ExerciseStatus(status)
        await service.change_exercise_status(session, user_id=user_id, exercise_id=exercise_id, target=target)
    except ValueError:
        return _redirect(user_id, error="Неизвестный статус упражнения.")
    except service.DomainError as exc:
        return _redirect(user_id, error=str(exc))
    return _redirect(user_id)


@router.post("/users/{user_id}/readiness")
async def check_readiness(user_id: uuid.UUID, session: Session, agent: Agent) -> RedirectResponse:
    if await service.get_user(session, user_id) is None:
        return _redirect(error="Пользователь не найден.")

    await service.run_readiness_check(session, user_id=user_id, agent=agent)
    return _redirect(user_id)


def _retrieve(query: str) -> list[RetrievalResult]:
    return get_retrieval_service().retrieve(query)


def _redirect(user_id: uuid.UUID | None = None, *, error: str | None = None, rag: bool = True) -> RedirectResponse:
    params: dict[str, str] = {}
    if user_id:
        params["user_id"] = str(user_id)
    if error:
        params["error"] = error
    if not rag:
        params["rag"] = "0"
    query = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"/{query}#last", status_code=303)
