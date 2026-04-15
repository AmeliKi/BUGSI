from unittest.mock import MagicMock, patch

import pytest

from bugsi_daemon.hardware.lte import SixfabLteModem
from bugsi_daemon.hardware_mock.lte import MockLteModem


@pytest.mark.asyncio
class TestSixfabLteModemSerial:
    """Test the real LTE driver's serial connection handling (mocked serial port)."""

    def _make_modem_with_mock_serial(self):
        modem = SixfabLteModem(serial_port="/dev/ttyUSB_FAKE")
        modem._powered = True
        modem._active_port = "/dev/ttyUSB_FAKE"
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.readline.side_effect = [b"+CSQ: 15,0\r\n", b"OK\r\n"]
        modem._serial_conn = mock_ser
        return modem, mock_ser

    async def test_reuses_persistent_connection(self):
        """AT commands should reuse the same serial connection, not open a new one."""
        modem, mock_ser = self._make_modem_with_mock_serial()

        with patch("bugsi_daemon.hardware.lte.serial", create=True):
            result = await modem._send_at_command("AT+CSQ", timeout=5.0)

        assert "+CSQ:" in result
        mock_ser.reset_input_buffer.assert_called_once()
        mock_ser.write.assert_called_once_with(b"AT+CSQ\r\n")

    async def test_multiple_commands_same_connection(self):
        """Multiple AT commands should all use the same serial object."""
        modem, mock_ser = self._make_modem_with_mock_serial()

        # First command
        mock_ser.readline.side_effect = [b"OK\r\n"]
        await modem._send_at_command("AT", timeout=5.0)

        # Second command — same connection, no re-open
        mock_ser.readline.side_effect = [b"+CSQ: 15,0\r\n", b"OK\r\n"]
        await modem._send_at_command("AT+CSQ", timeout=5.0)

        assert mock_ser.reset_input_buffer.call_count == 2
        assert modem._serial_conn is mock_ser

    async def test_reopens_if_connection_closed(self):
        """If the serial connection was closed, it should reopen."""
        modem, mock_ser = self._make_modem_with_mock_serial()
        mock_ser.is_open = False

        new_mock_ser = MagicMock()
        new_mock_ser.is_open = True
        new_mock_ser.readline.side_effect = [b"OK\r\n"]

        with patch("serial.Serial", return_value=new_mock_ser):
            await modem._send_at_command("AT", timeout=5.0)

        assert modem._serial_conn is new_mock_ser
        new_mock_ser.reset_input_buffer.assert_called_once()


@pytest.mark.asyncio
class TestMockLteModem:
    async def test_starts_powered_off(self):
        modem = MockLteModem()
        assert not modem.is_powered()

    async def test_power_on_off(self):
        modem = MockLteModem()
        await modem.power_on()
        assert modem.is_powered()
        await modem.power_off()
        assert not modem.is_powered()

    async def test_wait_for_network_when_powered(self):
        modem = MockLteModem()
        await modem.power_on()
        result = await modem.wait_for_network(timeout=5.0)
        assert result is True

    async def test_wait_for_network_when_off(self):
        modem = MockLteModem()
        result = await modem.wait_for_network(timeout=5.0)
        assert result is False

    async def test_signal_info_when_powered(self):
        modem = MockLteModem()
        await modem.power_on()
        info = await modem.get_signal_info()

        assert "lte_signal_strength" in info
        assert "lte_signal_quality" in info
        assert -110 <= info["lte_signal_strength"] <= -60
        assert -20 <= info["lte_signal_quality"] <= -3

    async def test_signal_info_when_off(self):
        modem = MockLteModem()
        info = await modem.get_signal_info()

        assert info["lte_signal_strength"] is None
        assert info["lte_signal_quality"] is None
