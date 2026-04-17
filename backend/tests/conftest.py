"""Test configuration and fixtures."""
import os
import pytest
import logging
import asyncio
from typing import AsyncGenerator, Dict
from httpx import AsyncClient, ASGITransport
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.settings import get_settings
from app.main import app
from app.models import Base
from app.models.user import User
from app.schemas.user import UserResponse
from app.utils.auth import create_access_token, get_password_hash

settings = get_settings()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test database URL
TEST_DATABASE_URL = settings.TEST_DATABASE_URL or "postgresql+asyncpg://postgres:postgres@localhost:5433/time_logger_test"

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def engine():
    """Create a test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=True
    )
    yield engine
    await engine.dispose()

@pytest.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Get a test database session."""
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Test database initialized")

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        logger.info("Test database cleaned up")

@pytest.fixture
def app_with_db(db_session):
    """Get the FastAPI app with test database session."""
    app.state.db = db_session
    return app

@pytest.fixture
def client(app_with_db) -> AsyncClient:
    """Create a test client for the app."""
    return AsyncClient(
        transport=ASGITransport(app=app_with_db),
        base_url="http://testserver",
        follow_redirects=True
    )

@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        email="test@example.com",
        hashed_password=get_password_hash("password123"),
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest.fixture
def auth_headers(test_user: User) -> Dict[str, str]:
    """Get authentication headers for test user."""
    access_token = create_access_token(data={"sub": test_user.email})
    return {"Authorization": f"Bearer {access_token}"}

@pytest.fixture
def auth_client(client: AsyncClient, auth_headers: Dict[str, str]) -> AsyncClient:
    """Get an authenticated test client."""
    client.headers.update(auth_headers)
    return client

# Override database dependency for testing
async def override_get_db():
    """Override get_db dependency for testing."""
    try:
        db = app.state.db
        yield db
    finally:
        await db.close()
