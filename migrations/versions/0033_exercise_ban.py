"""per-user exercise ban flag, and rating becomes optional (ban-only rows)

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0033"
down_revision: Union[str, Sequence[str], None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "exercise_ratings",
        sa.Column("banned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column(
        "exercise_ratings", "rating", existing_type=sa.Integer(), nullable=True
    )


def downgrade() -> None:
    op.alter_column(
        "exercise_ratings", "rating", existing_type=sa.Integer(), nullable=False
    )
    op.drop_column("exercise_ratings", "banned")
