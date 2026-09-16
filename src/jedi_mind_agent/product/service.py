"""Domain commands. The only place that changes product state; agent output is applied here after validation."""

import logging
import uuid
from collections.abc import Callable, Sequence

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from jedi_mind_agent.ai.agent import History, JediAgent
from jedi_mind_agent.ai.schemas import DiagnosticUpdate, ExerciseProposal
from jedi_mind_agent.ai.service import fallback_answer
from jedi_mind_agent.product.enums import (
    ACTIVE_EXERCISE_STATUSES,
    EXERCISE_TRANSITIONS,
    LEVEL_RANK,
    NEXT_LEVEL,
    ChatRole,
    ExerciseStatus,
    ReadinessResult,
    UserLevel,
)
from jedi_mind_agent.product.models import (
    ChatMessage,
    ChatSession,
    ReadinessCheck,
    User,
    UserExercise,
    UserState,
    UserStatusLog,
    utcnow,
)
from jedi_mind_agent.rag.retrieval import format_rag_context
from jedi_mind_agent.rag.schemas import RetrievalResult

logger = logging.getLogger(__name__)

DEFAULT_USERNAME = "default"
HISTORY_LIMIT = 20
MAX_ACTIVE_EXERCISES = 3
READINESS_MIN_COMPLETED = 1

# Everything a reset deletes. Chat messages come before chat sessions because they reference them.
USER_DATA_MODELS = (ChatMessage, ChatSession, UserExercise, ReadinessCheck, UserStatusLog)

Retriever = Callable[[str], list[RetrievalResult]]


class DomainError(Exception):
    pass


# --- queries -----------------------------------------------------------------


async def get_state(session: AsyncSession, user_id: uuid.UUID) -> UserState:
    state = await session.scalar(select(UserState).where(UserState.user_id == user_id))
    if state is None:
        state = UserState(user_id=user_id, level=UserLevel.UNKNOWN)
        session.add(state)
        await session.flush()
    return state


async def find_chat_session(session: AsyncSession, user_id: uuid.UUID) -> ChatSession | None:
    return await session.scalar(
        select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.updated_at.desc()).limit(1)
    )


async def list_messages(session: AsyncSession, chat_session_id: uuid.UUID, limit: int | None = None) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == chat_session_id)
        .order_by(ChatMessage.created_at.desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(reversed((await session.scalars(stmt)).all()))


async def list_exercises(session: AsyncSession, user_id: uuid.UUID) -> list[UserExercise]:
    return list(
        await session.scalars(
            select(UserExercise).where(UserExercise.user_id == user_id).order_by(UserExercise.updated_at.desc())
        )
    )


async def last_readiness_check(session: AsyncSession, user_id: uuid.UUID) -> ReadinessCheck | None:
    return await session.scalar(
        select(ReadinessCheck)
        .where(ReadinessCheck.user_id == user_id)
        .order_by(ReadinessCheck.created_at.desc())
        .limit(1)
    )


# --- commands ----------------------------------------------------------------


async def get_or_create_user(session: AsyncSession, username: str) -> User:
    user = await session.scalar(select(User).where(User.username == username))
    if user is not None:
        return user

    user = User(username=username)
    session.add(user)
    await session.flush()
    session.add(UserState(user_id=user.id, level=UserLevel.UNKNOWN))
    await session.commit()
    return user


async def reset_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Delete all of the user's product data in one transaction. The user and an empty state remain."""
    for model in USER_DATA_MODELS:
        await session.execute(delete(model).where(model.user_id == user_id))

    await session.execute(
        update(UserState)
        .where(UserState.user_id == user_id)
        .values(
            level=UserLevel.UNKNOWN,
            energy_level=None,
            focus_level=None,
            main_problem=None,
            time_limit_minutes=None,
            diagnostic_completed_at=None,
            updated_at=utcnow(),
        )
    )
    await session.commit()


async def change_exercise_status(
    session: AsyncSession, *, user_id: uuid.UUID, exercise_id: uuid.UUID, target: ExerciseStatus
) -> UserExercise:
    exercise = await session.get(UserExercise, exercise_id)
    if exercise is None or exercise.user_id != user_id:
        raise DomainError("Упражнение не найдено.")
    if target not in EXERCISE_TRANSITIONS.get(exercise.status, ()):
        raise DomainError(f"Недопустимый переход статуса: {exercise.status} → {target}.")

    exercise.status = target
    if target == ExerciseStatus.IN_PROGRESS:
        exercise.started_at = utcnow()
    elif target == ExerciseStatus.COMPLETED:
        exercise.completed_at = utcnow()
    await session.commit()
    return exercise


async def handle_chat_message(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    text: str,
    agent: JediAgent,
    retrieve: Retriever | None,
) -> None:
    chat = await _get_or_create_chat_session(session, user_id)
    session.add(ChatMessage(session_id=chat.id, user_id=user_id, role=ChatRole.USER, content=text))
    chat.updated_at = utcnow()
    # Commit before the LLM call: the user's message survives an agent failure.
    await session.commit()

    state = await get_state(session, user_id)
    exercises = await list_exercises(session, user_id)
    history = await list_messages(session, chat.id, limit=HISTORY_LIMIT)
    rag_results = await _retrieve(retrieve, text) if retrieve else []

    reply, used_fallback = await agent.reply(
        user_context=build_user_context(state, exercises),
        history=_to_history(history),
        rag_context=format_rag_context(rag_results) if rag_results else None,
    )

    if not used_fallback:
        _apply_diagnostic(session, user_id, state, reply.diagnostic)
        _apply_exercise_proposal(session, user_id, state, exercises, reply.exercise, rag_results)

    await _post_assistant_message(
        session,
        chat,
        reply.answer,
        used_fallback=used_fallback,
        sources=[_source_ref(result) for result in rag_results],
    )


async def run_readiness_check(session: AsyncSession, *, user_id: uuid.UUID, agent: JediAgent) -> None:
    state = await get_state(session, user_id)
    chat = await _get_or_create_chat_session(session, user_id)
    from_level = state.level

    if from_level == UserLevel.UNKNOWN:
        await _post_assistant_message(
            session,
            chat,
            "Уровень пока не определён. Расскажите в чате о своём состоянии — после диагностики можно проверить готовность.",
        )
        return

    target_level = NEXT_LEVEL.get(from_level)
    if target_level is None:
        await _post_assistant_message(session, chat, "Вы уже на последнем уровне. Продолжайте закреплять практики.")
        return

    exercises = await list_exercises(session, user_id)
    completed = [e for e in exercises if e.status == ExerciseStatus.COMPLETED and e.level == from_level]

    # Deterministic gate: without completed practice the LLM is not asked at all.
    if len(completed) < READINESS_MIN_COMPLETED:
        result = ReadinessResult.NOT_READY
        summary = (
            "На текущем уровне пока нет выполненных упражнений. "
            "Выполните хотя бы одно из предложенных и попробуйте проверку снова."
        )
    else:
        history = await list_messages(session, chat.id, limit=HISTORY_LIMIT)
        assessment = await agent.assess_readiness(
            user_context=build_user_context(state, exercises), history=_to_history(history)
        )
        if assessment is None:
            await _post_assistant_message(
                session, chat, fallback_answer("readiness assessment is unavailable."), used_fallback=True
            )
            return
        result, summary = assessment.result, assessment.summary

    if result == ReadinessResult.READY:
        state.level = target_level
        session.add(
            UserStatusLog(
                user_id=user_id,
                level=target_level,
                energy_level=state.energy_level,
                focus_level=state.focus_level,
                summary=f"Readiness check: {from_level} -> {target_level}",
            )
        )

    session.add(
        ReadinessCheck(
            user_id=user_id, from_level=from_level, target_level=target_level, result=result, summary=summary
        )
    )
    await _post_assistant_message(session, chat, summary)


# --- helpers -----------------------------------------------------------------


def build_user_context(state: UserState, exercises: Sequence[UserExercise]) -> str:
    def show(value: object) -> str:
        return "неизвестно" if value is None else str(value)

    lines = [
        f"- уровень: {state.level}",
        f"- мыслетопливо (1–10): {show(state.energy_level)}",
        f"- фокус (1–10): {show(state.focus_level)}",
        f"- главная проблема: {show(state.main_problem)}",
        f"- время на практики, минут в день: {show(state.time_limit_minutes)}",
    ]

    active = [e for e in exercises if e.status in ACTIVE_EXERCISE_STATUSES]
    closed = [e for e in exercises if e.status not in ACTIVE_EXERCISE_STATUSES][:10]
    lines.append("Активные упражнения:" if active else "Активные упражнения: нет")
    lines.extend(f"- {e.title} [{e.status}, {e.level}]" for e in active)
    if closed:
        lines.append("Недавно закрытые упражнения:")
        lines.extend(f"- {e.title} [{e.status}, {e.level}]" for e in closed)
    return "\n".join(lines)


def _apply_diagnostic(
    session: AsyncSession, user_id: uuid.UUID, state: UserState, update: DiagnosticUpdate | None
) -> None:
    if update is None:
        return

    changed = False
    # Guardrail: the chat may only set the initial level; later changes go through a readiness check.
    if update.level not in (None, UserLevel.UNKNOWN) and state.level == UserLevel.UNKNOWN:
        state.level = update.level
        state.diagnostic_completed_at = utcnow()
        changed = True

    for field, value in (
        ("energy_level", _scale(update.energy_level)),
        ("focus_level", _scale(update.focus_level)),
        ("main_problem", _text(update.main_problem)),
        ("time_limit_minutes", update.time_limit_minutes if update.time_limit_minutes and 0 < update.time_limit_minutes <= 600 else None),
    ):
        if value is not None and getattr(state, field) != value:
            setattr(state, field, value)
            changed = True

    if changed:
        session.add(
            UserStatusLog(
                user_id=user_id,
                level=state.level,
                energy_level=state.energy_level,
                focus_level=state.focus_level,
                summary="Diagnostic update from chat",
                raw=update.model_dump(mode="json"),
            )
        )


def _apply_exercise_proposal(
    session: AsyncSession,
    user_id: uuid.UUID,
    state: UserState,
    exercises: Sequence[UserExercise],
    proposal: ExerciseProposal | None,
    rag_results: Sequence[RetrievalResult],
) -> None:
    if proposal is None or state.level == UserLevel.UNKNOWN:
        return

    # Guardrail from the book: the user's level is the ceiling of practices.
    # An unspecified or unknown practice level defaults to the user's level.
    level = proposal.level if proposal.level not in (None, UserLevel.UNKNOWN) else state.level
    if LEVEL_RANK[level] > LEVEL_RANK[state.level]:
        logger.info("Exercise proposal rejected: practice level %s is above user level %s", level, state.level)
        return

    title = _text(proposal.title)
    description = _text(proposal.description)
    if not title or not description:
        return

    active = [e for e in exercises if e.status in ACTIVE_EXERCISE_STATUSES]
    if len(active) >= MAX_ACTIVE_EXERCISES:
        logger.info("Exercise proposal skipped: user %s already has %d active exercises", user_id, len(active))
        return
    if any(e.title.casefold() == title.casefold() for e in active):
        return

    minutes = proposal.estimated_minutes
    session.add(
        UserExercise(
            user_id=user_id,
            level=level,
            title=title[:200],
            description=description,
            estimated_minutes=minutes if minutes and 0 < minutes <= 600 else None,
            status=ExerciseStatus.SUGGESTED,
            sources=[{"chunk_id": r.chunk_id, **_source_ref(r)} for r in rag_results] or None,
        )
    )


async def _get_or_create_chat_session(session: AsyncSession, user_id: uuid.UUID) -> ChatSession:
    chat = await find_chat_session(session, user_id)
    if chat is None:
        chat = ChatSession(user_id=user_id)
        session.add(chat)
        await session.flush()
    return chat


async def _post_assistant_message(
    session: AsyncSession,
    chat: ChatSession,
    content: str,
    *,
    used_fallback: bool = False,
    sources: list[dict] | None = None,
) -> None:
    session.add(
        ChatMessage(
            session_id=chat.id,
            user_id=chat.user_id,
            role=ChatRole.ASSISTANT,
            content=content,
            meta={"used_fallback": used_fallback, "sources": sources or []},
        )
    )
    chat.updated_at = utcnow()
    await session.commit()


async def _retrieve(retrieve: Retriever, query: str) -> list[RetrievalResult]:
    try:
        return await run_in_threadpool(retrieve, query)
    except Exception:
        logger.exception("RAG retrieval failed; answering without book context")
        return []


def _to_history(messages: Sequence[ChatMessage]) -> History:
    return [(message.role.value, message.content) for message in messages]


def _source_ref(result: RetrievalResult) -> dict:
    # Only the title and pages reach the UI: no file paths, no chunk text.
    return {
        "source_title": result.source_title or result.source_slug,
        "page_start": result.page_start,
        "page_end": result.page_end,
    }


def _scale(value: int | None) -> int | None:
    return value if value is not None and 1 <= value <= 10 else None


def _text(value: str | None) -> str | None:
    return value.strip() or None if value else None
