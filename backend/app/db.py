"""
Database configuration and async session management.
"""
import os
import ssl as _ssl
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger(__name__)

# Select URL based on test mode (set before importing settings to avoid caching issues)
if os.getenv("TEST_MODE") == "true":
    DATABASE_URL = os.getenv(
        "TEST_DATABASE_URL",
        "sqlite+aiosqlite:///./test.db",
    )
    logger.info("Running in TEST mode")
else:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "mysql+aiomysql://root:password@localhost:3306/brief_wechat",
    )

_echo = os.getenv("DB_ECHO", "false").lower() == "true"
_is_production = os.getenv("ENVIRONMENT") == "production"

# Supabase requires SSL — create an SSL context for production
_connect_args = {}
if _is_production and DATABASE_URL.startswith("postgresql"):
    ssl_ctx = _ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = _ssl.CERT_NONE
    _connect_args["ssl"] = ssl_ctx

engine = create_async_engine(
    DATABASE_URL,
    echo=_echo,
    future=True,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=20,
    pool_timeout=30,
    connect_args=_connect_args,
)

async_session = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    from app.models import Base as ModelBase  # noqa: F401 — ensures all models are registered
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: ModelBase.metadata.create_all(c, checkfirst=True))
    logger.info("Database initialized")
