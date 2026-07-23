"""add target_weight to block_exercises

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: Union[str, Sequence[str], None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "block_exercises", sa.Column("target_weight", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("block_exercises", "target_weight")
