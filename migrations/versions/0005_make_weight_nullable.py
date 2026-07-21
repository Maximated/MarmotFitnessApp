"""make workout_sets.weight nullable

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("workout_sets", "weight", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    op.alter_column("workout_sets", "weight", existing_type=sa.Float(), nullable=False)
