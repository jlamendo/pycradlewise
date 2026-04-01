"""Tests for pycradlewise.mqtt."""

import asyncio
import json
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from pycradlewise.mqtt import CradlewiseMqtt, MQTT_AVAILABLE


class TestCradlewiseMqtt:
    def test_init(self):
        mqtt = CradlewiseMqtt()
        assert mqtt.available is False
        assert mqtt._connected is False
        assert mqtt._connection is None

    @pytest.mark.asyncio
    async def test_connect_without_awsiotsdk(self):
        mqtt = CradlewiseMqtt()
        with patch("pycradlewise.mqtt.MQTT_AVAILABLE", False):
            await mqtt.connect("ak", "sk", "token", ["c1"], lambda cid, state: None)
        assert mqtt._connected is False

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MQTT_AVAILABLE, reason="awsiotsdk not installed")
    async def test_connect_without_endpoint(self):
        mqtt = CradlewiseMqtt()
        await mqtt.connect("ak", "sk", "token", ["c1"], lambda cid, state: None)
        assert mqtt._connected is False

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MQTT_AVAILABLE, reason="awsiotsdk not installed")
    async def test_connect_success(self):
        mqtt = CradlewiseMqtt()

        mock_connection = MagicMock()
        mock_future = MagicMock()
        mock_future.result.return_value = None
        mock_connection.connect.return_value = mock_future
        mock_connection.subscribe.return_value = (mock_future, 1)
        mock_connection.publish.return_value = (mock_future, 1)

        with patch.object(mqtt, "_build_connection", return_value=mock_connection):
            await mqtt.connect(
                "ak", "sk", "token", ["cradle-1"], lambda cid, state: None,
                iot_endpoint="test-endpoint.iot.us-east-1.amazonaws.com",
            )

        assert mqtt._connected is True
        assert mqtt.available is True
        # Should subscribe to 2 topics per cradle (shadow + state)
        assert mock_connection.subscribe.call_count == 2
        # Should publish shadow get request
        assert mock_connection.publish.call_count == 1

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MQTT_AVAILABLE, reason="awsiotsdk not installed")
    async def test_connect_failure(self):
        mqtt = CradlewiseMqtt()

        mock_connection = MagicMock()
        mock_future = MagicMock()
        mock_future.result.side_effect = Exception("Connection refused")
        mock_connection.connect.return_value = mock_future

        with patch.object(mqtt, "_build_connection", return_value=mock_connection):
            await mqtt.connect(
                "ak", "sk", "token", ["c1"], lambda cid, state: None,
                iot_endpoint="test-endpoint.iot.us-east-1.amazonaws.com",
            )

        assert mqtt._connected is False
        assert mqtt.available is False

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MQTT_AVAILABLE, reason="awsiotsdk not installed")
    async def test_disconnect(self):
        mqtt = CradlewiseMqtt()
        mqtt._connected = True
        mock_connection = MagicMock()
        mock_future = MagicMock()
        mock_future.result.return_value = None
        mock_connection.disconnect.return_value = mock_future
        mqtt._connection = mock_connection

        await mqtt.disconnect()
        assert mqtt._connected is False
        mock_connection.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        mqtt = CradlewiseMqtt()
        await mqtt.disconnect()  # Should not raise

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MQTT_AVAILABLE, reason="awsiotsdk not installed")
    async def test_reconnect(self):
        mqtt = CradlewiseMqtt()
        mqtt._connected = True
        mock_connection = MagicMock()
        mock_future = MagicMock()
        mock_future.result.return_value = None
        mock_connection.disconnect.return_value = mock_future
        mock_connection.connect.return_value = mock_future
        mock_connection.subscribe.return_value = (mock_future, 1)
        mock_connection.publish.return_value = (mock_future, 1)
        mqtt._connection = mock_connection

        with patch.object(mqtt, "_build_connection", return_value=mock_connection):
            await mqtt.reconnect(
                "ak", "sk", "token", ["c1"], lambda cid, state: None,
                iot_endpoint="test-endpoint.iot.us-east-1.amazonaws.com",
            )

        mock_connection.disconnect.assert_called_once()
        assert mqtt._connected is True

    def test_on_interrupted(self):
        mqtt = CradlewiseMqtt()
        mqtt._connected = True
        mqtt._on_interrupted(None, Exception("network error"))
        assert mqtt._connected is False

    def test_on_resumed(self):
        mqtt = CradlewiseMqtt()
        mqtt._connected = False
        mqtt._on_resumed(None, 0, True)
        assert mqtt._connected is True

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MQTT_AVAILABLE, reason="awsiotsdk not installed")
    async def test_subscribe_callback_parses_shadow(self):
        """Test that MQTT message callback correctly parses shadow responses."""
        mqtt = CradlewiseMqtt()
        mqtt._loop = asyncio.get_running_loop()

        received = {}

        def on_update(cradle_id, state):
            received["cradle_id"] = cradle_id
            received["state"] = state

        mock_connection = MagicMock()
        mock_future = MagicMock()
        mock_future.result.return_value = None
        mqtt._connection = mock_connection

        callbacks = []
        def fake_subscribe(topic, qos, callback):
            callbacks.append(callback)
            return (mock_future, 1)
        mock_connection.subscribe.side_effect = fake_subscribe
        mock_connection.publish.return_value = (mock_future, 1)

        await mqtt._subscribe_cradle("cradle-1", on_update)

        shadow_payload = json.dumps({
            "state": {
                "reported": {"babyPresent": True, "mode": "Normal"}
            }
        }).encode()

        callbacks[0]("$aws/things/cradle-1/shadow/get/accepted", shadow_payload)
        # call_soon_threadsafe schedules but needs a tick to execute
        await asyncio.sleep(0)

        assert received["cradle_id"] == "cradle-1"
        assert received["state"]["babyPresent"] is True
        assert received["state"]["mode"] == "Normal"

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MQTT_AVAILABLE, reason="awsiotsdk not installed")
    async def test_subscribe_callback_parses_direct_state(self):
        """Test that MQTT message callback handles direct state messages."""
        mqtt = CradlewiseMqtt()
        mqtt._loop = asyncio.get_running_loop()

        received = {}

        def on_update(cradle_id, state):
            received["state"] = state

        mock_connection = MagicMock()
        mock_future = MagicMock()
        mock_future.result.return_value = None
        mqtt._connection = mock_connection

        callbacks = []
        def fake_subscribe(topic, qos, callback):
            callbacks.append(callback)
            return (mock_future, 1)
        mock_connection.subscribe.side_effect = fake_subscribe
        mock_connection.publish.return_value = (mock_future, 1)

        await mqtt._subscribe_cradle("cradle-1", on_update)

        direct_payload = json.dumps({"babyPresent": False}).encode()
        callbacks[1]("cradle-1/cradle_state", direct_payload)
        await asyncio.sleep(0)

        assert received["state"]["babyPresent"] is False

    @pytest.mark.asyncio
    @pytest.mark.skipif(not MQTT_AVAILABLE, reason="awsiotsdk not installed")
    async def test_subscribe_callback_handles_bad_json(self):
        """Callback should not crash on invalid JSON."""
        mqtt = CradlewiseMqtt()
        mqtt._loop = asyncio.get_running_loop()

        mock_connection = MagicMock()
        mock_future = MagicMock()
        mock_future.result.return_value = None
        mqtt._connection = mock_connection

        callbacks = []
        mock_connection.subscribe.side_effect = lambda topic, qos, callback: (callbacks.append(callback), (mock_future, 1))[1]
        mock_connection.publish.return_value = (mock_future, 1)

        await mqtt._subscribe_cradle("c1", lambda cid, state: None)
        # Should not raise
        callbacks[0]("topic", b"not json")

    @pytest.mark.skipif(not MQTT_AVAILABLE, reason="awsiotsdk not installed")
    def test_build_connection(self):
        mqtt = CradlewiseMqtt()
        mqtt._endpoint = "test-endpoint.iot.us-east-1.amazonaws.com"
        with patch("pycradlewise.mqtt.mqtt_connection_builder") as mock_builder:
            mock_builder.websockets_with_default_aws_signing.return_value = MagicMock()
            conn = mqtt._build_connection("ak", "sk", "token")

            mock_builder.websockets_with_default_aws_signing.assert_called_once()
            kwargs = mock_builder.websockets_with_default_aws_signing.call_args[1]
            assert kwargs["endpoint"] == "test-endpoint.iot.us-east-1.amazonaws.com"
            assert kwargs["region"] == "us-east-1"
            assert kwargs["clean_session"] is True
