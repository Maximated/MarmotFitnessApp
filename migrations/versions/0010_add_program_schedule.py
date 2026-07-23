"""add program scheduling fields and link workouts to program days

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("programs", sa.Column("current_day_number", sa.Integer(), nullable=True))
    op.add_column("programs", sa.Column("next_due_date", sa.Date(), nullable=True))

    op.add_column(
        "workouts",
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("programs.id"), nullable=True),
    )
    op.add_column(
        "workouts",
        sa.Column(
            "day_template_id", sa.Integer(), sa.ForeignKey("day_templates.id"), nullable=True
        ),
    )
    op.create_index("ix_workouts_program_id", "workouts", ["program_id"])


def downgrade() -> None:
    op.drop_index("ix_workouts_program_id", table_name="workouts")
    op.drop_column("workouts", "day_template_id")
    op.drop_column("workouts", "program_id")
    op.drop_column("programs", "next_due_date")
    op.drop_column("programs", "current_day_number")
