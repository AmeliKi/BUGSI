from __future__ import annotations

import asyncio
import json

import pytest

from bugsi_daemon.config import ConfigManager
from bugsi_daemon.hardware_mock.wlan import MockWlan
from bugsi_daemon.web.wlan_manager import WlanManager


@pytest.fixture
def wlan():
    return MockWlan()


def _make_config(
    tmp_path,
    battery=False,
    timeout_minutes=10,
    ap_fallback_enabled=True,
    ap_ssid="BUGSI-Test",
    ap_password="testpass1234",
    recheck_minutes=999,
    connect_wait=0,
):
    default_path = tmp_path / "default.json"
    default_path.write_text(json.dumps({
        "power": {"battery": battery, "wlan_timeout_minutes": timeout_minutes},
        "webserver": {"enabled": True},
        "wifi": {
            "ap_fallback_enabled": ap_fallback_enabled,
            "ap_ssid": ap_ssid,
            "ap_password": ap_password,
            "ap_recheck_interval_minutes": recheck_minutes,
            "ap_connect_wait_seconds": connect_wait,
        },
    }))
    cm = ConfigManager(
        default_config_path=default_path,
        local_config_path=str(tmp_path / "local.json"),
        credentials_path=str(tmp_path / "cred.json"),
    )
    cm.load()
    return cm


async def test_known_network_available_no_ap(tmp_path, wlan):
    """When a known network is available, no AP should start."""
    wlan._connected = True
    config = _make_config(tmp_path)
    mgr = WlanManager(config=config, wlan=wlan)

    await mgr.start("cold_boot")

    assert not wlan._hotspot_active
    assert not mgr.ap_mode
    await mgr.stop()


async def test_no_known_network_starts_ap(tmp_path, wlan):
    """When no known network is available, AP should start."""
    wlan._connected = False
    config = _make_config(tmp_path)
    mgr = WlanManager(config=config, wlan=wlan)

    await mgr.start("cold_boot")

    assert wlan._hotspot_active
    assert mgr.ap_mode
    await mgr.stop()


async def test_ap_fallback_disabled(tmp_path, wlan):
    """When AP fallback is disabled, no AP even without network."""
    wlan._connected = False
    config = _make_config(tmp_path, ap_fallback_enabled=False)
    mgr = WlanManager(config=config, wlan=wlan)

    await mgr.start("cold_boot")

    assert not wlan._hotspot_active
    assert not mgr.ap_mode
    await mgr.stop()


async def test_recheck_finds_network(tmp_path, wlan):
    """When periodic recheck finds a known network, switch to client mode."""
    wlan._connected = False
    config = _make_config(tmp_path, recheck_minutes=0.001, connect_wait=0)
    mgr = WlanManager(config=config, wlan=wlan)

    await mgr.start("cold_boot")
    assert mgr.ap_mode

    # Simulate known network appearing
    wlan._connected = True
    await asyncio.sleep(0.15)

    assert not mgr.ap_mode
    await mgr.stop()


async def test_recheck_no_network_stays_in_ap_mode(tmp_path, wlan):
    """When recheck finds no network, device stays in AP mode."""
    wlan._connected = False
    config = _make_config(tmp_path, recheck_minutes=0.001, connect_wait=0)
    mgr = WlanManager(config=config, wlan=wlan)

    await mgr.start("cold_boot")
    assert mgr.ap_mode

    # After recheck cycles, still no network — ap_mode stays True
    await asyncio.sleep(0.15)
    assert mgr.ap_mode
    await mgr.stop()


async def test_rtc_wake_no_ap(tmp_path, wlan):
    """Battery mode RTC wake should not start AP."""
    config = _make_config(tmp_path, battery=True)
    mgr = WlanManager(config=config, wlan=wlan)

    should_start = await mgr.start("rtc_wake")
    assert should_start is False
    assert not mgr.ap_mode
    assert not wlan._hotspot_active
    await mgr.stop()


async def test_stop_cleans_up_hotspot(tmp_path, wlan):
    """stop() should deactivate the hotspot and cancel recheck task."""
    wlan._connected = False
    config = _make_config(tmp_path)
    mgr = WlanManager(config=config, wlan=wlan)

    await mgr.start("cold_boot")
    assert wlan._hotspot_active
    assert mgr.ap_mode

    await mgr.stop()
    assert not wlan._hotspot_active
    assert not mgr.ap_mode


async def test_custom_ssid_password(tmp_path, wlan):
    """Custom SSID and password from config should be used."""
    wlan._connected = False
    config = _make_config(tmp_path, ap_ssid="MyBUGSI", ap_password="secret99")
    mgr = WlanManager(config=config, wlan=wlan)

    await mgr.start("cold_boot")

    assert wlan._hotspot_active
    assert wlan._last_hotspot_ssid == "MyBUGSI"
    assert wlan._last_hotspot_password == "secret99"
    await mgr.stop()
