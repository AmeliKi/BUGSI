from __future__ import annotations

import asyncio
import collections
import json
import logging
from pathlib import Path

from aiohttp import web

from bugsi_daemon.config import ConfigManager

logger = logging.getLogger(__name__)

# In-memory ring buffer for recent log entries (accessible via /api/logs)
_LOG_BUFFER: collections.deque[dict] = collections.deque(maxlen=500)


class WebLogHandler(logging.Handler):
    """Logging handler that stores records in a ring buffer for the web UI."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _LOG_BUFFER.append({
                "ts": self.format(record).split(" ")[0] if " " in self.format(record) else "",
                "time": record.created,
                "level": record.levelname,
                "name": record.name,
                "message": record.getMessage(),
            })
        except Exception:
            pass


def install_web_log_handler() -> None:
    """Install the ring buffer log handler on the root logger."""
    handler = WebLogHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s"))
    logging.getLogger("bugsi_daemon").addHandler(handler)


_CAMERA_CONFIG_KEYS = {
    "still_camera.type", "still_camera.resolution_width", "still_camera.resolution_height",
    "still_camera.exposure_us", "still_camera.gain_db", "still_camera.white_balance",
    "still_camera.balance_ratio_red", "still_camera.balance_ratio_green",
    "still_camera.balance_ratio_blue", "still_camera.gamma", "still_camera.black_level",
    "still_camera.acquisition_frame_rate", "still_camera.binning_horizontal",
    "still_camera.binning_vertical", "still_camera.camera_id", "still_camera.jpeg_quality",
    "event_camera.type", "event_camera.device_path", "event_camera.event_threshold",
    "event_camera.detection_window_ms", "event_camera.min_cluster_area",
    "event_camera.jpeg_quality",
}


def _has_camera_changes(config_data: dict, current: dict) -> bool:
    """Check if a config update actually changes camera-related values."""
    for section in ("still_camera", "event_camera"):
        new_sec = config_data.get(section)
        if not isinstance(new_sec, dict):
            continue
        cur_sec = current.get(section, {})
        for key, val in new_sec.items():
            if cur_sec.get(key) != val:
                return True
    return False


async def _trigger_camera_reload(config: ConfigManager, components: dict) -> None:
    """Reload cameras if hw dict is available in components."""
    hw = components.get("hw")
    if hw is None:
        return
    try:
        from bugsi_daemon.cli import reload_cameras
        await reload_cameras(
            config=config,
            components=components,
            hw=hw,
            image_pipeline=components.get("image_pipeline"),
            mock=components.get("mock", False),
        )
    except Exception:
        logger.warning("Camera reload failed", exc_info=True)


# Config sections/keys whose changes require a full daemon restart because
# the values are read once at init and stored in instance variables.
_RESTART_SECTIONS = {"zigbee", "lte"}
_RESTART_KEYS_IN_SECTION: dict[str, set[str]] = {
    "storage": {"buffer_db_path", "backup_path"},
    "webserver": {"enabled", "host", "port"},
    "image_capture": {"enabled", "save_dir"},
    "power": {"battery"},
}


def _has_restart_required_changes(config_data: dict, current: dict) -> bool:
    """Check if a config update actually changes values that require a daemon restart."""
    for section in _RESTART_SECTIONS:
        new_sec = config_data.get(section)
        if not isinstance(new_sec, dict):
            continue
        cur_sec = current.get(section, {})
        for key, val in new_sec.items():
            if cur_sec.get(key) != val:
                return True
    for section, keys in _RESTART_KEYS_IN_SECTION.items():
        new_sec = config_data.get(section)
        if not isinstance(new_sec, dict):
            continue
        cur_sec = current.get(section, {})
        for k in keys:
            if k in new_sec and new_sec[k] != cur_sec.get(k):
                return True
    return False


async def _schedule_restart(components: dict, delay: float = 2.0) -> None:
    """Schedule a graceful daemon restart after *delay* seconds.

    The delay gives time for the HTTP response to be sent before the
    daemon stops.  systemd ``Restart=always`` will bring it back up.
    """
    scheduler = components.get("scheduler")
    if scheduler is None:
        logger.warning("Cannot restart: scheduler not available in components")
        return
    logger.info("Daemon restart scheduled in %.0fs (config change requires restart)", delay)
    await asyncio.sleep(delay)
    await scheduler.request_restart()


def create_api_routes(config: ConfigManager, components: dict) -> list[web.RouteDef]:
    """Create API route definitions."""
    routes = web.RouteTableDef()

    @routes.get("/api/config")
    async def get_config(request: web.Request) -> web.Response:
        return web.json_response({
            "config": config.get_all(),
            "version": config.version,
        })

    @routes.put("/api/config")
    async def update_config(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        config_data = body.get("config")
        if not isinstance(config_data, dict):
            return web.json_response({"error": "Missing or invalid 'config' field"}, status=400)

        current = config.get_all()
        needs_camera_reload = _has_camera_changes(config_data, current)
        needs_restart = _has_restart_required_changes(config_data, current)
        new_version = config.apply_local(config_data)

        # Reload cameras if camera config changed (and no full restart pending)
        if needs_camera_reload and not needs_restart:
            await _trigger_camera_reload(config, components)

        # Try to push to SaaS immediately
        client = components.get("client")
        push_result = None
        if client and config.is_configured:
            try:
                push_result = client.push_config(config.get_all(), new_version)
                config.clear_unpushed()
                logger.info("Config pushed to SaaS successfully")
            except Exception:
                logger.warning("Failed to push config to SaaS, will retry on next upload")

        # Schedule restart after sending response
        if needs_restart:
            asyncio.ensure_future(_schedule_restart(components))

        return web.json_response({
            "version": new_version,
            "config": config.get_all(),
            "pushed_to_saas": push_result is not None,
            "restart_pending": needs_restart,
        })

    @routes.post("/api/config/pull")
    async def pull_config(request: web.Request) -> web.Response:
        """Pull latest config from SaaS backend."""
        client = components.get("client")
        if not client or not config.is_configured:
            return web.json_response(
                {"error": "Not connected to SaaS (no API key/URL configured)"},
                status=503,
            )

        try:
            result = client.poll_config()
        except Exception as exc:
            logger.warning("Failed to poll config from SaaS: %s", exc)
            return web.json_response(
                {"error": f"Failed to reach SaaS: {exc}"},
                status=502,
            )

        if result.get("has_update"):
            version = result["version"]
            config_data = result["config"]
            current = config.get_all()
            changed = config.apply_remote(config_data, version)
            if changed:
                try:
                    client.ack_config(version)
                except Exception:
                    logger.warning("Config applied but ack failed")

                needs_restart = _has_restart_required_changes(config_data, current)
                if _has_camera_changes(config_data, current) and not needs_restart:
                    await _trigger_camera_reload(config, components)
                if needs_restart:
                    asyncio.ensure_future(_schedule_restart(components))

                return web.json_response({
                    "status": "updated",
                    "version": version,
                    "config": config.get_all(),
                    "restart_pending": needs_restart,
                })
            return web.json_response({
                "status": "already_current",
                "version": config.version,
                "config": config.get_all(),
            })
        else:
            return web.json_response({
                "status": "no_update",
                "version": config.version,
                "config": config.get_all(),
            })

    @routes.get("/api/status")
    async def get_status(request: web.Request) -> web.Response:
        buffer = components.get("buffer")
        power_manager = components.get("power_manager")
        wlan = components.get("wlan")

        status = {
            "config_version": config.version,
            "api_configured": config.is_configured,
        }

        if buffer:
            try:
                stats = await buffer.get_stats()
                status["buffer"] = stats
            except Exception:
                status["buffer"] = "error"

        if power_manager:
            status["power_mode"] = power_manager.mode.value

        if wlan:
            status["wlan_enabled"] = wlan.is_enabled()

        return web.json_response(status)

    @routes.post("/api/restart")
    async def restart_daemon(request: web.Request) -> web.Response:
        """Trigger a graceful daemon restart."""
        scheduler = components.get("scheduler")
        if scheduler is None:
            return web.json_response(
                {"error": "Scheduler not available (restart not supported)"},
                status=503,
            )
        asyncio.ensure_future(_schedule_restart(components))
        return web.json_response({"status": "restart_scheduled"})

    @routes.get("/api/logs")
    async def get_logs(request: web.Request) -> web.Response:
        level = request.query.get("level", "").upper()
        limit = int(request.query.get("limit", "200"))
        entries = list(_LOG_BUFFER)
        if level:
            entries = [e for e in entries if e["level"] == level]
        entries = entries[-limit:]
        return web.json_response({"logs": entries, "total": len(_LOG_BUFFER)})

    @routes.get("/api/gallery")
    async def list_gallery(request: web.Request) -> web.Response:
        detections_dir = config.get(
            "webserver.detections_dir",
            "/opt/bugsi/insect-detector/detections",
        )
        jsonl_path = Path(detections_dir) / "detections.jsonl"

        limit = int(request.query.get("limit", "50"))
        offset = int(request.query.get("offset", "0"))

        detections = []
        if jsonl_path.exists():
            with open(jsonl_path) as f:
                lines = f.readlines()

            # Read in reverse (newest first)
            lines.reverse()
            for line in lines[offset : offset + limit]:
                line = line.strip()
                if line:
                    try:
                        detections.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        # Also list crop images directly if no JSONL
        crops_dir = Path(detections_dir) / "crops"
        crops = []
        if crops_dir.exists():
            image_files = sorted(crops_dir.glob("*.jpg"), reverse=True)
            for img in image_files[offset : offset + limit]:
                crops.append({
                    "filename": img.name,
                    "path": f"/api/gallery/image/crops/{img.name}",
                    "size_bytes": img.stat().st_size,
                })

        return web.json_response({
            "detections": detections,
            "crops": crops,
            "total_crops": len(list(crops_dir.glob("*.jpg"))) if crops_dir.exists() else 0,
        })

    @routes.get("/api/gallery/image/{subdir}/{filename}")
    async def serve_gallery_image(request: web.Request) -> web.Response:
        detections_dir = config.get(
            "webserver.detections_dir",
            "/opt/bugsi/insect-detector/detections",
        )
        subdir = request.match_info["subdir"]
        filename = request.match_info["filename"]

        # Path traversal prevention
        if ".." in subdir or ".." in filename or "/" in filename:
            return web.json_response({"error": "Invalid path"}, status=400)
        if subdir not in ("crops", "frames"):
            return web.json_response({"error": "Invalid directory"}, status=400)

        file_path = Path(detections_dir) / subdir / filename
        if not file_path.exists():
            return web.json_response({"error": "Not found"}, status=404)

        return web.FileResponse(file_path)

    @routes.get("/api/credentials")
    async def get_credentials(request: web.Request) -> web.Response:
        key = config.api_key
        if len(key) > 4:
            masked = "****" + key[-4:]
        elif key:
            masked = "****"
        else:
            masked = ""
        return web.json_response({
            "api_url": config.api_url,
            "api_key_masked": masked,
            "is_configured": config.is_configured,
        })

    @routes.put("/api/credentials")
    async def update_credentials(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        api_url = body.get("api_url")
        api_key = body.get("api_key")

        if api_url is not None and not isinstance(api_url, str):
            return web.json_response({"error": "'api_url' must be a string"}, status=400)
        if api_url is not None and not api_url.strip():
            return web.json_response({"error": "'api_url' must not be empty"}, status=400)
        if api_key is not None and not isinstance(api_key, str):
            return web.json_response({"error": "'api_key' must be a string"}, status=400)
        if api_url is None and api_key is None:
            return web.json_response({"error": "Provide 'api_url' and/or 'api_key'"}, status=400)

        config.save_credentials(api_key=api_key, api_url=api_url)

        # Recreate BugsiClient with new credentials
        from bugsi_daemon.net.client import BugsiClient

        old_client = components.get("client")
        if old_client is not None:
            try:
                old_client.close()
            except Exception:
                pass
        new_client = BugsiClient(config.api_url, config.api_key)
        components["client"] = new_client

        # Update UploadCycle client reference so no restart is needed
        upload = components.get("upload")
        if upload is not None:
            upload._client = new_client

        key = config.api_key
        if len(key) > 4:
            masked = "****" + key[-4:]
        elif key:
            masked = "****"
        else:
            masked = ""

        return web.json_response({
            "api_url": config.api_url,
            "api_key_masked": masked,
            "is_configured": config.is_configured,
        })

    return routes
