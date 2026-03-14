import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_user_can_change_own_password(client: AsyncClient, regular_user, user_token):
    resp = await client.post("/api/auth/me/password", headers={
        "Authorization": f"Bearer {user_token}",
    }, json={
        "current_password": "user123",
        "new_password": "newpassword456",
    })
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_change_password_wrong_current_password(client: AsyncClient, regular_user, user_token):
    resp = await client.post("/api/auth/me/password", headers={
        "Authorization": f"Bearer {user_token}",
    }, json={
        "current_password": "wrongpassword",
        "new_password": "newpassword456",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_with_new_password_after_change(client: AsyncClient, regular_user, user_token):
    new_password = "changedpassword789"

    resp = await client.post("/api/auth/me/password", headers={
        "Authorization": f"Bearer {user_token}",
    }, json={
        "current_password": "user123",
        "new_password": new_password,
    })
    assert resp.status_code == 204

    # Old password should fail
    resp = await client.post("/api/auth/login", json={
        "email": "user@test.local",
        "password": "user123",
    })
    assert resp.status_code == 401

    # New password should work
    resp = await client.post("/api/auth/login", json={
        "email": "user@test.local",
        "password": new_password,
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_unauthenticated_cannot_change_password(client: AsyncClient):
    resp = await client.post("/api/auth/me/password", json={
        "current_password": "anything",
        "new_password": "anything",
    })
    assert resp.status_code == 401
