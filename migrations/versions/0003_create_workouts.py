"""create workouts and workout_sets tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_workouts_user_id", "workouts", ["user_id"])

    op.create_table(
        "workout_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workout_id",
            sa.Integer(),
            sa.ForeignKey("workouts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "exercise_id",
            sa.Integer(),
            sa.ForeignKey("exercises.id"),
            nullable=False,
        ),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False),
    )
    op.create_index("ix_workout_sets_workout_id", "workout_sets", ["workout_id"])
    op.create_index("ix_workout_sets_exercise_id", "workout_sets", ["exercise_id"])


def downgrade() -> None:
    op.drop_index("ix_workout_sets_exercise_id", table_name="workout_sets")
    op.drop_index("ix_workout_sets_workout_id", table_name="workout_sets")
    op.drop_table("workout_sets")
    op.drop_index("ix_workouts_user_id", table_name="workouts")
    op.drop_table("workouts")
