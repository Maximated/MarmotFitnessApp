"""add programs.is_active and day_templates.subtitle

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "programs",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("day_templates", sa.Column("subtitle", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("day_templates", "subtitle")
    op.drop_column("programs", "is_active")
