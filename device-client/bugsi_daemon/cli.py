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
        resolution_width=config.get("still_camera.resolution_width", 3840) if config else 3840,
        resolution_height=config.get("still_camera.resolution_height", 2160) if config else 2160,
        camera_id=config.get("still_camera.camera_id", 1) if config else 1,
        autofocus_mode=config.get("still_camera.autofocus_mode", "continuous") if config else "continuous",
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
            mqtt_host=config.get("zigbee.mqtt_host", "localhost") if config else "localhost",
            mqtt_port=config.get("zigbee.mqtt_port", 1883) if config else 1883,
            device_name=config.get("zigbee.device_name", "SNZB-02WD") if config else "SNZB-02WD",
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
        wlan=hw["wlan"],
    )

    # Upload cycle
    upload = UploadCycle(
        client=client,
        buffer=buffer,
        config=config,
        power_manager=power_manager,
        telemetry_collector=telemetry,
    )

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
                still_cam = hw.get("still_camera")
                if still_cam is not None:
                    jpeg_quality = config.get("still_camera.jpeg_quality", 85)
                    web_camera = WebCamera(still_cam, jpeg_quality=jpeg_quality)
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


async def cmd_test_hardware(config: ConfigManager, mock: bool, subsystem: str | None = None) -> None:
    """Test individual hardware subsystems interactively."""
    components = await init_components(config, mock)
    hw = components["hw"]

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
        pm_mgr = components["power_manager"]
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
                print("  No devices found (or Zigbee2MQTT not responding)")
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

            # Try reading sensor data
            device_name = config.get("zigbee.device_name", "SNZB-02WD")
            warmup = config.get("image_capture.zigbee_warmup_seconds", 5)
            print(f"  Waiting {warmup}s for sensor data from '{device_name}'...")
            import asyncio as _asyncio
            await _asyncio.sleep(warmup)
            reading = await climate.read()
            if reading:
                print(f"  Sensor data: {reading}")
            else:
                print(f"  No data received from '{device_name}' (check pairing)")

            await climate.power_off()
            print("  OK")
        except Exception as e:
            print(f"  ERROR: {e}")

    async def test_capture():
        print("\n=== Image Capture Pipeline ===")
        pipeline = components.get("image_pipeline")
        if pipeline is None:
            print("  Pipeline not enabled (set image_capture.enabled=true)")
            return
        try:
            print("  Running one capture sequence...")
            await pipeline._capture_sequence()
            print(f"  Pictures taken: {pipeline.pictures_taken}")
            print("  OK")
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

    try:
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
    finally:
        await components["buffer"].close()
        components["client"].close()
