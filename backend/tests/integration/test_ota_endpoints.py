import io
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.device import Device
from app.services.auth_service import generate_api_key
from tests.helpers import build_test_package


@pytest_asyncio.fixture
async def ota_device(db_session):
    plaintext, key_hash, key_prefix = generate_api_key()
    device = Device(
        id=uuid.uuid4(),
        name="OTA Test Device",
        serial_number="BUGSI-OTA-001",
        api_key_hash=key_hash,
        api_key_prefix=key_prefix,
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device, plaintext


@pytest.mark.asyncio
async def test_upload_ota_package(client: AsyncClient, admin_user, admin_token):
    file_content = build_test_package(version="1.0.0", package_type="full")
    resp = await client.post("/api/ota/packages", headers={
        "Authorization": f"Bearer {admin_token}",
    }, data={
        "version": "1.0.0",
        "package_type": "full",
        "description": "Initial release",
    }, files={
        "file": ("update.tar.gz", io.BytesIO(file_content), "application/gzip"),
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["version"] == "1.0.0"
    assert data["package_type"] == "full"
    assert data["file_size_bytes"] == len(file_content)


@pytest.mark.asyncio
async def test_list_packages(client: AsyncClient, admin_user, admin_token):
    file_content = build_test_package(version="2.0.0", package_type="daemon_only")
    await client.post("/api/ota/packages", headers={
        "Authorization": f"Bearer {admin_token}",
    }, data={
        "version": "2.0.0",
        "package_type": "daemon_only",
    }, files={
        "file": ("update.tar.gz", io.BytesIO(file_content), "application/gzip"),
    })

    resp = await client.get("/api/ota/packages", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_deploy_and_check_ota(client: AsyncClient, admin_user, admin_token, ota_device):
    device, api_key = ota_device

    file_content = build_test_package(version="3.0.0", package_type="full")
    pkg_resp = await client.post("/api/ota/packages", headers={
        "Authorization": f"Bearer {admin_token}",
    }, data={
        "version": "3.0.0",
        "package_type": "full",
    }, files={
        "file": ("update.tar.gz", io.BytesIO(file_content), "application/gzip"),
    })
    pkg_id = pkg_resp.json()["id"]

    # Deploy to device
    deploy_resp = await client.post("/api/ota/deploy", headers={
        "Authorization": f"Bearer {admin_token}",
    }, json={
        "package_id": pkg_id,
        "device_ids": [str(device.id)],
    })
    assert deploy_resp.status_code == 201
    deployments = deploy_resp.json()
    assert len(deployments) == 1
    assert deployments[0]["status"] == "pending"
    deployment_id = deployments[0]["id"]

    # Device checks for OTA
    check_resp = await client.get("/api/device-data/ota/check", headers={
        "X-API-Key": api_key,
    })
    assert check_resp.status_code == 200
    data = check_resp.json()
    assert data["has_update"] is True
    assert data["deployment"]["package_version"] == "3.0.0"

    # Device reports completion
    status_resp = await client.post(f"/api/device-data/ota/{deployment_id}/status", headers={
        "X-API-Key": api_key,
    }, json={"status": "completed"})
    assert status_resp.status_code == 204

    # Check again - no more updates
    check_resp = await client.get("/api/device-data/ota/check", headers={
        "X-API-Key": api_key,
    })
    assert check_resp.json()["has_update"] is False


@pytest.mark.asyncio
async def test_upload_invalid_package_rejected(client: AsyncClient, admin_user, admin_token):
    resp = await client.post("/api/ota/packages", headers={
        "Authorization": f"Bearer {admin_token}",
    }, data={
        "version": "bad.0.0",
        "package_type": "full",
    }, files={
        "file": ("update.tar.gz", io.BytesIO(b"not a tar file"), "application/gzip"),
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_invalid_package_type_rejected(client: AsyncClient, admin_user, admin_token):
    resp = await client.post("/api/ota/packages", headers={
        "Authorization": f"Bearer {admin_token}",
    }, data={
        "version": "4.0.0",
        "package_type": "invalid_type",
    }, files={
        "file": ("update.tar.gz", io.BytesIO(b"data"), "application/gzip"),
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_version_mismatch_rejected(client: AsyncClient, admin_user, admin_token):
    file_content = build_test_package(version="5.0.0", package_type="full")
    resp = await client.post("/api/ota/packages", headers={
        "Authorization": f"Bearer {admin_token}",
    }, data={
        "version": "6.0.0",  # Mismatch with manifest version 5.0.0
        "package_type": "full",
    }, files={
        "file": ("update.tar.gz", io.BytesIO(file_content), "application/gzip"),
    })
    assert resp.status_code == 422
