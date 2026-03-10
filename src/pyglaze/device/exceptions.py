from __future__ import annotations


class DeviceComError(Exception):
    """Raised when an error occurs in the communication with the device."""


class FirmwareUpdateError(DeviceComError):
    """Raised when a firmware update fails."""
