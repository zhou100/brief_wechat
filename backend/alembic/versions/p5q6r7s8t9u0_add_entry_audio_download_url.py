"""add entry audio download url

Revision ID: p5q6r7s8t9u0
Revises: o4p5q6r7s8t9
Create Date: 2026-04-16 22:20:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "p5q6r7s8t9u0"
down_revision = "o4p5q6r7s8t9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("entries", sa.Column("raw_audio_download_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("entries", "raw_audio_download_url")
