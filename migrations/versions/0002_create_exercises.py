"""create exercises table

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("target_muscle", sa.String(), nullable=False),
        sa.Column("equipment", sa.String(), nullable=False),
        sa.Column("gif_url", sa.String(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_exercises_external_id", "exercises", ["external_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_exercises_external_id", table_name="exercises")
    op.drop_table("exercises")
