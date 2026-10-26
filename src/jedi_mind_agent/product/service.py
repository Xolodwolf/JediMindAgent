"""Domain commands. The only place that changes product state; agent output is applied here after validation.

Django runs in autocommit mode: every save is committed at once. Multi-row changes use `transaction.atomic`,
and LLM calls always happen outside a transaction, after the user's message is already stored.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from jedi_mind_agent.ai.agent import History, JediAgent
from jedi_mind_agent.ai.schemas import DiagnosticUpdate, ExerciseProposal
from jedi_mind_agent.knowledge.rag import RetrievalResult, format_rag_context
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
    UserExercise,
    UserState,
    UserStatusLog,
)

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 20
# The book suggests working on a small portion of practices at a time.
MAX_NEW_EXERCISES = 3

# Everything a reset deletes. Chat messages are deleted with their sessions.
USER_DATA_MODELS = (ChatSession, UserExercise, LevelTest, UserStatusLog)

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


def get_state(user_id: int) -> UserState:
    state, _ = UserState.objects.get_or_create(user_id=user_id, defaults={"level": UserLevel.UNKNOWN})
    return state


def find_chat_session(user_id: int) -> ChatSession | None:
    return ChatSession.objects.filter(user_id=user_id).order_by("-updated_at").first()


def list_messages(chat_session_id, limit: int | None = None, *, exclude_test: bool = False) -> list[ChatMessage]:
    messages = ChatMessage.objects.filter(session_id=chat_session_id)
    if exclude_test:
        # Test questions and answers stay in the chat, but never take up the agent's history window.
        messages = messages.filter(Q(meta__isnull=True) | ~Q(meta__has_key="test"))
    messages = messages.order_by("-created_at")
    if limit is not None:
        messages = messages[:limit]
    return list(reversed(messages))


def list_user_messages(user_id: int) -> list[ChatMessage]:
    chat = find_chat_session(user_id)
    return list_messages(chat.id) if chat else []


def list_exercises(user_id: int) -> list[UserExercise]:
    return list(UserExercise.objects.filter(user_id=user_id).order_by("-updated_at"))


def find_active_test(user_id: int) -> LevelTest | None:
    return LevelTest.objects.filter(user_id=user_id, completed_at__isnull=True).order_by("-created_at").first()


# --- commands ----------------------------------------------------------------


def reset_user(user_id: int) -> UserState:
    """Delete all of the user's product data in one transaction. The account and an empty state remain."""
    with transaction.atomic():
        for model in USER_DATA_MODELS:
            model.objects.filter(user_id=user_id).delete()
        state = get_state(user_id)
        state.level = UserLevel.UNKNOWN
        state.energy_level = state.focus_level = state.main_problem = state.time_limit_minutes = None
        state.diagnostic_completed_at = None
        state.save()
    return state


def change_exercise_status(*, user_id: int, exercise_id, target: ExerciseStatus) -> UserExercise:
    exercise = UserExercise.objects.filter(id=exercise_id, user_id=user_id).first()
    if exercise is None:
        raise NotFoundError("Упражнение не найдено.")
    if target not in EXERCISE_TRANSITIONS.get(ExerciseStatus(exercise.status), ()):
        raise DomainError(f"Недопустимый переход статуса: {exercise.status} → {target}.")

    exercise.status = target
    exercise.save(update_fields=["status", "updated_at"])
    return exercise


def delete_exercise(*, user_id: int, exercise_id) -> None:
    deleted, _ = UserExercise.objects.filter(id=exercise_id, user_id=user_id).delete()
    if not deleted:
        raise NotFoundError("Упражнение не найдено.")


def start_level_test(*, user_id: int, restart: bool) -> ChatTurn:
    """Ask the first test question in the chat. Without `restart` an unfinished test is resumed as it is."""
    state = get_state(user_id)
    with transaction.atomic():
        active = find_active_test(user_id)
        if active is not None:
            if not restart:
                return ChatTurn([], state)
            active.delete()

        chat = _get_or_create_chat_session(user_id)
        test = LevelTest.objects.create(user_id=user_id, answers=[])
        question = _post_test_question(chat, test, step=0, prefix=level_test.INTRO)
    return ChatTurn([question], state)


def handle_chat_message(*, user_id: int, text: str, agent: JediAgent, retrieve: Retriever | None) -> ChatTurn:
    state = get_state(user_id)
    test = find_active_test(user_id)
    if test is not None:
        return _answer_level_test(test=test, state=state, text=text, agent=agent)

    chat = _get_or_create_chat_session(user_id)
    # Saved before the LLM call: the user's message survives an agent failure.
    user_message = _add_message(chat, ChatRole.USER, text)

    if state.level == UserLevel.UNKNOWN:
        # Only the test sets the level, so a conversation without a level starts with the test.
        turn = start_level_test(user_id=user_id, restart=False)
        return ChatTurn([user_message, *turn.messages], turn.state)

    exercises = list_exercises(user_id)
    history = list_messages(chat.id, limit=HISTORY_LIMIT, exclude_test=True)
    # The level is the ceiling of practices, so book sections above it never reach the agent's context.
    rag_results = _retrieve(retrieve, text, LEVEL_RANK[UserLevel(state.level)]) if retrieve else []

    reply, used_fallback = agent.reply(
        user_context=build_user_context(state, exercises),
        history=_to_history(history),
        rag_context=format_rag_context(rag_results) if rag_results else None,
    )

    new_exercises: list[UserExercise] = []
    with transaction.atomic():
        if not used_fallback:
            _apply_diagnostic(user_id, state, reply.diagnostic)
            exercise = _apply_exercise_proposal(user_id, state, exercises, reply.exercise, rag_results)
            if exercise is not None:
                new_exercises.append(exercise)

        assistant_message = _add_message(
            chat,
            ChatRole.ASSISTANT,
            _unescape_newlines(reply.answer),
            {"used_fallback": used_fallback, "sources": [_source_ref(result) for result in rag_results]},
        )
    return ChatTurn([user_message, assistant_message], state, new_exercises)


# --- level test --------------------------------------------------------------


def _answer_level_test(*, test: LevelTest, state: UserState, text: str, agent: JediAgent) -> ChatTurn:
    """Handle a chat message as a test answer. Deterministic: the LLM only explains the final result."""
    chat = _get_or_create_chat_session(test.user_id)
    step = len(test.answers)
    choice = level_test.parse_choice(text, step)

    user_message = _add_message(
        chat,
        ChatRole.USER,
        level_test.answer_label(step, choice) if choice else text,
        {"test": {"test_id": str(test.id), "step": step, "choice": choice}},
    )

    if choice is None:
        question = _post_test_question(chat, test, step=step, prefix=level_test.INVALID_ANSWER)
        return ChatTurn([user_message, question], state)

    if step < level_test.ENERGY_STEP:
        with transaction.atomic():
            test.answers = [*test.answers, {"choice": choice, "score": level_test.score(step, choice)}]
            test.save(update_fields=["answers"])
            question = _post_test_question(chat, test, step=step + 1)
        return ChatTurn([user_message, question], state)

    # The mental fuel scale is the last step: the test is complete.
    level = level_test.level_from_scores([answer["score"] for answer in test.answers])
    now = timezone.now()
    # Saved before the LLM call: the explanation is optional, the level is not.
    with transaction.atomic():
        test.level, test.energy_level, test.completed_at = level, choice, now
        test.save(update_fields=["level", "energy_level", "completed_at"])
        state.level, state.energy_level, state.diagnostic_completed_at = level, choice, now
        state.save()
        UserStatusLog.objects.create(
            user_id=test.user_id,
            level=level,
            energy_level=choice,
            focus_level=state.focus_level,
            summary="Level test",
            raw={"test_id": str(test.id), "answers": test.answers},
        )

    explanation = agent.explain_test_result(
        level_rank=LEVEL_RANK[level],
        level_title=LEVEL_TITLES[level],
        energy_level=choice,
        answers=level_test.describe_answers(test.answers),
    )
    result = _add_message(
        chat,
        ChatRole.ASSISTANT,
        level_test.result_text(level, choice, explanation),
        {"used_fallback": explanation is None, "sources": []},
    )
    return ChatTurn([user_message, result], state)


def _post_test_question(chat: ChatSession, test: LevelTest, *, step: int, prefix: str | None = None) -> ChatMessage:
    text = level_test.question_text(step)
    return _add_message(
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


def _apply_diagnostic(user_id: int, state: UserState, update: DiagnosticUpdate | None) -> None:
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
        state.save()
        UserStatusLog.objects.create(
            user_id=user_id,
            level=state.level,
            energy_level=state.energy_level,
            focus_level=state.focus_level,
            summary="Diagnostic update from chat",
            raw=update.model_dump(mode="json"),
        )


def _apply_exercise_proposal(
    user_id: int,
    state: UserState,
    exercises: Sequence[UserExercise],
    proposal: ExerciseProposal | None,
    rag_results: Sequence[RetrievalResult],
) -> UserExercise | None:
    if proposal is None or state.level == UserLevel.UNKNOWN:
        return None

    # Guardrail from the book: the user's level is the ceiling of practices.
    # An unspecified or unknown practice level defaults to the user's level.
    user_level = UserLevel(state.level)
    level = proposal.level if proposal.level not in (None, UserLevel.UNKNOWN) else user_level
    if LEVEL_RANK[level] > LEVEL_RANK[user_level]:
        logger.info("Exercise proposal rejected: practice level %s is above user level %s", level, user_level)
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
    return UserExercise.objects.create(
        user_id=user_id,
        level=level,
        title=title[:200],
        description=description,
        estimated_minutes=minutes if minutes and 0 < minutes <= 600 else None,
        status=ExerciseStatus.SUGGESTED,
        sources=[{"chunk_id": r.chunk_id, **_source_ref(r)} for r in rag_results] or None,
    )


def _get_or_create_chat_session(user_id: int) -> ChatSession:
    return find_chat_session(user_id) or ChatSession.objects.create(user_id=user_id)


def _add_message(chat: ChatSession, role: ChatRole, content: str, meta: dict[str, Any] | None = None) -> ChatMessage:
    message = ChatMessage.objects.create(session=chat, user_id=chat.user_id, role=role, content=content, meta=meta)
    chat.save(update_fields=["updated_at"])
    return message


def _retrieve(retrieve: Retriever, query: str, max_level: int) -> list[RetrievalResult]:
    try:
        return retrieve(query, max_level)
    except Exception:
        logger.exception("RAG retrieval failed; answering without book context")
        return []


def _to_history(messages: Sequence[ChatMessage]) -> History:
    return [(message.role, message.content) for message in messages]


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
