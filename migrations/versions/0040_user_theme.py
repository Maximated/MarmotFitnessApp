"""per-user theme override, so someone can pick light mode explicitly
instead of only ever following the OS's prefers-color-scheme

Revision ID: 0040
Revises: 0039
Create Date: 2026-09-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0040"
down_revision: Union[str, Sequence[str], None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("theme", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "theme")
