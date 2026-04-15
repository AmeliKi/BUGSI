import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bugsi_daemon.cli import cmd_pair_zigbee


@pytest.mark.asyncio
async def test_cmd_pair_zigbee_mock_mode(capsys):
    """Pair-zigbee command completes in mock mode and prints expected output."""
    config = MagicMock()
    config.get.return_value = None

    await cmd_pair_zigbee(config, mock=True, timeout=120, rename=None)

    output = capsys.readouterr().out
    assert "Powering on Zigbee stack..." in output
    assert "Opening pairing window" in output
    assert "[JOINED]" in output
    assert "Paired devices:" in output
    assert "Done." in output


@pytest.mark.asyncio
async def test_cmd_pair_zigbee_mock_with_rename_conflict(capsys):
    """Pair-zigbee skips rename when name is already in use."""
    config = MagicMock()
    config.get.return_value = None

    # Mock get_devices returns "climate_sensor" already, so rename is skipped
    await cmd_pair_zigbee(config, mock=True, timeout=120, rename="climate_sensor")

    output = capsys.readouterr().out
    assert "already in use" in output
    assert "climate_sensor" in output


@pytest.mark.asyncio
async def test_cmd_pair_zigbee_mock_with_rename_success(capsys):
    """Pair-zigbee renames when the name is available."""
    config = MagicMock()
    config.get.return_value = None

    await cmd_pair_zigbee(config, mock=True, timeout=120, rename="my_sensor")

    output = capsys.readouterr().out
    assert "Renaming" in output
    assert "my_sensor" in output
    assert "OK" in output


@pytest.mark.asyncio
async def test_cmd_pair_zigbee_handles_power_failure(capsys):
    """Pair-zigbee reports error and shuts down cleanly when power_on fails."""
    config = MagicMock()
    config.get.return_value = None

    mock_climate = AsyncMock()
    mock_climate.power_on = AsyncMock(
        side_effect=BrokenPipeError("Broken pipe"),
    )
    mock_climate.power_off = AsyncMock()

    mock_hw = {"climate": mock_climate}
    with patch("bugsi_daemon.cli._init_hardware", AsyncMock(return_value=mock_hw)):
        await cmd_pair_zigbee(config, mock=False, timeout=120, rename=None)

    output = capsys.readouterr().out
    assert "ERROR" in output
    assert "Failed to start Zigbee controller" in output
    assert "FEHLER" in output
    mock_climate.power_off.assert_called_once()
