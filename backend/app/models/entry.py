"""
Entry model — replaces the old Audio model.
Stores the core content unit: a recorded audio clip + its transcript.
"""
import uuid
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Date, Text, func, Index
from sqlalchemy.orm import relationship
from .base import Base
from .types import GUID


class Entry(Base):
    __tablename__ = "entries"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    raw_audio_key = Column(String(1024), nullable=True)       # object storage key (MinIO/S3)
    transcript = Column(Text, nullable=True)            # filled by worker after Whisper
    recorded_at = Column(DateTime(timezone=True), nullable=True)   # client-reported time
    duration_seconds = Column(Integer, nullable=True)
    local_date = Column(Date, nullable=True)              # user's local calendar date
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="entries")
    classifications = relationship(
        "EntryClassification",
        back_populates="entry",
        uselist=True,
        cascade="all, delete-orphan",
        order_by="EntryClassification.display_order",
    )
    metadata_items = relationship(
        "EntryMetadata", back_populates="entry", cascade="all, delete-orphan"
    )
    jobs = relationship("Job", back_populates="entry", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_entries_user_id_created_at", "user_id", "created_at"),
        Index("ix_entries_user_id_local_date", "user_id", "local_date"),
    )
