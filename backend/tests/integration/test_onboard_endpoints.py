import io
import tarfile
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.config import settings
from app.models.device import Device
from app.services.auth_service import generate_api_key


@pytest_asyncio.fixture
async def test_device_with_key(db_session):
    """Create a test device and return (device, plaintext_api_key)."""
    plaintext, key_hash, key_prefix = generate_api_key()
    device = Device(
        id=uuid.uuid4(),
        name="Onboard Test Device",
        serial_number="BUGSI-ONBOARD-001",
        api_key_hash=key_hash,
        api_key_prefix=key_prefix,
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device, plaintext


@pytest_asyncio.fixture
def fake_device_client_dir(tmp_path, monkeypatch):
    """Create minimal fake device-client and insect-detector directories and patch settings."""
    # Device client
    client_dir = tmp_path / "device-client"
    client_dir.mkdir()
    (client_dir / "install.sh").write_text("#!/bin/bash\necho install")
    (client_dir / "install_hardware.sh").write_text("#!/bin/bash\necho hw")
    (client_dir / "pyproject.toml").write_text("[project]\nname='bugsi'")
    pkg = client_dir / "bugsi_daemon"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    # Add excludable dirs to verify filtering
    (client_dir / ".venv").mkdir()
    (client_dir / "__pycache__").mkdir()

    # Insect detector
    detector_dir = tmp_path / "insect-detector"
    detector_dir.mkdir()
    (detector_dir / "detector.py").write_text("print('detect')")
    (detector_dir / "install.sh").write_text("#!/bin/bash\necho detector")
    config = detector_dir / "config"
    config.mkdir()
    (config / "defaults.json").write_text("{}")

    monkeypatch.setattr(settings, "DEVICE_CLIENT_DIR", str(client_dir))
    monkeypatch.setattr(settings, "INSECT_DETECTOR_DIR", str(detector_dir))
    return tmp_path


@pytest.mark.asyncio
async def test_onboard_returns_shell_script(client: AsyncClient, test_device_with_key):
    device, api_key = test_device_with_key
    resp = await client.get("/api/device-data/onboard", headers={"X-API-Key": api_key})
    assert resp.status_code == 200
    assert "text/x-shellscript" in resp.headers["content-type"]
    body = resp.text
    assert body.startswith("#!/usr/bin/env bash")
    assert api_key in body
    assert "/api/device-data" in body
    assert device.name in body


@pytest.mark.asyncio
async def test_onboard_invalid_key(client: AsyncClient):
    resp = await client.get("/api/device-data/onboard", headers={"X-API-Key": "invalid_key"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_onboard_bundle_returns_tarball(
    client: AsyncClient, test_device_with_key, fake_device_client_dir,
):
    _, api_key = test_device_with_key
    resp = await client.get("/api/device-data/onboard/bundle", headers={"X-API-Key": api_key})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/gzip"
    assert "bugsi-bundle.tar.gz" in resp.headers["content-disposition"]

    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        names = tar.getnames()
    assert any("install.sh" in n for n in names)
    assert any("install_hardware.sh" in n for n in names)
    assert any("detector.py" in n for n in names)


@pytest.mark.asyncio
async def test_onboard_bundle_excludes_venv(
    client: AsyncClient, test_device_with_key, fake_device_client_dir,
):
    _, api_key = test_device_with_key
    resp = await client.get("/api/device-data/onboard/bundle", headers={"X-API-Key": api_key})

    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        names = tar.getnames()
    assert not any(".venv" in n for n in names)
    assert not any("__pycache__" in n for n in names)


@pytest.mark.asyncio
async def test_onboard_bundle_invalid_key(client: AsyncClient):
    resp = await client.get("/api/device-data/onboard/bundle", headers={"X-API-Key": "invalid_key"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_onboard_bundle_missing_dir(
    client: AsyncClient, test_device_with_key, monkeypatch,
):
    _, api_key = test_device_with_key
    monkeypatch.setattr(settings, "DEVICE_CLIENT_DIR", "/nonexistent/path")
    resp = await client.get("/api/device-data/onboard/bundle", headers={"X-API-Key": api_key})
    assert resp.status_code == 404
