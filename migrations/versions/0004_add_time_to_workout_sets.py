"""add time column to workout_sets

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workout_sets",
        sa.Column(
            "time", sa.Time(), nullable=False, server_default=sa.text("'00:00:00'")
        ),
    )
    op.alter_column("workout_sets", "time", server_default=None)


def downgrade() -> None:
    op.drop_column("workout_sets", "time")
