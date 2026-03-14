import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.services.auth_service import generate_api_key


@pytest_asyncio.fixture
async def test_device_with_key(db_session: AsyncSession):
    plaintext, key_hash, key_prefix = generate_api_key()
    device = Device(
        id=uuid.uuid4(),
        name="Config Push Test Device",
        serial_number=f"BUGSI-CFGPUSH-{uuid.uuid4().hex[:6]}",
        api_key_hash=key_hash,
        api_key_prefix=key_prefix,
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device, plaintext


@pytest.mark.asyncio
async def test_device_push_config_creates_config(client: AsyncClient, test_device_with_key):
    device, api_key = test_device_with_key

    resp = await client.put("/api/device-data/config", headers={
        "X-API-Key": api_key,
    }, json={
        "config": {"telemetry": {"interval": 10}},
        "version": 1,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is True
    assert data["version"] == 1


@pytest.mark.asyncio
async def test_device_push_config_updates_existing(client: AsyncClient, test_device_with_key):
    device, api_key = test_device_with_key

    # First push
    resp = await client.put("/api/device-data/config", headers={
        "X-API-Key": api_key,
    }, json={
        "config": {"a": 1},
        "version": 1,
    })
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True

    # Second push with higher version
    resp = await client.put("/api/device-data/config", headers={
        "X-API-Key": api_key,
    }, json={
        "config": {"a": 2},
        "version": 2,
    })
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True
    assert resp.json()["version"] == 2


@pytest.mark.asyncio
async def test_device_push_config_rejected_if_server_newer(client: AsyncClient, test_device_with_key, admin_user, admin_token):
    device, api_key = test_device_with_key

    # Admin sets config via normal endpoint first (creates version 1, then updates to 2)
    resp = await client.put(f"/api/config/{device.id}", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={"config_json": {"from_admin": True}})
    assert resp.status_code == 200

    # Update again to bump version to 2
    resp = await client.put(f"/api/config/{device.id}", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={"config_json": {"from_admin": True, "v2": True}})
    assert resp.status_code == 200

    # Device tries to push with lower version
    resp = await client.put("/api/device-data/config", headers={
        "X-API-Key": api_key,
    }, json={
        "config": {"from_device": True},
        "version": 1,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is False
    assert data["version"] == 3  # Server's version (get_or_create starts at 1, +2 admin updates)


@pytest.mark.asyncio
async def test_device_push_config_sets_acked_version(client: AsyncClient, test_device_with_key):
    device, api_key = test_device_with_key

    # Push config
    await client.put("/api/device-data/config", headers={
        "X-API-Key": api_key,
    }, json={
        "config": {"key": "value"},
        "version": 5,
    })

    # Poll should show no update (device already has this version)
    resp = await client.get("/api/device-data/config", headers={
        "X-API-Key": api_key,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_update"] is False
    assert data["version"] == 5


@pytest.mark.asyncio
async def test_device_push_config_no_api_key(client: AsyncClient):
    resp = await client.put("/api/device-data/config", json={
        "config": {"key": "value"},
        "version": 1,
    })
    assert resp.status_code in (401, 403, 422)  # 422 if API key header missing triggers validation


@pytest.mark.asyncio
async def test_device_push_config_oversized(client: AsyncClient, test_device_with_key):
    device, api_key = test_device_with_key

    # Create a config larger than 64KB
    big_config = {"data": "x" * 70000}
    resp = await client.put("/api/device-data/config", headers={
        "X-API-Key": api_key,
    }, json={
        "config": big_config,
        "version": 1,
    })
    assert resp.status_code == 422
