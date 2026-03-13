from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, TypeVar, cast

import numpy as np
import serial

from pyglaze.device.configuration import AMP_BAUDRATE
from pyglaze.device.discovery import discover_one
from pyglaze.device.exceptions import DeviceComError
from pyglaze.device.transport import (
    MAX_COMMAND_RETRIES,
    PROTOCOL_BASELINE_S,
    Connection,
    MimLinkTransport,
)
from pyglaze.mimlink import msg_types as mt
from pyglaze.mimlink.proto.envelope_pb2 import TRANSFER_MODE_PER_POINT

if TYPE_CHECKING:
    from collections.abc import Callable

    from pyglaze.device.configuration import DeviceConfiguration
    from pyglaze.helpers._types import FloatArray
    from pyglaze.mimlink.proto import envelope_pb2 as pb


_T = TypeVar("_T")

_SERIAL_BITS_PER_BYTE = 10  # 8 data + start + stop
_BYTES_PER_RESULT_POINT = 16  # 3 x float32 + framing overhead
_TRANSFER_SAFETY_FACTOR = 2.5
_TRANSFER_BASELINE_S = 0.5  # fixed latency headroom
_PROTOCOL_SWEEP_SAFETY_FACTOR = 2
_MIN_STATUS_POLL_S = 0.005
_RESULTS_CHUNK_SIZE = 20
_MAX_RETRANSMIT_ATTEMPTS = 3
_LIST_CHUNK_SIZE = 50


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
        n_points: int,
        sweep_length_ms: float,
    ) -> None:
        self._transport = transport
        self._n_points = n_points
        self._sweep_length_ms = sweep_length_ms
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
        resp = self._transport.send_expect(
            env, mt.SET_SETTINGS_RESPONSE
        ).set_settings_response
        if not resp.success:
            msg = f"Failed to set settings: {resp}"
            raise DeviceComError(msg)

    def upload_list(self, scanning_list: list[float]) -> None:
        """Upload the scan list to the device. Retries the full sequence on failure."""
        last_err: DeviceComError | None = None
        for _ in range(MAX_COMMAND_RETRIES + 1):
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
        resp = self._transport.send_expect(
            env, mt.SET_LIST_START_RESPONSE
        ).set_list_start_response
        if not resp.ready:
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

        complete = self._transport.receive()
        if (
            complete.type != mt.SET_LIST_COMPLETE_RESPONSE
            or not complete.set_list_complete_response.success
        ):
            msg = f"Failed to upload list: {complete}"
            raise DeviceComError(msg)

    def start_scan(self) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Start scan and collect results. Returns (times, Xs, Ys)."""
        timeout = self._scan_timeout_s(self._sweep_length_ms)
        env = self._transport.build_envelope(mt.START_SCAN_REQUEST)
        env.start_scan_request.SetInParent()
        resp = self._transport.send_expect(
            env, mt.START_SCAN_RESPONSE, timeout=timeout
        ).start_scan_response
        if not resp.started:
            msg = f"Failed to start scan: {resp}"
            raise DeviceComError(msg)

        if resp.transfer_mode == TRANSFER_MODE_PER_POINT:
            return self._collect_per_point(timeout=timeout)
        return self._collect_bulk(timeout=timeout)

    def _collect_bulk(
        self,
        *,
        timeout: float | None = None,
    ) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Wait for scan to finish, then request and collect chunked results.

        Tolerates a timeout if at least one chunk was received, then retransmits missing chunks.
        """
        if timeout is None:
            timeout = self._scan_timeout_s(self._sweep_length_ms)
        self._await_scan_complete(
            sweep_length_ms=self._sweep_length_ms, timeout=timeout
        )

        env = self._transport.build_envelope(mt.GET_RESULTS_REQUEST)
        env.get_results_request.SetInParent()
        self._transport.send(env)

        chunks: list[pb.ResultsChunk | pb.ResultsChunkRetransmit] = []
        try:
            for e in self._transport.envelope_stream(
                timeout=_transfer_timeout_s(self._n_points)
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

        self._retransmit_missing_chunks(
            chunks, n_points=self._n_points, timeout=timeout
        )

        chunks = _dedup_sorted(chunks, key=lambda c: c.chunk_index)
        times = np.concatenate([np.array(list(c.times)) for c in chunks])
        Xs = np.concatenate([np.array(list(c.x)) for c in chunks])
        Ys = np.concatenate([np.array(list(c.y)) for c in chunks])
        return times, Xs, Ys

    def _collect_per_point(
        self,
        *,
        timeout: float | None = None,
    ) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Collect results streamed per-point during the scan.

        Detects gaps inline and NAKs missing points before they age out of the
        device's circular buffer. Retransmit responses arrive interleaved in the
        same stream. A final retransmit pass catches any stragglers.
        """
        if timeout is None:
            timeout = self._scan_timeout_s(self._sweep_length_ms)

        points: list[pb.ResultPoint | pb.ResultPointRetransmit] = []
        received: set[int] = set()
        next_expected = 0
        stream_timeout = self._sweep_length_ms * 1e-3 + _transfer_timeout_s(
            self._n_points
        )
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

        self._retransmit_missing_points(
            points, n_points=self._n_points, timeout=timeout
        )

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
            + PROTOCOL_BASELINE_S
        )

    def get_device_info(self) -> pb.GetDeviceInfoResponse:
        """Query device info. Delegates to transport."""
        return self._transport.get_device_info()

    def get_status(self) -> pb.GetStatusResponse:
        """Query device status. Delegates to transport."""
        return self._transport.get_status()

    def close(self) -> None:
        """Close the connection. Delegates to transport."""
        self._transport.close()
