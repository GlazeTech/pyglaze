from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from pyglaze.device.exceptions import DeviceComError
from pyglaze.mimlink.proto import envelope_pb2 as pb

if TYPE_CHECKING:
    from pyglaze.mimlink.proto.envelope_pb2 import TransferMode


class OperationalState(str, Enum):
    """Pyglaze-facing operational-state enum."""

    NORMAL = "normal"
    COMMISSIONING_IDLE = "commissioning_idle"
    COMMISSIONING_TRIM_ACTIVE = "commissioning_trim_active"


class ConfigStatusReason(str, Enum):
    """Pyglaze-facing config-status enum."""

    NONE = "none"
    UNCONFIGURED = "unconfigured"
    INVALID_CONFIG = "invalid_config"


_OPERATIONAL_STATE_MAP: dict[int, OperationalState] = {
    pb.OPERATIONAL_STATE_NORMAL: OperationalState.NORMAL,
    pb.OPERATIONAL_STATE_COMMISSIONING_IDLE: OperationalState.COMMISSIONING_IDLE,
    pb.OPERATIONAL_STATE_COMMISSIONING_TRIM_ACTIVE: (
        OperationalState.COMMISSIONING_TRIM_ACTIVE
    ),
}

_CONFIG_STATUS_REASON_MAP: dict[int, ConfigStatusReason] = {
    pb.CONFIG_STATUS_REASON_NONE: ConfigStatusReason.NONE,
    pb.CONFIG_STATUS_REASON_UNCONFIGURED: ConfigStatusReason.UNCONFIGURED,
    pb.CONFIG_STATUS_REASON_INVALID_CONFIG: ConfigStatusReason.INVALID_CONFIG,
}

_STATE_REPORTING_REQUIRED_MSG = (
    "Device firmware does not report operational/config status; "
    "pyglaze requires firmware with config-status support."
)


@dataclass(frozen=True)
class DeviceState:
    """Structured device state exposed by pyglaze."""

    operational_state: OperationalState
    config_status_reason: ConfigStatusReason

    @property
    def is_commissioning_idle(self) -> bool:
        """Whether the device is in shared commissioning idle."""
        return self.operational_state is OperationalState.COMMISSIONING_IDLE

    @property
    def is_trim_active(self) -> bool:
        """Whether commissioning trim mode is active."""
        return self.operational_state is OperationalState.COMMISSIONING_TRIM_ACTIVE

    @property
    def is_recovery_idle(self) -> bool:
        """Whether commissioning idle reflects a missing or invalid config."""
        return self.is_commissioning_idle and self.config_status_reason in {
            ConfigStatusReason.UNCONFIGURED,
            ConfigStatusReason.INVALID_CONFIG,
        }

    @property
    def blocks_normal_scan(self) -> bool:
        """Whether normal scan workflows should be blocked."""
        return self.operational_state in {
            OperationalState.COMMISSIONING_IDLE,
            OperationalState.COMMISSIONING_TRIM_ACTIVE,
        }


@dataclass(frozen=True)
class DeviceInfo:
    """Device identification, capabilities, and operational state."""

    serial_number: str
    firmware_version: str
    firmware_target: str
    bsp_name: str
    build_type: str
    transfer_mode: TransferMode
    hardware_type: str
    hardware_revision: int
    state: DeviceState

    @property
    def operational_state(self) -> OperationalState:
        """Operational state reported by the device."""
        return self.state.operational_state

    @property
    def config_status_reason(self) -> ConfigStatusReason:
        """Config-status reason reported by the device."""
        return self.state.config_status_reason


@dataclass(frozen=True)
class DeviceStatus:
    """Current runtime status and operational state."""

    scan_ongoing: bool
    list_length: int
    max_list_length: int
    modulation_frequency_hz: int
    settings_valid: bool
    list_valid: bool
    state: DeviceState

    @property
    def operational_state(self) -> OperationalState:
        """Operational state reported by the device."""
        return self.state.operational_state

    @property
    def config_status_reason(self) -> ConfigStatusReason:
        """Config-status reason reported by the device."""
        return self.state.config_status_reason


def device_state_from_proto(
    operational_state: int, config_status_reason: int
) -> DeviceState:
    """Convert MimLink proto enum values into pyglaze enums."""
    if (
        int(operational_state) == pb.OPERATIONAL_STATE_UNSPECIFIED
        or int(config_status_reason) == pb.CONFIG_STATUS_REASON_UNSPECIFIED
    ):
        raise DeviceComError(_STATE_REPORTING_REQUIRED_MSG)

    try:
        pyglaze_operational_state = _OPERATIONAL_STATE_MAP[int(operational_state)]
    except KeyError as exc:
        msg = f"Unsupported operational_state value {int(operational_state)}"
        raise DeviceComError(msg) from exc

    try:
        pyglaze_config_status_reason = _CONFIG_STATUS_REASON_MAP[
            int(config_status_reason)
        ]
    except KeyError as exc:
        msg = f"Unsupported config_status_reason value {int(config_status_reason)}"
        raise DeviceComError(msg) from exc

    return DeviceState(
        operational_state=pyglaze_operational_state,
        config_status_reason=pyglaze_config_status_reason,
    )


def device_info_from_proto(resp: pb.GetDeviceInfoResponse) -> DeviceInfo:
    """Convert a MimLink device-info response into a pyglaze model."""
    return DeviceInfo(
        serial_number=str(resp.serial_number),
        firmware_version=str(resp.firmware_version),
        firmware_target=str(resp.firmware_target),
        bsp_name=str(resp.bsp_name),
        build_type=str(resp.build_type),
        transfer_mode=resp.transfer_mode,
        hardware_type=str(resp.hardware_type),
        hardware_revision=int(resp.hardware_revision),
        state=device_state_from_proto(
            resp.operational_state,
            resp.config_status_reason,
        ),
    )


def device_status_from_proto(resp: pb.GetStatusResponse) -> DeviceStatus:
    """Convert a MimLink status response into a pyglaze model."""
    return DeviceStatus(
        scan_ongoing=bool(resp.scan_ongoing),
        list_length=int(resp.list_length),
        max_list_length=int(resp.max_list_length),
        modulation_frequency_hz=int(resp.modulation_frequency_hz),
        settings_valid=bool(resp.settings_valid),
        list_valid=bool(resp.list_valid),
        state=device_state_from_proto(
            resp.operational_state,
            resp.config_status_reason,
        ),
    )


__all__ = [
    "ConfigStatusReason",
    "DeviceInfo",
    "DeviceState",
    "DeviceStatus",
    "OperationalState",
    "device_info_from_proto",
    "device_state_from_proto",
    "device_status_from_proto",
]
