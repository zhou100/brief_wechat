"""add capture status + edited_text to entry_classifications

Revision ID: i8j9k0l1m2n3
Revises: h7i8j9k0l1m2
Create Date: 2026-04-05 23:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "i8j9k0l1m2n3"
down_revision: Union[str, None] = "h7i8j9k0l1m2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "entry_classifications",
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
    )
    op.add_column(
        "entry_classifications",
        sa.Column("edited_text", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_classifications_category_status",
        "entry_classifications",
        ["category", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_classifications_category_status", table_name="entry_classifications")
    op.drop_column("entry_classifications", "edited_text")
    op.drop_column("entry_classifications", "status")
