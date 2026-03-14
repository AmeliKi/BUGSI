import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_device(client: AsyncClient, admin_user, admin_token):
    resp = await client.post("/api/devices", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "name": "Test Device",
        "serial_number": "BUGSI-TEST-001",
        "location_description": "Test field",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Device"
    assert data["serial_number"] == "BUGSI-TEST-001"
    assert "api_key" in data
    assert data["api_key"].startswith("bugsi_")


@pytest.mark.asyncio
async def test_create_duplicate_device(client: AsyncClient, admin_user, admin_token):
    await client.post("/api/devices", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "name": "Device 1",
        "serial_number": "BUGSI-DUP-001",
    })
    resp = await client.post("/api/devices", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "name": "Device 2",
        "serial_number": "BUGSI-DUP-001",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_devices_as_admin(client: AsyncClient, admin_user, admin_token):
    await client.post("/api/devices", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "name": "List Test",
        "serial_number": "BUGSI-LIST-001",
    })
    resp = await client.get("/api/devices", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_create_device_as_user_forbidden(client: AsyncClient, regular_user, user_token):
    resp = await client.post("/api/devices", headers={
        "Authorization": f"Bearer {user_token}",
    }, json={
        "name": "Should Fail",
        "serial_number": "BUGSI-FAIL-001",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_device(client: AsyncClient, admin_user, admin_token):
    create_resp = await client.post("/api/devices", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "name": "Get Test",
        "serial_number": "BUGSI-GET-001",
    })
    device_id = create_resp.json()["id"]

    resp = await client.get(f"/api/devices/{device_id}", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Test"


@pytest.mark.asyncio
async def test_deactivate_device(client: AsyncClient, admin_user, admin_token):
    create_resp = await client.post("/api/devices", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "name": "Deactivate Test",
        "serial_number": "BUGSI-DEACT-001",
    })
    device_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/devices/{device_id}", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_active"] is False

    # Verify device is deactivated when fetched
    get_resp = await client.get(f"/api/devices/{device_id}", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert get_resp.status_code == 200
    assert get_resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_deactivate_device_as_user_forbidden(client: AsyncClient, admin_user, admin_token, regular_user, user_token):
    create_resp = await client.post("/api/devices", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "name": "Deactivate Forbidden",
        "serial_number": "BUGSI-DEACT-002",
    })
    device_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/devices/{device_id}", headers={
        "Authorization": f"Bearer {user_token}",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_activate_device(client: AsyncClient, admin_user, admin_token):
    create_resp = await client.post("/api/devices", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "name": "Activate Test",
        "serial_number": "BUGSI-ACT-001",
    })
    device_id = create_resp.json()["id"]

    # Deactivate first
    await client.delete(f"/api/devices/{device_id}", headers={
        "Authorization": f"Bearer {admin_token}",
    })

    # Activate
    resp = await client.post(f"/api/devices/{device_id}/activate", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


@pytest.mark.asyncio
async def test_list_devices_exclude_inactive(client: AsyncClient, admin_user, admin_token):
    create_resp = await client.post("/api/devices", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "name": "Filter Test",
        "serial_number": "BUGSI-FILTER-001",
    })
    device_id = create_resp.json()["id"]

    # Deactivate the device
    await client.delete(f"/api/devices/{device_id}", headers={
        "Authorization": f"Bearer {admin_token}",
    })

    # List without inactive — should not include deactivated device
    resp = await client.get("/api/devices?include_inactive=false", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert resp.status_code == 200
    device_ids = [d["id"] for d in resp.json()]
    assert device_id not in device_ids

    # List with inactive — should include it
    resp = await client.get("/api/devices?include_inactive=true", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert resp.status_code == 200
    device_ids = [d["id"] for d in resp.json()]
    assert device_id in device_ids
