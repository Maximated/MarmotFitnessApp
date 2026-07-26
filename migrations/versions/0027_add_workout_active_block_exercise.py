"""track which exercise the active rest/duration countdown belongs to

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: Union[str, Sequence[str], None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workouts",
        sa.Column(
            "active_block_exercise_id",
            sa.Integer(),
            sa.ForeignKey("block_exercises.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_workouts_active_block_exercise_id", "workouts", ["active_block_exercise_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_workouts_active_block_exercise_id", table_name="workouts")
    op.drop_column("workouts", "active_block_exercise_id")
