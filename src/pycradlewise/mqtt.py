"""MQTT real-time connection to Cradlewise via AWS IoT Core."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from uuid import uuid4

_DEFAULT_REGION = "us-east-1"

_LOGGER = logging.getLogger(__name__)

MQTT_AVAILABLE = True
try:
    from awscrt import auth as crt_auth
    from awscrt import mqtt as crt_mqtt
    from awsiot import mqtt_connection_builder
except ImportError:
    MQTT_AVAILABLE = False


class CradlewiseMqtt:
    """Manages MQTT connection to AWS IoT for real-time cradle state."""

    def __init__(self) -> None:
        self._connection = None
        self._connected = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._endpoint: str | None = None

    @property
    def available(self) -> bool:
        return MQTT_AVAILABLE and self._connected

    async def connect(
        self,
        access_key: str,
        secret_key: str,
        session_token: str,
        cradle_ids: list[str],
        on_state_update: Callable[[str, dict], None],
        region: str = _DEFAULT_REGION,
        iot_endpoint: str | None = None,
    ) -> None:
        """Connect to AWS IoT and subscribe to cradle state topics."""
        if not MQTT_AVAILABLE:
            _LOGGER.info(
                "awsiotsdk not installed — MQTT unavailable, using REST polling"
            )
            return

        self._loop = asyncio.get_running_loop()

        try:
            if iot_endpoint:
                self._endpoint = iot_endpoint
            if not self._endpoint:
                _LOGGER.warning(
                    "No IoT endpoint provided — MQTT unavailable"
                )
                return

            self._connection = await asyncio.to_thread(
                self._build_connection, access_key, secret_key, session_token, region
            )
            connect_future = self._connection.connect()
            await asyncio.to_thread(connect_future.result, 10)
            self._connected = True
            _LOGGER.info("Connected to Cradlewise MQTT")
        except Exception:
            _LOGGER.warning("Failed to connect to MQTT", exc_info=True)
            self._connected = False
            return

        for cradle_id in cradle_ids:
            await self._subscribe_cradle(cradle_id, on_state_update)

    def _build_connection(
        self, access_key: str, secret_key: str, session_token: str, region: str = _DEFAULT_REGION
    ):
        credentials_provider = crt_auth.AwsCredentialsProvider.new_static(
            access_key_id=access_key,
            secret_access_key=secret_key,
            session_token=session_token,
        )
        return mqtt_connection_builder.websockets_with_default_aws_signing(
            endpoint=self._endpoint,
            region=region,
            credentials_provider=credentials_provider,
            client_id=f"ha-cradlewise-{uuid4().hex[:8]}",
            clean_session=True,
            keep_alive_secs=30,
            on_connection_interrupted=self._on_interrupted,
            on_connection_resumed=self._on_resumed,
        )

    async def _subscribe_cradle(
        self, cradle_id: str, callback: Callable[[str, dict], None]
    ) -> None:
        shadow_topic = f"$aws/things/{cradle_id}/shadow/get/accepted"
        state_topic = f"{cradle_id}/cradle_state"

        def _on_message(topic, payload, **kwargs):
            try:
                data = json.loads(payload)
                if "state" in data and "reported" in data["state"]:
                    state = data["state"]["reported"]
                else:
                    state = data
                if self._loop and not self._loop.is_closed():
                    self._loop.call_soon_threadsafe(callback, cradle_id, state)
            except Exception:
                _LOGGER.debug("Failed to parse MQTT message on %s", topic)

        for topic in (shadow_topic, state_topic):
            try:
                sub_future, _ = self._connection.subscribe(
                    topic=topic,
                    qos=crt_mqtt.QoS.AT_LEAST_ONCE,
                    callback=_on_message,
                )
                await asyncio.to_thread(sub_future.result, 10)
                _LOGGER.debug("Subscribed to %s", topic)
            except Exception:
                _LOGGER.warning("Failed to subscribe to %s", topic, exc_info=True)

        try:
            pub_future, _ = self._connection.publish(
                topic=f"$aws/things/{cradle_id}/shadow/get",
                payload=json.dumps({}),
                qos=crt_mqtt.QoS.AT_LEAST_ONCE,
            )
            await asyncio.to_thread(pub_future.result, 5)
        except Exception:
            _LOGGER.debug("Failed to request shadow for %s", cradle_id)

    def _on_interrupted(self, connection, error, **kwargs):
        _LOGGER.warning("MQTT connection interrupted: %s", error)
        self._connected = False

    def _on_resumed(self, connection, return_code, session_present, **kwargs):
        _LOGGER.info("MQTT connection resumed (code=%s)", return_code)
        self._connected = True

    async def disconnect(self) -> None:
        if self._connection and self._connected:
            try:
                fut = self._connection.disconnect()
                await asyncio.to_thread(fut.result, 5)
            except Exception:
                pass
            self._connected = False

    async def reconnect(
        self,
        access_key: str,
        secret_key: str,
        session_token: str,
        cradle_ids: list[str],
        on_state_update: Callable[[str, dict], None],
        region: str = _DEFAULT_REGION,
        iot_endpoint: str | None = None,
    ) -> None:
        await self.disconnect()
        await self.connect(
            access_key, secret_key, session_token, cradle_ids, on_state_update,
            region, iot_endpoint=iot_endpoint,
        )
