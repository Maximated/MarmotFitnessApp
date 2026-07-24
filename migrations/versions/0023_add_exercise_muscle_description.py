"""add exercises.muscle_description

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: Union[str, Sequence[str], None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "exercises", sa.Column("muscle_description", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("exercises", "muscle_description")
