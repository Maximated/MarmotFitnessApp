"""create workout_substitutions

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: Union[str, Sequence[str], None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workout_substitutions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workout_id",
            sa.Integer(),
            sa.ForeignKey("workouts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "block_exercise_id",
            sa.Integer(),
            sa.ForeignKey("block_exercises.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id"), nullable=False),
        sa.UniqueConstraint(
            "workout_id", "block_exercise_id", name="uq_workout_substitution"
        ),
    )
    op.create_index(
        "ix_workout_substitutions_workout_id", "workout_substitutions", ["workout_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_workout_substitutions_workout_id", table_name="workout_substitutions")
    op.drop_table("workout_substitutions")
