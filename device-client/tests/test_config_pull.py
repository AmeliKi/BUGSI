import httpx
import pytest
import respx

from bugsi_daemon.net.client import BugsiClient
from bugsi_daemon.cli import cmd_config_pull


@pytest.mark.asyncio
class TestConfigPull:
    @respx.mock
    async def test_config_pull_applies_update(self, config_manager, mock_hardware, buffer_store, capsys):
        """Config pull fetches and applies a newer config version."""
        respx.get("http://test:8000/api/device-data/config").mock(
            return_value=httpx.Response(200, json={
                "version": 10,
                "config": {"upload": {"interval_minutes": 15}},
                "has_update": True,
            })
        )
        ack_route = respx.post("http://test:8000/api/device-data/config/ack").mock(
            return_value=httpx.Response(204)
        )

        await cmd_config_pull(config_manager, mock=True)

        assert ack_route.called
        assert config_manager.version == 10
        assert config_manager.get("upload.interval_minutes") == 15

        output = capsys.readouterr().out
        assert "Config updated to v10" in output

    @respx.mock
    async def test_config_pull_no_update(self, config_manager, mock_hardware, buffer_store, capsys):
        """Config pull reports no update when SaaS has no newer version."""
        respx.get("http://test:8000/api/device-data/config").mock(
            return_value=httpx.Response(200, json={
                "version": 0,
                "config": {},
                "has_update": False,
            })
        )

        await cmd_config_pull(config_manager, mock=True)

        output = capsys.readouterr().out
        assert "No config update available" in output

    @respx.mock
    async def test_config_pull_handles_error(self, config_manager, mock_hardware, buffer_store, capsys):
        """Config pull handles connection errors gracefully."""
        respx.get("http://test:8000/api/device-data/config").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        await cmd_config_pull(config_manager, mock=True)

        output = capsys.readouterr().err
        assert "Error fetching config" in output
