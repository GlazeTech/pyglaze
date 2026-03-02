from __future__ import annotations

import sys

import serial.tools.list_ports

_FTDI_VENDOR_ID = 0x0403
_SKIP_SUBSTRINGS = ("Bluetooth", "debug")
_FTDI_TEXTUAL_MARKERS = ("ftdi", "ft232")


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
    candidates: list[tuple[str, str | None]] = []
    for port_info in serial.tools.list_ports.comports():
        if _should_skip(port_info):
            continue
        if _is_ftdi(port_info):
            candidates.append((port_info.device, port_info.serial_number))

    if sys.platform == "darwin":
        candidates = _deduplicate_macos(candidates)

    return [device for device, _ in candidates]


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


def _should_skip(port_info: object) -> bool:
    device = getattr(port_info, "device", "") or ""
    return any(s in device for s in _SKIP_SUBSTRINGS)


def _is_ftdi(port_info: object) -> bool:
    vid = getattr(port_info, "vid", None)
    if vid == _FTDI_VENDOR_ID:
        return True
    meta = _port_metadata(port_info).lower()
    return any(marker in meta for marker in _FTDI_TEXTUAL_MARKERS)


def _port_metadata(port_info: object) -> str:
    parts = [
        getattr(port_info, attr, None)
        for attr in ("description", "manufacturer", "product", "hwid")
    ]
    return " ".join(str(p) for p in parts if p)


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
