"""Create product schema: users, state, chat, exercises, readiness checks.

Revision ID: 0002_product_schema
Revises: 0001_foundation_schema
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_product_schema"
down_revision: str | None = "0001_foundation_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_level = postgresql.ENUM("unknown", "level_1", "level_2", "level_3", name="user_level", create_type=False)
exercise_status = postgresql.ENUM(
    "suggested",
    "accepted",
    "in_progress",
    "completed",
    "skipped",
    "not_suitable",
    "cancelled",
    name="exercise_status",
    create_type=False,
)
chat_role = postgresql.ENUM("user", "assistant", "system", "tool", name="chat_role", create_type=False)
readiness_result = postgresql.ENUM("ready", "partially_ready", "not_ready", name="readiness_result", create_type=False)

ENUMS = (user_level, exercise_status, chat_role, readiness_result)


def _id() -> sa.Column:
    return sa.Column("id", sa.Uuid(), primary_key=True)


def _user_id() -> sa.Column:
    return sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def _updated_at() -> sa.Column:
    return sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        _id(),
        sa.Column("username", sa.String(length=50), nullable=False),
        _created_at(),
        _updated_at(),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )

    op.create_table(
        "user_states",
        _id(),
        _user_id(),
        sa.Column("level", user_level, nullable=False, server_default="unknown"),
        sa.Column("energy_level", sa.SmallInteger(), nullable=True),
        sa.Column("focus_level", sa.SmallInteger(), nullable=True),
        sa.Column("main_problem", sa.Text(), nullable=True),
        sa.Column("time_limit_minutes", sa.Integer(), nullable=True),
        sa.Column("diagnostic_completed_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        sa.UniqueConstraint("user_id", name="uq_user_states_user_id"),
        sa.CheckConstraint("energy_level between 1 and 10", name="ck_user_states_energy_level"),
        sa.CheckConstraint("focus_level between 1 and 10", name="ck_user_states_focus_level"),
    )

    op.create_table(
        "user_status_logs",
        _id(),
        _user_id(),
        sa.Column("level", user_level, nullable=False),
        sa.Column("energy_level", sa.SmallInteger(), nullable=True),
        sa.Column("focus_level", sa.SmallInteger(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("raw", postgresql.JSONB(), nullable=True),
        _created_at(),
    )
    op.create_index("ix_user_status_logs_user_created_at", "user_status_logs", ["user_id", "created_at"])

    op.create_table(
        "chat_sessions",
        _id(),
        _user_id(),
        sa.Column("title", sa.Text(), nullable=True),
        _created_at(),
        _updated_at(),
    )
    op.create_index("ix_chat_sessions_user_updated_at", "chat_sessions", ["user_id", "updated_at"])

    op.create_table(
        "chat_messages",
        _id(),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        _user_id(),
        sa.Column("role", chat_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        _created_at(),
    )
    op.create_index("ix_chat_messages_session_created_at", "chat_messages", ["session_id", "created_at"])

    op.create_table(
        "user_exercises",
        _id(),
        _user_id(),
        sa.Column("level", user_level, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("status", exercise_status, nullable=False, server_default="suggested"),
        sa.Column("sources", postgresql.JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
    )
    op.create_index("ix_user_exercises_user_status", "user_exercises", ["user_id", "status"])

    op.create_table(
        "readiness_checks",
        _id(),
        _user_id(),
        sa.Column("from_level", user_level, nullable=False),
        sa.Column("target_level", user_level, nullable=True),
        sa.Column("result", readiness_result, nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        _created_at(),
    )
    op.create_index("ix_readiness_checks_user_created_at", "readiness_checks", ["user_id", "created_at"])


def downgrade() -> None:
    for table in (
        "readiness_checks",
        "user_exercises",
        "chat_messages",
        "chat_sessions",
        "user_status_logs",
        "user_states",
        "users",
    ):
        op.drop_table(table)

    bind = op.get_bind()
    for enum in reversed(ENUMS):
        enum.drop(bind, checkfirst=True)
