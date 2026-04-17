"""
Job queue model — drives the async audio processing pipeline.
Uses SELECT FOR UPDATE SKIP LOCKED for worker coordination.
"""
import enum
import uuid
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Text, func, Index
from sqlalchemy.orm import relationship
from .base import Base
from .types import GUID


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    entry_id = Column(
        GUID(), ForeignKey("entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), default=JobStatus.PENDING.value, nullable=False, index=True)
    step = Column(String(50), nullable=True)    # "queued" | "transcribing" | "classifying" | "complete"
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    entry = relationship("Entry", back_populates="jobs")

    __table_args__ = (
        Index("ix_jobs_status_created_at", "status", "created_at"),
    )
