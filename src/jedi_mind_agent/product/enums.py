from enum import StrEnum


class UserLevel(StrEnum):
    UNKNOWN = "unknown"
    LEVEL_1 = "level_1"
    LEVEL_2 = "level_2"
    LEVEL_3 = "level_3"
    LEVEL_4 = "level_4"
    LEVEL_5 = "level_5"


class ExerciseStatus(StrEnum):
    SUGGESTED = "suggested"
    SUITABLE = "suitable"
    NOT_SUITABLE = "not_suitable"


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


# Exercises are not performed, only evaluated — the book's "keep / discard". The evaluation can be changed later.
EXERCISE_TRANSITIONS: dict[ExerciseStatus, tuple[ExerciseStatus, ...]] = {
    ExerciseStatus.SUGGESTED: (ExerciseStatus.SUITABLE, ExerciseStatus.NOT_SUITABLE),
    ExerciseStatus.SUITABLE: (ExerciseStatus.NOT_SUITABLE,),
    ExerciseStatus.NOT_SUITABLE: (ExerciseStatus.SUITABLE,),
}

LEVEL_RANK: dict[UserLevel, int] = {
    UserLevel.UNKNOWN: 0,
    UserLevel.LEVEL_1: 1,
    UserLevel.LEVEL_2: 2,
    UserLevel.LEVEL_3: 3,
    UserLevel.LEVEL_4: 4,
    UserLevel.LEVEL_5: 5,
}

LEVEL_BY_RANK: dict[int, UserLevel] = {rank: level for level, rank in LEVEL_RANK.items()}

# Approved level names, see docs/levels.md.
LEVEL_TITLES: dict[UserLevel, str] = {
    UserLevel.UNKNOWN: "не определён",
    UserLevel.LEVEL_1: "Все горит",
    UserLevel.LEVEL_2: "Ночь простоять да день продержаться",
    UserLevel.LEVEL_3: "Есть свет в конце тоннеля",
    UserLevel.LEVEL_4: "Планомерно к намеченным целям",
    UserLevel.LEVEL_5: "Естественно, спонтанно и все во благо",
}
