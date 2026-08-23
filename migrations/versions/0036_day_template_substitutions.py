"""allow a substitution to be scoped to a DayTemplate instead of a Workout,
so a future day can be "prepared" (exercises swapped) before it's started

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0036"
down_revision: Union[str, Sequence[str], None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "workout_substitutions", "workout_id", existing_type=sa.Integer(), nullable=True
    )
    op.add_column(
        "workout_substitutions", sa.Column("day_template_id", sa.Integer(), nullable=True)
    )
    op.create_index(
        op.f("ix_workout_substitutions_day_template_id"),
        "workout_substitutions",
        ["day_template_id"],
    )
    op.create_foreign_key(
        "fk_workout_substitutions_day_template_id",
        "workout_substitutions",
        "day_templates",
        ["day_template_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_day_template_substitution",
        "workout_substitutions",
        ["day_template_id", "block_exercise_id"],
    )
    op.create_check_constraint(
        "ck_workout_substitution_exactly_one_scope",
        "workout_substitutions",
        "(workout_id is not null) != (day_template_id is not null)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_workout_substitution_exactly_one_scope", "workout_substitutions", type_="check"
    )
    op.drop_constraint(
        "uq_day_template_substitution", "workout_substitutions", type_="unique"
    )
    op.drop_constraint(
        "fk_workout_substitutions_day_template_id", "workout_substitutions", type_="foreignkey"
    )
    op.drop_index(
        op.f("ix_workout_substitutions_day_template_id"), table_name="workout_substitutions"
    )
    op.drop_column("workout_substitutions", "day_template_id")
    op.alter_column(
        "workout_substitutions", "workout_id", existing_type=sa.Integer(), nullable=False
    )
