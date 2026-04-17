from sqlalchemy import Column, Integer, String, Boolean, select
from sqlalchemy.orm import relationship
from .base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    google_id = Column(String, unique=True, nullable=True, index=True)
    auth_provider = Column(String(20), default="email")  # "email" | "google" | "supabase"
    # Supabase Auth user UUID — set when using Supabase Auth
    supabase_id = Column(String, unique=True, nullable=True, index=True)
    wechat_openid = Column(String, unique=True, nullable=True, index=True)
    wechat_unionid = Column(String, unique=True, nullable=True, index=True)

    # Relationships
    entries = relationship("Entry", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    @classmethod
    async def get_by_email(cls, db, email: str):
        result = await db.execute(select(cls).filter(cls.email == email))
        return result.scalar_one_or_none()

    @classmethod
    async def get_by_id(cls, db, user_id: int):
        result = await db.execute(select(cls).filter(cls.id == user_id))
        return result.scalar_one_or_none()

    @classmethod
    async def get_by_google_id(cls, db, google_id: str):
        result = await db.execute(select(cls).filter(cls.google_id == google_id))
        return result.scalar_one_or_none()

    @classmethod
    async def get_by_supabase_id(cls, db, supabase_id: str):
        result = await db.execute(select(cls).filter(cls.supabase_id == supabase_id))
        return result.scalar_one_or_none()

    @classmethod
    async def get_by_wechat_openid(cls, db, openid: str):
        result = await db.execute(select(cls).filter(cls.wechat_openid == openid))
        return result.scalar_one_or_none()
