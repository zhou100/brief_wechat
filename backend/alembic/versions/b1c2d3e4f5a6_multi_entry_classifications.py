"""multi-entry classifications: drop unique, add extracted_text + display_order

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-03-23 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the UNIQUE constraint on entry_id so one entry can have N classifications.
    # PostgreSQL names inline unique constraints as {table}_{column}_key by default.
    op.drop_constraint(
        "entry_classifications_entry_id_key",
        "entry_classifications",
        type_="unique",
    )

    # Add extracted_text: the specific activity text for this classification.
    op.add_column(
        "entry_classifications",
        sa.Column("extracted_text", sa.Text, nullable=True),
    )

    # Add display_order: explicit insertion order (0-based) so we can guarantee
    # "first classification = primary category" without relying on UUID or timestamp.
    op.add_column(
        "entry_classifications",
        sa.Column(
            "display_order",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("entry_classifications", "display_order")
    op.drop_column("entry_classifications", "extracted_text")
    op.create_unique_constraint(
        "entry_classifications_entry_id_key",
        "entry_classifications",
        ["entry_id"],
    )
