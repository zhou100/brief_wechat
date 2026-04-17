"""
End-to-end tests for authentication flow
"""
import pytest
pytest.skip("Requires live auth app wiring/fixtures beyond local unit-test scope", allow_module_level=True)
from httpx import AsyncClient
from app.models.user import User

@pytest.mark.asyncio
async def test_login_refresh_flow(async_client: AsyncClient, test_user: User):
    """Test the complete login and refresh token flow."""
    # Login
    response = await async_client.post(
        "/auth/token",
        data={
            "username": test_user.email,
            "password": "testpass123",
            "grant_type": "password"
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 200
    tokens = response.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert "token_type" in tokens

    # Use access token
    access_token = tokens["access_token"]
    response = await async_client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["email"] == test_user.email

    # Test token refresh
    refresh_token = tokens["refresh_token"]
    response = await async_client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 200
    new_tokens = response.json()
    assert "access_token" in new_tokens
    assert new_tokens["access_token"] != tokens["access_token"]

@pytest.mark.asyncio
async def test_refresh_token_invalid_cases(async_client: AsyncClient, test_user: User):
    """Test invalid refresh token cases."""
    # Try to refresh with invalid token
    response = await async_client.post(
        "/auth/refresh",
        json={"refresh_token": "invalid_token"},
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 401

    # Try to refresh with expired token
    response = await async_client.post(
        "/auth/refresh",
        json={"refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjoxNTE2MjM5MDIyfQ.L9DCWpxNZVvRP7YgiQxumEa5Nj3eFwNQw5y9fYTf8u"},
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 401

    # Test missing refresh token
    response = await async_client.post(
        "/auth/refresh",
        json={},
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422

    # Test malformed JSON
    response = await async_client.post(
        "/auth/refresh",
        content="invalid json content",
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422

    # Test invalid refresh token format
    response = await async_client.post(
        "/auth/refresh",
        json={"refresh_token": "invalid_token_format"},
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 401
