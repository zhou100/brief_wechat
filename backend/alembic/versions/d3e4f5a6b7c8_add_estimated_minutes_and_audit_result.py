"""add estimated_minutes to entry_classifications and audit_results table

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-03-25 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add estimated_minutes to entry_classifications
    op.add_column(
        "entry_classifications",
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
    )

    # Create audit_results table for persisted audits
    op.create_table(
        "audit_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audit_date", sa.Date(), nullable=False),
        sa.Column("audit_type", sa.String(20), nullable=False, server_default="daily"),
        sa.Column("entries_count", sa.Integer(), nullable=False),
        sa.Column("breakdown_json", sa.Text(), nullable=True),
        sa.Column("audit_text", sa.Text(), nullable=True),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_results_user_date_type", "audit_results", ["user_id", "audit_date", "audit_type"])


def downgrade() -> None:
    op.drop_index("ix_audit_results_user_date_type", table_name="audit_results")
    op.drop_table("audit_results")
    op.drop_column("entry_classifications", "estimated_minutes")
