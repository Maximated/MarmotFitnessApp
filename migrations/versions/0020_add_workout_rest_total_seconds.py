"""add workouts.rest_total_seconds

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: Union[str, Sequence[str], None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workouts", sa.Column("rest_total_seconds", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("workouts", "rest_total_seconds")
