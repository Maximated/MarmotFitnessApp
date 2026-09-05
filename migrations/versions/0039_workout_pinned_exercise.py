"""persist the pinned (slot, exercise) pair on the workout itself, so it
survives fresh navigation (a tapped push notification, closing and
reopening the app) instead of living only in the page's URL

Revision ID: 0039
Revises: 0038
Create Date: 2026-09-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0039"
down_revision: Union[str, Sequence[str], None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workouts",
        sa.Column(
            "pinned_block_exercise_id",
            sa.Integer(),
            sa.ForeignKey("block_exercises.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "workouts",
        sa.Column(
            "pinned_exercise_id",
            sa.Integer(),
            sa.ForeignKey("exercises.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("workouts", "pinned_exercise_id")
    op.drop_column("workouts", "pinned_block_exercise_id")
