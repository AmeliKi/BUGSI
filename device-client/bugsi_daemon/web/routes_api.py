from __future__ import annotations

import json
import logging
from pathlib import Path

from aiohttp import web

from bugsi_daemon.config import ConfigManager

logger = logging.getLogger(__name__)


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

        new_version = config.apply_local(config_data)

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

        return web.json_response({
            "version": new_version,
            "config": config.get_all(),
            "pushed_to_saas": push_result is not None,
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

    return routes
