from __future__ import annotations

import contextlib
import math
import time
import zlib
from collections import deque
from typing import TYPE_CHECKING, Protocol, TypeVar, cast, runtime_checkable

import numpy as np
import serial

from pyglaze.device.configuration import AMP_BAUDRATE
from pyglaze.device.discovery import discover_one
from pyglaze.mimlink import msg_types as mt
from pyglaze.mimlink.codec import EnvelopeCodec
from pyglaze.mimlink.framing import FrameDecodeError
from pyglaze.mimlink.proto.envelope_pb2 import TRANSFER_MODE_PER_POINT
from pyglaze.mimlink.rx_stream import RxFrameStream

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from pyglaze.device.configuration import DeviceConfiguration
    from pyglaze.helpers._types import FloatArray
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

    def write(self, data: bytes) -> None:
        """Write bytes to the connection."""
        ...

    def close(self) -> None:
        """Close the connection."""
        ...

    def reset_input_buffer(self) -> None:
        """Discard buffered input bytes."""
        ...


# Transfer timeout estimation constants.
_SERIAL_BITS_PER_BYTE = 10  # 8 data + start + stop
_BYTES_PER_RESULT_POINT = 16  # 3 x float32 + framing overhead
_TRANSFER_SAFETY_FACTOR = 2.5
_TRANSFER_BASELINE_S = 0.5  # fixed latency headroom

# Protocol timeout constants.
_PROTOCOL_SWEEP_SAFETY_FACTOR = 2
_PROTOCOL_BASELINE_S = 1.0  # fixed latency headroom
_IDLE_READ_BACKOFF_S = 0.001
_MIN_STATUS_POLL_S = 0.005

# Protocol constants.
_RESULTS_CHUNK_SIZE = 20
_MAX_RETRANSMIT_ATTEMPTS = 3
_MAX_COMMAND_RETRIES = 2
_LIST_CHUNK_SIZE = 50
_FW_CHUNK_SIZE = 256
_FW_START_TIMEOUT_S = 10.0  # flash erase is slow
_FW_CHUNK_TIMEOUT_S = 2.0
_FW_FINISH_TIMEOUT_S = 10.0


_T = TypeVar("_T")


class DeviceComError(Exception):
    """Raised when an error occurs in the communication with the device."""


class FirmwareUpdateError(DeviceComError):
    """Raised when a firmware update fails."""


def _dedup_sorted(items: list[_T], key: Callable[[_T], int]) -> list[_T]:
    """Deduplicate by key, keeping first occurrence, and return sorted."""
    seen: dict[int, _T] = {}
    for item in reversed(items):
        seen[key(item)] = item
    return sorted(seen.values(), key=key)


def _transfer_timeout_s(n_points: int) -> float:
    """Estimated serial transfer time for *n_points* of scan results."""
    transfer_s = (
        n_points * _BYTES_PER_RESULT_POINT * _SERIAL_BITS_PER_BYTE / AMP_BAUDRATE
    )
    return transfer_s * _TRANSFER_SAFETY_FACTOR + _TRANSFER_BASELINE_S


def _connection_factory(
    config: DeviceConfiguration,
) -> Connection:
    """Create a connection from config. Dispatches on ``amp_port`` sentinel strings."""
    if "mock_device" in config.amp_port:
        from pyglaze.devtools.mock_device import _mock_device_factory  # noqa: PLC0415

        return _mock_device_factory(config)

    port = config.amp_port
    if port == "auto":
        port = discover_one()

    return cast(
        "Connection",
        serial.serial_for_url(
            url=port,
            baudrate=config.amp_baudrate,
            timeout=config.amp_timeout_seconds,
        ),
    )


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
        conn = cast(
            "Connection",
            serial.serial_for_url(
                url=port,
                baudrate=baudrate,
                timeout=timeout_s,
            ),
        )
        conn.reset_input_buffer()
        return cls(conn=conn, command_timeout_s=command_timeout_s or timeout_s)

    def __init__(
        self,
        conn: Connection,
        *,
        command_timeout_s: float | None = None,
    ) -> None:
        self._conn = conn
        self.default_timeout_s = (
            command_timeout_s if command_timeout_s is not None else _PROTOCOL_BASELINE_S
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
        for _ in range(_MAX_COMMAND_RETRIES + 1):
            try:
                resp = self.send_receive(envelope, timeout=timeout)
            except DeviceComError as e:
                last_err = e
                continue
            if resp.type != expected:
                msg = f"Unexpected response: expected {expected}, got {resp.type}"
                raise DeviceComError(msg)
            return resp
        raise last_err  # type: ignore[misc]

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


class ScanClient:
    """MimLink scan client. Wraps a transport with scan-specific parameters and logic."""

    @classmethod
    def from_config(cls, config: DeviceConfiguration) -> ScanClient:
        """Construct a scan client from a device configuration."""
        conn = _connection_factory(config)
        conn.reset_input_buffer()
        transport = MimLinkTransport(conn=conn)
        return cls(
            transport=transport,
            n_points=config.n_points,
            sweep_length_ms=config._sweep_length_ms,  # noqa: SLF001
        )

    def __init__(
        self,
        transport: MimLinkTransport,
        *,
        n_points: int | None = None,
        sweep_length_ms: float | None = None,
    ) -> None:
        self._transport = transport
        self._default_n_points = n_points
        self._default_sweep_length_ms = sweep_length_ms
        if sweep_length_ms is not None:
            self._transport.default_timeout_s = self._scan_timeout_s(sweep_length_ms)

    def set_settings(
        self, n_points: int, integration_periods: int, *, use_ema: bool
    ) -> None:
        """Send settings to device."""
        env = self._transport.build_envelope(mt.SET_SETTINGS_REQUEST)
        req = env.set_settings_request
        req.list_length = n_points
        req.integration_periods = integration_periods
        req.use_ema = use_ema
        resp = self._transport.send_expect(env, mt.SET_SETTINGS_RESPONSE)
        if not resp.set_settings_response.success:
            msg = f"Failed to set settings: {resp}"
            raise DeviceComError(msg)

    def upload_list(self, scanning_list: list[float]) -> None:
        """Upload the scan list to the device. Retries the full sequence on failure."""
        last_err: DeviceComError | None = None
        for _ in range(_MAX_COMMAND_RETRIES + 1):
            try:
                self._upload_list_sequence(scanning_list)
            except DeviceComError as e:  # noqa: PERF203
                last_err = e
            else:
                return
        raise last_err  # type: ignore[misc]

    def _upload_list_sequence(self, scanning_list: list[float]) -> None:
        """Execute the list upload sequence once."""
        total = len(scanning_list)

        env = self._transport.build_envelope(mt.SET_LIST_START_REQUEST)
        env.set_list_start_request.total_floats = total
        resp = self._transport.send_expect(env, mt.SET_LIST_START_RESPONSE)
        if not resp.set_list_start_response.ready:
            msg = f"Failed to start list upload: {resp}"
            raise DeviceComError(msg)

        total_chunks = math.ceil(total / _LIST_CHUNK_SIZE)
        for i in range(total_chunks):
            start = i * _LIST_CHUNK_SIZE
            end = min(start + _LIST_CHUNK_SIZE, total)
            chunk_env = self._transport.build_envelope(mt.LIST_CHUNK)
            chunk = chunk_env.list_chunk
            chunk.chunk_index = i
            chunk.values.extend(scanning_list[start:end])
            chunk.is_last = i == total_chunks - 1
            self._transport.send(chunk_env)

        resp = self._transport.receive()
        if (
            resp.type != mt.SET_LIST_COMPLETE_RESPONSE
            or not resp.set_list_complete_response.success
        ):
            msg = f"Failed to upload list: {resp}"
            raise DeviceComError(msg)

    def start_scan(
        self, *, n_points: int | None = None, sweep_length_ms: float | None = None
    ) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Start scan and collect results. Returns (times, Xs, Ys)."""
        n_points, sweep_length_ms = self._resolve_scan_context(
            n_points=n_points,
            sweep_length_ms=sweep_length_ms,
        )
        timeout = self._scan_timeout_s(sweep_length_ms)
        env = self._transport.build_envelope(mt.START_SCAN_REQUEST)
        env.start_scan_request.SetInParent()
        resp = self._transport.send_expect(env, mt.START_SCAN_RESPONSE, timeout=timeout)
        if not resp.start_scan_response.started:
            msg = f"Failed to start scan: {resp}"
            raise DeviceComError(msg)

        if resp.start_scan_response.transfer_mode == TRANSFER_MODE_PER_POINT:
            return self._collect_per_point(
                n_points=n_points,
                sweep_length_ms=sweep_length_ms,
                timeout=timeout,
            )
        return self._collect_bulk(
            n_points=n_points,
            sweep_length_ms=sweep_length_ms,
            timeout=timeout,
        )

    def _collect_bulk(
        self,
        *,
        n_points: int | None = None,
        sweep_length_ms: float | None = None,
        timeout: float | None = None,
    ) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Wait for scan to finish, then request and collect chunked results.

        Tolerates a timeout if at least one chunk was received, then retransmits missing chunks.
        """
        n_points, sweep_length_ms = self._resolve_scan_context(
            n_points=n_points,
            sweep_length_ms=sweep_length_ms,
        )
        if timeout is None:
            timeout = self._scan_timeout_s(sweep_length_ms)
        self._await_scan_complete(sweep_length_ms=sweep_length_ms, timeout=timeout)

        env = self._transport.build_envelope(mt.GET_RESULTS_REQUEST)
        env.get_results_request.SetInParent()
        self._transport.send(env)

        chunks: list[pb.ResultsChunk | pb.ResultsChunkRetransmit] = []
        try:
            for e in self._transport.envelope_stream(
                timeout=_transfer_timeout_s(n_points)
            ):
                if e.type == mt.RESULTS_CHUNK:
                    chunks.append(e.results_chunk)
                    if e.results_chunk.is_last:
                        break
                elif (
                    e.type == mt.RESULTS_CHUNK_RETRANSMIT
                    and e.results_chunk_retransmit.available
                ):
                    chunks.append(e.results_chunk_retransmit)
        except DeviceComError:
            if not chunks:
                raise

        self._retransmit_missing_chunks(chunks, n_points=n_points, timeout=timeout)

        chunks = _dedup_sorted(chunks, key=lambda c: c.chunk_index)
        times = np.concatenate([np.array(list(c.times)) for c in chunks])
        Xs = np.concatenate([np.array(list(c.x)) for c in chunks])
        Ys = np.concatenate([np.array(list(c.y)) for c in chunks])
        return times, Xs, Ys

    def _collect_per_point(
        self,
        *,
        n_points: int | None = None,
        sweep_length_ms: float | None = None,
        timeout: float | None = None,
    ) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Collect results streamed per-point during the scan.

        Detects gaps inline and NAKs missing points before they age out of the
        device's circular buffer. Retransmit responses arrive interleaved in the
        same stream. A final retransmit pass catches any stragglers.
        """
        n_points, sweep_length_ms = self._resolve_scan_context(
            n_points=n_points,
            sweep_length_ms=sweep_length_ms,
        )
        if timeout is None:
            timeout = self._scan_timeout_s(sweep_length_ms)

        points: list[pb.ResultPoint | pb.ResultPointRetransmit] = []
        received: set[int] = set()
        next_expected = 0
        stream_timeout = sweep_length_ms * 1e-3 + _transfer_timeout_s(n_points)
        try:
            for e in self._transport.envelope_stream(timeout=stream_timeout):
                if e.type == mt.RESULT_POINT:
                    p = e.result_point
                    points.append(p)
                    received.add(p.point_index)
                    while next_expected < p.point_index:
                        if next_expected not in received:
                            self._nak_point(next_expected)
                        next_expected += 1
                    next_expected = max(next_expected, p.point_index + 1)
                    if p.is_last:
                        break
                elif (
                    e.type == mt.RESULT_POINT_RETRANSMIT
                    and e.result_point_retransmit.available
                ):
                    points.append(e.result_point_retransmit)
                    received.add(e.result_point_retransmit.point_index)
        except DeviceComError:
            if not points:
                raise

        self._retransmit_missing_points(points, n_points=n_points, timeout=timeout)

        points = _dedup_sorted(points, key=lambda p: p.point_index)
        times = np.array([p.time for p in points])
        Xs = np.array([p.x for p in points])
        Ys = np.array([p.y for p in points])
        return times, Xs, Ys

    def _nak_point(self, point_index: int) -> None:
        """Fire-and-forget NAK for a missing point. Response arrives in the envelope stream."""
        env = self._transport.build_envelope(mt.RESULT_POINT_NAK)
        env.result_point_nak.point_index = point_index
        self._transport.send(env)

    def _retransmit_missing_chunks(
        self,
        chunks: list[pb.ResultsChunk | pb.ResultsChunkRetransmit],
        *,
        n_points: int,
        timeout: float,
    ) -> None:
        """NAK-retry any chunks missing from the received set. Appends recovered chunks in place."""
        expected_count = math.ceil(n_points / _RESULTS_CHUNK_SIZE)
        received = {c.chunk_index for c in chunks}
        missing = set(range(expected_count)) - received
        if not missing:
            return

        for idx in sorted(missing):
            for _attempt in range(_MAX_RETRANSMIT_ATTEMPTS):
                env = self._transport.build_envelope(mt.RESULTS_CHUNK_NAK)
                env.results_chunk_nak.chunk_index = idx
                resp = self._transport.send_receive(env, timeout=timeout)
                if (
                    resp.type == mt.RESULTS_CHUNK_RETRANSMIT
                    and resp.results_chunk_retransmit.available
                ):
                    chunks.append(resp.results_chunk_retransmit)
                    break
            else:
                msg = (
                    f"Chunk {idx} unavailable after {_MAX_RETRANSMIT_ATTEMPTS} attempts"
                )
                raise DeviceComError(msg)

    def _retransmit_missing_points(
        self,
        points: list[pb.ResultPoint | pb.ResultPointRetransmit],
        *,
        n_points: int,
        timeout: float,
    ) -> None:
        """NAK-retry any points missing from the received set. Appends recovered points in place."""
        expected = set(range(n_points))
        received = {p.point_index for p in points}
        missing = expected - received
        if not missing:
            return

        for idx in sorted(missing):
            for _attempt in range(_MAX_RETRANSMIT_ATTEMPTS):
                env = self._transport.build_envelope(mt.RESULT_POINT_NAK)
                env.result_point_nak.point_index = idx
                resp = self._transport.send_receive(env, timeout=timeout)
                if (
                    resp.type == mt.RESULT_POINT_RETRANSMIT
                    and resp.result_point_retransmit.available
                ):
                    points.append(resp.result_point_retransmit)
                    break
            else:
                msg = (
                    f"Point {idx} unavailable after {_MAX_RETRANSMIT_ATTEMPTS} attempts"
                )
                raise DeviceComError(msg)

    def _await_scan_complete(self, *, sweep_length_ms: float, timeout: float) -> None:
        """Poll device status until scan is no longer ongoing."""
        sweep_s = sweep_length_ms * 1e-3
        deadline = time.monotonic() + timeout
        initial_sleep = min(sweep_s, max(0.0, deadline - time.monotonic()))
        if initial_sleep > 0:
            time.sleep(initial_sleep)
        poll_sleep_s = max(sweep_s * 0.01, _MIN_STATUS_POLL_S)
        while time.monotonic() < deadline:
            status = self.get_status()
            if not status.scan_ongoing:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(poll_sleep_s, remaining))
        msg = "Timeout waiting for scan to complete"
        raise DeviceComError(msg)

    @staticmethod
    def _scan_timeout_s(sweep_length_ms: float) -> float:
        return (
            sweep_length_ms * 1e-3 * _PROTOCOL_SWEEP_SAFETY_FACTOR
            + _PROTOCOL_BASELINE_S
        )

    def _resolve_scan_context(
        self, *, n_points: int | None, sweep_length_ms: float | None
    ) -> tuple[int, float]:
        resolved_n_points = n_points if n_points is not None else self._default_n_points
        resolved_sweep_ms = (
            sweep_length_ms
            if sweep_length_ms is not None
            else self._default_sweep_length_ms
        )
        if resolved_n_points is None or resolved_sweep_ms is None:
            msg = (
                "Scan context is missing. Pass n_points and sweep_length_ms to "
                "start_scan(), or provide defaults in ScanClient(...)."
            )
            raise DeviceComError(msg)
        return resolved_n_points, resolved_sweep_ms

    def get_device_info(self) -> pb.GetDeviceInfoResponse:
        """Query device info. Delegates to transport."""
        return self._transport.get_device_info()

    def get_status(self) -> pb.GetStatusResponse:
        """Query device status. Delegates to transport."""
        return self._transport.get_status()

    def close(self) -> None:
        """Close the connection. Delegates to transport."""
        self._transport.close()


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
        from pyglaze.mimlink.proto import envelope_pb2 as pb  # noqa: PLC0415

        firmware_crc = zlib.crc32(firmware) & 0xFFFFFFFF

        # --- start ---
        env = self._transport.build_envelope(mt.FW_UPDATE_START_REQUEST)
        req = env.fw_update_start_request
        req.firmware_size = len(firmware)
        req.firmware_crc = firmware_crc
        req.chunk_size = chunk_size
        req.version = version
        resp = self._transport.send_expect(
            env, mt.FW_UPDATE_START_RESPONSE, timeout=_FW_START_TIMEOUT_S
        )
        if not resp.fw_update_start_response.accepted:
            error = resp.fw_update_start_response.error
            msg = f"Firmware update rejected: {error}"
            raise FirmwareUpdateError(msg)

        # --- chunks ---
        total_chunks = math.ceil(len(firmware) / chunk_size)
        for i in range(total_chunks):
            chunk_data = firmware[i * chunk_size : (i + 1) * chunk_size]
            chunk_crc = zlib.crc32(chunk_data) & 0xFFFFFFFF

            for _attempt in range(_MAX_RETRANSMIT_ATTEMPTS):
                chunk_env = self._transport.build_envelope(mt.FW_UPDATE_CHUNK)
                c = chunk_env.fw_update_chunk
                c.chunk_index = i
                c.data = chunk_data
                c.chunk_crc = chunk_crc
                ack = self._transport.send_expect(
                    chunk_env, mt.FW_UPDATE_CHUNK_ACK, timeout=_FW_CHUNK_TIMEOUT_S
                )
                status = ack.fw_update_chunk_ack.status
                if status == pb.FW_CHUNK_STATUS_OK:
                    break
                if status == pb.FW_CHUNK_STATUS_ABORT:
                    msg = f"Device aborted firmware update at chunk {i}"
                    raise FirmwareUpdateError(msg)
                # CRC_MISMATCH → retry
            else:
                msg = f"Chunk {i} CRC mismatch after {_MAX_RETRANSMIT_ATTEMPTS} retries"
                raise FirmwareUpdateError(msg)

        # --- finish ---
        fin_env = self._transport.build_envelope(mt.FW_UPDATE_FINISH_REQUEST)
        fin_env.fw_update_finish_request.SetInParent()
        fin_resp = self._transport.send_expect(
            fin_env, mt.FW_UPDATE_FINISH_RESPONSE, timeout=_FW_FINISH_TIMEOUT_S
        )
        if not fin_resp.fw_update_finish_response.success:
            error = fin_resp.fw_update_finish_response.error
            msg = f"Firmware update finish failed: {error}"
            raise FirmwareUpdateError(msg)

    def confirm_boot(self) -> str:
        """Confirm the current firmware after a successful update.

        Returns:
            The firmware version string reported by the device.
        """
        env = self._transport.build_envelope(mt.FW_BOOT_CONFIRM_REQUEST)
        env.fw_boot_confirm_request.SetInParent()
        resp = self._transport.send_expect(env, mt.FW_BOOT_CONFIRM_RESPONSE)
        return resp.fw_boot_confirm_response.version

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
