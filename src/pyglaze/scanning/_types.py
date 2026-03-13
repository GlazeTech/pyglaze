from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyglaze.mimlink.proto.envelope_pb2 import TransferMode


@dataclass(frozen=True)
class DeviceInfo:
    """Device identification and capabilities."""

    serial_number: str
    firmware_version: str
    firmware_target: str
    bsp_name: str
    build_type: str
    transfer_mode: TransferMode
    hardware_type: str
    hardware_revision: int
