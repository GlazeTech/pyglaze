from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from pyglaze.mimlink.proto import envelope_pb2 as pb


class FirmwareUpdateState(IntEnum):
    """Pyglaze-facing firmware update state."""

    UNKNOWN = -1
    IDLE = pb.FW_UPDATE_STATUS_IDLE
    RECEIVING = pb.FW_UPDATE_STATUS_RECEIVING
    VERIFYING = pb.FW_UPDATE_STATUS_VERIFYING
    BOOT_PENDING = pb.FW_UPDATE_STATUS_BOOT_PENDING
    CONFIRMED = pb.FW_UPDATE_STATUS_CONFIRMED


@dataclass(frozen=True)
class FirmwareUpdateStatus:
    """Structured firmware update progress reported by the device."""

    status: FirmwareUpdateState
    chunks_received: int
    total_chunks: int
    bytes_received: int


def firmware_update_state_from_proto(value: int) -> FirmwareUpdateState:
    """Convert a MimLink firmware-update enum value into a pyglaze enum."""
    try:
        return FirmwareUpdateState(int(value))
    except ValueError:
        return FirmwareUpdateState.UNKNOWN


def firmware_update_status_from_proto(
    resp: pb.FwUpdateStatusResponse,
) -> FirmwareUpdateStatus:
    """Convert a MimLink firmware-update status response into a pyglaze model."""
    return FirmwareUpdateStatus(
        status=firmware_update_state_from_proto(resp.status),
        chunks_received=int(resp.chunks_received),
        total_chunks=int(resp.total_chunks),
        bytes_received=int(resp.bytes_received),
    )


__all__ = [
    "FirmwareUpdateState",
    "FirmwareUpdateStatus",
    "firmware_update_state_from_proto",
    "firmware_update_status_from_proto",
]
