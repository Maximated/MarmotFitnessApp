"""create programs, day_templates, blocks, block_exercises tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "programs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("cycle_days", sa.Integer(), nullable=False),
    )
    op.create_index("ix_programs_user_id", "programs", ["user_id"])

    op.create_table(
        "day_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "program_id",
            sa.Integer(),
            sa.ForeignKey("programs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day_number", sa.Integer(), nullable=False),
    )
    op.create_index("ix_day_templates_program_id", "day_templates", ["program_id"])
    op.create_unique_constraint(
        "uq_day_templates_program_id_day_number",
        "day_templates",
        ["program_id", "day_number"],
    )

    op.create_table(
        "blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "day_template_id",
            sa.Integer(),
            sa.ForeignKey("day_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("muscle_group", sa.String(), nullable=True),
        sa.Column("variant", sa.String(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("num_exercises", sa.Integer(), nullable=False),
        sa.Column("rest_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "is_superset", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index("ix_blocks_day_template_id", "blocks", ["day_template_id"])

    op.create_table(
        "block_exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "block_id",
            sa.Integer(),
            sa.ForeignKey("blocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "exercise_id", sa.Integer(), sa.ForeignKey("exercises.id"), nullable=False
        ),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index("ix_block_exercises_block_id", "block_exercises", ["block_id"])
    op.create_index(
        "ix_block_exercises_exercise_id", "block_exercises", ["exercise_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_block_exercises_exercise_id", table_name="block_exercises")
    op.drop_index("ix_block_exercises_block_id", table_name="block_exercises")
    op.drop_table("block_exercises")

    op.drop_index("ix_blocks_day_template_id", table_name="blocks")
    op.drop_table("blocks")

    op.drop_constraint(
        "uq_day_templates_program_id_day_number",
        "day_templates",
        type_="unique",
    )
    op.drop_index("ix_day_templates_program_id", table_name="day_templates")
    op.drop_table("day_templates")

    op.drop_index("ix_programs_user_id", table_name="programs")
    op.drop_table("programs")
