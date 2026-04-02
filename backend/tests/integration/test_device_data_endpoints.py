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
async def test_poll_config_includes_event_camera_defaults(client: AsyncClient, test_device_with_key):
    device, api_key = test_device_with_key
    resp = await client.get("/api/device-data/config", headers={
        "X-API-Key": api_key,
    })
    assert resp.status_code == 200
    config = resp.json()["config"]
    # Event camera section should include bias fields from defaults
    ec = config.get("event_camera", {})
    assert "bias_diff_on" in ec
    assert "bias_diff_off" in ec
    assert "bias_fo" in ec
    assert "bias_hpf" in ec
    assert "bias_refr" in ec
    assert "jpeg_quality" in ec


@pytest.mark.asyncio
async def test_push_config_with_event_camera_biases(client: AsyncClient, test_device_with_key):
    device, api_key = test_device_with_key
    # First poll to get current version
    resp = await client.get("/api/device-data/config", headers={
        "X-API-Key": api_key,
    })
    assert resp.status_code == 200
    version = resp.json()["version"]

    # Push config with event camera biases
    resp = await client.put("/api/device-data/config", headers={
        "X-API-Key": api_key,
    }, json={
        "config": {"event_camera": {"bias_diff_on": 110, "bias_fo": 1600}},
        "version": version,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is True

    # Verify the pushed values are returned on next poll
    resp = await client.get("/api/device-data/config", headers={
        "X-API-Key": api_key,
    })
    assert resp.status_code == 200
    ec = resp.json()["config"].get("event_camera", {})
    assert ec.get("bias_diff_on") == 110
    assert ec.get("bias_fo") == 1600


@pytest.mark.asyncio
async def test_ota_check_no_update(client: AsyncClient, test_device_with_key):
    device, api_key = test_device_with_key
    resp = await client.get("/api/device-data/ota/check", headers={
        "X-API-Key": api_key,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_update"] is False


@pytest.mark.asyncio
async def test_download_heavy_file(client: AsyncClient, test_device_with_key, tmp_path):
    from app.config import settings

    device, api_key = test_device_with_key

    # Create test file in a temporary heavy-files dir
    original_dir = settings.HEAVY_FILES_DIR
    settings.HEAVY_FILES_DIR = str(tmp_path)
    test_file = tmp_path / "ids-peak_2.20.0.0-408_arm64.tgz"
    test_file.write_bytes(b"fake-tarball-content")

    try:
        resp = await client.get(
            "/api/device-data/files/ids-peak_2.20.0.0-408_arm64.tgz",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        assert resp.content == b"fake-tarball-content"
        assert "attachment" in resp.headers.get("content-disposition", "")
    finally:
        settings.HEAVY_FILES_DIR = original_dir


@pytest.mark.asyncio
async def test_download_heavy_file_not_in_whitelist(client: AsyncClient, test_device_with_key):
    device, api_key = test_device_with_key
    resp = await client.get(
        "/api/device-data/files/../../etc/passwd",
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code in (404, 422)


@pytest.mark.asyncio
async def test_download_heavy_file_invalid_key(client: AsyncClient):
    resp = await client.get(
        "/api/device-data/files/ids-peak_2.20.0.0-408_arm64.tgz",
        headers={"X-API-Key": "invalid_key"},
    )
    assert resp.status_code == 401
