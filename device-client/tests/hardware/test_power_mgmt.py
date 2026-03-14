from datetime import datetime, timezone

import pytest

from bugsi_daemon.hardware_mock.power_mgmt import MockPowerManagement


@pytest.mark.asyncio
class TestMockPowerManagement:
    async def test_initialize(self):
        pm = MockPowerManagement()
        await pm.initialize()

    async def test_get_rtc_time(self):
        pm = MockPowerManagement()
        await pm.initialize()
        t = await pm.get_rtc_time()
        assert isinstance(t, datetime)

    async def test_set_rtc_time(self):
        pm = MockPowerManagement()
        await pm.initialize()
        now = datetime.now(timezone.utc)
        await pm.set_rtc_time(now)  # Should not raise

    async def test_schedule_wakeup(self):
        pm = MockPowerManagement()
        await pm.initialize()
        wakeup_time = datetime(2026, 3, 8, 6, 0, 0, tzinfo=timezone.utc)
        await pm.schedule_wakeup(wakeup_time)
        result = await pm.get_next_wakeup()
        assert result == wakeup_time

    async def test_schedule_shutdown(self):
        pm = MockPowerManagement()
        await pm.initialize()
        shutdown_time = datetime(2026, 3, 7, 22, 0, 0, tzinfo=timezone.utc)
        await pm.schedule_shutdown(shutdown_time)  # Should not raise

    async def test_no_wakeup_initially(self):
        pm = MockPowerManagement()
        await pm.initialize()
        assert await pm.get_next_wakeup() is None
