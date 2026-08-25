"""mark a workout as a manually-picked session (recover/repeat a day
without moving that program's schedule)

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0037"
down_revision: Union[str, Sequence[str], None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workouts",
        sa.Column("is_manual_session", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("workouts", "is_manual_session")
