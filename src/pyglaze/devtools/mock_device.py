from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from pyglaze.device.transport import Connection
from pyglaze.mimlink import msg_types as mt
from pyglaze.mimlink.codec import EnvelopeCodec
from pyglaze.mimlink.framing import FrameDecodeError
from pyglaze.mimlink.rx_stream import RxFrameStream

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from pyglaze.device.configuration import DeviceConfiguration
    from pyglaze.helpers._types import FloatArray
    from pyglaze.mimlink.proto.envelope_pb2 import Envelope

from pyglaze.mimlink.proto.envelope_pb2 import (
    CONFIG_STATUS_REASON_INVALID_CONFIG,
    CONFIG_STATUS_REASON_NONE,
    CONFIG_STATUS_REASON_UNCONFIGURED,
    OPERATIONAL_STATE_COMMISSIONING_IDLE,
    OPERATIONAL_STATE_COMMISSIONING_TRIM_ACTIVE,
    OPERATIONAL_STATE_NORMAL,
    TRANSFER_MODE_BULK,
    TRANSFER_MODE_PER_POINT,
    ConfigStatusReason,
    OperationalState,
    TransferMode,
)


class MockDevice(ABC):
    """Base class for Mock devices for testing purposes."""

    @abstractmethod
    def __init__(self: MockDevice, config: MockDeviceConfig | None = None) -> None:
        pass


@dataclass(frozen=True)
class MockDeviceConfig:
    """Configuration for LeMockDevice behavior and fault injection."""

    transfer_mode: TransferMode = TRANSFER_MODE_BULK
    operational_state: OperationalState = OPERATIONAL_STATE_NORMAL
    config_status_reason: ConfigStatusReason = CONFIG_STATUS_REASON_NONE
    fail_after: float = np.inf
    n_fails: float = np.inf
    empty_responses: bool = False
    drop_retransmit_once: bool = False
    reject_settings: bool = False
    reject_list_start: bool = False
    reject_list_complete: bool = False
    reject_scan_start: bool = False
    timeout_after_n_responses: int | None = None
    retransmit_unavailable: bool = False


class ScriptedTransport(Connection):
    """Minimal serial-like transport returning pre-built response bytes."""

    def __init__(self, data: bytes) -> None:
        self._buf = bytearray(data)

    @property
    def in_waiting(self) -> int:
        """Bytes available for reading."""
        return len(self._buf)

    def read(self, size: int) -> bytes:
        """Read up to *size* bytes from the buffer."""
        chunk = bytes(self._buf[:size])
        del self._buf[:size]
        return chunk

    def write(self, data: bytes) -> int:
        """Accept and discard written bytes."""
        return len(data)

    def close(self) -> None:
        """Close the transport (no-op)."""

    def reset_input_buffer(self) -> None:
        """Discard all buffered bytes."""
        self._buf.clear()


def list_mock_devices() -> list[str]:
    """List all available mock devices."""
    return [
        "mock_device",
        "mock_device_commissioning_idle",
        "mock_device_unconfigured",
        "mock_device_invalid_config",
        "mock_device_per_point",
        "mock_device_scan_should_fail",
        "mock_device_empty_responses",
    ]


def _mock_device_factory(config: DeviceConfiguration) -> LeMockDevice:
    """Create a ``LeMockDevice`` dispatching on ``amp_port`` sentinel strings.

    Sentinel values:
        ``"mock_device"`` — default mock (bulk transfer)
        ``"mock_device_commissioning_idle"`` — commissioning idle with no config fault
        ``"mock_device_unconfigured"`` — commissioning idle with missing config
        ``"mock_device_invalid_config"`` — commissioning idle with invalid config
        ``"mock_device_per_point"`` — per-point transfer mode
        ``"mock_device_scan_should_fail"`` — scan fails immediately
        ``"mock_device_empty_responses"`` — silently ignores writes, returns empty reads
    """
    port = config.amp_port
    overrides = (
        (
            "mock_device_commissioning_idle",
            MockDeviceConfig(operational_state=OPERATIONAL_STATE_COMMISSIONING_IDLE),
        ),
        (
            "mock_device_unconfigured",
            MockDeviceConfig(
                operational_state=OPERATIONAL_STATE_COMMISSIONING_IDLE,
                config_status_reason=CONFIG_STATUS_REASON_UNCONFIGURED,
            ),
        ),
        (
            "mock_device_invalid_config",
            MockDeviceConfig(
                operational_state=OPERATIONAL_STATE_COMMISSIONING_IDLE,
                config_status_reason=CONFIG_STATUS_REASON_INVALID_CONFIG,
            ),
        ),
        (
            "mock_device_per_point",
            MockDeviceConfig(transfer_mode=TRANSFER_MODE_PER_POINT),
        ),
        ("mock_device_scan_should_fail", MockDeviceConfig(fail_after=0)),
        ("mock_device_empty_responses", MockDeviceConfig(empty_responses=True)),
    )
    for sentinel, override in overrides:
        if sentinel in port:
            return LeMockDevice(override)
    return LeMockDevice()


class LeMockDevice(MockDevice):
    """Mock MimLink endpoint implementing the binary protocol over a serial-like API."""

    LI_MODULATION_FREQUENCY = 10000
    TIME_WINDOW = 100e-12
    MAX_LIST_LENGTH = 6000
    MAX_INTEGRATION_PERIODS = 10000
    RESULTS_CHUNK_SIZE = 20
    _MIN_ITEMS_FOR_DROP = 2

    def __init__(
        self,
        config: MockDeviceConfig | None = None,
    ) -> None:
        self._config = config or MockDeviceConfig()
        self._n_failures = 0
        self._n_scans = 0
        self._rng = np.random.default_rng()
        self._retransmit_drop_done = False
        self._responses_sent = 0

        self._list_length: int | None = None
        self._expected_total_floats: int | None = None
        self._integration_periods: int | None = None
        self._use_ema: bool = False
        self._scanning_list: list[float] = []
        self._is_scanning = False
        self._scan_start_time: float | None = None
        self._tx_buffer = bytearray()

        self._result_points: dict[int, Envelope] = {}
        self._result_chunks: dict[int, Envelope] = {}

        self._codec = EnvelopeCodec()
        self._rx_stream = RxFrameStream()

        self._dispatch: dict[int, Callable[[Envelope], None]] = {
            mt.SET_SETTINGS_REQUEST: self._handle_set_settings,
            mt.SET_LIST_START_REQUEST: self._handle_set_list_start,
            mt.LIST_CHUNK: self._handle_list_chunk,
            mt.START_SCAN_REQUEST: self._handle_start_scan,
            mt.GET_STATUS_REQUEST: self._handle_get_status,
            mt.GET_RESULTS_REQUEST: self._handle_get_results,
            mt.GET_DEVICE_INFO_REQUEST: self._handle_get_device_info,
            mt.RESULT_POINT_NAK: self._handle_result_point_nak,
            mt.RESULTS_CHUNK_NAK: self._handle_results_chunk_nak,
        }

    @property
    def in_waiting(self) -> int:
        """Bytes available for host reads."""
        return len(self._tx_buffer)

    def reset_input_buffer(self) -> None:
        """Discard queued outgoing bytes."""
        self._tx_buffer.clear()

    def close(self) -> None:
        """Close the mock device."""

    def write(self, data: bytes) -> int:
        """Handle bytes written by host endpoint."""
        if self._config.empty_responses:
            return len(data)
        for frame in self._rx_stream.push(data):
            try:
                env = self._codec.decode(frame)
            except FrameDecodeError:
                continue
            self._on_envelope(env)
        return len(data)

    def read(self, size: int) -> bytes:
        """Read queued bytes produced by device endpoint."""
        if self._config.empty_responses or size <= 0 or not self._tx_buffer:
            return b""
        n_to_read = min(size, len(self._tx_buffer))
        data = bytes(self._tx_buffer[:n_to_read])
        del self._tx_buffer[:n_to_read]
        return data

    def _queue_tx(self, env: Envelope) -> None:
        if (
            self._config.timeout_after_n_responses is not None
            and self._responses_sent >= self._config.timeout_after_n_responses
        ):
            return
        self._tx_buffer.extend(self._codec.encode(env))
        self._responses_sent += 1

    @property
    def _scanning_time(self) -> float:
        if self._list_length is None or self._integration_periods is None:
            return 0.0
        return (
            self._list_length * self._integration_periods / self.LI_MODULATION_FREQUENCY
        )

    def _scan_has_finished(self) -> bool:
        if not self._is_scanning:
            return True
        if self._scan_start_time is None:
            return True
        finished = time.time() - self._scan_start_time > self._scanning_time
        if finished:
            self._is_scanning = False
            self._scan_start_time = None
        return finished

    def _prepare_scan_data(self) -> None:
        if not self._scanning_list:
            self._result_points = {}
            self._result_chunks = {}
            return

        self._n_scans += 1
        should_fail = (
            self._n_scans > self._config.fail_after
            and self._n_failures < self._config.n_fails
        )
        if should_fail:
            self._n_failures += 1
            self._result_points = {}
            self._result_chunks = {}
            return

        times = np.array(self._scanning_list) * self.TIME_WINDOW
        xs = self._rng.random(len(self._scanning_list)) + 1.0
        ys = self._rng.random(len(self._scanning_list)) + 1.0

        self._result_points = self._build_point_cache(times, xs, ys)
        self._result_chunks = self._build_chunk_cache(times, xs, ys)

    def _build_point_cache(
        self, times: FloatArray, xs: FloatArray, ys: FloatArray
    ) -> dict[int, Envelope]:
        points: dict[int, Envelope] = {}
        for idx, (t, x, y) in enumerate(zip(times, xs, ys)):
            env = self._codec.build_envelope(mt.RESULT_POINT)
            p = env.result_point
            p.point_index = idx
            p.time = float(t)
            p.x = float(x)
            p.y = float(y)
            p.is_last = idx == len(times) - 1
            p.send_timestamp_us = 0
            points[idx] = env
        return points

    def _build_chunk_cache(
        self, times: FloatArray, xs: FloatArray, ys: FloatArray
    ) -> dict[int, Envelope]:
        chunks: dict[int, Envelope] = {}
        for chunk_idx, start in enumerate(
            range(0, len(times), self.RESULTS_CHUNK_SIZE)
        ):
            end = min(start + self.RESULTS_CHUNK_SIZE, len(times))
            env = self._codec.build_envelope(mt.RESULTS_CHUNK)
            c = env.results_chunk
            c.chunk_index = chunk_idx
            c.times.extend([float(v) for v in times[start:end]])
            c.x.extend([float(v) for v in xs[start:end]])
            c.y.extend([float(v) for v in ys[start:end]])
            c.is_last = end == len(times)
            chunks[chunk_idx] = env
        return chunks

    def _maybe_drop_one(
        self, envelopes: Sequence[Envelope], index_of: Callable[[Envelope], int]
    ) -> list[Envelope]:
        """Return envelopes, optionally dropping one item to test retransmit."""
        if (
            not self._config.drop_retransmit_once
            or self._retransmit_drop_done
            or len(envelopes) <= self._MIN_ITEMS_FOR_DROP
        ):
            return list(envelopes)
        self._retransmit_drop_done = True
        return [e for e in envelopes if index_of(e) != 1]

    def _send_per_point_stream(self) -> None:
        points = sorted(
            self._result_points.values(), key=lambda e: e.result_point.point_index
        )
        for env in self._maybe_drop_one(points, lambda e: e.result_point.point_index):
            self._queue_tx(env)

    def _send_bulk_results(self) -> None:
        chunks = sorted(
            self._result_chunks.values(), key=lambda e: e.results_chunk.chunk_index
        )
        for env in self._maybe_drop_one(chunks, lambda e: e.results_chunk.chunk_index):
            self._queue_tx(env)

    def _on_envelope(self, env: Envelope) -> None:
        handler = self._dispatch.get(env.type)
        if handler is not None:
            handler(env)

    @property
    def _normal_scan_blocked(self) -> bool:
        return self._config.operational_state in {
            OPERATIONAL_STATE_COMMISSIONING_IDLE,
            OPERATIONAL_STATE_COMMISSIONING_TRIM_ACTIVE,
        }

    def _handle_set_settings(self, env: Envelope) -> None:
        req = env.set_settings_request
        valid = (
            not self._config.reject_settings
            and not self._normal_scan_blocked
            and 1 <= req.list_length <= self.MAX_LIST_LENGTH
            and 1 <= req.integration_periods <= self.MAX_INTEGRATION_PERIODS
        )
        if valid:
            self._list_length = req.list_length
            self._integration_periods = req.integration_periods
            self._use_ema = bool(req.use_ema)
            self._scanning_list = []
            self._expected_total_floats = None
        resp = self._codec.build_envelope(mt.SET_SETTINGS_RESPONSE)
        resp.set_settings_response.success = valid
        self._queue_tx(resp)

    def _handle_set_list_start(self, env: Envelope) -> None:
        total = env.set_list_start_request.total_floats
        ready = (
            not self._config.reject_list_start
            and not self._normal_scan_blocked
            and not self._is_scanning
            and self._list_length is not None
            and 0 < total <= self.MAX_LIST_LENGTH
            and total == self._list_length
        )
        if ready:
            self._expected_total_floats = total
            self._scanning_list = []
        resp = self._codec.build_envelope(mt.SET_LIST_START_RESPONSE)
        resp.set_list_start_response.ready = ready
        self._queue_tx(resp)

    def _handle_list_chunk(self, env: Envelope) -> None:
        chunk = env.list_chunk
        self._scanning_list.extend(list(chunk.values))
        if chunk.is_last:
            resp = self._codec.build_envelope(mt.SET_LIST_COMPLETE_RESPONSE)
            resp.set_list_complete_response.success = (
                not self._config.reject_list_complete
            )
            resp.set_list_complete_response.floats_received = len(self._scanning_list)
            self._queue_tx(resp)

    def _handle_start_scan(self, _env: Envelope) -> None:
        settings_valid = (
            self._list_length is not None and self._integration_periods is not None
        )
        list_valid = len(self._scanning_list) > 0
        started = (
            not self._config.reject_scan_start
            and not self._normal_scan_blocked
            and settings_valid
            and list_valid
        )
        resp = self._codec.build_envelope(mt.START_SCAN_RESPONSE)
        r = resp.start_scan_response
        r.started = started
        r.error = (
            "" if started else "Settings/list missing or operational state blocked"
        )
        r.transfer_mode = self._config.transfer_mode
        self._queue_tx(resp)
        if not started:
            return
        self._is_scanning = True
        self._scan_start_time = time.time()
        self._prepare_scan_data()
        if self._config.transfer_mode == TRANSFER_MODE_PER_POINT:
            self._send_per_point_stream()

    def _handle_get_status(self, _env: Envelope) -> None:
        scan_ongoing = not self._scan_has_finished()
        resp = self._codec.build_envelope(mt.GET_STATUS_RESPONSE)
        r = resp.get_status_response
        r.scan_ongoing = scan_ongoing
        r.list_length = len(self._scanning_list)
        r.max_list_length = self.MAX_LIST_LENGTH
        r.modulation_frequency_hz = self.LI_MODULATION_FREQUENCY
        r.settings_valid = (
            self._list_length is not None and self._integration_periods is not None
        )
        r.list_valid = bool(self._scanning_list)
        r.operational_state = self._config.operational_state
        r.config_status_reason = self._config.config_status_reason
        self._queue_tx(resp)

    def _handle_get_results(self, _env: Envelope) -> None:
        self._send_bulk_results()

    def _handle_get_device_info(self, _env: Envelope) -> None:
        resp = self._codec.build_envelope(mt.GET_DEVICE_INFO_RESPONSE)
        r = resp.get_device_info_response
        r.serial_number = "M-9999"
        r.firmware_version = "v0.1.0"
        r.firmware_target = "le-2-3-0"
        r.bsp_name = "mock"
        r.build_type = "Release"
        r.transfer_mode = self._config.transfer_mode
        r.hardware_type = "mock"
        r.hardware_revision = 0
        r.operational_state = self._config.operational_state
        r.config_status_reason = self._config.config_status_reason
        self._queue_tx(resp)

    def _handle_result_point_nak(self, env: Envelope) -> None:
        point_idx = env.result_point_nak.point_index
        point_env = self._result_points.get(point_idx)
        resp = self._codec.build_envelope(mt.RESULT_POINT_RETRANSMIT)
        r = resp.result_point_retransmit
        r.point_index = point_idx
        if self._config.retransmit_unavailable or point_env is None:
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

    def _handle_results_chunk_nak(self, env: Envelope) -> None:
        chunk_idx = env.results_chunk_nak.chunk_index
        chunk_env = self._result_chunks.get(chunk_idx)
        resp = self._codec.build_envelope(mt.RESULTS_CHUNK_RETRANSMIT)
        r = resp.results_chunk_retransmit
        r.chunk_index = chunk_idx
        if self._config.retransmit_unavailable or chunk_env is None:
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
