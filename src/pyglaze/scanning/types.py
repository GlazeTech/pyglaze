"""Typed return values for Scanner and GlazeClient APIs."""

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


@dataclass(frozen=True)
class DeviceStatus:
    """Device runtime status."""

    scan_ongoing: bool
    list_length: int
    max_list_length: int
    modulation_frequency_hz: int
    settings_valid: bool
    list_valid: bool


@dataclass(frozen=True)
class PingResult:
    """Result of a ping operation."""

    success: bool
    round_trip_us: float
    nonce: int
