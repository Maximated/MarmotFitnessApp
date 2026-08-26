"""public share links for a whole program or a single day

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0038"
down_revision: Union[str, Sequence[str], None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shared_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "program_id", sa.Integer(), sa.ForeignKey("programs.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column(
            "day_template_id",
            sa.Integer(),
            sa.ForeignKey("day_templates.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "(program_id is not null) != (day_template_id is not null)",
            name="ck_shared_link_exactly_one_scope",
        ),
    )
    op.create_index("ix_shared_links_token", "shared_links", ["token"], unique=True)
    op.create_index("ix_shared_links_user_id", "shared_links", ["user_id"])
    op.create_index("ix_shared_links_program_id", "shared_links", ["program_id"])
    op.create_index("ix_shared_links_day_template_id", "shared_links", ["day_template_id"])


def downgrade() -> None:
    op.drop_index("ix_shared_links_day_template_id", table_name="shared_links")
    op.drop_index("ix_shared_links_program_id", table_name="shared_links")
    op.drop_index("ix_shared_links_user_id", table_name="shared_links")
    op.drop_index("ix_shared_links_token", table_name="shared_links")
    op.drop_table("shared_links")
