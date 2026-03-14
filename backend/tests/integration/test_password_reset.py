import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_can_reset_user_password(client: AsyncClient, admin_user, regular_user, admin_token):
    resp = await client.post(f"/api/users/{regular_user.id}/reset-password", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "new_password": "newpassword456",
    })
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_non_admin_cannot_reset_password(client: AsyncClient, admin_user, regular_user, user_token):
    resp = await client.post(f"/api/users/{admin_user.id}/reset-password", headers={
        "Authorization": f"Bearer {user_token}",
    }, json={
        "new_password": "hackedpassword",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reset_password_nonexistent_user(client: AsyncClient, admin_user, admin_token):
    fake_id = uuid.uuid4()
    resp = await client.post(f"/api/users/{fake_id}/reset-password", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "new_password": "doesntmatter",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_login_with_new_password_after_reset(client: AsyncClient, admin_user, regular_user, admin_token):
    new_password = "resetpassword789"

    # Reset the password
    resp = await client.post(f"/api/users/{regular_user.id}/reset-password", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "new_password": new_password,
    })
    assert resp.status_code == 204

    # Login with old password should fail
    resp = await client.post("/api/auth/login", json={
        "email": "user@test.local",
        "password": "user123",
    })
    assert resp.status_code == 401

    # Login with new password should succeed
    resp = await client.post("/api/auth/login", json={
        "email": "user@test.local",
        "password": new_password,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
