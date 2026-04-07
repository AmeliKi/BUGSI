import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from bugsi_daemon.config import ConfigManager


class TestCLICommands:
    def test_config_command(self, config_manager, capsys):
        from bugsi_daemon.cli import cmd_config

        asyncio.run(cmd_config(config_manager, True))
        captured = capsys.readouterr()
        assert "Version:" in captured.out
        assert "telemetry" in captured.out

    def test_telemetry_command(self, config_manager, capsys, tmp_path):
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


class TestUploadCaptureImage:
    """Tests for the --capture-image flag on bugsi upload."""

    def test_upload_parser_accepts_capture_image_flag(self):
        from bugsi_daemon.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["upload", "--capture-image"])
        assert args.capture_image is True

    def test_upload_parser_defaults_capture_image_false(self):
        from bugsi_daemon.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["upload"])
        assert args.capture_image is False

    def test_upload_default_no_capture(self, config_manager, capsys, tmp_path):
        """Upload without --capture-image uses lightweight init, no capture."""
        from bugsi_daemon.cli import cmd_upload

        config_manager.apply_remote(
            {"storage": {"buffer_db_path": str(tmp_path / "buffer.db")}},
            version=99,
        )

        with patch("bugsi_daemon.cli._init_upload_components") as mock_init:
            mock_buffer = AsyncMock()
            mock_client = AsyncMock()
            mock_upload = AsyncMock()
            mock_upload.run = AsyncMock(return_value=True)
            mock_telemetry = AsyncMock()
            mock_telemetry.collect = AsyncMock(return_value={"battery_soc": 80, "timestamp": "2026-04-07T00:00:00Z"})

            mock_init.return_value = {
                "image_pipeline": None,
                "thumbnail_generator": None,
                "telemetry": mock_telemetry,
                "upload": mock_upload,
                "buffer": mock_buffer,
                "client": mock_client,
            }

            asyncio.run(cmd_upload(config_manager, True))
            # Lightweight init should be used, not full init_components
            mock_init.assert_called_once()

    def test_upload_with_capture_flag(self, config_manager, capsys, tmp_path):
        """Upload with capture_image=True should call _capture_sequence."""
        from bugsi_daemon.cli import cmd_upload

        config_manager.apply_remote(
            {"storage": {"buffer_db_path": str(tmp_path / "buffer.db")}},
            version=99,
        )

        with patch("bugsi_daemon.cli.init_components") as mock_init:
            mock_pipeline = AsyncMock()
            mock_pipeline.pictures_taken = 1
            mock_buffer = AsyncMock()
            mock_client = AsyncMock()
            mock_upload = AsyncMock()
            mock_upload.run = AsyncMock(return_value=True)
            mock_telemetry = AsyncMock()
            mock_telemetry.collect = AsyncMock(return_value={"battery_soc": 80, "timestamp": "2026-04-07T00:00:00Z"})

            mock_init.return_value = {
                "image_pipeline": mock_pipeline,
                "thumbnail_generator": None,
                "telemetry": mock_telemetry,
                "upload": mock_upload,
                "buffer": mock_buffer,
                "client": mock_client,
            }

            asyncio.run(cmd_upload(config_manager, True, capture_image=True))
            mock_pipeline._capture_sequence.assert_called_once()

    def test_upload_capture_failure_does_not_block_upload(self, config_manager, capsys, tmp_path):
        """If image capture fails, upload should still proceed."""
        from bugsi_daemon.cli import cmd_upload

        config_manager.apply_remote(
            {"storage": {"buffer_db_path": str(tmp_path / "buffer.db")}},
            version=99,
        )

        with patch("bugsi_daemon.cli.init_components") as mock_init:
            mock_pipeline = AsyncMock()
            mock_pipeline._capture_sequence = AsyncMock(side_effect=RuntimeError("Camera error"))
            mock_pipeline.pictures_taken = 0
            mock_buffer = AsyncMock()
            mock_client = AsyncMock()
            mock_upload = AsyncMock()
            mock_upload.run = AsyncMock(return_value=True)
            mock_telemetry = AsyncMock()
            mock_telemetry.collect = AsyncMock(return_value={"battery_soc": 80, "timestamp": "2026-04-07T00:00:00Z"})

            mock_init.return_value = {
                "image_pipeline": mock_pipeline,
                "thumbnail_generator": None,
                "telemetry": mock_telemetry,
                "upload": mock_upload,
                "buffer": mock_buffer,
                "client": mock_client,
            }

            asyncio.run(cmd_upload(config_manager, True, capture_image=True))
            # Upload should still be called despite capture failure
            mock_upload.run.assert_called_once()

    def test_upload_capture_no_pipeline_warns(self, config_manager, capsys, tmp_path):
        """If capture requested but no pipeline, should warn user."""
        from bugsi_daemon.cli import cmd_upload

        config_manager.apply_remote(
            {"storage": {"buffer_db_path": str(tmp_path / "buffer.db")}},
            version=99,
        )

        with patch("bugsi_daemon.cli.init_components") as mock_init:
            mock_buffer = AsyncMock()
            mock_client = AsyncMock()
            mock_upload = AsyncMock()
            mock_upload.run = AsyncMock(return_value=True)
            mock_telemetry = AsyncMock()
            mock_telemetry.collect = AsyncMock(return_value={"battery_soc": 80, "timestamp": "2026-04-07T00:00:00Z"})

            mock_init.return_value = {
                "image_pipeline": None,
                "thumbnail_generator": None,
                "telemetry": mock_telemetry,
                "upload": mock_upload,
                "buffer": mock_buffer,
                "client": mock_client,
            }

            asyncio.run(cmd_upload(config_manager, True, capture_image=True))
            captured = capsys.readouterr()
            assert "image pipeline is not enabled" in captured.out
