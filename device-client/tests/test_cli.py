import json
from unittest.mock import patch

import pytest

from bugsi_daemon.config import ConfigManager


class TestCLICommands:
    def test_config_command(self, config_manager, capsys):
        import asyncio
        from bugsi_daemon.cli import cmd_config

        asyncio.run(cmd_config(config_manager, True))
        captured = capsys.readouterr()
        assert "Version:" in captured.out
        assert "telemetry" in captured.out

    def test_telemetry_command(self, config_manager, capsys, tmp_path):
        import asyncio
        from bugsi_daemon.cli import cmd_telemetry

        # Override buffer path to use temp dir
        config_manager.apply_remote(
            {"storage": {"buffer_db_path": str(tmp_path / "buffer.db")}},
            version=99,
        )

        asyncio.run(cmd_telemetry(config_manager, True))
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert "timestamp" in output
        assert "battery_voltage" in output
        assert "temperature" in output

    def test_status_command(self, config_manager, capsys, tmp_path):
        import asyncio
        from bugsi_daemon.cli import cmd_status

        config_manager.apply_remote(
            {"storage": {"buffer_db_path": str(tmp_path / "buffer.db")}},
            version=99,
        )

        asyncio.run(cmd_status(config_manager, True))
        captured = capsys.readouterr()
        assert "Config version:" in captured.out
        assert "Power mode:" in captured.out
        assert "Buffer statistics:" in captured.out
