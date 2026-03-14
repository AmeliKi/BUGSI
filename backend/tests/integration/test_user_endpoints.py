import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_users_as_admin(client: AsyncClient, admin_user, admin_token):
    resp = await client.get("/api/users", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_list_users_as_regular_user_forbidden(client: AsyncClient, regular_user, user_token):
    resp = await client.get("/api/users", headers={
        "Authorization": f"Bearer {user_token}",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_user(client: AsyncClient, admin_user, admin_token):
    resp = await client.post("/api/users", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "email": "newuser@test.local",
        "password": "password123",
        "full_name": "New User",
        "role": "user",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newuser@test.local"
    assert data["role"] == "user"


@pytest.mark.asyncio
async def test_create_duplicate_user(client: AsyncClient, admin_user, admin_token):
    resp = await client.post("/api/users", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "email": "admin@test.local",
        "password": "pass",
        "full_name": "Dup",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_user(client: AsyncClient, admin_user, regular_user, admin_token):
    resp = await client.patch(f"/api/users/{regular_user.id}", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "full_name": "Updated Name",
    })
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"


@pytest.mark.asyncio
async def test_deactivate_user(client: AsyncClient, admin_user, regular_user, admin_token):
    resp = await client.delete(f"/api/users/{regular_user.id}", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
