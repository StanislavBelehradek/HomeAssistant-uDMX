"""Constants for the USB DMX512 (Lixada/uDMX) add-on."""
from __future__ import annotations

DMX_UNIVERSE_SIZE = 512
DMX_MIN_CHANNEL = 1
DMX_MAX_CHANNEL = DMX_UNIVERSE_SIZE

# uDMX firmware vendor requests (Anyma uDMX protocol, used by Lixada clones).
CMD_SET_SINGLE_CHANNEL = 1
CMD_SET_CHANNEL_RANGE = 2

# How many DMX channels each fixture mode occupies.
LIGHT_MODE_CHANNELS = {
    "single": 1,
    "cct": 2,
    "rgb": 3,
    "rgbcct": 5,
}

OPTIONS_FILE = "/data/options.json"
