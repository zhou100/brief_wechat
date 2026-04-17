"""
RefreshToken — persisted refresh tokens enabling proper session revocation.
Each refresh rotates the token (old jti revoked, new one issued).
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, func, Index
from sqlalchemy.orm import relationship
from .base import Base
from .types import GUID


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    jti = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    user_agent = Column(String(500), nullable=True)

    user = relationship("User", back_populates="refresh_tokens")

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    __table_args__ = (
        Index("ix_refresh_tokens_user_id", "user_id"),
    )
