"""
Notification model — persisted events for Supabase Realtime delivery.

The worker writes rows here after processing; Supabase Realtime pushes
INSERT events to subscribed frontend clients via Postgres changes.
"""
import uuid
from sqlalchemy import Column, Integer, ForeignKey, DateTime, String, Text, func
from .base import Base
from .types import GUID


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)  # "entry.classified" | "entry.failed"
    payload_json = Column(Text, nullable=False)       # JSON blob with entry_id, transcript, categories, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
