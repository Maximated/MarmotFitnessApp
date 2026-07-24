"""add exercise_aliases, blocks.note, nullable block_exercises.exercise_id + pending_name

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: Union[str, Sequence[str], None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exercise_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("raw_name", sa.String(), nullable=False),
        sa.Column("normalized_name", sa.String(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_exercise_aliases_exercise_id", "exercise_aliases", ["exercise_id"]
    )
    op.create_index(
        "ix_exercise_aliases_normalized_name",
        "exercise_aliases",
        ["normalized_name"],
        unique=True,
    )

    op.add_column("blocks", sa.Column("note", sa.Text(), nullable=True))

    op.add_column("block_exercises", sa.Column("pending_name", sa.String(), nullable=True))
    op.alter_column("block_exercises", "exercise_id", nullable=True)


def downgrade() -> None:
    op.alter_column("block_exercises", "exercise_id", nullable=False)
    op.drop_column("block_exercises", "pending_name")

    op.drop_column("blocks", "note")

    op.drop_index("ix_exercise_aliases_normalized_name", table_name="exercise_aliases")
    op.drop_index("ix_exercise_aliases_exercise_id", table_name="exercise_aliases")
    op.drop_table("exercise_aliases")
