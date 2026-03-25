from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyglaze.device.status import DeviceState


class DeviceComError(Exception):
    """Raised when an error occurs in the communication with the device."""


class DeviceStateError(DeviceComError):
    """Raised when a normal scan workflow is attempted in a blocked device state."""

    def __init__(self, state: DeviceState, action: str) -> None:
        self.state = state
        self.action = action
        super().__init__(state, action)

    def __str__(self) -> str:
        """Return a stable human-readable message for local and pickled instances."""
        return _format_device_state_error(self.state, action=self.action)


class FirmwareUpdateError(DeviceComError):
    """Raised when a firmware update fails."""


def _format_device_state_error(state: DeviceState, *, action: str) -> str:
    # Check from most-specific to least-specific because recovery idle is a
    # commissioning-idle subtype.
    if state.is_trim_active:
        detail = "device is in commissioning trim mode"
    elif state.is_recovery_idle:
        detail = "device is in commissioning/recovery idle"
    elif state.is_commissioning_idle:
        detail = "device is in commissioning idle"
    else:
        detail = "device is not in a normal operational state"

    return (
        f"Cannot {action}: {detail} "
        f"(operational_state={state.operational_state.value}, "
        f"config_status_reason={state.config_status_reason.value})"
    )
