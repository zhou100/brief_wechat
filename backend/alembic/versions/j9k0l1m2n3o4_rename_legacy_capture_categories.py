"""rename legacy capture categories to experiment/reflection

Revision ID: j9k0l1m2n3o4
Revises: i8j9k0l1m2n3
Create Date: 2026-04-07 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "j9k0l1m2n3o4"
down_revision: Union[str, None] = "i8j9k0l1m2n3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backfill legacy capture names so existing inbox items match the new
    # classifier/UI vocabulary.
    op.execute(
        """
        UPDATE entry_classifications
        SET category = 'EXPERIMENT'
        WHERE category = 'IDEA'
        """
    )
    op.execute(
        """
        UPDATE entry_classifications
        SET category = 'REFLECTION'
        WHERE category = 'THOUGHT'
        """
    )


def downgrade() -> None:
    # Best-effort reversal of the semantic rename. This treats all current
    # EXPERIMENT/REFLECTION rows as legacy rows, which is acceptable only when
    # downgrading the whole feature set.
    op.execute(
        """
        UPDATE entry_classifications
        SET category = 'IDEA'
        WHERE category = 'EXPERIMENT'
        """
    )
    op.execute(
        """
        UPDATE entry_classifications
        SET category = 'THOUGHT'
        WHERE category = 'REFLECTION'
        """
    )
