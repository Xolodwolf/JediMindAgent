import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from jedi_mind_agent.db.base import Base
from jedi_mind_agent.product.enums import ChatRole, ExerciseStatus, ReadinessResult, UserLevel


def utcnow() -> datetime:
    return datetime.now(UTC)


def _pg_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(enum_cls, name=name, values_callable=lambda members: [member.value for member in members])


USER_LEVEL = _pg_enum(UserLevel, "user_level")
EXERCISE_STATUS = _pg_enum(ExerciseStatus, "exercise_status")
CHAT_ROLE = _pg_enum(ChatRole, "chat_role")
READINESS_RESULT = _pg_enum(ReadinessResult, "readiness_result")


class UuidPk:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Timestamps(CreatedAt):
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


class User(UuidPk, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username", name="uq_users_username"),)

    username: Mapped[str] = mapped_column(String(50))


class UserState(UuidPk, Timestamps, Base):
    __tablename__ = "user_states"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_states_user_id"),
        CheckConstraint("energy_level between 1 and 10", name="ck_user_states_energy_level"),
        CheckConstraint("focus_level between 1 and 10", name="ck_user_states_focus_level"),
    )

    user_id: Mapped[uuid.UUID] = _user_fk()
    level: Mapped[UserLevel] = mapped_column(USER_LEVEL, default=UserLevel.UNKNOWN)
    energy_level: Mapped[int | None] = mapped_column(SmallInteger)
    focus_level: Mapped[int | None] = mapped_column(SmallInteger)
    main_problem: Mapped[str | None] = mapped_column(Text)
    time_limit_minutes: Mapped[int | None]
    diagnostic_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserStatusLog(UuidPk, CreatedAt, Base):
    __tablename__ = "user_status_logs"
    __table_args__ = (Index("ix_user_status_logs_user_created_at", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    level: Mapped[UserLevel] = mapped_column(USER_LEVEL)
    energy_level: Mapped[int | None] = mapped_column(SmallInteger)
    focus_level: Mapped[int | None] = mapped_column(SmallInteger)
    summary: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class ChatSession(UuidPk, Timestamps, Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (Index("ix_chat_sessions_user_updated_at", "user_id", "updated_at"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    title: Mapped[str | None] = mapped_column(Text)


class ChatMessage(UuidPk, CreatedAt, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_session_created_at", "session_id", "created_at"),)

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = _user_fk()
    role: Mapped[ChatRole] = mapped_column(CHAT_ROLE)
    content: Mapped[str] = mapped_column(Text)
    # "metadata" is reserved by the declarative API, so the attribute is named differently from the column.
    meta: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)


class UserExercise(UuidPk, Timestamps, Base):
    __tablename__ = "user_exercises"
    __table_args__ = (Index("ix_user_exercises_user_status", "user_id", "status"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    level: Mapped[UserLevel] = mapped_column(USER_LEVEL)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    estimated_minutes: Mapped[int | None]
    status: Mapped[ExerciseStatus] = mapped_column(EXERCISE_STATUS, default=ExerciseStatus.SUGGESTED)
    # RAG chunks live in ChromaDB, so references are stored as JSON instead of foreign keys.
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)


class ReadinessCheck(UuidPk, CreatedAt, Base):
    __tablename__ = "readiness_checks"
    __table_args__ = (Index("ix_readiness_checks_user_created_at", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    from_level: Mapped[UserLevel] = mapped_column(USER_LEVEL)
    target_level: Mapped[UserLevel | None] = mapped_column(USER_LEVEL)
    result: Mapped[ReadinessResult] = mapped_column(READINESS_RESULT)
    summary: Mapped[str] = mapped_column(Text)
