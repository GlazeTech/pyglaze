from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceInfo:
    """Device identification and capabilities."""

    serial_number: str
    firmware_version: str
    bsp_name: str
    build_type: str
    transfer_mode: int
    hardware_type: str
    hardware_revision: int
