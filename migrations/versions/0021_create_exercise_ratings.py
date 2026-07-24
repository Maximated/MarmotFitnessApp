"""create exercise_ratings

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: Union[str, Sequence[str], None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exercise_ratings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "exercise_id", name="uq_exercise_rating_user_exercise"),
    )
    op.create_index(
        "ix_exercise_ratings_user_id", "exercise_ratings", ["user_id"]
    )
    op.create_index(
        "ix_exercise_ratings_exercise_id", "exercise_ratings", ["exercise_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_exercise_ratings_exercise_id", table_name="exercise_ratings")
    op.drop_index("ix_exercise_ratings_user_id", table_name="exercise_ratings")
    op.drop_table("exercise_ratings")
