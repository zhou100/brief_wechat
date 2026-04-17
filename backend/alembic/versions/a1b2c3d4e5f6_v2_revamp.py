"""v2 revamp: entries pipeline, refresh tokens, gamification

Revision ID: a1b2c3d4e5f6
Revises: 65a8ae71f0d5
Create Date: 2026-03-23 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "52812e8c744e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── entries ───────────────────────────────────────────────────────────────
    op.create_table(
        "entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_audio_key", sa.String, nullable=True),
        sa.Column("transcript", sa.Text, nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_entries_user_id_created_at", "entries", ["user_id", "created_at"])

    # ── entry_classifications ─────────────────────────────────────────────────
    op.create_table(
        "entry_classifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entries.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("user_override", sa.Boolean, default=False),
        sa.Column("classified_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_entry_classifications_entry_id", "entry_classifications", ["entry_id"])

    # ── entry_metadata ────────────────────────────────────────────────────────
    op.create_table(
        "entry_metadata",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_entry_metadata_entry_id", "entry_metadata", ["entry_id"])

    # ── jobs ──────────────────────────────────────────────────────────────────
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", postgresql.ENUM("pending", "processing", "done", "failed", name="jobstatus"), nullable=False, server_default="pending"),
        sa.Column("step", sa.String(50), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_jobs_status_created_at", "jobs", ["status", "created_at"])
    op.create_index("ix_jobs_entry_id", "jobs", ["entry_id"])

    # ── refresh_tokens ────────────────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("jti", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    # ── user_events ───────────────────────────────────────────────────────────
    op.create_table(
        "user_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_user_events_user_id_type", "user_events", ["user_id", "event_type"])
    op.create_index("ix_user_events_user_id_occurred_at", "user_events", ["user_id", "occurred_at"])

    # ── user_stats ────────────────────────────────────────────────────────────
    op.create_table(
        "user_stats",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("total_entries", sa.Integer, nullable=False, server_default="0"),
        sa.Column("current_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("longest_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_minutes_logged", sa.Integer, nullable=False, server_default="0"),
        sa.Column("level", sa.Integer, nullable=False, server_default="1"),
        sa.Column("xp", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_stats")
    op.drop_index("ix_user_events_user_id_occurred_at", "user_events")
    op.drop_index("ix_user_events_user_id_type", "user_events")
    op.drop_table("user_events")
    op.drop_index("ix_refresh_tokens_user_id", "refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_jobs_entry_id", "jobs")
    op.drop_index("ix_jobs_status_created_at", "jobs")
    op.drop_table("jobs")
    op.execute("DROP TYPE IF EXISTS jobstatus")
    op.drop_index("ix_entry_metadata_entry_id", "entry_metadata")
    op.drop_table("entry_metadata")
    op.drop_index("ix_entry_classifications_entry_id", "entry_classifications")
    op.drop_table("entry_classifications")
    op.drop_index("ix_entries_user_id_created_at", "entries")
    op.drop_table("entries")
