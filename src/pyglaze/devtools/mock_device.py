from __future__ import annotations

import time

import numpy as np

from pyglaze.mimlink.codec import EnvelopeCodec
from pyglaze.mimlink.framing import FrameDecodeError
from pyglaze.mimlink.proto import envelope_pb2
from pyglaze.mimlink.rx_stream import RxFrameStream


def _msg_type(name: str) -> int:
    return envelope_pb2.MsgType.Value(name)


_SET_SETTINGS_REQUEST = _msg_type("MSG_TYPE_SET_SETTINGS_REQUEST")
_SET_SETTINGS_RESPONSE = _msg_type("MSG_TYPE_SET_SETTINGS_RESPONSE")
_SET_LIST_START_REQUEST = _msg_type("MSG_TYPE_SET_LIST_START_REQUEST")
_SET_LIST_START_RESPONSE = _msg_type("MSG_TYPE_SET_LIST_START_RESPONSE")
_LIST_CHUNK = _msg_type("MSG_TYPE_LIST_CHUNK")
_SET_LIST_COMPLETE_RESPONSE = _msg_type("MSG_TYPE_SET_LIST_COMPLETE_RESPONSE")
_START_SCAN_REQUEST = _msg_type("MSG_TYPE_START_SCAN_REQUEST")
_START_SCAN_RESPONSE = _msg_type("MSG_TYPE_START_SCAN_RESPONSE")
_GET_STATUS_REQUEST = _msg_type("MSG_TYPE_GET_STATUS_REQUEST")
_GET_STATUS_RESPONSE = _msg_type("MSG_TYPE_GET_STATUS_RESPONSE")
_GET_RESULTS_REQUEST = _msg_type("MSG_TYPE_GET_RESULTS_REQUEST")
_RESULTS_CHUNK = _msg_type("MSG_TYPE_RESULTS_CHUNK")
_GET_DEVICE_INFO_REQUEST = _msg_type("MSG_TYPE_GET_DEVICE_INFO_REQUEST")
_GET_DEVICE_INFO_RESPONSE = _msg_type("MSG_TYPE_GET_DEVICE_INFO_RESPONSE")
_RESULT_POINT = _msg_type("MSG_TYPE_RESULT_POINT")
_RESULT_POINT_NAK = _msg_type("MSG_TYPE_RESULT_POINT_NAK")
_RESULT_POINT_RETRANSMIT = _msg_type("MSG_TYPE_RESULT_POINT_RETRANSMIT")
_RESULTS_CHUNK_NAK = _msg_type("MSG_TYPE_RESULTS_CHUNK_NAK")
_RESULTS_CHUNK_RETRANSMIT = _msg_type("MSG_TYPE_RESULTS_CHUNK_RETRANSMIT")
_PING = _msg_type("MSG_TYPE_PING")
_PONG = _msg_type("MSG_TYPE_PONG")

_TRANSFER_MODE_BULK = 0
_TRANSFER_MODE_PER_POINT = 1


class MimLinkMockDevice:
    """Mock MimLink endpoint implementing the binary protocol over a serial-like API."""

    LI_MODULATION_FREQUENCY = 10000
    MAX_LIST_LENGTH = 6000
    RESULTS_CHUNK_SIZE = 20
    _MIN_ITEMS_FOR_DROP = 2

    def __init__(
        self,
        fail_after: float = np.inf,
        n_fails: float = np.inf,
        *,
        empty_responses: bool = False,
        instant_response: bool = False,
        transfer_mode: int = _TRANSFER_MODE_BULK,
        drop_chunk_once: bool = False,
        drop_point_once: bool = False,
    ) -> None:
        self.fail_after = fail_after
        self.fails_wanted = n_fails
        self.n_failures = 0
        self.n_scans = 0
        self.rng = np.random.default_rng()
        self.empty_responses = empty_responses
        self.instant_response = instant_response
        self.transfer_mode = transfer_mode
        self.drop_chunk_once = drop_chunk_once
        self.drop_point_once = drop_point_once
        self._chunk_drop_done = False
        self._point_drop_done = False

        self.list_length: int | None = None
        self.expected_total_floats: int | None = None
        self.integration_periods: int | None = None
        self.use_ema: bool = False
        self.scanning_list: list[float] = []
        self.is_scanning = False
        self._scan_start_time: float | None = None
        self._tx_buffer = bytearray()

        # Per-point result cache (for retransmit)
        self._result_points: dict[int, object] = {}
        # Bulk result cache (for retransmit)
        self._result_chunks: dict[int, object] = {}

        self._codec = EnvelopeCodec()
        self._rx_stream = RxFrameStream()

    @property
    def in_waiting(self) -> int:
        """Bytes available for host reads."""
        return len(self._tx_buffer)

    def reset_input_buffer(self) -> None:
        """Discard queued outgoing bytes."""
        self._tx_buffer.clear()

    def close(self) -> None:
        """Close the mock device."""

    def write(self, input_bytes: bytes) -> None:
        """Handle bytes written by host endpoint."""
        if self.empty_responses:
            return
        # Legacy ASCII detection byte — silently ignore.
        if input_bytes == b"H":
            return
        for frame in self._rx_stream.push(input_bytes):
            try:
                env = self._codec.decode(frame)
            except FrameDecodeError:
                continue
            self._on_envelope(env)

    def read(self, size: int) -> bytes:
        """Read queued bytes produced by device endpoint."""
        if self.empty_responses or size <= 0 or not self._tx_buffer:
            return b""
        n_to_read = min(size, len(self._tx_buffer))
        data = bytes(self._tx_buffer[:n_to_read])
        del self._tx_buffer[:n_to_read]
        return data

    def read_until(self, expected: bytes = b"\x00") -> bytes:
        """Read queued data up to expected delimiter (defaults to frame delimiter)."""
        if self.empty_responses or not self._tx_buffer:
            return b""

        idx = self._tx_buffer.find(expected)
        if idx < 0:
            data = bytes(self._tx_buffer)
            self._tx_buffer.clear()
            return data

        end = idx + len(expected)
        data = bytes(self._tx_buffer[:end])
        del self._tx_buffer[:end]
        return data

    def _queue_tx(self, env: object) -> None:
        self._tx_buffer.extend(self._codec.encode(env))

    @property
    def _scanning_time(self) -> float:
        if self.instant_response:
            return 0.0
        if self.list_length is None or self.integration_periods is None:
            return 0.0
        return (
            self.list_length * self.integration_periods / self.LI_MODULATION_FREQUENCY
        )

    def _scan_has_finished(self) -> bool:
        if not self.is_scanning:
            return True
        if self._scan_start_time is None:
            return True
        finished = time.time() - self._scan_start_time > self._scanning_time
        if finished:
            self.is_scanning = False
            self._scan_start_time = None
        return finished

    def _prepare_scan_data(self) -> None:
        if not self.scanning_list:
            self._result_points = {}
            self._result_chunks = {}
            return

        self.n_scans += 1
        should_fail = (
            self.n_scans > self.fail_after and self.n_failures < self.fails_wanted
        )
        if should_fail:
            self.n_failures += 1
            self._result_points = {}
            self._result_chunks = {}
            return

        times = np.array(self.scanning_list) * 100e-12
        xs = self.rng.random(len(self.scanning_list)) + 1.0
        ys = self.rng.random(len(self.scanning_list)) + 1.0

        # Build point cache
        self._result_points = {}
        for idx, (t, x, y) in enumerate(zip(times, xs, ys)):
            env = self._codec.build_envelope(_RESULT_POINT)
            p = env.result_point
            p.point_index = idx
            p.time = float(t)
            p.x = float(x)
            p.y = float(y)
            p.is_last = idx == len(times) - 1
            p.send_timestamp_us = 0
            self._result_points[idx] = env

        # Build chunk cache
        self._result_chunks = {}
        for chunk_idx, start in enumerate(
            range(0, len(times), self.RESULTS_CHUNK_SIZE)
        ):
            end = min(start + self.RESULTS_CHUNK_SIZE, len(times))
            env = self._codec.build_envelope(_RESULTS_CHUNK)
            c = env.results_chunk
            c.chunk_index = chunk_idx
            c.times.extend([float(v) for v in times[start:end]])
            c.x.extend([float(v) for v in xs[start:end]])
            c.y.extend([float(v) for v in ys[start:end]])
            c.is_last = end == len(times)
            self._result_chunks[chunk_idx] = env

    def _send_per_point_stream(self) -> None:
        points = sorted(
            self._result_points.values(), key=lambda e: e.result_point.point_index
        )
        if not points:
            return
        drop_idx = (
            1 if self.drop_point_once and len(points) > self._MIN_ITEMS_FOR_DROP else -1
        )
        for env in points:
            if env.result_point.point_index == drop_idx and not self._point_drop_done:
                self._point_drop_done = True
                continue
            self._queue_tx(env)

    def _send_bulk_results(self) -> None:
        chunks = sorted(
            self._result_chunks.values(), key=lambda e: e.results_chunk.chunk_index
        )
        if not chunks:
            return
        drop_idx = (
            1 if self.drop_chunk_once and len(chunks) > self._MIN_ITEMS_FOR_DROP else -1
        )
        for env in chunks:
            if env.results_chunk.chunk_index == drop_idx and not self._chunk_drop_done:
                self._chunk_drop_done = True
                continue
            self._queue_tx(env)

    def _on_envelope(self, env: object) -> None:  # noqa: PLR0915
        env_type = env.type

        if env_type == _PING:
            resp = self._codec.build_envelope(_PONG)
            resp.pong.nonce = env.ping.nonce
            self._queue_tx(resp)
            return

        if env_type == _SET_SETTINGS_REQUEST:
            req = env.set_settings_request
            self.list_length = req.list_length
            self.integration_periods = req.integration_periods
            self.use_ema = bool(req.use_ema)
            resp = self._codec.build_envelope(_SET_SETTINGS_RESPONSE)
            resp.set_settings_response.success = True
            self._queue_tx(resp)
            return

        if env_type == _SET_LIST_START_REQUEST:
            self.expected_total_floats = env.set_list_start_request.total_floats
            self.scanning_list = []
            resp = self._codec.build_envelope(_SET_LIST_START_RESPONSE)
            resp.set_list_start_response.ready = True
            self._queue_tx(resp)
            return

        if env_type == _LIST_CHUNK:
            chunk = env.list_chunk
            self.scanning_list.extend(list(chunk.values))
            if chunk.is_last:
                resp = self._codec.build_envelope(_SET_LIST_COMPLETE_RESPONSE)
                resp.set_list_complete_response.success = True
                resp.set_list_complete_response.floats_received = len(
                    self.scanning_list
                )
                self._queue_tx(resp)
            return

        if env_type == _START_SCAN_REQUEST:
            settings_valid = (
                self.list_length is not None and self.integration_periods is not None
            )
            list_valid = len(self.scanning_list) > 0
            started = settings_valid and list_valid
            resp = self._codec.build_envelope(_START_SCAN_RESPONSE)
            r = resp.start_scan_response
            r.started = started
            r.error = "" if started else "Settings/list missing"
            r.transfer_mode = self.transfer_mode
            self._queue_tx(resp)
            if not started:
                return
            self.is_scanning = True
            self._scan_start_time = time.time()
            self._prepare_scan_data()
            if self.transfer_mode == _TRANSFER_MODE_PER_POINT:
                self._send_per_point_stream()
            return

        if env_type == _GET_STATUS_REQUEST:
            scan_ongoing = not self._scan_has_finished()
            resp = self._codec.build_envelope(_GET_STATUS_RESPONSE)
            r = resp.get_status_response
            r.scan_ongoing = scan_ongoing
            r.list_length = len(self.scanning_list)
            r.max_list_length = self.MAX_LIST_LENGTH
            r.modulation_frequency_hz = self.LI_MODULATION_FREQUENCY
            r.settings_valid = (
                self.list_length is not None and self.integration_periods is not None
            )
            r.list_valid = bool(self.scanning_list)
            self._queue_tx(resp)
            return

        if env_type == _GET_RESULTS_REQUEST:
            self._send_bulk_results()
            return

        if env_type == _GET_DEVICE_INFO_REQUEST:
            resp = self._codec.build_envelope(_GET_DEVICE_INFO_RESPONSE)
            r = resp.get_device_info_response
            r.serial_number = "M-9999"
            r.firmware_version = "v0.1.0"
            r.bsp_name = "mock"
            r.build_type = "Release"
            r.transfer_mode = self.transfer_mode
            r.hardware_type = "mock"
            r.hardware_revision = 0
            self._queue_tx(resp)
            return

        if env_type == _RESULT_POINT_NAK:
            point_idx = env.result_point_nak.point_index
            point_env = self._result_points.get(point_idx)
            resp = self._codec.build_envelope(_RESULT_POINT_RETRANSMIT)
            r = resp.result_point_retransmit
            r.point_index = point_idx
            if point_env is None:
                r.available = False
                r.time = 0.0
                r.x = 0.0
                r.y = 0.0
            else:
                p = point_env.result_point
                r.available = True
                r.time = p.time
                r.x = p.x
                r.y = p.y
            self._queue_tx(resp)
            return

        if env_type == _RESULTS_CHUNK_NAK:
            chunk_idx = env.results_chunk_nak.chunk_index
            chunk_env = self._result_chunks.get(chunk_idx)
            resp = self._codec.build_envelope(_RESULTS_CHUNK_RETRANSMIT)
            r = resp.results_chunk_retransmit
            r.chunk_index = chunk_idx
            if chunk_env is None:
                r.available = False
                r.is_last = False
            else:
                c = chunk_env.results_chunk
                r.times.extend(list(c.times))
                r.x.extend(list(c.x))
                r.y.extend(list(c.y))
                r.is_last = c.is_last
                r.available = True
            self._queue_tx(resp)
            return


def list_mock_devices() -> list[str]:
    """List all available mock devices."""
    return [
        "mock_mimlink_device",
        "mock_mimlink_per_point",
        "mock_mimlink_drop_chunk",
        "mock_mimlink_drop_point",
        "mock_mimlink_scan_should_fail",
        "mock_mimlink_fail_first_scan",
    ]


def _mock_device_factory(port: str) -> MimLinkMockDevice:
    if port == "mock_mimlink_device":
        return MimLinkMockDevice(transfer_mode=_TRANSFER_MODE_BULK)
    if port == "mock_mimlink_per_point":
        return MimLinkMockDevice(transfer_mode=_TRANSFER_MODE_PER_POINT)
    if port == "mock_mimlink_drop_chunk":
        return MimLinkMockDevice(
            transfer_mode=_TRANSFER_MODE_BULK, drop_chunk_once=True
        )
    if port == "mock_mimlink_drop_point":
        return MimLinkMockDevice(
            transfer_mode=_TRANSFER_MODE_PER_POINT, drop_point_once=True
        )
    if port == "mock_mimlink_scan_should_fail":
        return MimLinkMockDevice(fail_after=0, transfer_mode=_TRANSFER_MODE_BULK)
    if port == "mock_mimlink_fail_first_scan":
        return MimLinkMockDevice(
            fail_after=0,
            n_fails=1,
            transfer_mode=_TRANSFER_MODE_BULK,
        )

    msg = f"Unknown mock device requested: {port}. Valid options are: {list_mock_devices()}"
    raise ValueError(msg)
