"""DMX light fixtures exposed to Home Assistant via MQTT discovery.

Uses the standard MQTT JSON light schema
(https://www.home-assistant.io/integrations/light.mqtt/#json-schema) so no
custom Home Assistant component is required - the built-in MQTT integration
creates the entities automatically.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .const import LIGHT_MODE_CHANNELS
from .dmx_controller import UsbDmxController

MIN_MIREDS = 153  # ~6500K (cold white)
MAX_MIREDS = 370  # ~2700K (warm white)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    return _SLUG_RE.sub("_", name.lower()).strip("_")


class DmxLight:
    """Base class for a DMX-controlled light fixture bridged over MQTT."""

    mode: str

    def __init__(self, controller: UsbDmxController, name: str, start_channel: int) -> None:
        self._controller = controller
        self.name = name
        self.start_channel = start_channel
        self.object_id = f"{_slugify(name)}_{start_channel}"
        self.unique_id = f"usb_dmx_{self.object_id}"
        self.command_topic = f"usb_dmx/{self.object_id}/set"
        self.state_topic = f"usb_dmx/{self.object_id}/state"
        # controls the HA entity_id (e.g. light.udmx_bodovkychodba) instead of
        # HA's default of combining the device name with the entity name
        self.entity_object_id = f"udmx_{_slugify(name)}"
        self.is_on = False
        self.brightness = 255

    @property
    def channel_count(self) -> int:
        return LIGHT_MODE_CHANNELS[self.mode]

    def discovery_payload(
        self, discovery_prefix: str, availability_topic: str
    ) -> tuple[str, dict[str, Any]]:
        """Build the (topic, payload) for MQTT discovery of this light."""
        topic = f"{discovery_prefix}/light/usb_dmx/{self.object_id}/config"
        payload: dict[str, Any] = {
            "name": self.name,
            "unique_id": self.unique_id,
            "object_id": self.entity_object_id,
            "schema": "json",
            "command_topic": self.command_topic,
            "state_topic": self.state_topic,
            "availability_topic": availability_topic,
            "brightness": True,
            "device": {
                "identifiers": ["usb_dmx"],
                "name": "USB DMX512 (Lixada/uDMX)",
                "manufacturer": "Lixada/uDMX",
            },
        }
        payload.update(self._extra_discovery_fields())
        return topic, payload

    def _extra_discovery_fields(self) -> dict[str, Any]:
        return {}

    def initial_state_payload(self) -> dict[str, Any]:
        return {"state": "OFF"}

    def handle_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Apply an incoming MQTT command, write DMX channels, return new state."""
        raise NotImplementedError

    def off_values(self) -> list[int]:
        return [0] * self.channel_count

    def turn_off(self) -> dict[str, Any]:
        self.is_on = False
        self._controller.set_channels(self.start_channel, self.off_values())
        return {"state": "OFF"}


class SingleChannelLight(DmxLight):
    """A single dimmable DMX channel (e.g. a plain white channel)."""

    mode = "single"

    def _extra_discovery_fields(self) -> dict[str, Any]:
        return {"supported_color_modes": ["brightness"]}

    def initial_state_payload(self) -> dict[str, Any]:
        return {"state": "OFF", "brightness": self.brightness, "color_mode": "brightness"}

    def handle_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("state") == "OFF":
            return self.turn_off()

        self.is_on = True
        self.brightness = payload.get("brightness", self.brightness)
        self._controller.set_channel(self.start_channel, self.brightness)
        return {"state": "ON", "brightness": self.brightness, "color_mode": "brightness"}


class CctLight(DmxLight):
    """Tunable-white fixture using two channels: cold white, warm white."""

    mode = "cct"

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.color_temp = MIN_MIREDS

    def _extra_discovery_fields(self) -> dict[str, Any]:
        return {
            "supported_color_modes": ["color_temp"],
            "min_mireds": MIN_MIREDS,
            "max_mireds": MAX_MIREDS,
        }

    def initial_state_payload(self) -> dict[str, Any]:
        return {
            "state": "OFF",
            "brightness": self.brightness,
            "color_temp": self.color_temp,
            "color_mode": "color_temp",
        }

    def handle_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("state") == "OFF":
            return self.turn_off()

        self.is_on = True
        self.brightness = payload.get("brightness", self.brightness)
        self.color_temp = payload.get("color_temp", self.color_temp)

        span = MAX_MIREDS - MIN_MIREDS
        warm_ratio = (self.color_temp - MIN_MIREDS) / span
        warm_ratio = max(0.0, min(1.0, warm_ratio))
        cold_value = round(self.brightness * (1 - warm_ratio))
        warm_value = round(self.brightness * warm_ratio)

        self._controller.set_channels(self.start_channel, [cold_value, warm_value])
        return {
            "state": "ON",
            "brightness": self.brightness,
            "color_temp": self.color_temp,
            "color_mode": "color_temp",
        }


class RgbLight(DmxLight):
    """RGB fixture using three channels: red, green, blue."""

    mode = "rgb"

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.rgb = (255, 255, 255)

    def _extra_discovery_fields(self) -> dict[str, Any]:
        return {"supported_color_modes": ["rgb"]}

    def initial_state_payload(self) -> dict[str, Any]:
        r, g, b = self.rgb
        return {
            "state": "OFF",
            "brightness": self.brightness,
            "color_mode": "rgb",
            "color": {"r": r, "g": g, "b": b},
        }

    def handle_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("state") == "OFF":
            return self.turn_off()

        self.is_on = True
        self.brightness = payload.get("brightness", self.brightness)
        color = payload.get("color", {})
        self.rgb = (
            color.get("r", self.rgb[0]),
            color.get("g", self.rgb[1]),
            color.get("b", self.rgb[2]),
        )

        scale = self.brightness / 255
        values = [round(c * scale) for c in self.rgb]
        self._controller.set_channels(self.start_channel, values)

        r, g, b = self.rgb
        return {
            "state": "ON",
            "brightness": self.brightness,
            "color_mode": "rgb",
            "color": {"r": r, "g": g, "b": b},
        }


class RgbCctLight(DmxLight):
    """RGB + tunable-white fixture: red, green, blue, cold white, warm white."""

    mode = "rgbcct"

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.rgbww = (255, 255, 255, 0, 0)

    def _extra_discovery_fields(self) -> dict[str, Any]:
        return {"supported_color_modes": ["rgbww"]}

    def initial_state_payload(self) -> dict[str, Any]:
        r, g, b, c, w = self.rgbww
        return {
            "state": "OFF",
            "brightness": self.brightness,
            "color_mode": "rgbww",
            "color": {"r": r, "g": g, "b": b, "c": c, "w": w},
        }

    def handle_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("state") == "OFF":
            return self.turn_off()

        self.is_on = True
        self.brightness = payload.get("brightness", self.brightness)
        color = payload.get("color", {})
        self.rgbww = (
            color.get("r", self.rgbww[0]),
            color.get("g", self.rgbww[1]),
            color.get("b", self.rgbww[2]),
            color.get("c", self.rgbww[3]),
            color.get("w", self.rgbww[4]),
        )

        scale = self.brightness / 255
        values = [round(c * scale) for c in self.rgbww]
        self._controller.set_channels(self.start_channel, values)

        r, g, b, c, w = self.rgbww
        return {
            "state": "ON",
            "brightness": self.brightness,
            "color_mode": "rgbww",
            "color": {"r": r, "g": g, "b": b, "c": c, "w": w},
        }


LIGHT_CLASSES: dict[str, type[DmxLight]] = {
    "single": SingleChannelLight,
    "cct": CctLight,
    "rgb": RgbLight,
    "rgbcct": RgbCctLight,
}


def create_light(mode: str, controller: UsbDmxController, name: str, start_channel: int) -> DmxLight:
    return LIGHT_CLASSES[mode](controller, name, start_channel)


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload)
