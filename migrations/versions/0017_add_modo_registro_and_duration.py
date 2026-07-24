"""add modo_registro/duracion_segundos to block_exercises; duration_seconds + nullable reps to workout_sets

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: Union[str, Sequence[str], None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "block_exercises",
        sa.Column(
            "modo_registro", sa.String(), nullable=False, server_default=sa.text("'series'")
        ),
    )
    op.add_column("block_exercises", sa.Column("duracion_segundos", sa.Integer(), nullable=True))

    op.add_column("workout_sets", sa.Column("duration_seconds", sa.Integer(), nullable=True))
    op.alter_column("workout_sets", "reps", nullable=True)


def downgrade() -> None:
    op.alter_column("workout_sets", "reps", nullable=False)
    op.drop_column("workout_sets", "duration_seconds")

    op.drop_column("block_exercises", "duracion_segundos")
    op.drop_column("block_exercises", "modo_registro")
