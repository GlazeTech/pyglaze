from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pyglaze.device.exceptions import DeviceComError
from pyglaze.mimlink.proto import envelope_pb2 as pb

if TYPE_CHECKING:
    from pyglaze.mimlink.proto.envelope_pb2 import TransferMode

OperationalState = Literal[
    "normal",
    "commissioning_idle",
    "commissioning_trim_active",
]

ConfigStatusReason = Literal[
    "none",
    "unconfigured",
    "invalid_config",
]

_OPERATIONAL_STATE_MAP: dict[int, OperationalState] = {
    pb.OPERATIONAL_STATE_NORMAL: "normal",
    pb.OPERATIONAL_STATE_COMMISSIONING_IDLE: "commissioning_idle",
    pb.OPERATIONAL_STATE_COMMISSIONING_TRIM_ACTIVE: "commissioning_trim_active",
}

_CONFIG_STATUS_REASON_MAP: dict[int, ConfigStatusReason] = {
    pb.CONFIG_STATUS_REASON_NONE: "none",
    pb.CONFIG_STATUS_REASON_UNCONFIGURED: "unconfigured",
    pb.CONFIG_STATUS_REASON_INVALID_CONFIG: "invalid_config",
}


@dataclass(frozen=True)
class DeviceState:
    """Structured device state exposed by pyglaze."""

    operational_state: OperationalState
    config_status_reason: ConfigStatusReason

    @property
    def is_commissioning_idle(self) -> bool:
        """Whether the device is in shared commissioning idle."""
        return self.operational_state == "commissioning_idle"

    @property
    def is_trim_active(self) -> bool:
        """Whether commissioning trim mode is active."""
        return self.operational_state == "commissioning_trim_active"

    @property
    def is_recovery_idle(self) -> bool:
        """Whether commissioning idle reflects a missing or invalid config."""
        return self.is_commissioning_idle and self.config_status_reason in {
            "unconfigured",
            "invalid_config",
        }

    @property
    def blocks_normal_scan(self) -> bool:
        """Whether normal scan workflows should be blocked."""
        return self.operational_state in {
            "commissioning_idle",
            "commissioning_trim_active",
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
    """Convert MimLink proto enum values into pyglaze types."""
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
