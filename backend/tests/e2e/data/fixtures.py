"""
Test data fixtures for e2e tests
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.utils.auth import get_password_hash

@pytest.fixture
async def seed_test_data(e2e_db: AsyncSession):
    """Seed basic test data for e2e tests."""
    # Create test users
    test_users = [
        User(
            email="test1@example.com",
            hashed_password=get_password_hash("password123"),
            is_active=True
        ),
        User(
            email="test2@example.com",
            hashed_password=get_password_hash("password123"),
            is_active=True
        )
    ]
    
    for user in test_users:
        e2e_db.add(user)
    await e2e_db.commit()
    
    yield
    
    # Cleanup
    await e2e_db.execute(User.__table__.delete())
    await e2e_db.commit()
