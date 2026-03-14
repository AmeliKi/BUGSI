import hashlib
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.device import Device
from app.services.auth_service import generate_api_key


@pytest_asyncio.fixture
async def test_device_with_key(db_session):
    """Create a test device and return (device, plaintext_api_key)."""
    plaintext, key_hash, key_prefix = generate_api_key()
    device = Device(
        id=uuid.uuid4(),
        name="Data Test Device",
        serial_number="BUGSI-DATA-001",
        api_key_hash=key_hash,
        api_key_prefix=key_prefix,
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device, plaintext


@pytest.mark.asyncio
async def test_ingest_telemetry(client: AsyncClient, test_device_with_key):
    device, api_key = test_device_with_key
    resp = await client.post("/api/device-data/telemetry", headers={
        "X-API-Key": api_key,
    }, json={
        "readings": [
            {
                "timestamp": "2026-03-06T12:00:00Z",
                "battery_soc": 75.5,
                "battery_voltage": 26.1,
                "temperature": 22.3,
                "humidity": 55.0,
            }
        ]
    })
    assert resp.status_code == 201
    data = resp.json()
    assert len(data) == 1
    assert data[0]["battery_soc"] == 75.5


@pytest.mark.asyncio
async def test_ingest_telemetry_invalid_key(client: AsyncClient):
    resp = await client.post("/api/device-data/telemetry", headers={
        "X-API-Key": "invalid_key",
    }, json={
        "readings": [{"timestamp": "2026-03-06T12:00:00Z"}]
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_poll_config(client: AsyncClient, test_device_with_key):
    device, api_key = test_device_with_key
    resp = await client.get("/api/device-data/config", headers={
        "X-API-Key": api_key,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "config" in data
    assert "has_update" in data


@pytest.mark.asyncio
async def test_ota_check_no_update(client: AsyncClient, test_device_with_key):
    device, api_key = test_device_with_key
    resp = await client.get("/api/device-data/ota/check", headers={
        "X-API-Key": api_key,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_update"] is False
