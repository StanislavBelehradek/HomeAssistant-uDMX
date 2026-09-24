# USB DMX512 (Lixada/uDMX) add-on

Controls a DMX512 universe through a uDMX-compatible USB adapter (e.g.
**Lixada USB DMX512**) using `libusb` (installed in this add-on's container,
since Home Assistant OS does not ship it) and exposes configured fixtures as
Home Assistant `light` entities via MQTT discovery.

## Configuration

| Option | Description |
| --- | --- |
| `vendor_id` / `product_id` | USB IDs of the adapter (hex). Defaults `16C0`/`05DC` match the common uDMX clone firmware. |
| `refresh_rate` | Hz at which the full DMX universe is resent. `0` = send only on change. |
| `chunk_size` | Max channels per USB control transfer. `0` = send the whole range in one transfer. |
| `mqtt_host` / `mqtt_port` / `mqtt_username` / `mqtt_password` | Fallback MQTT broker connection details, only used if the Supervisor-managed broker (see below) isn't available. |
| `discovery_prefix` | MQTT discovery prefix configured in the Home Assistant MQTT integration (default `homeassistant`). |
| `lights` | List of fixtures: `name`, `mode` (`single`, `cct`, `rgb`, `rgbcct`), `start_channel` (1-512). |

## MQTT broker discovery

This add-on requests the `mqtt` Supervisor service (`services: ["mqtt:want"]`),
so if you have the official Mosquitto broker add-on (or another add-on
providing the MQTT service) installed, the broker host/port/credentials are
picked up automatically - no manual configuration needed. The `mqtt_host` /
`mqtt_port` / `mqtt_username` / `mqtt_password` options are only used as a
fallback when no such service is available (e.g. an external broker).

## Requirements

- The Home Assistant MQTT integration must be set up so discovered entities
  are picked up (a broker such as the Mosquitto add-on satisfies both this
  and the automatic discovery above).
- Pass the adapter through to the add-on (`usb: true` is already set); on
  Home Assistant OS this is handled automatically once the USB device is
  detected.
