from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiohttp import web

from bugsi_daemon.config import ConfigManager
from bugsi_daemon.web.routes_api import create_api_routes, install_web_log_handler
from bugsi_daemon.web.routes_camera import create_camera_routes

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


class WebServer:
    """Local device webserver using aiohttp."""

    def __init__(
        self,
        config: ConfigManager,
        components: dict,
        on_request_callback=None,
    ):
        self._config = config
        self._components = components
        self._on_request_callback = on_request_callback
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._running = False
        self._shutting_down = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._running

    def _create_app(self) -> web.Application:
        install_web_log_handler()
        app = web.Application(middlewares=[self._activity_middleware])

        # Make shutdown event available to route handlers
        self._components["_shutdown_event"] = self._shutting_down

        # API routes
        api_routes = create_api_routes(self._config, self._components)
        app.router.add_routes(api_routes)

        # Camera routes
        camera_routes = create_camera_routes(self._config, self._components)
        app.router.add_routes(camera_routes)

        # Static files
        if STATIC_DIR.exists():
            app.router.add_static("/", STATIC_DIR, name="static", show_index=True)

        return app

    @web.middleware
    async def _activity_middleware(self, request: web.Request, handler):
        if self._on_request_callback:
            self._on_request_callback()
        return await handler(request)

    async def start(self) -> None:
        """Start the web server."""
        host = self._config.get("webserver.host", "0.0.0.0")
        port = self._config.get("webserver.port", 8080)

        app = self._create_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host, port)
        await self._site.start()
        self._running = True
        logger.info("Web server started on %s:%d", host, port)

    async def stop(self) -> None:
        """Stop the web server."""
        # Signal streaming handlers to exit before tearing down the server
        self._shutting_down.set()
        await asyncio.sleep(0.2)  # give streams a moment to finish

        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
        self._running = False
        logger.info("Web server stopped")
