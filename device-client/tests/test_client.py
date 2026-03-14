import json

import httpx
import pytest
import respx

from bugsi_daemon.net.client import BugsiClient


@pytest.fixture
def mock_client():
    return BugsiClient("http://test-backend:8000/api/device-data", "bugsi_test_key_123")


class TestBugsiClient:
    @respx.mock
    def test_send_telemetry(self, mock_client):
        route = respx.post("http://test-backend:8000/api/device-data/telemetry").mock(
            return_value=httpx.Response(201, json=[{"id": "abc", "battery_soc": 75.0}])
        )
        result = mock_client.send_telemetry([{"timestamp": "2026-03-06T12:00:00Z", "battery_soc": 75.0}])
        assert len(result) == 1
        assert route.called
        assert route.calls[0].request.headers["x-api-key"] == "bugsi_test_key_123"

    @respx.mock
    def test_poll_config(self, mock_client):
        respx.get("http://test-backend:8000/api/device-data/config").mock(
            return_value=httpx.Response(200, json={
                "version": 3,
                "config": {"detection": {"cooldown_seconds": 10}},
                "has_update": True,
            })
        )
        result = mock_client.poll_config()
        assert result["version"] == 3
        assert result["has_update"] is True

    @respx.mock
    def test_ack_config(self, mock_client):
        route = respx.post("http://test-backend:8000/api/device-data/config/ack").mock(
            return_value=httpx.Response(204)
        )
        mock_client.ack_config(3)
        assert route.called
        body = json.loads(route.calls[0].request.content)
        assert body["version"] == 3

    @respx.mock
    def test_check_ota_no_update(self, mock_client):
        respx.get("http://test-backend:8000/api/device-data/ota/check").mock(
            return_value=httpx.Response(200, json={"has_update": False, "deployment": None})
        )
        result = mock_client.check_ota()
        assert result["has_update"] is False

    @respx.mock
    def test_report_ota_status(self, mock_client):
        route = respx.post("http://test-backend:8000/api/device-data/ota/deploy-123/status").mock(
            return_value=httpx.Response(204)
        )
        mock_client.report_ota_status("deploy-123", "completed")
        assert route.called
        body = json.loads(route.calls[0].request.content)
        assert body["status"] == "completed"

    @respx.mock
    def test_unauthorized_raises(self, mock_client):
        respx.get("http://test-backend:8000/api/device-data/config").mock(
            return_value=httpx.Response(401, json={"detail": "Invalid API key"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            mock_client.poll_config()
