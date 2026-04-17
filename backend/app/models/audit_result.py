"""
AuditResult — persisted AI audit output, cached per user + date + type.
Invalidated (is_stale=True) when new entries arrive for the same date.
"""
import uuid
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, DateTime, Date, Text, func, Index
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class AuditResult(Base):
    __tablename__ = "audit_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    audit_date = Column(Date, nullable=False)
    audit_type = Column(String(20), nullable=False, default="daily")  # "daily" | "weekly"
    entries_count = Column(Integer, nullable=False)
    breakdown_json = Column(Text, nullable=True)  # JSON-serialized breakdown dict
    audit_text = Column(Text, nullable=True)
    report_json = Column(Text, nullable=True)  # structured 4-section weekly report JSON
    is_stale = Column(Boolean, nullable=False, default=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_audit_results_user_date_type", "user_id", "audit_date", "audit_type"),
    )
