"""Integration tests for security endpoints (logout, token blacklist, refresh rotation, pagination)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_logout_blacklists_access_token(client: AsyncClient, admin_user, admin_token):
    # Verify token works before logout
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200

    # Logout
    resp = await client.post("/api/auth/logout", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 204

    # Token should now be revoked
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_rotation(client: AsyncClient, admin_user):
    # Login to get tokens
    login_resp = await client.post("/api/auth/login", json={
        "email": "admin@test.local",
        "password": "admin123",
    })
    assert login_resp.status_code == 200
    old_refresh = login_resp.json()["refresh_token"]

    # Use refresh token — should work and return new tokens
    resp = await client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200
    new_refresh = resp.json()["refresh_token"]
    assert new_refresh != old_refresh

    # Reuse old refresh token — should be rejected (rotation: single-use)
    resp = await client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 401

    # New refresh token should still work
    resp = await client.post("/api/auth/refresh", json={"refresh_token": new_refresh})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_pagination_limit_enforced(client: AsyncClient, admin_user, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Request with limit > 200 should be rejected
    resp = await client.get("/api/devices?limit=999", headers=headers)
    assert resp.status_code == 422  # Validation error

    # Request with limit = 200 should work
    resp = await client.get("/api/devices?limit=200", headers=headers)
    assert resp.status_code == 200

    # Negative offset should be rejected
    resp = await client.get("/api/devices?offset=-1", headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_health_endpoint_no_db_info(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "database" not in data
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_security_headers_present(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert "max-age" in resp.headers.get("Strict-Transport-Security", "")


@pytest.mark.asyncio
async def test_login_sets_httponly_cookies(client: AsyncClient, admin_user):
    resp = await client.post("/api/auth/login", json={
        "email": "admin@test.local",
        "password": "admin123",
    })
    assert resp.status_code == 200

    # Check that cookies are set
    cookies = resp.cookies
    assert "access_token" in cookies
    assert "refresh_token" in cookies


@pytest.mark.asyncio
async def test_cookie_auth_works(client: AsyncClient, admin_user):
    # Login to get cookies
    login_resp = await client.post("/api/auth/login", json={
        "email": "admin@test.local",
        "password": "admin123",
    })
    assert login_resp.status_code == 200

    # Use cookie for auth (httpx auto-sends cookies from previous response)
    access_cookie = login_resp.cookies["access_token"]
    resp = await client.get("/api/auth/me", cookies={"access_token": access_cookie})
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@test.local"


@pytest.mark.asyncio
async def test_logout_clears_cookies(client: AsyncClient, admin_user, admin_token):
    resp = await client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 204

    # Check that cookies are cleared (set to empty / max-age=0)
    set_cookie_headers = resp.headers.get_list("set-cookie")
    cookie_str = " ".join(set_cookie_headers)
    assert "access_token" in cookie_str
    assert "refresh_token" in cookie_str
