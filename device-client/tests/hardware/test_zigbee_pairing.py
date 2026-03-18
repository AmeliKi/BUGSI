import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bugsi_daemon.hardware.climate import ZigbeeClimateSensor


def _make_sensor(**kwargs) -> ZigbeeClimateSensor:
    return ZigbeeClimateSensor(**kwargs)


class _FakeMessage:
    def __init__(self, topic: str, payload: dict):
        self.topic = topic
        self.payload = json.dumps(payload).encode()


@pytest.mark.asyncio
class TestPairZigbee:
    async def test_not_powered_raises(self):
        sensor = _make_sensor()
        with pytest.raises(RuntimeError, match="powered on"):
            await sensor.pair_zigbee()

    async def test_publishes_permit_join(self):
        sensor = _make_sensor()
        sensor._powered = True

        published = []

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def subscribe(self, topic):
                pass

            async def publish(self, topic, payload, **kwargs):
                raw = payload.decode() if isinstance(payload, bytes) else payload
                published.append((topic, json.loads(raw)))

            @property
            def messages(self):
                return _empty_messages()

        async def _empty_messages():
            return
            yield

        with patch("aiomqtt.Client", return_value=FakeClient()):
            await sensor.pair_zigbee(timeout=1)

        # First publish: enable permit join; second: disable
        assert len(published) == 2
        assert published[0][0] == "zigbee2mqtt/bridge/request/permit_join"
        assert published[0][1] == {"value": True, "time": 1}
        assert published[1][1] == {"value": False}

    async def test_collects_joined_devices(self):
        sensor = _make_sensor()
        sensor._powered = True

        join_event = {
            "type": "device_joined",
            "data": {
                "friendly_name": "0xaabbccdd",
                "ieee_address": "0xaabbccdd",
                "model": "ZTH01",
                "vendor": "Tuya",
            },
        }

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def subscribe(self, topic):
                pass

            async def publish(self, topic, payload, **kwargs):
                pass

            @property
            def messages(self):
                return self._gen()

            async def _gen(self):
                yield _FakeMessage("zigbee2mqtt/bridge/event", join_event)
                await asyncio.sleep(999)

        with patch("aiomqtt.Client", return_value=FakeClient()):
            joined = await sensor.pair_zigbee(timeout=1)

        assert len(joined) == 1
        assert joined[0]["ieee_address"] == "0xaabbccdd"
        assert joined[0]["model"] == "ZTH01"

    async def test_callback_called(self):
        sensor = _make_sensor()
        sensor._powered = True

        join_event = {
            "type": "device_joined",
            "data": {"friendly_name": "0xaabb", "ieee_address": "0xaabb"},
        }

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def subscribe(self, topic):
                pass

            async def publish(self, topic, payload, **kwargs):
                pass

            @property
            def messages(self):
                return self._gen()

            async def _gen(self):
                yield _FakeMessage("zigbee2mqtt/bridge/event", join_event)
                await asyncio.sleep(999)

        callback_args = []

        with patch("aiomqtt.Client", return_value=FakeClient()):
            await sensor.pair_zigbee(timeout=1, on_device_joined=lambda d: callback_args.append(d))

        assert len(callback_args) == 1
        assert callback_args[0]["friendly_name"] == "0xaabb"

    async def test_disables_permit_join_after(self):
        sensor = _make_sensor()
        sensor._powered = True

        published = []

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def subscribe(self, topic):
                pass

            async def publish(self, topic, payload, **kwargs):
                raw = payload.decode() if isinstance(payload, bytes) else payload
                published.append((topic, json.loads(raw)))

            @property
            def messages(self):
                return self._gen()

            async def _gen(self):
                return
                yield

        with patch("aiomqtt.Client", return_value=FakeClient()):
            await sensor.pair_zigbee(timeout=1)

        last = published[-1]
        assert last[0] == "zigbee2mqtt/bridge/request/permit_join"
        assert last[1] == {"value": False}


@pytest.mark.asyncio
class TestRenameDevice:
    async def test_not_powered_raises(self):
        sensor = _make_sensor()
        with pytest.raises(RuntimeError, match="powered on"):
            await sensor.rename_device("old", "new")

    async def test_success(self):
        sensor = _make_sensor()
        sensor._powered = True

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def subscribe(self, topic):
                pass

            async def publish(self, topic, payload, **kwargs):
                pass

            @property
            def messages(self):
                return self._gen()

            async def _gen(self):
                yield _FakeMessage(
                    "zigbee2mqtt/bridge/response/device/rename",
                    {"status": "ok"},
                )

        with patch("aiomqtt.Client", return_value=FakeClient()):
            result = await sensor.rename_device("old_name", "new_name")

        assert result is True

    async def test_timeout(self):
        sensor = _make_sensor()
        sensor._powered = True

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def subscribe(self, topic):
                pass

            async def publish(self, topic, payload, **kwargs):
                pass

            @property
            def messages(self):
                return self._gen()

            async def _gen(self):
                return
                yield

        with patch("aiomqtt.Client", return_value=FakeClient()):
            result = await sensor.rename_device("old_name", "new_name")

        assert result is False
