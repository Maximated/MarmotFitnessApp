"""subgrupo muscular (variante) del catálogo, para afinar ejercicios similares

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0031"
down_revision: Union[str, Sequence[str], None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# One-time backfill only -- keep this self-contained rather than importing
# scripts/exercise_data.py, which can change independently later without
# this migration needing to know. Any future refinement of the rules only
# affects new imports there; existing rows would need their own follow-up
# migration if they ever need to be reclassified.
def upgrade() -> None:
    op.add_column("exercises", sa.Column("variante", sa.String(), nullable=True))

    op.execute(
        """
        UPDATE exercises
        SET variante = 'bajo'
        WHERE target_muscle = 'pectorales' AND name ILIKE '%declinad%'
        """
    )
    op.execute(
        """
        UPDATE exercises
        SET variante = 'alto'
        WHERE target_muscle = 'pectorales' AND name ILIKE '%inclinad%'
        """
    )
    op.execute(
        """
        UPDATE exercises
        SET variante = 'vertical'
        WHERE target_muscle IN ('dorsales', 'espalda alta')
          AND (name ILIKE '%jalón%' OR name ILIKE '%jalon%' OR name ILIKE '%dominada%')
        """
    )
    op.execute(
        """
        UPDATE exercises
        SET variante = 'horizontal'
        WHERE target_muscle IN ('dorsales', 'espalda alta') AND name ILIKE '%remo%'
        """
    )


def downgrade() -> None:
    op.drop_column("exercises", "variante")
