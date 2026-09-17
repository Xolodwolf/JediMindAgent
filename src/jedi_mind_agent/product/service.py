"""Domain commands. The only place that changes product state; agent output is applied here after validation."""

import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from jedi_mind_agent.ai.agent import History, JediAgent
from jedi_mind_agent.ai.schemas import DiagnosticUpdate, ExerciseProposal
from jedi_mind_agent.product import level_test
from jedi_mind_agent.product.enums import (
    EXERCISE_TRANSITIONS,
    LEVEL_RANK,
    LEVEL_TITLES,
    ChatRole,
    ExerciseStatus,
    UserLevel,
)
from jedi_mind_agent.product.models import (
    ChatMessage,
    ChatSession,
    LevelTest,
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
# The book suggests working on a small portion of practices at a time.
MAX_NEW_EXERCISES = 3

# Everything a reset deletes. Chat messages come before chat sessions because they reference them.
USER_DATA_MODELS = (ChatMessage, ChatSession, UserExercise, LevelTest, UserStatusLog)

# (query, max_level) -> book chunks with level <= max_level
Retriever = Callable[[str, int], list[RetrievalResult]]


class DomainError(Exception):
    pass


class NotFoundError(DomainError):
    pass


@dataclass
class ChatTurn:
    """Messages created by one user action, in chronological order, and the resulting state."""

    messages: list[ChatMessage]
    state: UserState
    new_exercises: list[UserExercise] = field(default_factory=list)


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


async def list_messages(
    session: AsyncSession, chat_session_id: uuid.UUID, limit: int | None = None, *, exclude_test: bool = False
) -> list[ChatMessage]:
    stmt = select(ChatMessage).where(ChatMessage.session_id == chat_session_id)
    if exclude_test:
        # Test questions and answers stay in the chat, but never take up the agent's history window.
        stmt = stmt.where(or_(ChatMessage.meta.is_(None), ~ChatMessage.meta.has_key("test")))
    stmt = stmt.order_by(ChatMessage.created_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(reversed((await session.scalars(stmt)).all()))


async def list_user_messages(session: AsyncSession, user_id: uuid.UUID) -> list[ChatMessage]:
    chat = await find_chat_session(session, user_id)
    return await list_messages(session, chat.id) if chat else []


async def list_exercises(session: AsyncSession, user_id: uuid.UUID) -> list[UserExercise]:
    return list(
        await session.scalars(
            select(UserExercise).where(UserExercise.user_id == user_id).order_by(UserExercise.updated_at.desc())
        )
    )


async def find_active_test(session: AsyncSession, user_id: uuid.UUID) -> LevelTest | None:
    return await session.scalar(
        select(LevelTest)
        .where(LevelTest.user_id == user_id, LevelTest.completed_at.is_(None))
        .order_by(LevelTest.created_at.desc())
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


async def reset_user(session: AsyncSession, user_id: uuid.UUID) -> UserState:
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
        .execution_options(synchronize_session="fetch")
    )
    await session.commit()
    return await get_state(session, user_id)


async def change_exercise_status(
    session: AsyncSession, *, user_id: uuid.UUID, exercise_id: uuid.UUID, target: ExerciseStatus
) -> UserExercise:
    exercise = await session.get(UserExercise, exercise_id)
    if exercise is None or exercise.user_id != user_id:
        raise NotFoundError("Упражнение не найдено.")
    if target not in EXERCISE_TRANSITIONS.get(exercise.status, ()):
        raise DomainError(f"Недопустимый переход статуса: {exercise.status} → {target}.")

    exercise.status = target
    await session.commit()
    return exercise


async def delete_exercise(session: AsyncSession, *, user_id: uuid.UUID, exercise_id: uuid.UUID) -> None:
    exercise = await session.get(UserExercise, exercise_id)
    if exercise is None or exercise.user_id != user_id:
        raise NotFoundError("Упражнение не найдено.")
    await session.delete(exercise)
    await session.commit()


async def start_level_test(session: AsyncSession, *, user_id: uuid.UUID, restart: bool) -> ChatTurn:
    """Ask the first test question in the chat. Without `restart` an unfinished test is resumed as it is."""
    state = await get_state(session, user_id)
    active = await find_active_test(session, user_id)
    if active is not None:
        if not restart:
            return ChatTurn([], state)
        await session.delete(active)

    chat = await _get_or_create_chat_session(session, user_id)
    test = LevelTest(user_id=user_id, answers=[])
    session.add(test)
    await session.flush()
    question = await _post_test_question(session, chat, test, step=0, prefix=level_test.INTRO)
    return ChatTurn([question], state)


async def handle_chat_message(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    text: str,
    agent: JediAgent,
    retrieve: Retriever | None,
) -> ChatTurn:
    state = await get_state(session, user_id)
    test = await find_active_test(session, user_id)
    if test is not None:
        return await _answer_level_test(session, test=test, state=state, text=text, agent=agent)

    chat = await _get_or_create_chat_session(session, user_id)
    user_message = _add_message(session, chat, ChatRole.USER, text)
    # Commit before the LLM call: the user's message survives an agent failure.
    await session.commit()

    if state.level == UserLevel.UNKNOWN:
        # Only the test sets the level, so a conversation without a level starts with the test.
        turn = await start_level_test(session, user_id=user_id, restart=False)
        return ChatTurn([user_message, *turn.messages], turn.state)

    exercises = await list_exercises(session, user_id)
    history = await list_messages(session, chat.id, limit=HISTORY_LIMIT, exclude_test=True)
    # The level is the ceiling of practices, so book sections above it never reach the agent's context.
    rag_results = await _retrieve(retrieve, text, LEVEL_RANK[state.level]) if retrieve else []

    reply, used_fallback = await agent.reply(
        user_context=build_user_context(state, exercises),
        history=_to_history(history),
        rag_context=format_rag_context(rag_results) if rag_results else None,
    )

    new_exercises: list[UserExercise] = []
    if not used_fallback:
        _apply_diagnostic(session, user_id, state, reply.diagnostic)
        exercise = _apply_exercise_proposal(session, user_id, state, exercises, reply.exercise, rag_results)
        if exercise is not None:
            new_exercises.append(exercise)

    assistant_message = _add_message(
        session,
        chat,
        ChatRole.ASSISTANT,
        _unescape_newlines(reply.answer),
        {"used_fallback": used_fallback, "sources": [_source_ref(result) for result in rag_results]},
    )
    await session.commit()
    return ChatTurn([user_message, assistant_message], state, new_exercises)


# --- level test --------------------------------------------------------------


async def _answer_level_test(
    session: AsyncSession, *, test: LevelTest, state: UserState, text: str, agent: JediAgent
) -> ChatTurn:
    """Handle a chat message as a test answer. Deterministic: the LLM only explains the final result."""
    chat = await _get_or_create_chat_session(session, test.user_id)
    step = len(test.answers)
    choice = level_test.parse_choice(text, step)

    user_message = _add_message(
        session,
        chat,
        ChatRole.USER,
        level_test.answer_label(step, choice) if choice else text,
        {"test": {"test_id": str(test.id), "step": step, "choice": choice}},
    )
    await session.commit()

    if choice is None:
        question = await _post_test_question(session, chat, test, step=step, prefix=level_test.INVALID_ANSWER)
        return ChatTurn([user_message, question], state)

    if step < level_test.ENERGY_STEP:
        # Reassign instead of appending: in-place changes of a JSONB list are not tracked.
        test.answers = [*test.answers, {"choice": choice, "score": level_test.score(step, choice)}]
        question = await _post_test_question(session, chat, test, step=step + 1)
        return ChatTurn([user_message, question], state)

    # The mental fuel scale is the last step: the test is complete.
    level = level_test.level_from_scores([answer["score"] for answer in test.answers])
    now = utcnow()
    test.level, test.energy_level, test.completed_at = level, choice, now
    state.level, state.energy_level, state.diagnostic_completed_at = level, choice, now
    session.add(
        UserStatusLog(
            user_id=test.user_id,
            level=level,
            energy_level=choice,
            focus_level=state.focus_level,
            summary="Level test",
            raw={"test_id": str(test.id), "answers": test.answers},
        )
    )
    # Commit the result before the LLM call: the explanation is optional, the level is not.
    await session.commit()

    explanation = await agent.explain_test_result(
        level_rank=LEVEL_RANK[level],
        level_title=LEVEL_TITLES[level],
        energy_level=choice,
        answers=level_test.describe_answers(test.answers),
    )
    result = _add_message(
        session,
        chat,
        ChatRole.ASSISTANT,
        level_test.result_text(level, choice, explanation),
        {"used_fallback": explanation is None, "sources": []},
    )
    await session.commit()
    return ChatTurn([user_message, result], state)


async def _post_test_question(
    session: AsyncSession, chat: ChatSession, test: LevelTest, *, step: int, prefix: str | None = None
) -> ChatMessage:
    text = level_test.question_text(step)
    message = _add_message(
        session,
        chat,
        ChatRole.ASSISTANT,
        f"{prefix}\n\n{text}" if prefix else text,
        {
            "used_fallback": False,
            "sources": [],
            "test": {
                "test_id": str(test.id),
                "step": step,
                "total": level_test.TOTAL_STEPS,
                "kind": "scale" if level_test.is_scale(step) else "choice",
                "choices": level_test.choices(step),
            },
        },
    )
    await session.commit()
    return message


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

    for label, status in (
        ("Новые упражнения, ещё не оценены", ExerciseStatus.SUGGESTED),
        ("Упражнения, которые подошли", ExerciseStatus.SUITABLE),
        ("Упражнения, которые не подошли", ExerciseStatus.NOT_SUITABLE),
    ):
        items = [e for e in exercises if e.status == status][:10]
        lines.append(f"{label}:" if items else f"{label}: нет")
        lines.extend(f"- {e.title} [{e.level}]" for e in items)
    return "\n".join(lines)


def _apply_diagnostic(
    session: AsyncSession, user_id: uuid.UUID, state: UserState, update: DiagnosticUpdate | None
) -> None:
    # The level is not here on purpose: only the level test sets it.
    if update is None:
        return

    changed = False
    for field_name, value in (
        ("energy_level", _scale(update.energy_level)),
        ("focus_level", _scale(update.focus_level)),
        ("main_problem", _text(update.main_problem)),
        ("time_limit_minutes", update.time_limit_minutes if update.time_limit_minutes and 0 < update.time_limit_minutes <= 600 else None),
    ):
        if value is not None and getattr(state, field_name) != value:
            setattr(state, field_name, value)
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
) -> UserExercise | None:
    if proposal is None or state.level == UserLevel.UNKNOWN:
        return None

    # Guardrail from the book: the user's level is the ceiling of practices.
    # An unspecified or unknown practice level defaults to the user's level.
    level = proposal.level if proposal.level not in (None, UserLevel.UNKNOWN) else state.level
    if LEVEL_RANK[level] > LEVEL_RANK[state.level]:
        logger.info("Exercise proposal rejected: practice level %s is above user level %s", level, state.level)
        return None

    title = _text(proposal.title)
    description = _text(_unescape_newlines(proposal.description))
    if not title or not description:
        return None

    new = [e for e in exercises if e.status == ExerciseStatus.SUGGESTED]
    if len(new) >= MAX_NEW_EXERCISES:
        logger.info("Exercise proposal skipped: user %s already has %d unevaluated exercises", user_id, len(new))
        return None
    # Never re-suggest a practice the user already has, including one that did not suit them.
    if any(e.title.casefold() == title.casefold() for e in exercises):
        return None

    minutes = proposal.estimated_minutes
    exercise = UserExercise(
        user_id=user_id,
        level=level,
        title=title[:200],
        description=description,
        estimated_minutes=minutes if minutes and 0 < minutes <= 600 else None,
        status=ExerciseStatus.SUGGESTED,
        sources=[{"chunk_id": r.chunk_id, **_source_ref(r)} for r in rag_results] or None,
    )
    session.add(exercise)
    return exercise


async def _get_or_create_chat_session(session: AsyncSession, user_id: uuid.UUID) -> ChatSession:
    chat = await find_chat_session(session, user_id)
    if chat is None:
        chat = ChatSession(user_id=user_id)
        session.add(chat)
        await session.flush()
    return chat


def _add_message(
    session: AsyncSession, chat: ChatSession, role: ChatRole, content: str, meta: dict[str, Any] | None = None
) -> ChatMessage:
    message = ChatMessage(session_id=chat.id, user_id=chat.user_id, role=role, content=content, meta=meta)
    session.add(message)
    chat.updated_at = utcnow()
    return message


async def _retrieve(retrieve: Retriever, query: str, max_level: int) -> list[RetrievalResult]:
    try:
        return await run_in_threadpool(retrieve, query, max_level)
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


def _unescape_newlines(value: str) -> str:
    # The model occasionally double-escapes line breaks in tool arguments ("\\n" instead of "\n").
    if "\n" not in value and "\\n" in value:
        return value.replace("\\n", "\n")
    return value
