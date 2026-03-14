import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, admin_user):
    resp = await client.post("/api/auth/login", json={
        "email": "admin@test.local",
        "password": "admin123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, admin_user):
    resp = await client.post("/api/auth/login", json={
        "email": "admin@test.local",
        "password": "wrong",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    resp = await client.post("/api/auth/login", json={
        "email": "nobody@test.local",
        "password": "pass",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_token(client: AsyncClient, admin_user, admin_token):
    resp = await client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "admin@test.local"
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_me_without_token(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient, admin_user):
    # Login to get tokens
    login_resp = await client.post("/api/auth/login", json={
        "email": "admin@test.local",
        "password": "admin123",
    })
    refresh_token = login_resp.json()["refresh_token"]

    # Use refresh token
    resp = await client.post("/api/auth/refresh", json={
        "refresh_token": refresh_token,
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()
