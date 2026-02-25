"""Synchronous MimLink transport over serial."""

from __future__ import annotations

import contextlib
import math
import time
from typing import TYPE_CHECKING, Any, Protocol, cast

import numpy as np
import serial

from pyglaze.device.ampcom import DeviceComError, _points_per_interval
from pyglaze.devtools.mock_device import _mock_device_factory
from pyglaze.mimlink.codec import EnvelopeCodec
from pyglaze.mimlink.framing import FrameDecodeError
from pyglaze.mimlink.proto import envelope_pb2
from pyglaze.mimlink.rx_stream import RxFrameStream

if TYPE_CHECKING:
    from pyglaze.device.configuration import Interval, LeDeviceConfiguration


def _msg_type(name: str) -> int:
    return envelope_pb2.MsgType.Value(name)


# Cache commonly used message type ints.
_PING = _msg_type("MSG_TYPE_PING")
_PONG = _msg_type("MSG_TYPE_PONG")
_SET_SETTINGS_REQUEST = _msg_type("MSG_TYPE_SET_SETTINGS_REQUEST")
_SET_SETTINGS_RESPONSE = _msg_type("MSG_TYPE_SET_SETTINGS_RESPONSE")
_SET_LIST_START_REQUEST = _msg_type("MSG_TYPE_SET_LIST_START_REQUEST")
_SET_LIST_START_RESPONSE = _msg_type("MSG_TYPE_SET_LIST_START_RESPONSE")
_LIST_CHUNK = _msg_type("MSG_TYPE_LIST_CHUNK")
_SET_LIST_COMPLETE_RESPONSE = _msg_type("MSG_TYPE_SET_LIST_COMPLETE_RESPONSE")
_START_SCAN_REQUEST = _msg_type("MSG_TYPE_START_SCAN_REQUEST")
_START_SCAN_RESPONSE = _msg_type("MSG_TYPE_START_SCAN_RESPONSE")
_GET_RESULTS_REQUEST = _msg_type("MSG_TYPE_GET_RESULTS_REQUEST")
_RESULTS_CHUNK = _msg_type("MSG_TYPE_RESULTS_CHUNK")
_GET_STATUS_REQUEST = _msg_type("MSG_TYPE_GET_STATUS_REQUEST")
_GET_STATUS_RESPONSE = _msg_type("MSG_TYPE_GET_STATUS_RESPONSE")
_GET_DEVICE_INFO_REQUEST = _msg_type("MSG_TYPE_GET_DEVICE_INFO_REQUEST")
_GET_DEVICE_INFO_RESPONSE = _msg_type("MSG_TYPE_GET_DEVICE_INFO_RESPONSE")
_RESULT_POINT = _msg_type("MSG_TYPE_RESULT_POINT")
_RESULT_POINT_NAK = _msg_type("MSG_TYPE_RESULT_POINT_NAK")
_RESULT_POINT_RETRANSMIT = _msg_type("MSG_TYPE_RESULT_POINT_RETRANSMIT")
_RESULTS_CHUNK_NAK = _msg_type("MSG_TYPE_RESULTS_CHUNK_NAK")
_RESULTS_CHUNK_RETRANSMIT = _msg_type("MSG_TYPE_RESULTS_CHUNK_RETRANSMIT")

_TRANSFER_MODE_PER_POINT = 1
_RESULTS_CHUNK_SIZE = 20
_MAX_RETRANSMIT_ATTEMPTS = 3
_LIST_CHUNK_SIZE = 50


class _SerialLike(Protocol):
    @property
    def in_waiting(self) -> int: ...

    def read(self, size: int) -> bytes: ...

    def write(self, data: bytes) -> int | None: ...

    def reset_input_buffer(self) -> None: ...

    def close(self) -> None: ...


def _compute_scanning_list(
    n_points: int, intervals: list[Interval]
) -> list[float]:
    """Compute the scanning frequency list from config."""
    scanning_list: list[float] = []
    for interval, pts in zip(
        intervals,
        _points_per_interval(n_points, intervals),
    ):
        scanning_list.extend(
            np.linspace(
                interval.lower,
                interval.upper,
                pts,
                endpoint=len(intervals) == 1,
            ),
        )
    return scanning_list


class MimLinkTransport:
    """Synchronous MimLink communication over serial."""

    def __init__(self, config: LeDeviceConfiguration) -> None:
        self._config = config
        self._codec = EnvelopeCodec()
        self._rx_stream = RxFrameStream()
        self._env_buffer: list[Any] = []

        if "mock_" in config.amp_port:
            self._ser: _SerialLike = cast(
                "_SerialLike", _mock_device_factory(config)
            )
        else:
            self._ser = cast(
                "_SerialLike",
                serial.serial_for_url(
                    url=config.amp_port,
                    baudrate=config.amp_baudrate,
                    timeout=config.amp_timeout_seconds,
                ),
            )
        self._ser.reset_input_buffer()
        self.last_transfer_mode: int = 0

    def __del__(self) -> None:
        """Clean up serial connection."""
        self.close()

    def _send(self, envelope: Any) -> None:
        self._ser.write(self._codec.encode(envelope))

    def _drain_serial(self) -> None:
        """Read available serial bytes and decode all complete frames into the envelope buffer."""
        available = self._ser.in_waiting
        if available > 0:
            data = self._ser.read(available)
        else:
            data = self._ser.read(1)
            if not data:
                return
        for frame in self._rx_stream.push(data):
            try:
                self._env_buffer.append(self._codec.decode(frame))
            except FrameDecodeError:  # noqa: PERF203
                continue

    def _receive(self, timeout: float | None = None) -> Any:
        """Block until one Envelope is received. Raises DeviceComError on timeout."""
        if timeout is None:
            timeout = self._config.amp_timeout_seconds or 5.0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._env_buffer:
                return self._env_buffer.pop(0)
            self._drain_serial()
        msg = "Timeout waiting for device response"
        raise DeviceComError(msg)

    def _send_receive(self, envelope: Any, timeout: float | None = None) -> Any:
        self._send(envelope)
        return self._receive(timeout)

    def _receive_until(
        self,
        predicate: Any,
        collector: Any,
        timeout: float | None = None,
    ) -> None:
        """Read envelopes until predicate(envelope) returns True, calling collector(envelope) for each."""
        if timeout is None:
            timeout = self._config.amp_timeout_seconds or 5.0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # Process buffered envelopes first.
            while self._env_buffer:
                env = self._env_buffer.pop(0)
                collector(env)
                if predicate(env):
                    return
            self._drain_serial()
        msg = "Timeout waiting for device response"
        raise DeviceComError(msg)

    # --- High-level operations ---

    def set_settings(self, n_points: int, integration_periods: int, *, use_ema: bool) -> None:
        """Send settings to device."""
        env = self._codec.build_envelope(_SET_SETTINGS_REQUEST)
        req = env.set_settings_request
        req.list_length = n_points
        req.integration_periods = integration_periods
        req.use_ema = use_ema
        resp = self._send_receive(env)
        if resp.type != _SET_SETTINGS_RESPONSE or not resp.set_settings_response.success:
            msg = f"Failed to set settings: {resp}"
            raise DeviceComError(msg)

    def upload_list(self, scanning_list: list[float]) -> None:
        """Upload scanning frequency list to device."""
        total = len(scanning_list)

        env = self._codec.build_envelope(_SET_LIST_START_REQUEST)
        env.set_list_start_request.total_floats = total
        resp = self._send_receive(env)
        if resp.type != _SET_LIST_START_RESPONSE or not resp.set_list_start_response.ready:
            msg = f"Failed to start list upload: {resp}"
            raise DeviceComError(msg)

        total_chunks = (total + _LIST_CHUNK_SIZE - 1) // _LIST_CHUNK_SIZE
        for i in range(total_chunks):
            start = i * _LIST_CHUNK_SIZE
            end = min(start + _LIST_CHUNK_SIZE, total)
            chunk_env = self._codec.build_envelope(_LIST_CHUNK)
            chunk = chunk_env.list_chunk
            chunk.chunk_index = i
            chunk.values.extend(scanning_list[start:end])
            chunk.is_last = i == total_chunks - 1
            self._send(chunk_env)

        resp = self._receive()
        if resp.type != _SET_LIST_COMPLETE_RESPONSE or not resp.set_list_complete_response.success:
            msg = f"Failed to upload list: {resp}"
            raise DeviceComError(msg)

    def start_scan(self, n_points: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Start scan and collect results. Returns (times, Xs, Ys)."""
        env = self._codec.build_envelope(_START_SCAN_REQUEST)
        env.start_scan_request.SetInParent()
        resp = self._send_receive(env)
        if resp.type != _START_SCAN_RESPONSE or not resp.start_scan_response.started:
            msg = f"Failed to start scan: {resp}"
            raise DeviceComError(msg)

        self.last_transfer_mode = resp.start_scan_response.transfer_mode

        if resp.start_scan_response.transfer_mode == _TRANSFER_MODE_PER_POINT:
            return self._collect_per_point(n_points)
        return self._collect_bulk(n_points)

    def _collect_bulk(self, n_points: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        self._await_scan_complete()

        env = self._codec.build_envelope(_GET_RESULTS_REQUEST)
        env.get_results_request.SetInParent()
        self._send(env)

        chunks: list[Any] = []
        complete = False

        def collector(e: Any) -> None:
            nonlocal complete
            if e.type == _RESULTS_CHUNK:
                chunks.append(e.results_chunk)
                if e.results_chunk.is_last:
                    complete = True
            elif e.type == _RESULTS_CHUNK_RETRANSMIT:
                rt = e.results_chunk_retransmit
                if rt.available:
                    chunks.append(rt)

        try:
            self._receive_until(lambda _: complete, collector, timeout=10.0)
        except DeviceComError:
            if not chunks:
                raise

        self._retransmit_missing_chunks(chunks, n_points)

        chunks.sort(key=lambda c: c.chunk_index)
        times = np.concatenate([np.array(list(c.times)) for c in chunks])
        Xs = np.concatenate([np.array(list(c.x)) for c in chunks])
        Ys = np.concatenate([np.array(list(c.y)) for c in chunks])
        return times, Xs, Ys

    def _collect_per_point(self, n_points: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        points: list[Any] = []
        complete = False

        def collector(e: Any) -> None:
            nonlocal complete
            if e.type == _RESULT_POINT:
                points.append(e.result_point)
                if e.result_point.is_last:
                    complete = True
            elif e.type == _RESULT_POINT_RETRANSMIT:
                rt = e.result_point_retransmit
                if rt.available:
                    points.append(rt)

        try:
            self._receive_until(lambda _: complete, collector, timeout=10.0)
        except DeviceComError:
            if not points:
                raise

        self._retransmit_missing_points(points, n_points)

        points.sort(key=lambda p: p.point_index)
        times = np.array([p.time for p in points])
        Xs = np.array([p.x for p in points])
        Ys = np.array([p.y for p in points])
        return times, Xs, Ys

    def _retransmit_missing_chunks(self, chunks: list[Any], n_points: int) -> None:
        expected_count = math.ceil(n_points / _RESULTS_CHUNK_SIZE)
        received = {c.chunk_index for c in chunks}
        missing = set(range(expected_count)) - received
        if not missing:
            return

        for idx in sorted(missing):
            for _attempt in range(_MAX_RETRANSMIT_ATTEMPTS):
                env = self._codec.build_envelope(_RESULTS_CHUNK_NAK)
                env.results_chunk_nak.chunk_index = idx
                resp = self._send_receive(env, timeout=5.0)
                if resp.type == _RESULTS_CHUNK_RETRANSMIT and resp.results_chunk_retransmit.available:
                    chunks.append(resp.results_chunk_retransmit)
                    break
            else:
                msg = f"Chunk {idx} unavailable after {_MAX_RETRANSMIT_ATTEMPTS} attempts"
                raise DeviceComError(msg)

    def _retransmit_missing_points(self, points: list[Any], n_points: int) -> None:
        expected = set(range(n_points))
        received = {p.point_index for p in points}
        missing = expected - received
        if not missing:
            return

        for idx in sorted(missing):
            for _attempt in range(_MAX_RETRANSMIT_ATTEMPTS):
                env = self._codec.build_envelope(_RESULT_POINT_NAK)
                env.result_point_nak.point_index = idx
                resp = self._send_receive(env, timeout=5.0)
                if resp.type == _RESULT_POINT_RETRANSMIT and resp.result_point_retransmit.available:
                    points.append(resp.result_point_retransmit)
                    break
            else:
                msg = f"Point {idx} unavailable after {_MAX_RETRANSMIT_ATTEMPTS} attempts"
                raise DeviceComError(msg)

    def _await_scan_complete(self) -> None:
        """Poll device status until scan is no longer ongoing."""
        time.sleep(self._config._sweep_length_ms * 1e-3)  # noqa: SLF001
        while True:
            env = self._codec.build_envelope(_GET_STATUS_REQUEST)
            env.get_status_request.SetInParent()
            resp = self._send_receive(env)
            if resp.type != _GET_STATUS_RESPONSE or not resp.get_status_response.scan_ongoing:
                return
            time.sleep(self._config._sweep_length_ms * 1e-3 * 0.01)  # noqa: SLF001

    def ping(self, nonce: int) -> int:
        """Send a ping and return the echoed nonce."""
        env = self._codec.build_envelope(_PING)
        env.ping.nonce = nonce
        resp = self._send_receive(env, timeout=2.0)
        if resp.type != _PONG or resp.pong.nonce != nonce:
            msg = f"Ping nonce mismatch: sent {nonce}, got {resp}"
            raise DeviceComError(msg)
        return resp.pong.nonce

    def get_device_info(self) -> Any:
        """Query device info. Returns the protobuf GetDeviceInfoResponse sub-message."""
        env = self._codec.build_envelope(_GET_DEVICE_INFO_REQUEST)
        env.get_device_info_request.SetInParent()
        resp = self._send_receive(env)
        if resp.type != _GET_DEVICE_INFO_RESPONSE:
            msg = f"Failed to get device info: {resp}"
            raise DeviceComError(msg)
        return resp.get_device_info_response

    def get_status(self) -> Any:
        """Query device status. Returns the protobuf GetStatusResponse sub-message."""
        env = self._codec.build_envelope(_GET_STATUS_REQUEST)
        env.get_status_request.SetInParent()
        resp = self._send_receive(env)
        if resp.type != _GET_STATUS_RESPONSE:
            msg = f"Failed to get status: {resp}"
            raise DeviceComError(msg)
        return resp.get_status_response

    def close(self) -> None:
        """Close the serial connection."""
        with contextlib.suppress(AttributeError):
            self._rx_stream.reset()
        with contextlib.suppress(AttributeError):
            self._ser.close()
