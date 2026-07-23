"""move superset to block_exercises (per pair), make blocks.num_sets nullable

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("blocks", "is_superset")
    op.alter_column("blocks", "num_sets", existing_type=sa.Integer(), nullable=True)
    op.add_column(
        "block_exercises",
        sa.Column(
            "is_superset_with_next",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("block_exercises", "is_superset_with_next")
    op.alter_column("blocks", "num_sets", existing_type=sa.Integer(), nullable=False)
    op.add_column(
        "blocks",
        sa.Column("is_superset", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
