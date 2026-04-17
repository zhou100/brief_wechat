"""
End-to-end tests for user functionality
"""
import pytest
pytest.skip("Legacy users e2e test uses removed fixtures/routes; auth flow is covered elsewhere", allow_module_level=True)
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.schemas.user import UserResponse

logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_get_current_user(auth_async_client: AsyncClient, test_user: User):
    """Test getting current user information."""
    logger.info("Testing get current user info")
    response = await auth_async_client.get("/users/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email
    assert data["id"] == test_user.id
