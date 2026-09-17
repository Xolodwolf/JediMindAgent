"""Level test in the chat replaces readiness checks.

Revision ID: 0005_level_test
Revises: 0004_exercise_fit
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_level_test"
down_revision: str | None = "0004_exercise_fit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_level = postgresql.ENUM(
    "unknown", "level_1", "level_2", "level_3", "level_4", "level_5", name="user_level", create_type=False
)
readiness_result = postgresql.ENUM("ready", "partially_ready", "not_ready", name="readiness_result", create_type=False)


def upgrade() -> None:
    op.create_table(
        "level_tests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("answers", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("level", user_level, nullable=True),
        sa.Column("energy_level", sa.SmallInteger(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("energy_level between 1 and 10", name="ck_level_tests_energy_level"),
    )
    op.create_index("ix_level_tests_user_created_at", "level_tests", ["user_id", "created_at"])

    # Readiness checks are replaced by retaking the test; their rows are dropped.
    op.drop_index("ix_readiness_checks_user_created_at", table_name="readiness_checks")
    op.drop_table("readiness_checks")
    readiness_result.drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    readiness_result.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "readiness_checks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_level", user_level, nullable=False),
        sa.Column("target_level", user_level, nullable=True),
        sa.Column("result", readiness_result, nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_readiness_checks_user_created_at", "readiness_checks", ["user_id", "created_at"])

    op.drop_index("ix_level_tests_user_created_at", table_name="level_tests")
    op.drop_table("level_tests")
