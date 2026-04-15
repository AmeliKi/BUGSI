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
        "web_event_camera": None,
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


async def test_event_camera_snapshot_no_camera(config, components, aiohttp_client):
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/camera/event/snapshot")
    assert resp.status == 503


async def test_event_camera_snapshot_with_mock(config, components, aiohttp_client):
    from bugsi_daemon.hardware_mock.event_camera import MockEventCamera
    from bugsi_daemon.web.camera import WebEventCamera

    web_event_camera = WebEventCamera(MockEventCamera(frame_width=160, frame_height=120), jpeg_quality=70)
    components["web_event_camera"] = web_event_camera

    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/camera/event/snapshot")
    assert resp.status == 200
    assert resp.content_type == "image/jpeg"
    data = await resp.read()
    assert len(data) > 0


async def test_camera_info_both_available(config, components, aiohttp_client):
    from bugsi_daemon.hardware_mock.camera import MockCamera
    from bugsi_daemon.hardware_mock.event_camera import MockEventCamera
    from bugsi_daemon.web.camera import WebCamera, WebEventCamera

    components["web_camera"] = WebCamera(MockCamera(), jpeg_quality=70)
    components["web_event_camera"] = WebEventCamera(MockEventCamera(), jpeg_quality=70)

    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/camera/info")
    assert resp.status == 200
    data = await resp.json()
    assert data["still_camera"]["available"] is True
    assert data["event_camera"]["available"] is True


async def test_camera_info_event_not_available(config, components, aiohttp_client):
    from bugsi_daemon.hardware_mock.camera import MockCamera
    from bugsi_daemon.web.camera import WebCamera

    components["web_camera"] = WebCamera(MockCamera(), jpeg_quality=70)
    # web_event_camera is None (from fixture)

    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/camera/info")
    assert resp.status == 200
    data = await resp.json()
    assert data["still_camera"]["available"] is True
    assert data["event_camera"]["available"] is False


async def test_camera_info_no_cameras(config, components, aiohttp_client):
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/camera/info")
    assert resp.status == 200
    data = await resp.json()
    assert data["still_camera"]["available"] is False
    assert data["event_camera"]["available"] is False


async def test_config_pull_no_client(config, components, aiohttp_client):
    """Pull from SaaS returns 503 when no client is configured."""
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.post("/api/config/pull")
    assert resp.status == 503
    data = await resp.json()
    assert "error" in data


async def test_config_roundtrip_event_camera_fields(config, components, aiohttp_client):
    """PUT event_camera bias fields and verify GET returns them."""
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    new_config = {
        "event_camera": {
            "type": "ids_evs",
            "event_threshold": 600,
            "bias_diff_on": 110,
            "bias_diff_off": 80,
            "bias_fo": 1500,
            "bias_hpf": 1600,
            "bias_refr": 1400,
            "jpeg_quality": 90,
        }
    }
    resp = await client.put("/api/config", json={"config": new_config})
    assert resp.status == 200
    put_data = await resp.json()
    assert put_data["version"] == 1

    resp = await client.get("/api/config")
    assert resp.status == 200
    get_data = await resp.json()
    ec = get_data["config"]["event_camera"]
    assert ec["bias_diff_on"] == 110
    assert ec["bias_diff_off"] == 80
    assert ec["bias_fo"] == 1500
    assert ec["bias_hpf"] == 1600
    assert ec["bias_refr"] == 1400
    assert ec["jpeg_quality"] == 90
    assert ec["event_threshold"] == 600


async def test_config_roundtrip_null_values(config, components, aiohttp_client):
    """PUT null values and verify they are preserved."""
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    new_config = {"lte": {"serial_port": None, "gpio_pin": 26}}
    resp = await client.put("/api/config", json={"config": new_config})
    assert resp.status == 200

    resp = await client.get("/api/config")
    assert resp.status == 200
    get_data = await resp.json()
    assert get_data["config"]["lte"]["serial_port"] is None
    assert get_data["config"]["lte"]["gpio_pin"] == 26


def test_has_camera_changes_detects_still_camera():
    from bugsi_daemon.web.routes_api import _has_camera_changes
    current = {
        "still_camera": {"type": "arducam_64mp", "exposure_us": 0},
        "event_camera": {"type": "prophesee_genx320"},
        "upload": {"interval_minutes": 60},
    }
    # Actual change triggers
    assert _has_camera_changes({"still_camera": {"type": "ids_rgb"}}, current) is True
    assert _has_camera_changes({"event_camera": {"type": "ids_evs"}}, current) is True
    # Same value does not trigger
    assert _has_camera_changes({"still_camera": {"type": "arducam_64mp"}}, current) is False
    assert _has_camera_changes({"still_camera": {"exposure_us": 0}}, current) is False
    # Non-camera sections never trigger
    assert _has_camera_changes({"upload": {"interval_minutes": 30}}, current) is False
    assert _has_camera_changes({}, current) is False


async def test_config_put_triggers_camera_reload(config, components, aiohttp_client):
    """PUT with camera config triggers reload (doesn't crash even without hw)."""
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.put("/api/config", json={
        "config": {"still_camera": {"type": "ids_rgb", "gamma": 0.8}}
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["config"]["still_camera"]["type"] == "ids_rgb"


async def test_config_put_no_reload_for_non_camera_change(config, components, aiohttp_client):
    """PUT without camera keys does not trigger reload."""
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.put("/api/config", json={
        "config": {"upload": {"interval_minutes": 30}}
    })
    assert resp.status == 200


def test_has_restart_required_changes():
    from bugsi_daemon.web.routes_api import _has_restart_required_changes
    current = {
        "zigbee": {"serial_port": "auto", "adapter": "ezsp"},
        "lte": {"gpio_pin": 26},
        "storage": {"buffer_db_path": "/old/path", "backup_path": "/old/backup",
                     "cleanup_after_days": 30, "backup_interval_minutes": 60},
        "webserver": {"enabled": True, "host": "0.0.0.0", "port": 8080,
                       "camera_fps": 2, "detections_dir": "/det"},
        "image_capture": {"enabled": True, "save_dir": "/old/dir", "cooldown_seconds": 10},
        "power": {"battery": False, "wlan_timeout_minutes": 10},
        "upload": {"interval_minutes": 60},
    }
    # Whole sections that require restart — value actually changed
    assert _has_restart_required_changes({"zigbee": {"serial_port": "/dev/ttyUSB1"}}, current) is True
    assert _has_restart_required_changes({"lte": {"gpio_pin": 17}}, current) is True
    # Specific keys within sections — value actually changed
    assert _has_restart_required_changes({"storage": {"buffer_db_path": "/new/path"}}, current) is True
    assert _has_restart_required_changes({"storage": {"backup_path": "/new/backup"}}, current) is True
    assert _has_restart_required_changes({"webserver": {"enabled": False}}, current) is True
    assert _has_restart_required_changes({"webserver": {"host": "127.0.0.1"}}, current) is True
    assert _has_restart_required_changes({"webserver": {"port": 9090}}, current) is True
    assert _has_restart_required_changes({"image_capture": {"enabled": False}}, current) is True
    assert _has_restart_required_changes({"image_capture": {"save_dir": "/new/dir"}}, current) is True
    assert _has_restart_required_changes({"power": {"battery": True}}, current) is True
    # Same values — no restart needed
    assert _has_restart_required_changes({"zigbee": {"serial_port": "auto"}}, current) is False
    assert _has_restart_required_changes({"lte": {"gpio_pin": 26}}, current) is False
    assert _has_restart_required_changes({"webserver": {"port": 8080}}, current) is False
    assert _has_restart_required_changes({"storage": {"buffer_db_path": "/old/path"}}, current) is False
    # Dynamic keys do NOT require restart even if changed
    assert _has_restart_required_changes({"storage": {"cleanup_after_days": 7}}, current) is False
    assert _has_restart_required_changes({"storage": {"backup_interval_minutes": 30}}, current) is False
    assert _has_restart_required_changes({"webserver": {"camera_fps": 5}}, current) is False
    assert _has_restart_required_changes({"webserver": {"detections_dir": "/tmp"}}, current) is False
    assert _has_restart_required_changes({"image_capture": {"cooldown_seconds": 30}}, current) is False
    assert _has_restart_required_changes({"power": {"wlan_timeout_minutes": 5}}, current) is False
    assert _has_restart_required_changes({"upload": {"interval_minutes": 30}}, current) is False
    assert _has_restart_required_changes({}, current) is False


async def test_config_put_restart_pending_for_zigbee(config, components, aiohttp_client):
    """PUT with zigbee config returns restart_pending=True."""
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.put("/api/config", json={
        "config": {"zigbee": {"serial_port": "/dev/ttyUSB1"}}
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["restart_pending"] is True


async def test_config_put_no_restart_for_dynamic_keys(config, components, aiohttp_client):
    """PUT with only dynamic keys returns restart_pending=False."""
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.put("/api/config", json={
        "config": {"upload": {"interval_minutes": 15}}
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["restart_pending"] is False


async def test_restart_endpoint_no_scheduler(config, components, aiohttp_client):
    """POST /api/restart returns 503 when no scheduler is available."""
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.post("/api/restart")
    assert resp.status == 503
    data = await resp.json()
    assert "error" in data


async def test_restart_endpoint_with_scheduler(config, components, aiohttp_client):
    """POST /api/restart schedules a restart when scheduler is available."""
    restart_called = []

    class FakeScheduler:
        async def request_restart(self):
            restart_called.append(True)

    components["scheduler"] = FakeScheduler()
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.post("/api/restart")
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "restart_scheduled"


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


# --- Credentials endpoints ---


@pytest.fixture
def config_with_creds(tmp_path):
    default_path = tmp_path / "default.json"
    default_path.write_text(json.dumps({
        "webserver": {"enabled": True, "host": "127.0.0.1", "port": 0, "camera_fps": 1,
                      "detections_dir": str(tmp_path / "detections")},
        "power": {"battery": False, "wlan_timeout_minutes": 10},
    }))
    cred_path = tmp_path / "cred.json"
    cred_path.write_text(json.dumps({
        "api_key": "bugsi_test_key_123",
        "api_url": "http://test:8000/api/device-data",
    }))
    cm = ConfigManager(
        default_config_path=default_path,
        local_config_path=str(tmp_path / "local.json"),
        credentials_path=str(cred_path),
    )
    cm.load()
    return cm


async def test_credentials_get_no_creds(config, components, aiohttp_client):
    """GET /api/credentials with unconfigured device."""
    server = WebServer(config=config, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/credentials")
    assert resp.status == 200
    data = await resp.json()
    assert data["api_url"] == ""
    assert data["api_key_masked"] == ""
    assert data["is_configured"] is False


async def test_credentials_get_masked_key(config_with_creds, components, aiohttp_client):
    """GET /api/credentials returns masked API key."""
    server = WebServer(config=config_with_creds, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/credentials")
    assert resp.status == 200
    data = await resp.json()
    assert data["api_url"] == "http://test:8000/api/device-data"
    assert data["api_key_masked"] == "****_123"
    assert data["is_configured"] is True


async def test_credentials_put_url(config_with_creds, components, aiohttp_client):
    """PUT /api/credentials updates the URL."""
    server = WebServer(config=config_with_creds, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.put("/api/credentials", json={
        "api_url": "http://new-host:9000/api/device-data",
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["api_url"] == "http://new-host:9000/api/device-data"
    assert data["is_configured"] is True
    assert config_with_creds.api_url == "http://new-host:9000/api/device-data"


async def test_credentials_put_recreates_client(config_with_creds, components, aiohttp_client):
    """PUT /api/credentials replaces the BugsiClient in components."""
    from bugsi_daemon.net.client import BugsiClient

    old_client = BugsiClient("http://old:8000/api/device-data", "old_key")
    components["client"] = old_client

    server = WebServer(config=config_with_creds, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.put("/api/credentials", json={
        "api_url": "http://new:9000/api/device-data",
    })
    assert resp.status == 200
    assert components["client"] is not old_client
    old_client.close()


async def test_credentials_put_invalid_json(config_with_creds, components, aiohttp_client):
    server = WebServer(config=config_with_creds, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.put("/api/credentials", data=b"not json",
                            headers={"Content-Type": "application/json"})
    assert resp.status == 400


async def test_credentials_put_empty_url(config_with_creds, components, aiohttp_client):
    server = WebServer(config=config_with_creds, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.put("/api/credentials", json={"api_url": ""})
    assert resp.status == 400


async def test_credentials_put_missing_fields(config_with_creds, components, aiohttp_client):
    server = WebServer(config=config_with_creds, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.put("/api/credentials", json={})
    assert resp.status == 400


async def test_credentials_put_with_api_key(config_with_creds, components, aiohttp_client):
    """PUT /api/credentials with both url and key updates both."""
    server = WebServer(config=config_with_creds, components=components)
    app = server._create_app()
    client = await aiohttp_client(app)

    resp = await client.put("/api/credentials", json={
        "api_url": "https://prod:443/api/device-data",
        "api_key": "new_secret_key_456",
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["api_url"] == "https://prod:443/api/device-data"
    assert data["api_key_masked"] == "****_456"
    assert config_with_creds.api_key == "new_secret_key_456"
