"""workout sets must survive program/block-exercise deletion, like ratings do

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0028"
down_revision: Union[str, Sequence[str], None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workout_sets", sa.Column("pending_name", sa.String(), nullable=True))

    op.drop_constraint("workout_sets_block_exercise_id_fkey", "workout_sets", type_="foreignkey")
    op.create_foreign_key(
        "workout_sets_block_exercise_id_fkey",
        "workout_sets",
        "block_exercises",
        ["block_exercise_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Backfill the snapshot for existing catalog-less sets so they don't lose
    # their name if the block_exercise gets deleted later.
    op.execute(
        """
        UPDATE workout_sets
        SET pending_name = block_exercises.pending_name
        FROM block_exercises
        WHERE workout_sets.block_exercise_id = block_exercises.id
          AND workout_sets.exercise_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint("workout_sets_block_exercise_id_fkey", "workout_sets", type_="foreignkey")
    op.create_foreign_key(
        "workout_sets_block_exercise_id_fkey",
        "workout_sets",
        "block_exercises",
        ["block_exercise_id"],
        ["id"],
    )
    op.drop_column("workout_sets", "pending_name")
