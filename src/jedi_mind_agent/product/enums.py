from enum import StrEnum


class UserLevel(StrEnum):
    UNKNOWN = "unknown"
    LEVEL_1 = "level_1"
    LEVEL_2 = "level_2"
    LEVEL_3 = "level_3"


class ExerciseStatus(StrEnum):
    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    NOT_SUITABLE = "not_suitable"
    CANCELLED = "cancelled"


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ReadinessResult(StrEnum):
    READY = "ready"
    PARTIALLY_READY = "partially_ready"
    NOT_READY = "not_ready"


EXERCISE_TRANSITIONS: dict[ExerciseStatus, tuple[ExerciseStatus, ...]] = {
    ExerciseStatus.SUGGESTED: (ExerciseStatus.ACCEPTED, ExerciseStatus.SKIPPED, ExerciseStatus.NOT_SUITABLE),
    ExerciseStatus.ACCEPTED: (ExerciseStatus.IN_PROGRESS, ExerciseStatus.SKIPPED, ExerciseStatus.NOT_SUITABLE),
    ExerciseStatus.IN_PROGRESS: (ExerciseStatus.COMPLETED, ExerciseStatus.NOT_SUITABLE, ExerciseStatus.CANCELLED),
}

ACTIVE_EXERCISE_STATUSES = frozenset(EXERCISE_TRANSITIONS)

NEXT_LEVEL: dict[UserLevel, UserLevel] = {
    UserLevel.LEVEL_1: UserLevel.LEVEL_2,
    UserLevel.LEVEL_2: UserLevel.LEVEL_3,
}
