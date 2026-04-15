import pytest


@pytest.mark.asyncio
async def test_preferences_default_empty(client, regular_user, user_token):
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {user_token}"})
    assert resp.status_code == 200
    assert resp.json()["preferences"] == {}


@pytest.mark.asyncio
async def test_update_preferences_hidden_fields(client, regular_user, user_token):
    resp = await client.patch(
        "/api/auth/me/preferences",
        json={"preferences": {"hidden_telemetry_fields": ["battery_current", "cpu_temp"]}},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["preferences"]["hidden_telemetry_fields"] == ["battery_current", "cpu_temp"]


@pytest.mark.asyncio
async def test_preferences_merge_not_replace(client, regular_user, user_token):
    headers = {"Authorization": f"Bearer {user_token}"}

    # Set first preference
    await client.patch(
        "/api/auth/me/preferences",
        json={"preferences": {"hidden_telemetry_fields": ["cpu_temp"]}},
        headers=headers,
    )

    # Set another preference key - should merge, not replace
    resp = await client.patch(
        "/api/auth/me/preferences",
        json={"preferences": {"some_other_pref": True}},
        headers=headers,
    )
    assert resp.status_code == 200
    prefs = resp.json()["preferences"]
    assert prefs["hidden_telemetry_fields"] == ["cpu_temp"]
    assert prefs["some_other_pref"] is True


@pytest.mark.asyncio
async def test_preferences_invalid_telemetry_field(client, regular_user, user_token):
    resp = await client.patch(
        "/api/auth/me/preferences",
        json={"preferences": {"hidden_telemetry_fields": ["not_a_real_field"]}},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 422
    assert "not_a_real_field" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_preferences_hidden_fields_not_a_list(client, regular_user, user_token):
    resp = await client.patch(
        "/api/auth/me/preferences",
        json={"preferences": {"hidden_telemetry_fields": "battery_soc"}},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 422
    assert "must be a list" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_preferences_persists_across_requests(client, regular_user, user_token):
    headers = {"Authorization": f"Bearer {user_token}"}

    await client.patch(
        "/api/auth/me/preferences",
        json={"preferences": {"hidden_telemetry_fields": ["humidity"]}},
        headers=headers,
    )

    resp = await client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["preferences"]["hidden_telemetry_fields"] == ["humidity"]


@pytest.mark.asyncio
async def test_preferences_requires_auth(client):
    resp = await client.patch(
        "/api/auth/me/preferences",
        json={"preferences": {"hidden_telemetry_fields": []}},
    )
    assert resp.status_code == 401
