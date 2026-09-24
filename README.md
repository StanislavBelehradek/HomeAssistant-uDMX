# HomeAssistant UsbDMX Application

A Home Assistant **add-on** (formerly known as a "hass.io addon") that drives a
DMX512 universe through a cheap USB-to-DMX interface (e.g. **Lixada USB
DMX512**) using `libusb` via [PyUSB](https://github.com/pyusb/pyusb). It talks
to the widely cloned **uDMX (Anyma) protocol**, so most generic
uDMX-compatible adapters (VID `16C0` / PID `05DC`) should work.

It runs as a standalone add-on rather than a custom integration because Home
Assistant OS's Core container does not ship `libusb` and does not allow
installing arbitrary system packages; the add-on's own Docker image installs
`libusb` itself. Configured light fixtures are exposed to Home Assistant as
regular `light` entities through **MQTT discovery** (no custom component
required - just the built-in MQTT integration).

## Features

- Talks directly to the uDMX-protocol adapter via `libusb`/PyUSB.
- Publishes fixtures as Home Assistant `light` entities via MQTT discovery:
  - **Single** – one dimmable channel.
  - **CCT** – tunable white, 2 channels (cold white, warm white).
  - **RGB** – 3 channels (red, green, blue).
  - **RGBCCT** – 5 channels (red, green, blue, cold white, warm white).
- Configurable refresh behavior: periodic full-universe resend (`refresh_rate`)
  or send-only-on-change (`refresh_rate: 0`), and configurable USB transfer
  chunking (`chunk_size`, `0` = send the whole range in one transfer).

## Installation

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store → ⋮ →
   Repositories**, and add this repository's URL.
2. Install the **USB DMX512 (Lixada/uDMX)** add-on that appears in the store.
3. Configure the add-on: USB vendor/product ID, MQTT broker connection, and
   the list of light fixtures (name, mode, DMX start channel).
4. Start the add-on. The configured lights will appear in Home Assistant once
   MQTT discovery messages are published.

See [usb_dmx/README.md](usb_dmx/README.md) for the full list of configuration
options.

## Requirements

- The Home Assistant **MQTT integration**, backed by a broker (e.g. the
  official Mosquitto add-on), must already be set up.
- The USB DMX adapter must be plugged into the host running Home Assistant
  OS/Supervised; the add-on requests USB access (`usb: true`) automatically.

