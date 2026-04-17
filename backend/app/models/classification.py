"""
EntryClassification — stores AI categorization results, separate from the entry itself.
Keeping this separate allows re-running classification without touching source data.
"""
import uuid
from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import relationship
from .base import Base
from .types import GUID


class EntryClassification(Base):
    __tablename__ = "entry_classifications"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    entry_id = Column(
        GUID(),
        ForeignKey("entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        # unique=True removed — one entry now produces N classifications
    )
    # EARNING | LEARNING | RELAXING | FAMILY | TODO | EXPERIMENT | REFLECTION | TIME_RECORD (legacy)
    category = Column(String(20), nullable=False)
    # The specific extracted activity text for this classification
    extracted_text = Column(Text, nullable=True)
    # 0-based insertion order; guarantees stable "primary category" = classifications[0]
    display_order = Column(Integer, nullable=False, default=0)
    # AI-estimated duration in minutes (nullable — null means "unknown")
    estimated_minutes = Column(Integer, nullable=True)
    confidence = Column(Float, nullable=True)
    model_version = Column(String(50), nullable=True)   # track which model produced this
    user_override = Column(Boolean, default=False)      # did user correct the AI?
    # Capture Inbox lifecycle: open (default), done, dismissed
    status = Column(String(20), nullable=False, server_default="open")
    # User-refined text that overrides extracted_text for display (null = use extracted_text)
    edited_text = Column(Text, nullable=True)
    classified_at = Column(DateTime(timezone=True), server_default=func.now())

    entry = relationship("Entry", back_populates="classifications")

    @property
    def display_text(self):
        """Edited text takes precedence over the original extracted text."""
        return self.edited_text if self.edited_text else self.extracted_text
