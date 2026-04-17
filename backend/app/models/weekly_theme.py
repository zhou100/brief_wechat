"""
WeeklyTheme — long-term patterns/learnings extracted from weekly reviews.

Themes persist across weeks and are fuzzy-matched for dedup. Used to:
- Surface recurring patterns to the user on the main page (theme chips)
- Inject prior themes into the next weekly review prompt for continuity
"""
import uuid
from sqlalchemy import (
    Column, String, Integer, ForeignKey, DateTime, Date, Text, func, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import Base


class WeeklyTheme(Base):
    __tablename__ = "weekly_themes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    polarity = Column(String(20), nullable=False, default="neutral")  # positive | negative | neutral
    category = Column(String(50), nullable=True)  # EARNING | LEARNING | RELAXING | FAMILY | other

    first_seen = Column(Date, nullable=False)
    last_seen = Column(Date, nullable=False)
    occurrences = Column(Integer, nullable=False, default=1)

    # active | pinned | dismissed | resolved
    status = Column(String(20), nullable=False, default="active")
    user_note = Column(Text, nullable=True)

    # evidence: list of {audit_date, snippet} pointing back to weekly reviews
    evidence = Column(JSONB, nullable=False, default=list)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_weekly_themes_user_status", "user_id", "status"),
        Index("ix_weekly_themes_user_last_seen", "user_id", "last_seen"),
    )
