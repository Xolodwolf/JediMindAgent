"""Exercises are evaluated, not performed: suggested / suitable / not_suitable.

Revision ID: 0004_exercise_fit
Revises: 0003_five_levels
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_exercise_fit"
down_revision: str | None = "0003_five_levels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _recreate_status_type(values: str, mapping_sql: str) -> None:
    # PostgreSQL cannot drop enum values, so the type is recreated and rows are mapped.
    op.execute("ALTER TABLE user_exercises ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE exercise_status RENAME TO exercise_status_old")
    op.execute(f"CREATE TYPE exercise_status AS ENUM ({values})")
    op.execute(f"ALTER TABLE user_exercises ALTER COLUMN status TYPE exercise_status USING ({mapping_sql})::exercise_status")
    op.execute("ALTER TABLE user_exercises ALTER COLUMN status SET DEFAULT 'suggested'")
    op.execute("DROP TYPE exercise_status_old")


def upgrade() -> None:
    # Everything the user took on becomes "suitable"; everything they declined becomes "not_suitable".
    _recreate_status_type(
        "'suggested', 'suitable', 'not_suitable'",
        """CASE status::text
            WHEN 'suggested' THEN 'suggested'
            WHEN 'accepted' THEN 'suitable'
            WHEN 'in_progress' THEN 'suitable'
            WHEN 'completed' THEN 'suitable'
            ELSE 'not_suitable'
        END""",
    )
    op.drop_column("user_exercises", "started_at")
    op.drop_column("user_exercises", "completed_at")


def downgrade() -> None:
    # Lossy: skipped and cancelled exercises cannot be told apart from not_suitable ones anymore.
    op.add_column("user_exercises", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_exercises", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    _recreate_status_type(
        "'suggested', 'accepted', 'in_progress', 'completed', 'skipped', 'not_suitable', 'cancelled'",
        "CASE status::text WHEN 'suitable' THEN 'accepted' ELSE status::text END",
    )
