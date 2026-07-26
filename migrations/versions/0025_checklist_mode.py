"""drop blocks.note, add workout_checklist_items

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: Union[str, Sequence[str], None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("blocks", "note")

    op.create_table(
        "workout_checklist_items",
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
        sa.Column(
            "completed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("workout_id", "block_exercise_id", name="uq_workout_checklist_item"),
    )
    op.create_index(
        "ix_workout_checklist_items_workout_id",
        "workout_checklist_items",
        ["workout_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_workout_checklist_items_workout_id", table_name="workout_checklist_items")
    op.drop_table("workout_checklist_items")
    op.add_column("blocks", sa.Column("note", sa.Text(), nullable=True))
