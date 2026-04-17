"""
EntryMetadata — flexible key-value pairs extracted from an entry's content.
Examples: priority, time_spent, due_date, tags.
"""
import uuid
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from .base import Base


class EntryMetadata(Base):
    __tablename__ = "entry_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id = Column(
        UUID(as_uuid=True),
        ForeignKey("entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key = Column(String(100), nullable=False)   # e.g. 'priority', 'time_spent', 'tags'
    value = Column(JSONB, nullable=True)

    entry = relationship("Entry", back_populates="metadata_items")
