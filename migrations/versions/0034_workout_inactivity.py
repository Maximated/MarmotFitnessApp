"""track last activity on a workout, to auto-finish it after inactivity

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0034"
down_revision: Union[str, Sequence[str], None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workouts", sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "workouts", sa.Column("inactivity_prompt_sent_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("workouts", "inactivity_prompt_sent_at")
    op.drop_column("workouts", "last_activity_at")
