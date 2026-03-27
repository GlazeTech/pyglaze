from __future__ import annotations

import contextlib
import time
from collections import deque
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import serial

from pyglaze.device.configuration import AMP_BAUDRATE
from pyglaze.device.exceptions import DeviceComError
from pyglaze.mimlink import msg_types as mt
from pyglaze.mimlink.codec import EnvelopeCodec
from pyglaze.mimlink.framing import FrameDecodeError
from pyglaze.mimlink.rx_stream import RxFrameStream

if TYPE_CHECKING:
    from collections.abc import Generator

    from pyglaze.mimlink.proto import envelope_pb2 as pb
    from pyglaze.mimlink.proto.envelope_pb2 import MsgType


@runtime_checkable
class Connection(Protocol):
    """Serial-like connection interface used by MimLinkTransport."""

    @property
    def in_waiting(self) -> int:
        """Bytes available for reading."""
        ...

    def read(self, size: int) -> bytes:
        """Read up to *size* bytes."""
        ...

    def write(self, data: bytes) -> int:
        """Write bytes to the connection."""
        ...

    def close(self) -> None:
        """Close the connection."""
        ...

    def reset_input_buffer(self) -> None:
        """Discard buffered input bytes."""
        ...


PROTOCOL_BASELINE_S = 1.0  # fixed latency headroom
_IDLE_READ_BACKOFF_S = 0.001
MAX_COMMAND_RETRIES = 2


class MimLinkTransport:
    """Low-level MimLink protocol transport.

    Owns the serial connection, codec, and envelope send/receive machinery.
    Domain clients (ScanClient, FirmwareClient) compose over this.
    """

    @classmethod
    def from_port(
        cls,
        port: str,
        *,
        baudrate: int = AMP_BAUDRATE,
        timeout_s: float = 0.1,
        command_timeout_s: float | None = None,
    ) -> MimLinkTransport:
        """Construct a transport from a serial port."""
        from typing import cast  # noqa: PLC0415

        conn = cast(
            "Connection",
            serial.serial_for_url(
                url=port,
                baudrate=baudrate,
                timeout=timeout_s,
            ),
        )
        conn.reset_input_buffer()
        resolved_command_timeout_s = (
            timeout_s if command_timeout_s is None else command_timeout_s
        )
        return cls(
            conn=conn,
            command_timeout_s=resolved_command_timeout_s,
        )

    def __init__(
        self,
        conn: Connection,
        *,
        command_timeout_s: float | None = None,
    ) -> None:
        self._conn = conn
        self.default_timeout_s = (
            command_timeout_s if command_timeout_s is not None else PROTOCOL_BASELINE_S
        )
        self._codec = EnvelopeCodec()
        self._rx_stream = RxFrameStream()
        self._env_buffer: deque[pb.Envelope] = deque()

    def __del__(self) -> None:
        """Clean up the connection."""
        self.close()

    def build_envelope(self, msg_type: MsgType) -> pb.Envelope:
        """Build a new Envelope with the given message type."""
        return self._codec.build_envelope(msg_type)

    def send(self, envelope: pb.Envelope) -> None:
        """Encode and write an envelope to the connection."""
        self._conn.write(self._codec.encode(envelope))

    def _feed_rx_bytes(self, data: bytes) -> None:
        """Decode complete envelopes from raw connection bytes."""
        for frame in self._rx_stream.push(data):
            try:
                self._env_buffer.append(self._codec.decode(frame))
            except FrameDecodeError:  # noqa: PERF203
                continue

    def _try_fill_env_buffer(self) -> bool:
        """Read and decode one chunk of connection data into the envelope buffer."""
        data = self._read_some()
        if not data:
            return False
        self._feed_rx_bytes(data)
        return bool(self._env_buffer)

    def _sleep_until_retry(self, deadline: float) -> None:
        """Sleep for a short backoff interval without overshooting the deadline."""
        remaining = max(0.0, deadline - time.monotonic())
        time.sleep(min(_IDLE_READ_BACKOFF_S, remaining))

    def _read_some(self) -> bytes:
        """Read one blocking chunk, then drain any immediately buffered bytes."""
        data = self._conn.read(1)
        if not data:
            return b""

        available = self._conn.in_waiting
        if available > 0:
            data += self._conn.read(available)
        return data

    def envelope_stream(
        self, timeout: float | None = None
    ) -> Generator[pb.Envelope, None, None]:
        """Yield envelopes until timeout. Raises DeviceComError when deadline expires."""
        if timeout is None:
            timeout = self.default_timeout_s
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._env_buffer:
                yield self._env_buffer.popleft()
            else:
                if self._try_fill_env_buffer():
                    continue
                self._sleep_until_retry(deadline)
        msg = "Timeout waiting for device response"
        raise DeviceComError(msg)

    def receive(self, timeout: float | None = None) -> pb.Envelope:
        """Block until one Envelope is received. Raises DeviceComError on timeout."""
        return next(self.envelope_stream(timeout))

    def send_receive(
        self, envelope: pb.Envelope, timeout: float | None = None
    ) -> pb.Envelope:
        """Send an envelope and return the next received envelope."""
        self.send(envelope)
        return self.receive(timeout)

    def send_expect(
        self, envelope: pb.Envelope, expected: MsgType, *, timeout: float | None = None
    ) -> pb.Envelope:
        """Send an envelope and verify the response type.

        Retries on timeout. Raises DeviceComError on type mismatch or explicit rejection.
        """
        last_err: DeviceComError | None = None
        for _ in range(MAX_COMMAND_RETRIES + 1):
            try:
                resp = self.send_receive(envelope, timeout=timeout)
            except DeviceComError as e:
                last_err = e
                continue
            if resp.type != expected:
                msg = f"Unexpected response: expected {expected}, got {resp.type}"
                raise DeviceComError(msg)
            return resp
        if last_err is not None:
            raise last_err

        msg = "Failed to receive device response"
        raise DeviceComError(msg)

    def get_device_info(self) -> pb.GetDeviceInfoResponse:
        """Query device info. Returns the protobuf GetDeviceInfoResponse sub-message."""
        env = self.build_envelope(mt.GET_DEVICE_INFO_REQUEST)
        env.get_device_info_request.SetInParent()
        return self.send_expect(
            env, mt.GET_DEVICE_INFO_RESPONSE
        ).get_device_info_response

    def get_status(self) -> pb.GetStatusResponse:
        """Query device status. Returns the protobuf GetStatusResponse sub-message."""
        env = self.build_envelope(mt.GET_STATUS_REQUEST)
        env.get_status_request.SetInParent()
        return self.send_expect(env, mt.GET_STATUS_RESPONSE).get_status_response

    def reboot(self) -> None:
        """Request a device reboot. Fire-and-forget — no response expected."""
        env = self.build_envelope(mt.REBOOT_REQUEST)
        env.reboot_request.SetInParent()
        self.send(env)

    def close(self) -> None:
        """Close the connection."""
        with contextlib.suppress(AttributeError):
            self._rx_stream.reset()
        with contextlib.suppress(AttributeError):
            self._conn.close()
