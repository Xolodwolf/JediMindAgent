import uuid
from enum import StrEnum

from django.conf import settings
from django.db import models

from jedi_mind_agent.product.enums import ChatRole, ExerciseStatus, UserLevel


def _choices(enum_cls: type[StrEnum]) -> list[tuple[str, str]]:
    return [(member.value, member.value) for member in enum_cls]


USER_LEVEL_CHOICES = _choices(UserLevel)


class UuidModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        abstract = True


def _user_fk(related_name: str) -> models.ForeignKey:
    return models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name=related_name, verbose_name="пользователь"
    )


def _scale_check(model: str, field: str) -> models.CheckConstraint:
    return models.CheckConstraint(
        condition=models.Q(**{f"{field}__isnull": True}) | models.Q(**{f"{field}__gte": 1, f"{field}__lte": 10}),
        name=f"ck_{model}_{field}",
    )


class UserState(UuidModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="jedi_state", verbose_name="пользователь"
    )
    level = models.CharField("уровень", max_length=20, choices=USER_LEVEL_CHOICES, default=UserLevel.UNKNOWN)
    energy_level = models.PositiveSmallIntegerField("мыслетопливо", null=True, blank=True)
    focus_level = models.PositiveSmallIntegerField("фокус", null=True, blank=True)
    main_problem = models.TextField("главная проблема", null=True, blank=True)
    time_limit_minutes = models.PositiveIntegerField("минут в день на практики", null=True, blank=True)
    diagnostic_completed_at = models.DateTimeField("тест пройден", null=True, blank=True)
    updated_at = models.DateTimeField("изменено", auto_now=True)

    class Meta:
        verbose_name = "состояние пользователя"
        verbose_name_plural = "состояния пользователей"
        constraints = [_scale_check("userstate", "energy_level"), _scale_check("userstate", "focus_level")]

    def __str__(self) -> str:
        return f"{self.user} — {self.level}"


class UserStatusLog(UuidModel):
    user = _user_fk("jedi_status_logs")
    level = models.CharField("уровень", max_length=20, choices=USER_LEVEL_CHOICES)
    energy_level = models.PositiveSmallIntegerField("мыслетопливо", null=True, blank=True)
    focus_level = models.PositiveSmallIntegerField("фокус", null=True, blank=True)
    summary = models.TextField("событие", null=True, blank=True)
    raw = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "запись журнала состояния"
        verbose_name_plural = "журнал состояния"
        indexes = [models.Index(fields=["user", "created_at"], name="ix_statuslog_user_ct")]


class ChatSession(UuidModel):
    user = _user_fk("jedi_chat_sessions")
    title = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField("изменено", auto_now=True)

    class Meta:
        verbose_name = "чат"
        verbose_name_plural = "чаты"
        indexes = [models.Index(fields=["user", "updated_at"], name="ix_chatsession_user_upd")]

    def __str__(self) -> str:
        return f"Чат {self.user} от {self.created_at:%Y-%m-%d}"


class ChatMessage(UuidModel):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages", verbose_name="чат")
    user = _user_fk("jedi_chat_messages")
    role = models.CharField("роль", max_length=20, choices=_choices(ChatRole))
    content = models.TextField("текст")
    meta = models.JSONField(db_column="metadata", null=True, blank=True)

    class Meta:
        verbose_name = "сообщение"
        verbose_name_plural = "сообщения"
        indexes = [models.Index(fields=["session", "created_at"], name="ix_chatmessage_session_ct")]


class UserExercise(UuidModel):
    user = _user_fk("jedi_exercises")
    level = models.CharField("уровень", max_length=20, choices=USER_LEVEL_CHOICES)
    title = models.CharField("название", max_length=200)
    description = models.TextField("описание")
    estimated_minutes = models.PositiveIntegerField("минут", null=True, blank=True)
    status = models.CharField(
        "оценка", max_length=20, choices=_choices(ExerciseStatus), default=ExerciseStatus.SUGGESTED
    )
    # RAG chunks live in ChromaDB, so references are stored as JSON instead of foreign keys.
    sources = models.JSONField(null=True, blank=True)
    updated_at = models.DateTimeField("изменено", auto_now=True)

    class Meta:
        verbose_name = "упражнение"
        verbose_name_plural = "упражнения"
        indexes = [models.Index(fields=["user", "status"], name="ix_exercise_user_status")]

    def __str__(self) -> str:
        return self.title


class LevelTest(UuidModel):
    """One attempt of the level test. An attempt without completed_at is the test currently running in the chat."""

    user = _user_fk("jedi_level_tests")
    # [{"choice": displayed option number, "score": level of that option}, ...]; the next question is len(answers).
    answers = models.JSONField(default=list, blank=True)
    level = models.CharField("уровень", max_length=20, choices=USER_LEVEL_CHOICES, null=True, blank=True)
    energy_level = models.PositiveSmallIntegerField("мыслетопливо", null=True, blank=True)
    completed_at = models.DateTimeField("завершён", null=True, blank=True)

    class Meta:
        verbose_name = "попытка теста"
        verbose_name_plural = "попытки теста"
        indexes = [models.Index(fields=["user", "created_at"], name="ix_leveltest_user_ct")]
        constraints = [_scale_check("leveltest", "energy_level")]
