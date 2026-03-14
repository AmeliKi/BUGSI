import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_defaults_requires_auth(client: AsyncClient):
    resp = await client.get("/api/config/defaults")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_defaults_returns_config(client: AsyncClient, admin_token):
    resp = await client.get("/api/config/defaults", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "camera" in data
    assert "telemetry" in data
    assert "upload" in data
    assert "power" in data
    assert "storage" in data
    assert "webserver" in data


@pytest.mark.asyncio
async def test_create_device_has_default_config(client: AsyncClient, admin_token):
    # Create device
    resp = await client.post("/api/devices", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "name": "Config Default Test",
        "serial_number": "BUGSI-CFGDEF-001",
    })
    assert resp.status_code == 201
    device_id = resp.json()["id"]

    # Get config - should have defaults, not empty
    resp = await client.get(f"/api/config/{device_id}", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert resp.status_code == 200
    config = resp.json()["config_json"]
    assert "camera" in config
    assert "telemetry" in config
    assert config["camera"]["resolution_width"] == 3840


@pytest.mark.asyncio
async def test_update_config_merges_defaults(client: AsyncClient, admin_token):
    # Create device
    resp = await client.post("/api/devices", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "name": "Config Merge Test",
        "serial_number": "BUGSI-CFGMRG-001",
    })
    assert resp.status_code == 201
    device_id = resp.json()["id"]

    # Update with partial config (only camera section)
    resp = await client.put(f"/api/config/{device_id}", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "config_json": {"camera": {"resolution_width": 1920}},
    })
    assert resp.status_code == 200
    config = resp.json()["config_json"]

    # Should have the custom value
    assert config["camera"]["resolution_width"] == 1920
    # Should have other camera defaults filled in
    assert "resolution_height" in config["camera"]
    # Should have other sections from defaults
    assert "telemetry" in config
    assert "power" in config
