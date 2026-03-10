from __future__ import annotations

import math

from pyglaze.device.configuration import AMP_BAUDRATE
from pyglaze.device.exceptions import FirmwareUpdateError
from pyglaze.device.transport import MimLinkTransport
from pyglaze.mimlink import msg_types as mt
from pyglaze.mimlink.crc import crc32
from pyglaze.mimlink.proto import envelope_pb2 as pb

_FW_CHUNK_SIZE = 256
_FW_START_TIMEOUT_S = 10.0  # flash erase is slow
_FW_CHUNK_TIMEOUT_S = 2.0
_FW_FINISH_TIMEOUT_S = 10.0
_MAX_RETRANSMIT_ATTEMPTS = 3


class FirmwareClient:
    """MimLink firmware client. Wraps a transport for firmware update operations."""

    @classmethod
    def from_port(
        cls,
        port: str,
        *,
        baudrate: int = AMP_BAUDRATE,
        timeout_s: float = 0.1,
        command_timeout_s: float | None = None,
    ) -> FirmwareClient:
        """Construct a firmware client from a serial port."""
        transport = MimLinkTransport.from_port(
            port=port,
            baudrate=baudrate,
            timeout_s=timeout_s,
            command_timeout_s=command_timeout_s,
        )
        return cls(transport=transport)

    def __init__(self, transport: MimLinkTransport) -> None:
        self._transport = transport

    def update_firmware(
        self,
        firmware: bytes,
        *,
        chunk_size: int = _FW_CHUNK_SIZE,
        version: str = "",
    ) -> None:
        """Upload firmware to the device.

        After a successful upload the device reboots automatically.
        Call :meth:`confirm_boot` on a fresh connection to make the
        update permanent.
        """
        self._start_update(firmware, chunk_size=chunk_size, version=version)
        self._send_chunks(firmware, chunk_size=chunk_size)
        self._finish_update()

    def _start_update(self, firmware: bytes, *, chunk_size: int, version: str) -> None:
        env = self._transport.build_envelope(mt.FW_UPDATE_START_REQUEST)
        req = env.fw_update_start_request
        req.firmware_size = len(firmware)
        req.firmware_crc = crc32(firmware)
        req.chunk_size = chunk_size
        req.version = version
        resp = self._transport.send_expect(
            env, mt.FW_UPDATE_START_RESPONSE, timeout=_FW_START_TIMEOUT_S
        ).fw_update_start_response
        if not resp.accepted:
            msg = f"Firmware update rejected: {resp.error}"
            raise FirmwareUpdateError(msg)

    def _send_chunks(self, firmware: bytes, *, chunk_size: int) -> None:
        total_chunks = math.ceil(len(firmware) / chunk_size)
        for i in range(total_chunks):
            chunk_data = firmware[i * chunk_size : (i + 1) * chunk_size]
            self._send_chunk(i, chunk_data)

    def _send_chunk(self, index: int, data: bytes) -> None:
        chunk_crc = crc32(data)
        for _attempt in range(_MAX_RETRANSMIT_ATTEMPTS):
            env = self._transport.build_envelope(mt.FW_UPDATE_CHUNK)
            chunk = env.fw_update_chunk
            chunk.chunk_index = index
            chunk.data = data
            chunk.chunk_crc = chunk_crc
            ack = self._transport.send_expect(
                env, mt.FW_UPDATE_CHUNK_ACK, timeout=_FW_CHUNK_TIMEOUT_S
            )
            status = ack.fw_update_chunk_ack.status
            if status == pb.FW_CHUNK_STATUS_OK:
                return
            if status == pb.FW_CHUNK_STATUS_ABORT:
                msg = f"Device aborted firmware update at chunk {index}"
                raise FirmwareUpdateError(msg)
            if status == pb.FW_CHUNK_STATUS_CRC_MISMATCH:
                continue
            msg = f"Unexpected chunk status {status} for chunk {index}"
            raise FirmwareUpdateError(msg)
        msg = f"Chunk {index} CRC mismatch after {_MAX_RETRANSMIT_ATTEMPTS} retries"
        raise FirmwareUpdateError(msg)

    def _finish_update(self) -> None:
        env = self._transport.build_envelope(mt.FW_UPDATE_FINISH_REQUEST)
        env.fw_update_finish_request.SetInParent()
        resp = self._transport.send_expect(
            env, mt.FW_UPDATE_FINISH_RESPONSE, timeout=_FW_FINISH_TIMEOUT_S
        ).fw_update_finish_response
        if not resp.success:
            msg = f"Firmware update finish failed: {resp.error}"
            raise FirmwareUpdateError(msg)

    def confirm_boot(self) -> str:
        """Confirm the current firmware after a successful update.

        Returns:
            The firmware version string reported by the device.
        """
        env = self._transport.build_envelope(mt.FW_BOOT_CONFIRM_REQUEST)
        env.fw_boot_confirm_request.SetInParent()
        resp = self._transport.send_expect(
            env, mt.FW_BOOT_CONFIRM_RESPONSE
        ).fw_boot_confirm_response
        return resp.version

    def get_firmware_update_status(self) -> pb.FwUpdateStatusResponse:
        """Query firmware update progress."""
        env = self._transport.build_envelope(mt.FW_UPDATE_STATUS_REQUEST)
        env.fw_update_status_request.SetInParent()
        return self._transport.send_expect(
            env, mt.FW_UPDATE_STATUS_RESPONSE
        ).fw_update_status_response

    def get_device_info(self) -> pb.GetDeviceInfoResponse:
        """Query device info. Delegates to transport."""
        return self._transport.get_device_info()

    def reboot(self) -> None:
        """Request a device reboot. Delegates to transport."""
        self._transport.reboot()

    def close(self) -> None:
        """Close the connection. Delegates to transport."""
        self._transport.close()
