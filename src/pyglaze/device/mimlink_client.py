from __future__ import annotations

import contextlib
import math
import time
from collections import deque
from typing import TYPE_CHECKING

import numpy as np
import serial

from pyglaze.device.configuration import AMP_BAUDRATE
from pyglaze.mimlink import msg_types as mt
from pyglaze.mimlink.codec import EnvelopeCodec
from pyglaze.mimlink.framing import FrameDecodeError
from pyglaze.mimlink.rx_stream import RxFrameStream

if TYPE_CHECKING:
    from collections.abc import Generator

    from pyglaze.device.configuration import LeDeviceConfiguration
    from pyglaze.devtools.mock_device import MimLinkMockDevice
    from pyglaze.helpers._types import FloatArray
    from pyglaze.mimlink.proto import envelope_pb2 as pb

# Transfer timeout estimation constants.
_SERIAL_BITS_PER_BYTE = 10  # 8 data + start + stop
_BYTES_PER_RESULT_POINT = 16  # 3 x float32 + framing overhead
_TRANSFER_SAFETY_FACTOR = 2.5
_TRANSFER_BASELINE_S = 0.5  # fixed latency headroom

# Protocol constants.
_TRANSFER_MODE_PER_POINT = 1
_RESULTS_CHUNK_SIZE = 20
_MAX_RETRANSMIT_ATTEMPTS = 3
_LIST_CHUNK_SIZE = 50


class DeviceComError(Exception):
    """Raised when an error occurs in the communication with the device."""


def _transfer_timeout_s(n_points: int) -> float:
    """Estimated serial transfer time for *n_points* of scan results."""
    transfer_s = (
        n_points * _BYTES_PER_RESULT_POINT * _SERIAL_BITS_PER_BYTE / AMP_BAUDRATE
    )
    return transfer_s * _TRANSFER_SAFETY_FACTOR + _TRANSFER_BASELINE_S


def _connection_factory(
    config: LeDeviceConfiguration,
) -> serial.Serial | MimLinkMockDevice:
    """Create a connection from config. Dispatches on ``amp_port`` sentinel strings."""
    if "mock_device" in config.amp_port:
        from pyglaze.devtools.mock_device import _mock_device_factory  # noqa: PLC0415

        return _mock_device_factory(config)
    return serial.serial_for_url(
        url=config.amp_port,
        baudrate=config.amp_baudrate,
        timeout=config.amp_timeout_seconds,
    )


class MimLinkClient:
    """Synchronous MimLink protocol client."""

    def __init__(
        self,
        conn: serial.Serial | MimLinkMockDevice,
        timeout: float = 5.0,
    ) -> None:
        self._conn = conn
        self._timeout = timeout
        self._codec = EnvelopeCodec()
        self._rx_stream = RxFrameStream()
        self._env_buffer: deque[pb.Envelope] = deque()

    def __del__(self) -> None:
        """Clean up the connection."""
        self.close()

    def _send(self, envelope: pb.Envelope) -> None:
        self._conn.write(self._codec.encode(envelope))

    def _drain(self) -> None:
        """Read available bytes and decode complete frames into the envelope buffer."""
        available = self._conn.in_waiting
        if available > 0:
            data = self._conn.read(available)
        else:
            data = self._conn.read(1)
            if not data:
                return
        for frame in self._rx_stream.push(data):
            try:
                self._env_buffer.append(self._codec.decode(frame))
            except FrameDecodeError:  # noqa: PERF203
                continue

    def _envelope_stream(
        self, timeout: float | None = None
    ) -> Generator[pb.Envelope, None, None]:
        """Yield envelopes until timeout. Raises DeviceComError when deadline expires."""
        if timeout is None:
            timeout = self._timeout
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._env_buffer:
                yield self._env_buffer.popleft()
            else:
                self._drain()
        msg = "Timeout waiting for device response"
        raise DeviceComError(msg)

    def _receive(self, timeout: float | None = None) -> pb.Envelope:
        """Block until one Envelope is received. Raises DeviceComError on timeout."""
        return next(self._envelope_stream(timeout))

    def _send_receive(
        self, envelope: pb.Envelope, timeout: float | None = None
    ) -> pb.Envelope:
        self._send(envelope)
        return self._receive(timeout)

    def _send_expect(
        self, envelope: pb.Envelope, expected: int, *, timeout: float | None = None
    ) -> pb.Envelope:
        """Send an envelope and verify the response type. Raises DeviceComError on mismatch."""
        resp = self._send_receive(envelope, timeout=timeout)
        if resp.type != expected:
            msg = f"Unexpected response: expected {expected}, got {resp.type}"
            raise DeviceComError(msg)
        return resp

    def set_settings(
        self, n_points: int, integration_periods: int, *, use_ema: bool
    ) -> None:
        """Send settings to device."""
        env = self._codec.build_envelope(mt.SET_SETTINGS_REQUEST)
        req = env.set_settings_request
        req.list_length = n_points
        req.integration_periods = integration_periods
        req.use_ema = use_ema
        resp = self._send_expect(env, mt.SET_SETTINGS_RESPONSE)
        if not resp.set_settings_response.success:
            msg = f"Failed to set settings: {resp}"
            raise DeviceComError(msg)

    def upload_list(self, scanning_list: list[float]) -> None:
        """Upload scanning frequency list to device."""
        total = len(scanning_list)

        env = self._codec.build_envelope(mt.SET_LIST_START_REQUEST)
        env.set_list_start_request.total_floats = total
        resp = self._send_expect(env, mt.SET_LIST_START_RESPONSE)
        if not resp.set_list_start_response.ready:
            msg = f"Failed to start list upload: {resp}"
            raise DeviceComError(msg)

        total_chunks = math.ceil(total / _LIST_CHUNK_SIZE)
        for i in range(total_chunks):
            start = i * _LIST_CHUNK_SIZE
            end = min(start + _LIST_CHUNK_SIZE, total)
            chunk_env = self._codec.build_envelope(mt.LIST_CHUNK)
            chunk = chunk_env.list_chunk
            chunk.chunk_index = i
            chunk.values.extend(scanning_list[start:end])
            chunk.is_last = i == total_chunks - 1
            self._send(chunk_env)

        resp = self._receive()
        if (
            resp.type != mt.SET_LIST_COMPLETE_RESPONSE
            or not resp.set_list_complete_response.success
        ):
            msg = f"Failed to upload list: {resp}"
            raise DeviceComError(msg)

    def start_scan(
        self, n_points: int, sweep_length_ms: float
    ) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Start scan and collect results. Returns (times, Xs, Ys)."""
        env = self._codec.build_envelope(mt.START_SCAN_REQUEST)
        env.start_scan_request.SetInParent()
        resp = self._send_expect(env, mt.START_SCAN_RESPONSE)
        if not resp.start_scan_response.started:
            msg = f"Failed to start scan: {resp}"
            raise DeviceComError(msg)

        if resp.start_scan_response.transfer_mode == _TRANSFER_MODE_PER_POINT:
            return self._collect_per_point(n_points, sweep_length_ms)
        return self._collect_bulk(n_points, sweep_length_ms)

    def _collect_bulk(
        self, n_points: int, sweep_length_ms: float
    ) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Wait for scan to finish, then request and collect chunked results.

        Tolerates a timeout if at least one chunk was received, then retransmits missing chunks.
        """
        self._await_scan_complete(sweep_length_ms)

        env = self._codec.build_envelope(mt.GET_RESULTS_REQUEST)
        env.get_results_request.SetInParent()
        self._send(env)

        chunks: list[pb.ResultsChunk | pb.ResultsChunkRetransmit] = []
        try:
            for e in self._envelope_stream(timeout=_transfer_timeout_s(n_points)):
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

        self._retransmit_missing_chunks(chunks, n_points)

        chunks.sort(key=lambda c: c.chunk_index)
        times = np.concatenate([np.array(list(c.times)) for c in chunks])
        Xs = np.concatenate([np.array(list(c.x)) for c in chunks])
        Ys = np.concatenate([np.array(list(c.y)) for c in chunks])
        return times, Xs, Ys

    def _collect_per_point(
        self, n_points: int, sweep_length_ms: float
    ) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Collect results streamed per-point during the scan.

        Detects gaps inline and NAKs missing points before they age out of the
        device's circular buffer. Retransmit responses arrive interleaved in the
        same stream. A final retransmit pass catches any stragglers.
        """
        points: list[pb.ResultPoint | pb.ResultPointRetransmit] = []
        received: set[int] = set()
        next_expected = 0
        timeout = sweep_length_ms * 1e-3 + _transfer_timeout_s(n_points)
        try:
            for e in self._envelope_stream(timeout=timeout):
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

        self._retransmit_missing_points(points, n_points)

        points.sort(key=lambda p: p.point_index)
        times = np.array([p.time for p in points])
        Xs = np.array([p.x for p in points])
        Ys = np.array([p.y for p in points])
        return times, Xs, Ys

    def _nak_point(self, point_index: int) -> None:
        """Fire-and-forget NAK for a missing point. Response arrives in the envelope stream."""
        env = self._codec.build_envelope(mt.RESULT_POINT_NAK)
        env.result_point_nak.point_index = point_index
        self._send(env)

    def _retransmit_missing_chunks(
        self, chunks: list[pb.ResultsChunk | pb.ResultsChunkRetransmit], n_points: int
    ) -> None:
        """NAK-retry any chunks missing from the received set. Appends recovered chunks in place."""
        expected_count = math.ceil(n_points / _RESULTS_CHUNK_SIZE)
        received = {c.chunk_index for c in chunks}
        missing = set(range(expected_count)) - received
        if not missing:
            return

        for idx in sorted(missing):
            for _attempt in range(_MAX_RETRANSMIT_ATTEMPTS):
                env = self._codec.build_envelope(mt.RESULTS_CHUNK_NAK)
                env.results_chunk_nak.chunk_index = idx
                resp = self._send_receive(env, timeout=self._timeout)
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
        self, points: list[pb.ResultPoint | pb.ResultPointRetransmit], n_points: int
    ) -> None:
        """NAK-retry any points missing from the received set. Appends recovered points in place."""
        expected = set(range(n_points))
        received = {p.point_index for p in points}
        missing = expected - received
        if not missing:
            return

        for idx in sorted(missing):
            for _attempt in range(_MAX_RETRANSMIT_ATTEMPTS):
                env = self._codec.build_envelope(mt.RESULT_POINT_NAK)
                env.result_point_nak.point_index = idx
                resp = self._send_receive(env, timeout=self._timeout)
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

    def _await_scan_complete(self, sweep_length_ms: float) -> None:
        """Poll device status until scan is no longer ongoing."""
        sweep_s = sweep_length_ms * 1e-3
        time.sleep(sweep_s)
        deadline = time.monotonic() + sweep_s
        while time.monotonic() < deadline:
            env = self._codec.build_envelope(mt.GET_STATUS_REQUEST)
            env.get_status_request.SetInParent()
            resp = self._send_expect(env, mt.GET_STATUS_RESPONSE)
            if not resp.get_status_response.scan_ongoing:
                return
            time.sleep(sweep_s * 0.01)
        msg = "Timeout waiting for scan to complete"
        raise DeviceComError(msg)

    def ping(self, nonce: int) -> int:
        """Send a ping and return the echoed nonce."""
        env = self._codec.build_envelope(mt.PING)
        env.ping.nonce = nonce
        resp = self._send_expect(env, mt.PONG)
        if resp.pong.nonce != nonce:
            msg = f"Ping nonce mismatch: sent {nonce}, got {resp}"
            raise DeviceComError(msg)
        return resp.pong.nonce

    def get_device_info(self) -> pb.GetDeviceInfoResponse:
        """Query device info. Returns the protobuf GetDeviceInfoResponse sub-message."""
        env = self._codec.build_envelope(mt.GET_DEVICE_INFO_REQUEST)
        env.get_device_info_request.SetInParent()
        return self._send_expect(
            env, mt.GET_DEVICE_INFO_RESPONSE
        ).get_device_info_response

    def get_status(self) -> pb.GetStatusResponse:
        """Query device status. Returns the protobuf GetStatusResponse sub-message."""
        env = self._codec.build_envelope(mt.GET_STATUS_REQUEST)
        env.get_status_request.SetInParent()
        return self._send_expect(env, mt.GET_STATUS_RESPONSE).get_status_response

    def close(self) -> None:
        """Close the connection."""
        with contextlib.suppress(AttributeError):
            self._rx_stream.reset()
        with contextlib.suppress(AttributeError):
            self._conn.close()
