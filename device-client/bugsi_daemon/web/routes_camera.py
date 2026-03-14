from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from bugsi_daemon.config import ConfigManager

logger = logging.getLogger(__name__)


def create_camera_routes(config: ConfigManager, components: dict) -> list[web.RouteDef]:
    """Create camera-related route definitions."""
    routes = web.RouteTableDef()

    def _get_camera():
        return components.get("web_camera")

    @routes.get("/api/camera/snapshot")
    async def camera_snapshot(request: web.Request) -> web.Response:
        camera = _get_camera()
        if camera is None:
            return web.json_response({"error": "No camera available"}, status=503)

        try:
            image_bytes = await camera.capture_jpeg()
            return web.Response(body=image_bytes, content_type="image/jpeg")
        except Exception:
            logger.exception("Snapshot capture failed")
            return web.json_response({"error": "Capture failed"}, status=500)

    @routes.get("/api/camera/stream")
    async def camera_stream(request: web.Request) -> web.StreamResponse:
        camera = _get_camera()
        if camera is None:
            return web.json_response({"error": "No camera available"}, status=503)

        fps = config.get("webserver.camera_fps", 2)
        interval = 1.0 / max(fps, 1)

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "multipart/x-mixed-replace; boundary=frame",
                "Cache-Control": "no-cache",
            },
        )
        await response.prepare(request)

        try:
            while True:
                try:
                    image_bytes = await camera.capture_jpeg()
                except Exception:
                    logger.exception("Stream capture failed")
                    break

                await response.write(
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + image_bytes
                    + b"\r\n"
                )
                await asyncio.sleep(interval)
        except (ConnectionResetError, asyncio.CancelledError):
            pass

        return response

    return routes
