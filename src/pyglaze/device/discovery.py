from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import serial.tools.list_ports

if TYPE_CHECKING:
    from collections.abc import Callable

_GLAZE_MANUFACTURER = "GLAZE Technologies"
_GLAZE_PRODUCTS = ("THz-CCS",)
_SKIP_SUBSTRINGS = ("Bluetooth", "debug")


class DeviceNotFoundError(Exception):
    """No GLAZE device found on any serial port."""


class MultipleDevicesError(Exception):
    """Multiple GLAZE devices found when exactly one was expected."""


def discover() -> list[str]:
    """Find all connected GLAZE devices.

    Enumerates serial ports and filters for FTDI-based devices by VID
    or textual metadata. On macOS, deduplicates cu.*/tty.* pairs (keeps cu.*).

    Returns:
        List of serial port device paths.
    """
    return _enumerate_ports(_is_glaze_device)


def list_serial_ports() -> list[str]:
    """List all plausible serial ports (Bluetooth and debug ports excluded).

    On macOS, deduplicates cu.*/tty.* pairs (keeps cu.*).

    Returns:
        List of serial port device paths.
    """
    return _enumerate_ports(lambda _: True)


def discover_one() -> str:
    """Find exactly one connected GLAZE device.

    Returns:
        Serial port device path.

    Raises:
        DeviceNotFoundError: If no devices are found.
        MultipleDevicesError: If more than one device is found.
    """
    devices = discover()
    if len(devices) == 0:
        msg = "No GLAZE devices found. Check USB connection and FTDI drivers."
        raise DeviceNotFoundError(msg)
    if len(devices) > 1:
        msg = f"Multiple GLAZE devices found: {devices}. Specify amp_port explicitly."
        raise MultipleDevicesError(msg)
    return devices[0]


def _enumerate_ports(
    predicate: Callable[[object], bool],
) -> list[str]:
    """Enumerate serial ports, apply *predicate*, skip junk, and deduplicate."""
    candidates = [
        (port_info.device, port_info.serial_number)
        for port_info in serial.tools.list_ports.comports()
        if predicate(port_info)
        and not any(s in port_info.device for s in _SKIP_SUBSTRINGS)
    ]

    if sys.platform == "darwin":
        candidates = _deduplicate_macos(candidates)

    return [device for device, _ in candidates]


def _is_glaze_device(port_info: object) -> bool:
    manufacturer = getattr(port_info, "manufacturer", None) or ""
    product = getattr(port_info, "product", None) or ""
    return manufacturer == _GLAZE_MANUFACTURER and product in _GLAZE_PRODUCTS


def _deduplicate_macos(
    candidates: list[tuple[str, str | None]],
) -> list[tuple[str, str | None]]:
    """On macOS, each USB serial device appears as both /dev/cu.* and /dev/tty.*.

    Keep cu.* (non-blocking open) and drop the tty.* duplicate.
    Groups by serial_number; if serial_number is None, keeps both entries.
    """
    by_serial: dict[str | None, list[tuple[str, str | None]]] = {}
    for entry in candidates:
        by_serial.setdefault(entry[1], []).append(entry)

    result: list[tuple[str, str | None]] = []
    for serial_number, group in by_serial.items():
        if serial_number is None:
            result.extend(group)
            continue
        cu_ports = [e for e in group if "/dev/cu." in e[0]]
        result.append(cu_ports[0] if cu_ports else group[0])
    return result
