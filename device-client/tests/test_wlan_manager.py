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


def _make_config(tmp_path, battery=False, timeout_minutes=10):
    default_path = tmp_path / "default.json"
    default_path.write_text(json.dumps({
        "power": {"battery": battery, "wlan_timeout_minutes": timeout_minutes},
        "webserver": {"enabled": True},
    }))
    cm = ConfigManager(
        default_config_path=default_path,
        local_config_path=str(tmp_path / "local.json"),
        credentials_path=str(tmp_path / "cred.json"),
    )
    cm.load()
    return cm


async def test_no_battery_mode_always_starts(tmp_path, wlan):
    config = _make_config(tmp_path, battery=False)
    mgr = WlanManager(config=config, wlan=wlan)

    should_start = await mgr.start("cold_boot")
    assert should_start is True
    assert not mgr.battery_mode


async def test_battery_mode_cold_boot_starts(tmp_path, wlan):
    config = _make_config(tmp_path, battery=True)
    mgr = WlanManager(config=config, wlan=wlan)

    should_start = await mgr.start("cold_boot")
    assert should_start is True
    assert mgr.battery_mode
    assert wlan.is_enabled()
    await mgr.stop()


async def test_battery_mode_rtc_wake_no_start(tmp_path, wlan):
    config = _make_config(tmp_path, battery=True)
    mgr = WlanManager(config=config, wlan=wlan)

    should_start = await mgr.start("rtc_wake")
    assert should_start is False


async def test_inactivity_timeout_disables_wlan(tmp_path, wlan):
    # Use very short timeout for testing
    config = _make_config(tmp_path, battery=True, timeout_minutes=0.001)  # ~60ms
    mgr = WlanManager(config=config, wlan=wlan)

    await mgr.start("cold_boot")
    assert wlan.is_enabled()

    # Wait for timeout
    await asyncio.sleep(0.15)
    assert not wlan.is_enabled()


async def test_timer_reset_extends_timeout(tmp_path, wlan):
    config = _make_config(tmp_path, battery=True, timeout_minutes=0.002)  # ~120ms
    mgr = WlanManager(config=config, wlan=wlan)

    await mgr.start("cold_boot")
    assert wlan.is_enabled()

    # Reset timer before it expires
    await asyncio.sleep(0.05)
    mgr.reset_timer()

    # Original timeout would have fired, but we reset
    await asyncio.sleep(0.1)
    assert wlan.is_enabled()

    # Now wait for new timeout
    await asyncio.sleep(0.15)
    assert not wlan.is_enabled()


async def test_no_timer_without_battery_mode(tmp_path, wlan):
    config = _make_config(tmp_path, battery=False)
    mgr = WlanManager(config=config, wlan=wlan)

    await mgr.start("cold_boot")
    # reset_timer should be a no-op
    mgr.reset_timer()
    assert wlan.is_enabled()
    await mgr.stop()


async def test_stop_cancels_timer(tmp_path, wlan):
    config = _make_config(tmp_path, battery=True, timeout_minutes=0.001)
    mgr = WlanManager(config=config, wlan=wlan)

    await mgr.start("cold_boot")
    await mgr.stop()

    # Timer should be cancelled, WLAN should stay as-is
    await asyncio.sleep(0.15)
    assert wlan.is_enabled()
