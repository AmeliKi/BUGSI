"""Tests for bugsi_daemon.net.routing helpers."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from bugsi_daemon.net.routing import LteRoute, resolve_ip, resolve_server_host


class TestResolveServerHost:
    def test_with_explicit_port(self):
        host, port = resolve_server_host("http://192.168.1.5:8000/api/device-data")
        assert host == "192.168.1.5"
        assert port == 8000

    def test_https_default_port(self):
        host, port = resolve_server_host("https://api.bugsi.io/api/device-data")
        assert host == "api.bugsi.io"
        assert port == 443

    def test_http_default_port(self):
        host, port = resolve_server_host("http://backend/api/device-data")
        assert host == "backend"
        assert port == 80


class TestResolveIp:
    def test_localhost(self):
        ip = resolve_ip("localhost")
        assert ip == "127.0.0.1"

    def test_invalid_host(self):
        ip = resolve_ip("this-host-does-not-exist.invalid")
        assert ip is None

    def test_ip_passthrough(self):
        ip = resolve_ip("10.42.0.1")
        assert ip == "10.42.0.1"


@pytest.mark.asyncio
class TestLteRoute:
    async def test_adds_and_removes_route(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("bugsi_daemon.net.routing.asyncio.create_subprocess_exec",
                    return_value=mock_proc) as mock_exec:
            route = LteRoute("1.2.3.4", "usb0")
            await route.__aenter__()
            assert route._route_added is True

            await route.__aexit__(None, None, None)

            # Should have been called twice: add and del
            assert mock_exec.call_count == 2
            add_call = mock_exec.call_args_list[0]
            assert "add" in add_call.args
            assert "1.2.3.4/32" in add_call.args
            assert "usb0" in add_call.args

            del_call = mock_exec.call_args_list[1]
            assert "del" in del_call.args

    async def test_handles_existing_route(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"RTNETLINK answers: File exists")
        )
        mock_proc.returncode = 2

        with patch("bugsi_daemon.net.routing.asyncio.create_subprocess_exec",
                    return_value=mock_proc):
            route = LteRoute("1.2.3.4", "usb0")
            await route.__aenter__()
            # Should still be marked as added (we'll clean it up)
            assert route._route_added is True

    async def test_add_failure_skips_delete(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"Network is unreachable")
        )
        mock_proc.returncode = 2

        with patch("bugsi_daemon.net.routing.asyncio.create_subprocess_exec",
                    return_value=mock_proc) as mock_exec:
            route = LteRoute("1.2.3.4", "usb0")
            await route.__aenter__()
            assert route._route_added is False

            await route.__aexit__(None, None, None)
            # Only the add call should have been made, no del
            assert mock_exec.call_count == 1
