"""libusb-backed DMX512 universe controller for uDMX-protocol adapters.

Targets cheap "Anyma uDMX" firmware clones (e.g. Lixada USB DMX512), which
expose a control-transfer interface (USB_TYPE_VENDOR | USB_RECIP_DEVICE):

  CMD_SET_CHANNEL_RANGE (bRequest=2): wValue=channel count, wIndex=start
  channel (0-based), data=channel values. Some firmware clones only accept
  small chunks per control transfer (chunk_size); set it to 0 to send the
  whole range/universe in a single transfer instead.

By default the DMX universe (512 channels) is refreshed continuously from a
background thread, because these adapters do not generate a DMX signal on
their own between updates. Set refresh_rate to 0 to disable that background
refresh and instead push only the changed channels immediately.
"""
from __future__ import annotations

import logging
import threading
import time

import usb.core
import usb.util

from .const import CMD_SET_CHANNEL_RANGE, DMX_UNIVERSE_SIZE

_LOGGER = logging.getLogger(__name__)

_CTRL_OUT = usb.util.build_request_type(
    usb.util.CTRL_OUT, usb.util.CTRL_TYPE_VENDOR, usb.util.CTRL_RECIPIENT_DEVICE
)


class UsbDmxError(Exception):
    """Raised when the USB DMX adapter cannot be opened or controlled."""


class UsbDmxController:
    """Owns the USB device and the DMX universe buffer."""

    def __init__(
        self,
        vendor_id: int,
        product_id: int,
        refresh_rate: int,
        chunk_size: int,
    ) -> None:
        self._vendor_id = vendor_id
        self._product_id = product_id
        self._chunk_size = chunk_size
        # refresh_rate == 0 disables the periodic background resend.
        self._refresh_interval = 1.0 / refresh_rate if refresh_rate > 0 else None
        self._device: usb.core.Device | None = None
        self._buffer = bytearray(DMX_UNIVERSE_SIZE)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def open(self) -> None:
        """Find and initialize the USB device."""
        device = usb.core.find(idVendor=self._vendor_id, idProduct=self._product_id)
        if device is None:
            raise UsbDmxError(
                f"No USB device found for VID={self._vendor_id:04X} "
                f"PID={self._product_id:04X}"
            )
        try:
            if device.is_kernel_driver_active(0):
                device.detach_kernel_driver(0)
        except (NotImplementedError, usb.core.USBError):
            pass
        try:
            device.set_configuration()
        except usb.core.USBError as err:
            raise UsbDmxError(f"Failed to configure USB DMX adapter: {err}") from err

        self._device = device
        self._stop_event.clear()
        if self._refresh_interval is not None:
            self._thread = threading.Thread(
                target=self._refresh_loop, name="usb_dmx_refresh", daemon=True
            )
            self._thread.start()

    def close(self) -> None:
        """Stop the refresh thread (if any) and release the USB device."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        if self._device is not None:
            usb.util.dispose_resources(self._device)
            self._device = None

    def set_channel(self, channel: int, value: int) -> None:
        """Set a single 1-based DMX channel value (0-255)."""
        self.set_channels(channel, [value])

    def set_channels(self, start_channel: int, values: list[int]) -> None:
        """Set a contiguous range of 1-based DMX channels."""
        clamped = [max(0, min(255, v)) for v in values]
        with self._lock:
            self._buffer[start_channel - 1 : start_channel - 1 + len(clamped)] = clamped
            if self._refresh_interval is None:
                # No background refresh - push this change immediately.
                self._send_data(start_channel - 1, bytes(clamped))

    def _refresh_loop(self) -> None:
        while not self._stop_event.is_set():
            start_time = time.monotonic()
            with self._lock:
                snapshot = bytes(self._buffer)
            self._send_data(0, snapshot)
            elapsed = time.monotonic() - start_time
            self._stop_event.wait(max(0.0, self._refresh_interval - elapsed))

    def _send_data(self, start_channel_0based: int, data: bytes) -> None:
        assert self._device is not None
        if self._chunk_size <= 0:
            segments = [(start_channel_0based, data)]
        else:
            segments = [
                (start_channel_0based + offset, data[offset : offset + self._chunk_size])
                for offset in range(0, len(data), self._chunk_size)
            ]
        for index, chunk in segments:
            try:
                self._device.ctrl_transfer(
                    _CTRL_OUT,
                    CMD_SET_CHANNEL_RANGE,
                    wValue=len(chunk),
                    wIndex=index,
                    data_or_wLength=chunk,
                )
            except usb.core.USBError as err:
                _LOGGER.warning("USB DMX write failed at channel %s: %s", index + 1, err)
                return
