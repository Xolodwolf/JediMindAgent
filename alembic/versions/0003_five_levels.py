"""Extend user_level enum to five levels.

Revision ID: 0003_five_levels
Revises: 0002_product_schema
Create Date: 2026-09-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_five_levels"
down_revision: str | None = "0002_product_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEVEL_COLUMNS = (
    ("user_states", "level"),
    ("user_status_logs", "level"),
    ("user_exercises", "level"),
    ("readiness_checks", "from_level"),
    ("readiness_checks", "target_level"),
)


def upgrade() -> None:
    # Adding values keeps existing rows intact; the new values are not used inside this migration.
    op.execute("ALTER TYPE user_level ADD VALUE IF NOT EXISTS 'level_4'")
    op.execute("ALTER TYPE user_level ADD VALUE IF NOT EXISTS 'level_5'")


def downgrade() -> None:
    # PostgreSQL cannot drop enum values, so the type is recreated. Levels 4-5 collapse into level 3.
    for table, column in LEVEL_COLUMNS:
        op.execute(f"UPDATE {table} SET {column} = 'level_3' WHERE {column} IN ('level_4', 'level_5')")

    op.execute("ALTER TABLE user_states ALTER COLUMN level DROP DEFAULT")
    op.execute("ALTER TYPE user_level RENAME TO user_level_old")
    op.execute("CREATE TYPE user_level AS ENUM ('unknown', 'level_1', 'level_2', 'level_3')")
    for table, column in LEVEL_COLUMNS:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE user_level USING {column}::text::user_level")
    op.execute("ALTER TABLE user_states ALTER COLUMN level SET DEFAULT 'unknown'")
    op.execute("DROP TYPE user_level_old")
