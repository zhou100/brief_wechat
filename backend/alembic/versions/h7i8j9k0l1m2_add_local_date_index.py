"""add index on (user_id, local_date)

Revision ID: h7i8j9k0l1m2
Revises: g6h7i8j9k0l1
Create Date: 2026-04-02 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "h7i8j9k0l1m2"
down_revision: Union[str, None] = "g6h7i8j9k0l1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_entries_user_id_local_date", "entries", ["user_id", "local_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_entries_user_id_local_date", table_name="entries")
