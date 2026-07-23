"""make workouts.program_id/day_template_id SET NULL on delete

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("workouts_program_id_fkey", "workouts", type_="foreignkey")
    op.create_foreign_key(
        "workouts_program_id_fkey",
        "workouts",
        "programs",
        ["program_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint("workouts_day_template_id_fkey", "workouts", type_="foreignkey")
    op.create_foreign_key(
        "workouts_day_template_id_fkey",
        "workouts",
        "day_templates",
        ["day_template_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("workouts_day_template_id_fkey", "workouts", type_="foreignkey")
    op.create_foreign_key(
        "workouts_day_template_id_fkey", "workouts", "day_templates", ["day_template_id"], ["id"]
    )
    op.drop_constraint("workouts_program_id_fkey", "workouts", type_="foreignkey")
    op.create_foreign_key(
        "workouts_program_id_fkey", "workouts", "programs", ["program_id"], ["id"]
    )
