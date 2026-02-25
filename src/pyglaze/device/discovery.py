from __future__ import annotations

import sys

import serial.tools.list_ports

FTDI_VENDOR_ID = 0x0403
GLAZE_MANUFACTURER = "GLAZE"


class DeviceNotFoundError(Exception):
    """No Glaze device found on any serial port."""


class MultipleDevicesError(Exception):
    """Multiple Glaze devices found when exactly one was expected."""


def discover() -> list[str]:
    """Find all connected Glaze devices.

    Enumerates serial ports and filters for FTDI devices.
    On macOS, deduplicates cu.*/tty.* pairs (keeps cu.*).

    Returns:
        List of serial port paths.
    """
    candidates: list[tuple[str, str | None]] = []
    for port_info in serial.tools.list_ports.comports():
        if port_info.vid != FTDI_VENDOR_ID:
            continue
        candidates.append((port_info.device, port_info.serial_number))

    if sys.platform == "darwin":
        candidates = _deduplicate_cu_tty(candidates)

    return [port for port, _ in candidates]


def discover_one() -> str:
    """Find exactly one connected Glaze device.

    Returns:
        Serial port path for the single discovered device.

    Raises:
        DeviceNotFoundError: If no devices are found.
        MultipleDevicesError: If more than one device is found.
    """
    devices = discover()
    if len(devices) == 0:
        msg = "No Glaze devices found. Check USB connection and FTDI drivers."
        raise DeviceNotFoundError(msg)
    if len(devices) > 1:
        msg = f"Multiple Glaze devices found: {devices}. Use discover() to select one."
        raise MultipleDevicesError(msg)
    return devices[0]


def _deduplicate_cu_tty(
    candidates: list[tuple[str, str | None]],
) -> list[tuple[str, str | None]]:
    """Deduplicate macOS cu.*/tty.* pairs. Keeps cu.* (non-blocking open)."""
    by_serial: dict[str | None, list[tuple[str, str | None]]] = {}
    for entry in candidates:
        by_serial.setdefault(entry[1], []).append(entry)

    result: list[tuple[str, str | None]] = []
    for serial_number, group in by_serial.items():
        if serial_number is None:
            result.extend(group)
            continue
        cu = [e for e in group if "/dev/cu." in e[0]]
        result.append(cu[0] if cu else group[0])
    return result
