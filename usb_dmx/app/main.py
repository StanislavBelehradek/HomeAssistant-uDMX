"""Entry point for the USB DMX512 (Lixada/uDMX) add-on.

Reads the add-on options, opens the USB DMX adapter, connects to the
configured MQTT broker, publishes MQTT discovery configs for the configured
light fixtures, and forwards incoming commands to the adapter.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
from types import FrameType

import paho.mqtt.client as mqtt

from .const import OPTIONS_FILE
from .dmx_controller import UsbDmxController, UsbDmxError
from .mqtt_light import DmxLight, create_light, dumps

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
_LOGGER = logging.getLogger("usb_dmx")

AVAILABILITY_TOPIC = "usb_dmx/status"


def _load_options() -> dict:
    with open(OPTIONS_FILE, encoding="utf-8") as handle:
        return json.load(handle)


def _mqtt_settings(options: dict) -> tuple[str, int, str | None, str | None]:
    """MQTT connection info: env vars set by run.sh (Supervisor service or
    manual fallback) take precedence over the raw add-on options."""
    host = os.environ.get("MQTT_HOST") or options.get("mqtt_host")
    port = int(os.environ.get("MQTT_PORT") or options.get("mqtt_port") or 1883)
    username = os.environ.get("MQTT_USERNAME") or options.get("mqtt_username") or None
    password = os.environ.get("MQTT_PASSWORD") or options.get("mqtt_password") or None
    if not host:
        raise UsbDmxError("No MQTT broker configured (Supervisor service unavailable and mqtt_host is empty)")
    return host, port, username, password


def _build_lights(options: dict, controller: UsbDmxController) -> list[DmxLight]:
    lights: list[DmxLight] = []
    for light_config in options.get("lights", []):
        light = create_light(
            light_config["mode"],
            controller,
            light_config["name"],
            light_config["start_channel"],
        )
        lights.append(light)
    return lights


def main() -> None:
    options = _load_options()

    controller = UsbDmxController(
        vendor_id=int(options["vendor_id"], 16),
        product_id=int(options["product_id"], 16),
        refresh_rate=options["refresh_rate"],
        chunk_size=options["chunk_size"],
    )
    try:
        controller.open()
    except UsbDmxError as err:
        _LOGGER.error("%s", err)
        sys.exit(1)

    lights = _build_lights(options, controller)
    lights_by_command_topic = {light.command_topic: light for light in lights}
    discovery_prefix = options.get("discovery_prefix", "homeassistant")

    try:
        mqtt_host, mqtt_port, mqtt_username, mqtt_password = _mqtt_settings(options)
    except UsbDmxError as err:
        _LOGGER.error("%s", err)
        sys.exit(1)

    client = mqtt.Client()
    if mqtt_username:
        client.username_pw_set(mqtt_username, mqtt_password)
    client.will_set(AVAILABILITY_TOPIC, payload="offline", retain=True)

    def on_connect(client: mqtt.Client, _userdata, _flags, _rc) -> None:
        _LOGGER.info("Connected to MQTT broker, publishing %d light(s)", len(lights))
        client.publish(AVAILABILITY_TOPIC, "online", retain=True)
        for light in lights:
            topic, payload = light.discovery_payload(discovery_prefix, AVAILABILITY_TOPIC)
            client.publish(topic, dumps(payload), retain=True)
            client.publish(light.state_topic, dumps(light.initial_state_payload()), retain=True)
            client.subscribe(light.command_topic)

    def on_message(client: mqtt.Client, _userdata, message: mqtt.MQTTMessage) -> None:
        light = lights_by_command_topic.get(message.topic)
        if light is None:
            return
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            _LOGGER.warning("Invalid command payload on %s", message.topic)
            return

        new_state = light.handle_command(payload)
        client.publish(light.state_topic, dumps(new_state), retain=True)

    client.on_connect = on_connect
    client.on_message = on_message

    def handle_shutdown(_signum: int, _frame: FrameType | None) -> None:
        _LOGGER.info("Shutting down")
        client.publish(AVAILABILITY_TOPIC, "offline", retain=True)
        client.disconnect()
        controller.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    client.connect(mqtt_host, mqtt_port)
    client.loop_forever()


if __name__ == "__main__":
    main()
