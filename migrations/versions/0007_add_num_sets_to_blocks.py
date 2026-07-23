"""add num_sets to blocks

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "blocks",
        sa.Column("num_sets", sa.Integer(), nullable=False, server_default="3"),
    )
    op.alter_column("blocks", "num_sets", server_default=None)


def downgrade() -> None:
    op.drop_column("blocks", "num_sets")
