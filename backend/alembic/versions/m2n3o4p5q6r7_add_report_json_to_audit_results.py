"""add report_json to audit_results

Revision ID: m2n3o4p5q6r7
Revises: l1m2n3o4p5q6
Create Date: 2026-04-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "m2n3o4p5q6r7"
down_revision = "l1m2n3o4p5q6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_results", sa.Column("report_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_results", "report_json")
