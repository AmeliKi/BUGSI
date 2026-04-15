from __future__ import annotations

import asyncio
import logging
import time

from aiohttp import web

from bugsi_daemon.config import ConfigManager

logger = logging.getLogger(__name__)

# Exceptions that indicate the client disconnected or the server is shutting down.
# These are expected during MJPEG streaming and should be silently ignored.
_STREAM_CLOSED = (
    ConnectionResetError,
    ConnectionAbortedError,
    BrokenPipeError,
    asyncio.CancelledError,
    asyncio.InvalidStateError,
)


def create_camera_routes(config: ConfigManager, components: dict) -> list[web.RouteDef]:
    """Create camera-related route definitions."""
    routes = web.RouteTableDef()

    # Live FPS counters updated by active streams
    fps_counters: dict[str, float] = {"still": 0.0, "event": 0.0}

    def _get_camera():
        return components.get("web_camera")

    def _get_event_camera():
        return components.get("web_event_camera")

    def _is_shutting_down() -> bool:
        ev = components.get("_shutdown_event")
        return ev is not None and ev.is_set()

    # --- Still camera endpoints ---

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

        fps = config.get("webserver.camera_fps", 10)
        interval = 1.0 / max(fps, 1)

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "multipart/x-mixed-replace; boundary=frame",
                "Cache-Control": "no-cache",
            },
        )
        await response.prepare(request)

        await camera.notify_stream_start(fps)
        try:
            last_time = time.monotonic()
            while not _is_shutting_down():
                cycle_start = time.monotonic()

                try:
                    image_bytes = await camera.get_cached_jpeg()
                except Exception:
                    logger.exception("Stream capture failed")
                    break

                now = time.monotonic()
                dt = now - last_time
                if dt > 0:
                    fps_counters["still"] = 1.0 / dt
                last_time = now

                try:
                    await response.write(
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + image_bytes
                        + b"\r\n"
                    )
                except _STREAM_CLOSED:
                    break

                # Adaptive sleep: subtract time already spent capturing/writing
                elapsed = time.monotonic() - cycle_start
                remaining = interval - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
        except _STREAM_CLOSED:
            pass
        finally:
            await camera.notify_stream_stop()

        fps_counters["still"] = 0.0
        return response

    # --- Event camera endpoints ---

    @routes.get("/api/camera/event/snapshot")
    async def event_camera_snapshot(request: web.Request) -> web.Response:
        camera = _get_event_camera()
        if camera is None:
            return web.json_response({"error": "No event camera available"}, status=503)

        try:
            image_bytes = await camera.capture_jpeg()
            return web.Response(body=image_bytes, content_type="image/jpeg")
        except Exception:
            logger.exception("Event camera snapshot failed")
            return web.json_response({"error": "Capture failed"}, status=500)

    @routes.get("/api/camera/event/stream")
    async def event_camera_stream(request: web.Request) -> web.StreamResponse:
        camera = _get_event_camera()
        if camera is None:
            return web.json_response({"error": "No event camera available"}, status=503)

        fps = config.get("webserver.camera_fps", 10)
        interval = 1.0 / max(fps, 1)

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "multipart/x-mixed-replace; boundary=frame",
                "Cache-Control": "no-cache",
            },
        )
        await response.prepare(request)

        await camera.notify_stream_start(fps)
        try:
            last_time = time.monotonic()
            while not _is_shutting_down():
                cycle_start = time.monotonic()

                try:
                    image_bytes = await camera.get_cached_jpeg()
                except Exception:
                    logger.exception("Event stream capture failed")
                    break

                now = time.monotonic()
                dt = now - last_time
                if dt > 0:
                    fps_counters["event"] = 1.0 / dt
                last_time = now

                try:
                    await response.write(
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + image_bytes
                        + b"\r\n"
                    )
                except _STREAM_CLOSED:
                    break

                # Adaptive sleep: subtract time already spent capturing/writing
                elapsed = time.monotonic() - cycle_start
                remaining = interval - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
        except _STREAM_CLOSED:
            pass
        finally:
            await camera.notify_stream_stop()

        fps_counters["event"] = 0.0
        return response

    # --- Camera info endpoint ---

    @routes.get("/api/camera/info")
    async def camera_info(request: web.Request) -> web.Response:
        still_type = config.get("still_camera.type", "unknown")
        event_type = config.get("event_camera.type", "unknown")
        target_fps = config.get("webserver.camera_fps", 10)

        return web.json_response({
            "still_camera": {
                "available": _get_camera() is not None,
                "type": still_type,
                "fps": round(fps_counters["still"], 1),
            },
            "event_camera": {
                "available": _get_event_camera() is not None,
                "type": event_type,
                "fps": round(fps_counters["event"], 1),
            },
            "target_fps": target_fps,
        })

    return routes
