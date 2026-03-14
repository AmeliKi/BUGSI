from __future__ import annotations

import json

import pytest
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from bugsi_daemon.config import ConfigManager
from bugsi_daemon.web.server import WebServer


@pytest.fixture
def config(tmp_path):
    default_path = tmp_path / "default.json"
    default_path.write_text(json.dumps({
        "webserver": {"enabled": True, "host": "127.0.0.1", "port": 0, "camera_fps": 1,
                      "detections_dir": str(tmp_path / "detections")},
        "power": {"battery": False, "wlan_timeout_minutes": 10},
    }))
    local_path = tmp_path / "local.json"
    cred_path = tmp_path / "cred.json"
    cm = ConfigManager(
        default_config_path=default_path,
        local_config_path=str(local_path),
        credentials_path=str(cred_path),
    )
    cm.load()
    return cm


@pytest.fixture
def components():
    return {
        "buffer": None,
        "client": None,
        "power_manager": None,
        "web_camera": None,
        "wlan": None,
    }


async def test_server_start_stop(config, components):
    server = WebServer(config=config, components=components)
    assert not server.is_running
    await server.start()
    assert server.is_running
    await server.stop()
    assert not server.is_running


async def test_config_get_route(config, components, aiohttp_client):
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/config")
    assert resp.status == 200
    data = await resp.json()
    assert "config" in data
    assert "version" in data


async def test_config_put_route(config, components, aiohttp_client):
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.put("/api/config", json={"config": {"telemetry": {"collection_interval_minutes": 10}}})
    assert resp.status == 200
    data = await resp.json()
    assert data["version"] == 1
    assert data["pushed_to_saas"] is False


async def test_config_put_invalid_json(config, components, aiohttp_client):
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.put("/api/config", data=b"not json", headers={"Content-Type": "application/json"})
    assert resp.status == 400


async def test_config_put_missing_config_field(config, components, aiohttp_client):
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.put("/api/config", json={"wrong": "field"})
    assert resp.status == 400


async def test_status_route(config, components, aiohttp_client):
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/status")
    assert resp.status == 200
    data = await resp.json()
    assert "config_version" in data


async def test_gallery_empty(config, components, aiohttp_client, tmp_path):
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/gallery")
    assert resp.status == 200
    data = await resp.json()
    assert data["crops"] == []
    assert data["detections"] == []


async def test_gallery_with_images(config, components, aiohttp_client, tmp_path):
    # Create detections dir with crops
    det_dir = tmp_path / "detections"
    crops_dir = det_dir / "crops"
    crops_dir.mkdir(parents=True)
    (crops_dir / "test1.jpg").write_bytes(b"\xff\xd8\xff\xe0")
    (crops_dir / "test2.jpg").write_bytes(b"\xff\xd8\xff\xe0")

    # Update config to point to our test dir
    config.apply_local({"webserver": {"detections_dir": str(det_dir)}})

    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/gallery")
    assert resp.status == 200
    data = await resp.json()
    assert len(data["crops"]) == 2
    assert data["total_crops"] == 2


async def test_gallery_image_path_traversal(config, components, aiohttp_client):
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/gallery/image/../../../etc/passwd")
    assert resp.status in (400, 404)

    # aiohttp normalizes .. in URLs, so test with encoded dots
    resp = await client.get("/api/gallery/image/crops/..%2F..%2Fetc%2Fpasswd")
    assert resp.status in (400, 404)


async def test_gallery_image_invalid_subdir(config, components, aiohttp_client):
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/gallery/image/secrets/file.jpg")
    assert resp.status == 400


async def test_camera_snapshot_no_camera(config, components, aiohttp_client):
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/camera/snapshot")
    assert resp.status == 503


async def test_camera_snapshot_with_mock(config, components, aiohttp_client, tmp_path):
    from bugsi_daemon.hardware_mock.camera import MockCamera
    from bugsi_daemon.web.camera import WebCamera

    web_camera = WebCamera(MockCamera(resolution_width=160, resolution_height=120), jpeg_quality=70)
    components["web_camera"] = web_camera

    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/camera/snapshot")
    assert resp.status == 200
    assert resp.content_type == "image/jpeg"
    data = await resp.read()
    assert len(data) > 0


async def test_activity_middleware_callback(config, components, aiohttp_client):
    calls = []

    def on_request():
        calls.append(1)

    server = WebServer(config=config, components=components, on_request_callback=on_request)
    app = server._create_app()
    client = await aiohttp_client(app)

    await client.get("/api/status")
    await client.get("/api/config")
    assert len(calls) == 2
