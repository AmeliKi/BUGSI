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
    from bugsi_daemon.hardware_mock.event_camera import MockEventCamera
    return {
        "battery": MockBattery,
        "solar": MockSolar,
        "climate": MockClimate,
        "lte": MockLteModem,
        "storage": MockStorage,
        "system": MockSystem,
        "power_mgmt": MockPowerManagement,
        "wlan": MockWlan,
        "still_camera": MockCamera,
        "event_camera": MockEventCamera,
    }


def _resolve_camera(config: ConfigManager, mock: bool) -> dict:
    """Resolve still and event cameras from registry based on config type."""
    from bugsi_daemon.hardware.base import (
        STILL_CAMERA_REGISTRY,
        EVENT_CAMERA_REGISTRY,
    )

    # Ensure drivers are imported so registrations happen
    # Real drivers register on import
    try:
        import bugsi_daemon.hardware.camera  # noqa: F401
    except ImportError:
        pass
    try:
        import bugsi_daemon.hardware.event_camera  # noqa: F401
    except ImportError:
        pass
    try:
        import bugsi_daemon.hardware.ids_camera  # noqa: F401
    except ImportError:
        pass
    try:
        import bugsi_daemon.hardware.ids_event_camera  # noqa: F401
    except ImportError:
        pass
    # Mock drivers also register
    import bugsi_daemon.hardware_mock.camera  # noqa: F401
    import bugsi_daemon.hardware_mock.event_camera  # noqa: F401

    cameras = {}

    # Still camera
    still_type = config.get("still_camera.type", "arducam_64mp") if config else "arducam_64mp"
    if mock:
        still_type = "mock"
    still_cls = STILL_CAMERA_REGISTRY.get(still_type)
    if still_cls is None:
        logger.warning("Still camera type '%s' not found in registry, using mock", still_type)
        still_cls = STILL_CAMERA_REGISTRY.get("mock")
    cameras["still_camera"] = still_cls(
        resolution_width=config.get("still_camera.resolution_width", 5136) if config else 5136,
        resolution_height=config.get("still_camera.resolution_height", 3856) if config else 3856,
        camera_id=config.get("still_camera.camera_id", 0) if config else 0,
        autofocus_mode=config.get("still_camera.autofocus_mode", "continuous") if config else "continuous",
        exposure_us=config.get("still_camera.exposure_us", 0) if config else 0,
        gain_db=config.get("still_camera.gain_db", 0.0) if config else 0.0,
        white_balance=config.get("still_camera.white_balance", "auto") if config else "auto",
        balance_ratio_red=config.get("still_camera.balance_ratio_red", 0.0) if config else 0.0,
        balance_ratio_green=config.get("still_camera.balance_ratio_green", 0.0) if config else 0.0,
        balance_ratio_blue=config.get("still_camera.balance_ratio_blue", 0.0) if config else 0.0,
        gamma=config.get("still_camera.gamma", 1.0) if config else 1.0,
        black_level=config.get("still_camera.black_level", 0.0) if config else 0.0,
        acquisition_frame_rate=config.get("still_camera.acquisition_frame_rate", 0.0) if config else 0.0,
        binning_horizontal=config.get("still_camera.binning_horizontal", 1) if config else 1,
        binning_vertical=config.get("still_camera.binning_vertical", 1) if config else 1,
    )

    # Event camera
    event_type = config.get("event_camera.type", "prophesee_genx320") if config else "prophesee_genx320"
    if mock:
        event_type = "mock"
    event_cls = EVENT_CAMERA_REGISTRY.get(event_type)
    if event_cls is None:
        logger.warning("Event camera type '%s' not found in registry, using mock", event_type)
        event_cls = EVENT_CAMERA_REGISTRY.get("mock")
    cameras["event_camera"] = event_cls(
        device_path=config.get("event_camera.device_path", "auto") if config else "auto",
        event_threshold=config.get("event_camera.event_threshold", 500) if config else 500,
        detection_window_ms=config.get("event_camera.detection_window_ms", 50) if config else 50,
        min_cluster_area=config.get("event_camera.min_cluster_area", 100) if config else 100,
    )

    return cameras


async def reload_cameras(
    config: ConfigManager,
    components: dict,
    hw: dict,
    image_pipeline=None,
    mock: bool = False,
) -> None:
    """Hot-reload cameras after a config change.

    Closes old cameras, creates new ones from the updated config, and swaps
    references in the components dict (used by web routes) and the image
    capture pipeline.
    """
    from bugsi_daemon.web.camera import CameraCoordinator, WebCamera, WebEventCamera

    # Stop background producers before closing cameras
    old_web_cam = components.get("web_camera")
    if old_web_cam is not None:
        try:
            await old_web_cam.stop_producer()
            old_web_cam.close()
        except Exception:
            logger.warning("Error closing old WebCamera", exc_info=True)

    old_web_ev = components.get("web_event_camera")
    if old_web_ev is not None:
        try:
            await old_web_ev.stop_producer()
            await old_web_ev.close()
        except Exception:
            logger.warning("Error closing old WebEventCamera", exc_info=True)

    # Close old raw cameras
    old_still = hw.get("still_camera")
    if old_still is not None and old_still is not getattr(old_web_cam, "_camera", None):
        try:
            old_still.close()
        except Exception:
            logger.warning("Error closing old still camera", exc_info=True)

    old_event = hw.get("event_camera")
    if old_event is not None and old_event is not getattr(old_web_ev, "_camera", None):
        try:
            await old_event.shutdown()
        except Exception:
            logger.warning("Error closing old event camera", exc_info=True)

    # Create new cameras from updated config
    cameras = _resolve_camera(config, mock=mock)
    hw.update(cameras)

    # Initialize event camera
    fallbacks = _mock_fallbacks()
    for name in ("still_camera", "event_camera"):
        sensor = hw[name]
        if hasattr(sensor, "initialize"):
            try:
                await sensor.initialize()
            except NotImplementedError:
                logger.warning("%s: real driver not implemented, using mock", name)
                hw[name] = fallbacks[name]()
                await hw[name].initialize()
                cameras[name] = hw[name]

    # Create coordinator for shared camera access
    coordinator = None
    still_cam = hw.get("still_camera")
    if still_cam is not None:
        coordinator = CameraCoordinator(still_cam)

    # Wrap for web
    try:
        if still_cam is not None:
            jpeg_quality = config.get("still_camera.jpeg_quality", 85)
            stream_width = config.get("webserver.stream_width", 960)
            components["web_camera"] = WebCamera(
                still_cam, jpeg_quality=jpeg_quality,
                stream_width=stream_width, coordinator=coordinator,
            )
        else:
            components["web_camera"] = None
    except Exception:
        logger.warning("Could not create new WebCamera", exc_info=True)
        components["web_camera"] = None

    try:
        event_cam = hw.get("event_camera")
        if event_cam is not None:
            jpeg_quality = config.get("event_camera.jpeg_quality", 85)
            components["web_event_camera"] = WebEventCamera(event_cam, jpeg_quality=jpeg_quality)
        else:
            components["web_event_camera"] = None
    except Exception:
        logger.warning("Could not create new WebEventCamera", exc_info=True)
        components["web_event_camera"] = None

    # Update image capture pipeline references
    if image_pipeline is not None:
        image_pipeline._still_camera = hw["still_camera"]
        image_pipeline._event_camera = hw["event_camera"]
        if coordinator is not None:
            image_pipeline._coordinator = coordinator

    logger.info(
        "Cameras reloaded: still=%s, event=%s",
        config.get("still_camera.type"),
        config.get("event_camera.type"),
    )


def create_hardware(mock: bool, config: ConfigManager | None = None) -> dict:
    """Create hardware instances (mock or real)."""
    fallbacks = _mock_fallbacks()
    if mock:
        hw = {name: cls() for name, cls in fallbacks.items()}
        # Override cameras from registry
        if config:
            cameras = _resolve_camera(config, mock=True)
            hw.update(cameras)
        return hw

    from bugsi_daemon.hardware.battery import VictronSmartShunt
    from bugsi_daemon.hardware.solar import VictronSmartSolar
    from bugsi_daemon.hardware.climate import ZigbeeClimateSensor
    from bugsi_daemon.hardware.lte import SixfabLteModem
    from bugsi_daemon.hardware.storage import UsbStorageMonitor
    from bugsi_daemon.hardware.system import SystemMonitor
    from bugsi_daemon.hardware.power_mgmt import WittyPiPowerManager
    from bugsi_daemon.hardware.wlan import SystemWlan

    hw = {
        "battery": VictronSmartShunt(),
        "solar": VictronSmartSolar(),
        "climate": ZigbeeClimateSensor(
            serial_port=config.get("zigbee.serial_port", "auto") if config else "auto",
            adapter=config.get("zigbee.adapter", "ezsp") if config else "ezsp",
            device_name=config.get("zigbee.device_name", "climate_sensor") if config else "climate_sensor",
            database_path=config.get("zigbee.database_path", "/var/cache/bugsi/zigbee.db") if config else "/var/cache/bugsi/zigbee.db",
            network_channel=config.get("zigbee.network_channel", 11) if config else 11,
            usb_hub=config.get("zigbee.usb_hub") if config else None,
            usb_port=config.get("zigbee.usb_port") if config else None,
        ),
        "lte": SixfabLteModem(
            serial_port=config.get("lte.serial_port") if config else None,
            gpio_pin=config.get("lte.gpio_pin", 26) if config else 26,
        ),
        "storage": UsbStorageMonitor(),
        "system": SystemMonitor(),
        "power_mgmt": WittyPiPowerManager(),
        "wlan": SystemWlan(),
    }

    # Resolve cameras from registry
    if config:
        cameras = _resolve_camera(config, mock=False)
        hw.update(cameras)
    else:
        # Fallback
        hw["still_camera"] = fallbacks["still_camera"]()
        hw["event_camera"] = fallbacks["event_camera"]()

    return hw


async def init_components(config: ConfigManager, mock: bool) -> dict:
    """Initialize all components and return them as a dict."""
    hw = create_hardware(mock, config)
    fallbacks = _mock_fallbacks()

    # Initialize all sensors in parallel, falling back to mock if real driver not implemented
    async def _init_sensor(name: str, sensor) -> None:
        try:
            await sensor.initialize()
        except NotImplementedError:
            logger.warning("%s: real driver not implemented, using mock", name)
            hw[name] = fallbacks[name]()
            await hw[name].initialize()

    init_tasks = [
        _init_sensor(name, sensor)
        for name, sensor in hw.items()
        if hasattr(sensor, "initialize")
    ]
    await asyncio.gather(*init_tasks)

    # Buffer - use temp path if configured path's parent doesn't exist (dev machine)
    db_path = config.get("storage.buffer_db_path", "/tmp/bugsi_buffer.db")
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        import tempfile
        db_path = os.path.join(tempfile.gettempdir(), "bugsi_buffer.db")
        logger.info("Buffer DB path unavailable, using %s", db_path)
    buffer = BufferStore(db_path)
    await buffer.initialize()

    # Backup - use temp path if configured path's parent doesn't exist (dev machine)
    backup_path = config.get("storage.backup_path", "/tmp/bugsi_backup/")
    backup_dir = os.path.dirname(backup_path.rstrip("/"))
    if backup_dir and not os.path.exists(backup_dir):
        import tempfile
        backup_path = os.path.join(tempfile.gettempdir(), "bugsi_backup")
        logger.info("Backup path unavailable, using %s", backup_path)
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
        wlan=hw["wlan"],
    )

    # Upload cycle
    upload = UploadCycle(
        client=client,
        buffer=buffer,
        config=config,
        power_manager=power_manager,
        telemetry_collector=telemetry,
        wlan=hw.get("wlan"),
    )

    # Camera coordinator for shared access between web stream and pipeline
    from bugsi_daemon.web.camera import CameraCoordinator
    coordinator = None
    still_cam = hw.get("still_camera")
    if still_cam is not None:
        coordinator = CameraCoordinator(still_cam)

    # Image capture pipeline
    image_pipeline = None
    if config.get("image_capture.enabled", True):
        from bugsi_daemon.core.image_capture_pipeline import ImageCapturePipeline
        save_dir = config.get("image_capture.save_dir", "/mnt/usb/bugsi/detections")
        # Use temp dir if save_dir doesn't exist (dev machine)
        if not os.path.exists(os.path.dirname(save_dir) if save_dir != "/" else save_dir):
            import tempfile
            save_dir = os.path.join(tempfile.gettempdir(), "bugsi_detections")
            logger.info("Detection save dir unavailable, using %s", save_dir)
        image_pipeline = ImageCapturePipeline(
            config=config,
            event_camera=hw["event_camera"],
            still_camera=hw["still_camera"],
            climate=hw["climate"],
            buffer=buffer,
            save_dir=save_dir,
            coordinator=coordinator,
        )

    # Mock thumbnail generator (only in mock mode when image pipeline is disabled)
    thumbnail_generator = None
    if mock and image_pipeline is None:
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

        # Apply energy saving mode
        await power_manager.apply_energy_saving(boot_type)

        should_start_web = await wlan_manager.start(boot_type)

        if should_start_web:
            # Create camera for live view
            web_camera = None
            try:
                from bugsi_daemon.web.camera import WebCamera
                if still_cam is not None:
                    jpeg_quality = config.get("still_camera.jpeg_quality", 85)
                    stream_width = config.get("webserver.stream_width", 960)
                    web_camera = WebCamera(
                        still_cam, jpeg_quality=jpeg_quality,
                        stream_width=stream_width, coordinator=coordinator,
                    )
            except Exception:
                logger.warning("Could not initialize camera for webserver, live view disabled", exc_info=True)

            # Create event camera for live view
            web_event_camera = None
            try:
                from bugsi_daemon.web.camera import WebEventCamera
                event_cam = hw.get("event_camera")
                if event_cam is not None:
                    jpeg_quality = config.get("event_camera.jpeg_quality", 85)
                    web_event_camera = WebEventCamera(event_cam, jpeg_quality=jpeg_quality)
            except Exception:
                logger.warning("Could not initialize event camera for webserver", exc_info=True)

            web_server = WebServer(
                config=config,
                components={
                    "buffer": buffer,
                    "client": client,
                    "power_manager": power_manager,
                    "web_camera": web_camera,
                    "web_event_camera": web_event_camera,
                    "wlan": hw["wlan"],
                    "wlan_manager": wlan_manager,
                    "hw": hw,
                    "image_pipeline": image_pipeline,
                    "mock": mock,
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
        "image_pipeline": image_pipeline,
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


async def _init_upload_components(config: ConfigManager, mock: bool) -> dict:
    """Lightweight init for upload: only telemetry sensors + upload infra.

    Skips cameras, webserver, and image pipeline to avoid conflicting
    with a running daemon that already holds those resources.
    """
    fallbacks = _mock_fallbacks()

    if mock:
        hw = {name: cls() for name, cls in fallbacks.items()}
    else:
        from bugsi_daemon.hardware.battery import VictronSmartShunt
        from bugsi_daemon.hardware.solar import VictronSmartSolar
        from bugsi_daemon.hardware.climate import ZigbeeClimateSensor
        from bugsi_daemon.hardware.lte import SixfabLteModem
        from bugsi_daemon.hardware.storage import UsbStorageMonitor
        from bugsi_daemon.hardware.system import SystemMonitor
        from bugsi_daemon.hardware.power_mgmt import WittyPiPowerManager
        from bugsi_daemon.hardware.wlan import SystemWlan

        hw = {
            "battery": VictronSmartShunt(),
            "solar": VictronSmartSolar(),
            "climate": ZigbeeClimateSensor(
                serial_port=config.get("zigbee.serial_port", "auto"),
                adapter=config.get("zigbee.adapter", "ezsp"),
                device_name=config.get("zigbee.device_name", "climate_sensor"),
                database_path=config.get("zigbee.database_path", "/var/cache/bugsi/zigbee.db"),
                network_channel=config.get("zigbee.network_channel", 11),
                usb_hub=config.get("zigbee.usb_hub"),
                usb_port=config.get("zigbee.usb_port"),
            ),
            "lte": SixfabLteModem(
                serial_port=config.get("lte.serial_port"),
                gpio_pin=config.get("lte.gpio_pin", 26),
            ),
            "storage": UsbStorageMonitor(),
            "system": SystemMonitor(),
            "power_mgmt": WittyPiPowerManager(),
            "wlan": SystemWlan(),
        }

    # Initialize sensors, falling back to mock on NotImplementedError
    for name, sensor in list(hw.items()):
        if hasattr(sensor, "initialize"):
            try:
                await sensor.initialize()
            except NotImplementedError:
                logger.warning("%s: real driver not implemented, using mock", name)
                hw[name] = fallbacks[name]()
                await hw[name].initialize()

    # Buffer
    db_path = config.get("storage.buffer_db_path", "/tmp/bugsi_buffer.db")
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        import tempfile
        db_path = os.path.join(tempfile.gettempdir(), "bugsi_buffer.db")
    buffer = BufferStore(db_path)
    await buffer.initialize()

    # Backup
    backup_path = config.get("storage.backup_path", "/tmp/bugsi_backup/")
    backup_dir = os.path.dirname(backup_path.rstrip("/"))
    if backup_dir and not os.path.exists(backup_dir):
        import tempfile
        backup_path = os.path.join(tempfile.gettempdir(), "bugsi_backup")
    backup = BufferBackup(db_path, backup_path)

    client = BugsiClient(config.api_url, config.api_key)

    telemetry = TelemetryCollector(
        buffer=buffer,
        battery=hw["battery"],
        solar=hw["solar"],
        climate=hw["climate"],
        storage=hw["storage"],
        system=hw["system"],
        lte=hw["lte"],
    )

    power_manager = PowerManager(
        config=config,
        lte=hw["lte"],
        power_mgmt=hw["power_mgmt"],
        backup=backup,
        wlan=hw.get("wlan"),
    )

    upload = UploadCycle(
        client=client,
        buffer=buffer,
        config=config,
        power_manager=power_manager,
        telemetry_collector=telemetry,
        wlan=hw.get("wlan"),
    )

    return {
        "hw": hw,
        "buffer": buffer,
        "client": client,
        "telemetry": telemetry,
        "upload": upload,
    }


async def cmd_upload(config: ConfigManager, mock: bool, capture_image: bool = False) -> None:
    """Run one upload cycle immediately."""
    should_capture = capture_image or config.get("upload.capture_image", False)

    if should_capture:
        # Full init needed for cameras + image pipeline
        components = await init_components(config, mock)
    else:
        # Lightweight init: only telemetry sensors + upload infra
        components = await _init_upload_components(config, mock)

    try:
        # Capture a fresh image if requested
        image_pipeline = components.get("image_pipeline")
        if should_capture and image_pipeline is not None:
            print("Capturing fresh image...")
            try:
                await image_pipeline._capture_sequence()
                print(f"Image captured successfully (total: {image_pipeline.pictures_taken})")
            except Exception as e:
                print(f"Image capture failed: {e}")
                print("Hint: stop the daemon first if it is running (sudo systemctl stop bugsi)")
                logger.exception("Image capture failed during upload command")
        elif should_capture and image_pipeline is None:
            print("Warning: --capture-image requested but image pipeline is not enabled")
            print("Set image_capture.enabled=true in config to enable image capture")

        # Generate a mock thumbnail (guaranteed for one-shot upload)
        thumbnail_gen = components.get("thumbnail_generator")
        if thumbnail_gen:
            await thumbnail_gen.maybe_generate(probability=1.0)

        # Collect telemetry (includes pictures_taken count)
        extra = {}
        if image_pipeline is not None:
            extra["pictures_taken"] = image_pipeline.pictures_taken
        elif thumbnail_gen:
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


async def cmd_config_pull(config: ConfigManager, mock: bool) -> None:
    """Fetch latest configuration from SaaS backend."""
    # Lightweight init: only LTE + HTTP client (no cameras, buffers, etc.)
    if mock:
        from bugsi_daemon.hardware_mock.lte import MockLteModem
        lte = MockLteModem()
    else:
        from bugsi_daemon.hardware.lte import SixfabLteModem
        lte = SixfabLteModem(
            serial_port=config.get("lte.serial_port") if config else None,
            gpio_pin=config.get("lte.gpio_pin", 26) if config else 26,
        )

    client = BugsiClient(config.api_url, config.api_key)

    try:
        # Power on LTE for network access
        print("Powering on LTE...")
        await lte.power_on()

        if not await lte.wait_for_network(timeout=60):
            print("Error: LTE network registration timeout", file=sys.stderr)
            return

        print("Polling config from SaaS...")
        result = client.poll_config()

        if result.get("has_update"):
            version = result["version"]
            config_data = result["config"]
            changed = config.apply_remote(config_data, version)
            if changed:
                client.ack_config(version)
                print(f"Config updated to v{version}")
            else:
                print(f"Config already up to date (v{config.version})")
        else:
            print(f"No config update available (v{config.version})")

        print(json.dumps(config.get_all(), indent=2))

    except Exception as e:
        print(f"Error fetching config: {e}", file=sys.stderr)
    finally:
        await lte.power_off()
        client.close()


async def _init_hardware(config: ConfigManager, mock: bool) -> dict:
    """Lightweight hardware init for test-hardware (no web server, WLAN, etc.)."""
    hw = create_hardware(mock, config)
    fallbacks = _mock_fallbacks()

    for name, sensor in list(hw.items()):
        if hasattr(sensor, "initialize"):
            try:
                await sensor.initialize()
            except NotImplementedError:
                logger.warning("%s: real driver not implemented, using mock", name)
                hw[name] = fallbacks[name]()
                await hw[name].initialize()

    return hw


async def cmd_test_hardware(config: ConfigManager, mock: bool, subsystem: str | None = None) -> None:
    """Test individual hardware subsystems interactively."""
    hw = await _init_hardware(config, mock)

    async def test_cameras():
        print("\n=== Still Camera ===")
        cam = hw["still_camera"]
        try:
            cam.open()
            frame = cam.capture()
            print(f"  Captured frame: {frame.shape} dtype={frame.dtype}")
            cam.close()
            print("  OK: open → capture → close")
        except Exception as e:
            print(f"  ERROR: {e}")

        print("\n=== Event Camera ===")
        ev = hw["event_camera"]
        try:
            await ev.initialize()
            await ev.start_detection()
            print("  Waiting for detection (5s timeout)...")
            detected = await ev.wait_for_detection(timeout=5.0)
            print(f"  Detection: {detected}")
            if detected:
                frame = await ev.capture_event_frame()
                print(f"  Event frame: {frame.shape} dtype={frame.dtype}")
            await ev.stop_detection()
            await ev.shutdown()
            print("  OK")
        except Exception as e:
            print(f"  ERROR: {e}")

    async def test_climate():
        print("\n=== Climate Sensor (Zigbee) ===")
        climate = hw["climate"]
        try:
            print("  Powering on...")
            await climate.power_on()
            print(f"  Powered: {climate.is_powered()}")
            print(f"  Healthy: {climate.is_healthy()}")
            reading = await climate.read()
            print(f"  Reading: {reading}")
            await climate.power_off()
            print(f"  Powered after off: {climate.is_powered()}")
            print("  OK")
        except Exception as e:
            print(f"  ERROR: {e}")

    async def test_lte():
        print("\n=== LTE Modem ===")
        lte = hw["lte"]
        try:
            print("  Powering on...")
            await lte.power_on()
            print(f"  Powered: {lte.is_powered()}")
            print("  Waiting for network (30s)...")
            connected = await lte.wait_for_network(timeout=30)
            print(f"  Network connected: {connected}")
            if connected:
                info = await lte.get_signal_info()
                print(f"  Signal info: {info}")
            await lte.power_off()
            print("  OK")
        except Exception as e:
            print(f"  ERROR: {e}")

    async def test_power_mgmt():
        print("\n=== Power Management (Witty Pi) ===")
        pm = hw["power_mgmt"]
        try:
            await pm.initialize()
            rtc = await pm.get_rtc_time()
            print(f"  RTC time: {rtc}")
            reason = await pm.get_wakeup_reason()
            print(f"  Wakeup reason: {reason}")
            temp = await pm.get_temperature()
            print(f"  Temperature: {temp}°C")
            voltage = await pm.get_input_voltage()
            print(f"  Input voltage: {voltage}V")
            wakeup = await pm.get_next_wakeup()
            print(f"  Next wakeup: {wakeup}")
            print("  OK")
        except Exception as e:
            print(f"  ERROR: {e}")

    async def test_power_schedule():
        print("\n=== Power Schedule ===")
        pm_mgr = PowerManager(
            config=config,
            lte=hw["lte"],
            power_mgmt=hw["power_mgmt"],
            backup=BufferBackup("/dev/null", "/tmp/bugsi_backup/"),
            wlan=hw.get("wlan"),
        )
        start, end = pm_mgr.get_active_hours()
        from datetime import datetime as dt
        now = dt.now()
        print(f"  Current time: {now.strftime('%H:%M')}")
        print(f"  Active hours: {start}:00 - {end}:00")
        print(f"  Night mode type: {config.get('power.night_mode_type', 'fixed')}")
        is_night = pm_mgr.check_night_mode(now.hour)
        print(f"  Currently night: {is_night}")
        print(f"  Energy saving: {config.get('power.energy_saving', False)}")
        print("  OK")

    async def test_sensors():
        print("\n=== Storage ===")
        try:
            reading = await hw["storage"].read()
            print(f"  {reading}")
        except Exception as e:
            print(f"  ERROR: {e}")

        print("\n=== System ===")
        try:
            reading = await hw["system"].read()
            print(f"  {reading}")
        except Exception as e:
            print(f"  ERROR: {e}")

        print("\n=== Battery ===")
        try:
            reading = await hw["battery"].read()
            print(f"  {reading}")
        except Exception as e:
            print(f"  ERROR: {e}")

        print("\n=== Solar ===")
        try:
            reading = await hw["solar"].read()
            print(f"  {reading}")
        except Exception as e:
            print(f"  ERROR: {e}")

    async def test_zigbee():
        print("\n=== Zigbee Network ===")
        climate = hw["climate"]
        try:
            print("  Powering on Zigbee stack...")
            await climate.power_on()

            # Query paired devices
            print("  Querying paired devices...")
            devices = await climate.get_devices()
            if not devices:
                print("  No devices found (or Zigbee stack not responding)")
            else:
                print(f"  Found {len(devices)} device(s):")
                for dev in devices:
                    name = dev.get("friendly_name", "unknown")
                    model = dev.get("model", "?")
                    vendor = dev.get("vendor", "?")
                    available = dev.get("available", "?")
                    dev_type = dev.get("type", "?")
                    ieee = dev.get("ieee_address", "?")
                    status = "ONLINE" if available else "OFFLINE"
                    print(f"    [{status}] {name} ({vendor} {model}, {dev_type}, {ieee})")

            # Wait for sensor data (sensor may join/initialize after power-on)
            device_name = config.get("zigbee.device_name", "climate_sensor")
            timeout = 90
            print(f"  Waiting up to {timeout}s for sensor data from '{device_name}'...")
            print("  (sleepy Zigbee devices may take time to wake up and report)")
            if hasattr(climate, "wait_for_reading"):
                reading = await climate.wait_for_reading(timeout=timeout)
            else:
                import asyncio as _asyncio
                await _asyncio.sleep(config.get("image_capture.zigbee_warmup_seconds", 5))
                reading = await climate.read()
            if reading:
                print(f"  Sensor data: {reading}")
            else:
                print(f"  No data received from '{device_name}' (check pairing)")
                print("  Tip: run 'bugsi pair-zigbee' first to pair the sensor")

            await climate.power_off()
            print("  OK")
        except Exception as e:
            print(f"  ERROR: {e}")

    async def test_capture():
        print("\n=== Image Capture Pipeline ===")
        if not config.get("image_capture.enabled", True):
            print("  Pipeline not enabled (set image_capture.enabled=true)")
            return
        try:
            from bugsi_daemon.core.image_capture_pipeline import ImageCapturePipeline
            import os
            import tempfile

            db_path = config.get("storage.buffer_db_path", "/tmp/bugsi_buffer.db")
            buffer = BufferStore(db_path)
            await buffer.initialize()

            save_dir = config.get("image_capture.save_dir", "/mnt/usb/bugsi/detections")
            if not os.path.exists(os.path.dirname(save_dir) if save_dir != "/" else save_dir):
                save_dir = os.path.join(tempfile.gettempdir(), "bugsi_detections")

            pipeline = ImageCapturePipeline(
                config=config,
                event_camera=hw["event_camera"],
                still_camera=hw["still_camera"],
                climate=hw["climate"],
                buffer=buffer,
                save_dir=save_dir,
            )
            print("  Running one capture sequence...")
            await pipeline._capture_sequence()
            print(f"  Pictures taken: {pipeline.pictures_taken}")
            print("  OK")
            await buffer.close()
        except Exception as e:
            print(f"  ERROR: {e}")

    tests = {
        "cameras": test_cameras,
        "climate": test_climate,
        "zigbee": test_zigbee,
        "lte": test_lte,
        "power": test_power_mgmt,
        "schedule": test_power_schedule,
        "sensors": test_sensors,
        "capture": test_capture,
    }

    mode_str = "MOCK" if mock else "REAL"
    print(f"BUGSI Hardware Test ({mode_str} mode)")
    print("=" * 40)

    if subsystem:
        if subsystem == "all":
            for test_fn in tests.values():
                await test_fn()
        elif subsystem in tests:
            await tests[subsystem]()
        else:
            print(f"Unknown subsystem: {subsystem}")
            print(f"Available: {', '.join(tests.keys())}, all")
    else:
        print(f"Available subsystems: {', '.join(tests.keys())}, all")
        print("Usage: bugsi test-hardware <subsystem>")


async def cmd_pair_zigbee(
    config: ConfigManager, mock: bool, timeout: int = 120, rename: str | None = None,
) -> None:
    """Pair a new Zigbee sensor."""
    hw = await _init_hardware(config, mock)
    climate = hw["climate"]

    try:
        print("Powering on Zigbee stack...")
        try:
            await climate.power_on()
        except Exception as exc:
            print(f"ERROR: Failed to start Zigbee controller: {exc}")
            print("The USB dongle may not be connected, or the serial port is busy.")
            print("Check 'dmesg | tail' for USB errors.")
            print("FEHLER: Zigbee-Controller konnte nicht gestartet werden.")
            return

        print(f"Zigbee stack ready. Opening pairing window for {timeout}s...")
        print("Put your Zigbee sensor into pairing mode now.")
        print()

        def on_joined(data: dict) -> None:
            name = data.get("friendly_name", "unknown")
            ieee = data.get("ieee_address", "?")
            model = data.get("model", "?")
            vendor = data.get("vendor", "?")
            print(f"  [JOINED] {ieee} ({vendor} {model}) as \"{name}\"")

        joined = await climate.pair_zigbee(timeout=timeout, on_device_joined=on_joined)
        print()

        if not joined:
            print("No devices joined during the pairing window.")
        else:
            # Determine the target name: explicit --rename, or the configured device_name
            target_name = rename or config.get("zigbee.device_name", "climate_sensor") if config else rename
            if target_name:
                # Check if the name is already taken by another device
                devices = await climate.get_devices()
                existing_names = {
                    d.get("friendly_name") for d in devices
                    if d.get("type") != "Coordinator"
                }
                first_name = joined[0].get("friendly_name", "")

                if first_name == target_name:
                    print(f"Device already named \"{target_name}\".")
                elif target_name in existing_names:
                    print(f"Name \"{target_name}\" is already in use by another device, skipping rename.")
                elif first_name:
                    print(f"Renaming \"{first_name}\" -> \"{target_name}\"...", end=" ")
                    success = await climate.rename_device(first_name, target_name)
                    print("OK" if success else "FAILED")
                print()

        # List all paired devices
        devices = await climate.get_devices()
        if devices:
            print("Paired devices:")
            for dev in devices:
                name = dev.get("friendly_name", "unknown")
                model = dev.get("model", "?")
                vendor = dev.get("vendor", "?")
                available = dev.get("available", False)
                dev_type = dev.get("type", "?")
                status = "ONLINE" if available else "OFFLINE"
                print(f"  [{status}] {name} ({vendor} {model}, {dev_type})")
            print()

    finally:
        print("Powering off Zigbee stack...", end=" ")
        await climate.power_off()
        print("Done.")
