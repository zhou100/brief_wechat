"""
E2E test configuration and fixtures
"""
import os
import pytest
import logging
import asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, Timeout
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from fastapi import Depends

from app.models.base import Base
from app.models.user import User
from app.db import get_db
from app.main import app
from app.utils.auth import get_password_hash, create_access_token

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# E2E Test database URL - using different port from unit tests
E2E_DATABASE_URL = os.getenv(
    "E2E_DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5433/time_logger_test_e2e"
)

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def e2e_engine():
    """Create test engine for e2e tests."""
    logger.info(f"Creating database engine with URL: {E2E_DATABASE_URL}")
    try:
        engine = create_async_engine(
            E2E_DATABASE_URL,
            echo=True,
            future=True,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            connect_args={
                "timeout": 10,  # Connection timeout in seconds
                "command_timeout": 10
            }
        )
        
        # Test connection
        async with engine.begin() as conn:
            logger.info("Testing database connection...")
            await conn.run_sync(lambda _: None)
            logger.info("Database connection successful")
        
        # Create all tables
        logger.info("Creating database tables...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
        
        yield engine
        
        # Cleanup after all tests
        logger.info("Cleaning up database...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
        logger.info("Database cleanup completed")
        
    except SQLAlchemyError as e:
        logger.error(f"Database error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in database setup: {str(e)}")
        raise

@pytest.fixture(scope="session")
async def e2e_session_factory(e2e_engine):
    """Create session factory for e2e tests."""
    try:
        return sessionmaker(
            bind=e2e_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False
        )
    except Exception as e:
        logger.error(f"Error creating session factory: {str(e)}")
        raise

@pytest.fixture(scope="function")
async def e2e_db(e2e_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Get a test database session."""
    try:
        async with e2e_session_factory() as session:
            logger.debug("Created new database session")
            try:
                yield session
            finally:
                logger.debug("Rolling back database session")
                await session.rollback()
                logger.debug("Closing database session")
                await session.close()
    except Exception as e:
        logger.error(f"Error in database session: {str(e)}")
        raise

@pytest.fixture
async def seed_test_data(e2e_db: AsyncSession):
    """Seed test data for e2e tests."""
    from app.utils.auth import get_password_hash
    
    try:
        logger.info("Seeding test data...")
        # Create test users
        test_user = User(
            email="test1@example.com",
            hashed_password=get_password_hash("password123"),
            is_active=True
        )
        e2e_db.add(test_user)
        await e2e_db.commit()
        await e2e_db.refresh(test_user)
        logger.info("Test data seeded successfully")
        
        yield test_user
        
        # Cleanup
        logger.info("Cleaning up test data...")
        await e2e_db.delete(test_user)
        await e2e_db.commit()
        logger.info("Test data cleanup completed")
        
    except Exception as e:
        logger.error(f"Error in test data setup: {str(e)}")
        raise

@pytest.fixture
async def test_user(e2e_db: AsyncSession) -> User:
    """Create a test user."""
    try:
        logger.info("Creating test user...")
        test_user = User(
            email="test@example.com",
            hashed_password=get_password_hash("testpassword"),
            is_active=True
        )
        e2e_db.add(test_user)
        await e2e_db.commit()
        await e2e_db.refresh(test_user)
        logger.info("Test user created successfully")

        yield test_user

        # Cleanup
        logger.info("Cleaning up test user...")
        await e2e_db.delete(test_user)
        await e2e_db.commit()
        logger.info("Test user cleanup completed")

    except Exception as e:
        logger.error(f"Error in test user setup: {str(e)}")
        raise

@pytest.fixture
def access_token(test_user: User) -> str:
    """Create an access token for the test user."""
    try:
        logger.info("Creating access token for test user...")
        token = create_access_token({"sub": test_user.email})
        logger.info("Access token created successfully")
        return token
    except Exception as e:
        logger.error(f"Error creating access token: {str(e)}")
        raise

@pytest.fixture
async def e2e_client(e2e_db, event_loop) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client with extended timeouts."""
    try:
        async def get_test_db():
            """Override database dependency for testing."""
            logger.debug("Using test database session")
            yield e2e_db
            logger.debug("Test database session complete")
            
        # Override the database dependency
        app.dependency_overrides[get_db] = get_test_db
        
        # Use base_url without scheme to avoid event loop issues
        timeout = Timeout(10.0, connect=5.0)
        async with AsyncClient(
            app=app,
            base_url="http://test",
            timeout=timeout
        ) as client:
            logger.debug("Created test client")
            yield client
        
        # Clear dependency overrides
        app.dependency_overrides.clear()
        logger.debug("Cleared dependency overrides")
    except Exception as e:
        logger.error(f"Error in test client setup: {str(e)}")
        raise
