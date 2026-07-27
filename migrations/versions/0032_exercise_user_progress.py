"""per-user auto-progressing target weight per exercise

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0032"
down_revision: Union[str, Sequence[str], None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exercise_user_progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "exercise_id",
            sa.Integer(),
            sa.ForeignKey("exercises.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("current_weight", sa.Float(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "exercise_id", name="uq_exercise_user_progress_user_exercise"
        ),
    )
    op.create_index(
        "ix_exercise_user_progress_user_id", "exercise_user_progress", ["user_id"]
    )
    op.create_index(
        "ix_exercise_user_progress_exercise_id", "exercise_user_progress", ["exercise_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_exercise_user_progress_exercise_id", table_name="exercise_user_progress")
    op.drop_index("ix_exercise_user_progress_user_id", table_name="exercise_user_progress")
    op.drop_table("exercise_user_progress")
