import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.device import Device
from app.models.device_assignment import DeviceAssignment
from app.services.auth_service import generate_api_key


@pytest_asyncio.fixture
async def config_device(db_session, admin_user):
    plaintext, key_hash, key_prefix = generate_api_key()
    device = Device(
        id=uuid.uuid4(),
        name="Config Test Device",
        serial_number="BUGSI-CFG-001",
        api_key_hash=key_hash,
        api_key_prefix=key_prefix,
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device, plaintext


@pytest.mark.asyncio
async def test_get_config_creates_default(client: AsyncClient, admin_token, config_device):
    device, _ = config_device
    resp = await client.get(f"/api/config/{device.id}", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == 1
    # Config should be populated with defaults (not empty)
    assert "camera" in data["config_json"]
    assert "telemetry" in data["config_json"]


@pytest.mark.asyncio
async def test_update_config_bumps_version(client: AsyncClient, admin_token, config_device):
    device, _ = config_device
    # Get initial config
    await client.get(f"/api/config/{device.id}", headers={
        "Authorization": f"Bearer {admin_token}",
    })

    # Update config
    resp = await client.put(f"/api/config/{device.id}", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "config_json": {"detection": {"cooldown_seconds": 15}},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == 2
    assert data["config_json"]["detection"]["cooldown_seconds"] == 15


@pytest.mark.asyncio
async def test_device_polls_and_acks_config(client: AsyncClient, admin_token, config_device):
    device, api_key = config_device

    # Admin updates config
    await client.get(f"/api/config/{device.id}", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    await client.put(f"/api/config/{device.id}", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "config_json": {"upload": {"interval_minutes": 30}},
    })

    # Device polls config
    resp = await client.get("/api/device-data/config", headers={"X-API-Key": api_key})
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_update"] is True
    assert data["version"] == 2

    # Device acknowledges config
    resp = await client.post("/api/device-data/config/ack", headers={
        "X-API-Key": api_key,
    }, json={"version": 2})
    assert resp.status_code == 204

    # Poll again - should show no update
    resp = await client.get("/api/device-data/config", headers={"X-API-Key": api_key})
    assert resp.json()["has_update"] is False
