"""split block_exercises.reps into reps_min/reps_max

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: Union[str, Sequence[str], None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("block_exercises", sa.Column("reps_min", sa.Integer(), nullable=True))
    op.add_column("block_exercises", sa.Column("reps_max", sa.Integer(), nullable=True))
    op.execute("UPDATE block_exercises SET reps_min = reps, reps_max = reps")
    op.drop_column("block_exercises", "reps")


def downgrade() -> None:
    op.add_column("block_exercises", sa.Column("reps", sa.Integer(), nullable=True))
    op.execute("UPDATE block_exercises SET reps = reps_min")
    op.drop_column("block_exercises", "reps_max")
    op.drop_column("block_exercises", "reps_min")
