from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

from bugsi_daemon.config import ConfigManager
from bugsi_daemon.core.power_manager import PowerManager
from bugsi_daemon.core.telemetry_collector import TelemetryCollector
from bugsi_daemon.core.upload_cycle import UploadCycle
from bugsi_daemon.buffer.backup import BufferBackup
from bugsi_daemon.buffer.store import BufferStore
from bugsi_daemon.net.client import BugsiClient

logger = logging.getLogger(__name__)


def _mock_fallbacks() -> dict:
    """Import and return mock hardware classes keyed by component name."""
    from bugsi_daemon.hardware_mock.battery import MockBattery
    from bugsi_daemon.hardware_mock.solar import MockSolar
    from bugsi_daemon.hardware_mock.climate import MockClimate
    from bugsi_daemon.hardware_mock.lte import MockLteModem
    from bugsi_daemon.hardware_mock.storage import MockStorage
    from bugsi_daemon.hardware_mock.system import MockSystem
    from bugsi_daemon.hardware_mock.power_mgmt import MockPowerManagement
    from bugsi_daemon.hardware_mock.wlan import MockWlan
    from bugsi_daemon.hardware_mock.camera import MockCamera
    return {
        "battery": MockBattery,
        "solar": MockSolar,
        "climate": MockClimate,
        "lte": MockLteModem,
        "storage": MockStorage,
        "system": MockSystem,
        "power_mgmt": MockPowerManagement,
        "wlan": MockWlan,
        "camera": MockCamera,
    }


def create_hardware(mock: bool, config: ConfigManager | None = None) -> dict:
    """Create hardware instances (mock or real)."""
    fallbacks = _mock_fallbacks()
    if mock:
        return {name: cls() for name, cls in fallbacks.items()}

    from bugsi_daemon.hardware.battery import VictronSmartShunt
    from bugsi_daemon.hardware.solar import VictronSmartSolar
    from bugsi_daemon.hardware.climate import ZigbeeClimateSensor
    from bugsi_daemon.hardware.lte import SixfabLteModem
    from bugsi_daemon.hardware.storage import UsbStorageMonitor
    from bugsi_daemon.hardware.system import SystemMonitor
    from bugsi_daemon.hardware.power_mgmt import WittyPiPowerManager
    from bugsi_daemon.hardware.wlan import SystemWlan
    try:
        from bugsi_daemon.hardware.camera import ArducamCamera
        camera = ArducamCamera(
            resolution_width=config.get("camera.resolution_width", 3840) if config else 3840,
            resolution_height=config.get("camera.resolution_height", 2160) if config else 2160,
            camera_id=config.get("camera.camera_id", 0) if config else 0,
            autofocus_mode=config.get("camera.autofocus_mode", "continuous") if config else "continuous",
        )
    except ImportError:
        camera = fallbacks["camera"]()
    return {
        "battery": VictronSmartShunt(),
        "solar": VictronSmartSolar(),
        "climate": ZigbeeClimateSensor(),
        "lte": SixfabLteModem(),
        "storage": UsbStorageMonitor(),
        "system": SystemMonitor(),
        "power_mgmt": WittyPiPowerManager(),
        "wlan": SystemWlan(),
        "camera": camera,
    }


async def init_components(config: ConfigManager, mock: bool) -> dict:
    """Initialize all components and return them as a dict."""
    hw = create_hardware(mock, config)
    fallbacks = _mock_fallbacks()

    # Initialize all sensors, falling back to mock if real driver not implemented
    for name, sensor in list(hw.items()):
        if hasattr(sensor, "initialize"):
            try:
                await sensor.initialize()
            except NotImplementedError:
                logger.warning("%s: real driver not implemented, using mock", name)
                hw[name] = fallbacks[name]()
                await hw[name].initialize()

    # Buffer - use temp path if configured path's parent doesn't exist (dev machine)
    db_path = config.get("storage.buffer_db_path", "/tmp/bugsi_buffer.db")
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        import tempfile
        db_path = os.path.join(tempfile.gettempdir(), "bugsi_buffer.db")
        logger.info("Buffer DB path unavailable, using %s", db_path)
    buffer = BufferStore(db_path)
    await buffer.initialize()

    # Backup
    backup_path = config.get("storage.backup_path", "/tmp/bugsi_backup/")
    backup = BufferBackup(db_path, backup_path)

    # Client
    client = BugsiClient(config.api_url, config.api_key)

    # Telemetry collector
    telemetry = TelemetryCollector(
        buffer=buffer,
        battery=hw["battery"],
        solar=hw["solar"],
        climate=hw["climate"],
        storage=hw["storage"],
        system=hw["system"],
        lte=hw["lte"],
    )

    # Power manager
    power_manager = PowerManager(
        config=config,
        lte=hw["lte"],
        power_mgmt=hw["power_mgmt"],
        backup=backup,
    )

    # Upload cycle
    upload = UploadCycle(
        client=client,
        buffer=buffer,
        config=config,
        power_manager=power_manager,
        telemetry_collector=telemetry,
    )

    # Mock thumbnail generator (only in mock mode)
    thumbnail_generator = None
    if mock:
        from bugsi_daemon.core.mock_thumbnail_generator import MockThumbnailGenerator
        thumbnail_dir = os.path.join(os.path.dirname(db_path), "thumbnails")
        thumbnail_generator = MockThumbnailGenerator(buffer=buffer, thumbnail_dir=thumbnail_dir)

    # Web server + WLAN manager
    web_server = None
    wlan_manager = None
    if config.get("webserver.enabled", True):
        from bugsi_daemon.web.server import WebServer
        from bugsi_daemon.web.wlan_manager import WlanManager

        wlan_manager = WlanManager(config=config, wlan=hw["wlan"])

        boot_type = await hw["power_mgmt"].get_wakeup_reason()
        should_start_web = await wlan_manager.start(boot_type)

        if should_start_web:
            # Create camera for live view
            web_camera = None
            try:
                from bugsi_daemon.web.camera import WebCamera
                camera = hw.get("camera")
                if camera is not None:
                    jpeg_quality = config.get("camera.jpeg_quality", 85)
                    web_camera = WebCamera(camera, jpeg_quality=jpeg_quality)
            except Exception:
                logger.warning("Could not initialize camera for webserver, live view disabled", exc_info=True)

            web_server = WebServer(
                config=config,
                components={
                    "buffer": buffer,
                    "client": client,
                    "power_manager": power_manager,
                    "web_camera": web_camera,
                    "wlan": hw["wlan"],
                },
                on_request_callback=wlan_manager.reset_timer,
            )

    return {
        "hw": hw,
        "buffer": buffer,
        "backup": backup,
        "client": client,
        "telemetry": telemetry,
        "power_manager": power_manager,
        "upload": upload,
        "thumbnail_generator": thumbnail_generator,
        "web_server": web_server,
        "wlan_manager": wlan_manager,
    }


async def cmd_telemetry(config: ConfigManager, mock: bool) -> None:
    """Collect and print one telemetry reading."""
    components = await init_components(config, mock)
    try:
        reading = await components["telemetry"].collect()
        print(json.dumps(reading, indent=2))
    finally:
        await components["buffer"].close()
        components["client"].close()


async def cmd_upload(config: ConfigManager, mock: bool) -> None:
    """Run one upload cycle immediately."""
    components = await init_components(config, mock)
    try:
        # Generate a mock thumbnail (guaranteed for one-shot upload)
        thumbnail_gen = components.get("thumbnail_generator")
        if thumbnail_gen:
            await thumbnail_gen.maybe_generate(probability=1.0)

        # Collect telemetry (includes pictures_taken count)
        extra = {}
        if thumbnail_gen:
            extra["pictures_taken"] = thumbnail_gen.pictures_taken
        reading = await components["telemetry"].collect(extra=extra)
        soc = reading.get("battery_soc")
        print(f"Battery SoC: {soc}%")

        success = await components["upload"].run(last_battery_soc=soc)
        if success:
            print("Upload cycle completed successfully")
        else:
            print("Upload cycle skipped or failed")
    finally:
        await components["buffer"].close()
        components["client"].close()


async def cmd_status(config: ConfigManager, mock: bool) -> None:
    """Show buffer stats, config version, and power mode."""
    components = await init_components(config, mock)
    try:
        stats = await components["buffer"].get_stats()
        print(f"Config version: {config.version}")
        print(f"Power mode: {components['power_manager'].mode.value}")
        print(f"API URL: {config.api_url}")
        print()
        print("Buffer statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    finally:
        await components["buffer"].close()
        components["client"].close()


async def cmd_config(config: ConfigManager, _mock: bool) -> None:
    """Show current configuration."""
    print(f"Version: {config.version}")
    print(json.dumps(config.get_all(), indent=2))
