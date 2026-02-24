from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TypedDict, cast

import numpy as np

from pyglaze.device.configuration import DeviceConfiguration
from pyglaze.mimlink import MessageType, ProtocolEndpoint
from pyglaze.mimlink.types import (
    ResultPoint,
    ResultPointNak,
    ResultsChunk,
    ResultsChunkNak,
    TransferMode,
)


class MockDevice(ABC):
    """Base class for Mock devices for testing purposes."""

    @abstractmethod
    def __init__(
        self: MockDevice,
        fail_after: float = np.inf,
        n_fails: float = np.inf,
        *,
        empty_responses: bool = False,
        instant_response: bool = False,
    ) -> None:
        pass


class MimLinkMockDevice(MockDevice):
    """Mock MimLink endpoint implementing the binary protocol over a serial-like API."""

    LI_MODULATION_FREQUENCY = 10000
    MAX_LIST_LENGTH = 6000
    RESULTS_CHUNK_SIZE = 20
    _MIN_ITEMS_FOR_DROP = 2

    def __init__(
        self: MimLinkMockDevice,
        fail_after: float = np.inf,
        n_fails: float = np.inf,
        *,
        empty_responses: bool = False,
        instant_response: bool = False,
        transfer_mode: int = TransferMode.BULK,
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
        self._result_points: dict[int, ResultPoint] = {}
        self._result_chunks: dict[int, ResultsChunk] = {}
        self._endpoint = ProtocolEndpoint(
            on_envelope=self._on_envelope,
            on_send=self._queue_tx,
        )

    @property
    def in_waiting(self: MimLinkMockDevice) -> int:
        """Bytes available for host reads."""
        return len(self._tx_buffer)

    def reset_input_buffer(self: MimLinkMockDevice) -> None:
        """Discard queued outgoing bytes."""
        self._tx_buffer.clear()

    def close(self: MimLinkMockDevice) -> None:
        """Close the mock device."""

    def write(self: MimLinkMockDevice, input_bytes: bytes) -> None:
        """Handle bytes written by host endpoint."""
        if self.empty_responses:
            return
        # Protocol detection sends a single ASCII status byte for legacy devices.
        # MimLink silently ignores unframed bytes.
        if input_bytes == b"H":
            return
        self._endpoint.on_rx_bytes(input_bytes)

    def read(self: MimLinkMockDevice, size: int) -> bytes:
        """Read queued bytes produced by device endpoint."""
        if self.empty_responses or size <= 0 or not self._tx_buffer:
            return b""
        n_to_read = min(size, len(self._tx_buffer))
        data = bytes(self._tx_buffer[:n_to_read])
        del self._tx_buffer[:n_to_read]
        return data

    def read_until(self: MimLinkMockDevice, expected: bytes = b"\x00") -> bytes:
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

    def _queue_tx(self: MimLinkMockDevice, data: bytes) -> int:
        self._tx_buffer.extend(data)
        return 0

    @property
    def _scanning_time(self: MimLinkMockDevice) -> float:
        if self.instant_response:
            return 0.0
        if self.list_length is None or self.integration_periods is None:
            return 0.0
        return self.list_length * self.integration_periods / self.LI_MODULATION_FREQUENCY

    def _scan_has_finished(self: MimLinkMockDevice) -> bool:
        if not self.is_scanning:
            return True
        if self._scan_start_time is None:
            return True
        finished = time.time() - self._scan_start_time > self._scanning_time
        if finished:
            self.is_scanning = False
            self._scan_start_time = None
        return finished

    def _prepare_scan_data(self: MimLinkMockDevice) -> None:
        if not self.scanning_list:
            self._result_points = {}
            self._result_chunks = {}
            return

        self.n_scans += 1
        should_fail = self.n_scans > self.fail_after and self.n_failures < self.fails_wanted
        if should_fail:
            self.n_failures += 1
            self._result_points = {}
            self._result_chunks = {}
            return

        times = np.array(self.scanning_list) * 100e-12
        xs = self.rng.random(len(self.scanning_list)) + 1.0
        ys = self.rng.random(len(self.scanning_list)) + 1.0

        self._result_points = {
            idx: ResultPoint(
                point_index=idx,
                time=float(t),
                x=float(x),
                y=float(y),
                is_last=idx == len(times) - 1,
                send_timestamp_us=0,
            )
            for idx, (t, x, y) in enumerate(zip(times, xs, ys))
        }

        self._result_chunks = {}
        for chunk_idx, start in enumerate(range(0, len(times), self.RESULTS_CHUNK_SIZE)):
            end = min(start + self.RESULTS_CHUNK_SIZE, len(times))
            self._result_chunks[chunk_idx] = ResultsChunk(
                chunk_index=chunk_idx,
                times=[float(v) for v in times[start:end]],
                x=[float(v) for v in xs[start:end]],
                y=[float(v) for v in ys[start:end]],
                is_last=end == len(times),
            )

    def _send_per_point_stream(self: MimLinkMockDevice) -> None:
        points = sorted(self._result_points.values(), key=lambda p: p.point_index)
        if not points:
            return
        drop_idx = (
            1 if self.drop_point_once and len(points) > self._MIN_ITEMS_FOR_DROP else -1
        )
        for point in points:
            if point.point_index == drop_idx and not self._point_drop_done:
                self._point_drop_done = True
                continue
            self._endpoint.send_result_point(
                point_index=point.point_index,
                time=point.time,
                x=point.x,
                y=point.y,
                is_last=point.is_last,
            )

    def _send_bulk_results(self: MimLinkMockDevice) -> None:
        chunks = sorted(self._result_chunks.values(), key=lambda c: c.chunk_index)
        if not chunks:
            return
        drop_idx = (
            1 if self.drop_chunk_once and len(chunks) > self._MIN_ITEMS_FOR_DROP else -1
        )
        for chunk in chunks:
            if chunk.chunk_index == drop_idx and not self._chunk_drop_done:
                self._chunk_drop_done = True
                continue
            self._endpoint.send_results_chunk(
                chunk_index=chunk.chunk_index,
                times=chunk.times,
                x=chunk.x,
                y=chunk.y,
                is_last=chunk.is_last,
            )

    def _on_envelope(
        self: MimLinkMockDevice, env_type: int, _seq: int, payload: object
    ) -> None:
        if env_type == MessageType.SET_SETTINGS_REQUEST:
            settings = cast("_SettingsRequestPayload", payload)
            self.list_length = settings["list_length"]
            self.integration_periods = settings["integration_periods"]
            self.use_ema = settings["use_ema"]
            self._endpoint.send_set_settings_response(success=True)
            return

        if env_type == MessageType.SET_LIST_START_REQUEST:
            request = cast("_SetListStartRequestPayload", payload)
            self.expected_total_floats = request["total_floats"]
            self.scanning_list = []
            self._endpoint.send_set_list_start_response(ready=True)
            return

        if env_type == MessageType.LIST_CHUNK:
            chunk = cast("_ListChunkPayload", payload)
            values = chunk["values"]
            self.scanning_list.extend(values)
            if chunk["is_last"]:
                self._endpoint.send_set_list_complete_response(
                    success=True,
                    floats_received=len(self.scanning_list),
                )
            return

        if env_type == MessageType.START_SCAN_REQUEST:
            settings_valid = self.list_length is not None and self.integration_periods is not None
            list_valid = len(self.scanning_list) > 0
            started = settings_valid and list_valid
            self._endpoint.send_start_scan_response(
                started=started,
                error=None if started else "Settings/list missing",
                transfer_mode=self.transfer_mode,
            )
            if not started:
                return
            self.is_scanning = True
            self._scan_start_time = time.time()
            self._prepare_scan_data()
            if self.transfer_mode == TransferMode.PER_POINT:
                self._send_per_point_stream()
            return

        if env_type == MessageType.GET_STATUS_REQUEST:
            scan_ongoing = not self._scan_has_finished()
            self._endpoint.send_get_status_response(
                scan_ongoing=scan_ongoing,
                list_length=len(self.scanning_list),
                max_list_length=self.MAX_LIST_LENGTH,
                modulation_frequency_hz=self.LI_MODULATION_FREQUENCY,
                settings_valid=self.list_length is not None and self.integration_periods is not None,
                list_valid=bool(self.scanning_list),
            )
            return

        if env_type == MessageType.GET_RESULTS_REQUEST:
            self._send_bulk_results()
            return

        if env_type == MessageType.GET_SERIAL_REQUEST:
            self._endpoint.send_get_serial_response(serial="M-9999")
            return

        if env_type == MessageType.GET_VERSION_REQUEST:
            self._endpoint.send_get_version_response(version="v0.1.0")
            return

        if env_type == MessageType.GET_CAPABILITIES_REQUEST:
            self._endpoint.send_get_capabilities_response(
                bsp_name="mock",
                build_type="Release",
                transfer_mode=self.transfer_mode,
            )
            return

        if env_type == MessageType.RESULT_POINT_NAK:
            point_nak = cast("ResultPointNak", payload)
            point = self._result_points.get(point_nak.point_index)
            if point is None:
                self._endpoint.send_result_point_retransmit(
                    point_index=point_nak.point_index,
                    available=False,
                    time=0.0,
                    x=0.0,
                    y=0.0,
                )
                return
            self._endpoint.send_result_point_retransmit(
                point_index=point.point_index,
                available=True,
                time=point.time,
                x=point.x,
                y=point.y,
            )
            return

        if env_type == MessageType.RESULTS_CHUNK_NAK:
            chunk_nak = cast("ResultsChunkNak", payload)
            chunk = self._result_chunks.get(chunk_nak.chunk_index)
            if chunk is None:
                self._endpoint.send_results_chunk_retransmit(
                    chunk_index=chunk_nak.chunk_index,
                    times=[],
                    x=[],
                    y=[],
                    is_last=False,
                    available=False,
                )
                return
            self._endpoint.send_results_chunk_retransmit(
                chunk_index=chunk.chunk_index,
                times=chunk.times,
                x=chunk.x,
                y=chunk.y,
                is_last=chunk.is_last,
                available=True,
            )
            return


class _SettingsRequestPayload(TypedDict):
    list_length: int
    integration_periods: int
    use_ema: bool


class _SetListStartRequestPayload(TypedDict):
    total_floats: int


class _ListChunkPayload(TypedDict):
    chunk_index: int
    values: list[float]
    is_last: bool


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


def _mock_device_factory(config: DeviceConfiguration) -> MimLinkMockDevice:
    if config.amp_port == "mock_mimlink_device":
        return MimLinkMockDevice(transfer_mode=TransferMode.BULK)
    if config.amp_port == "mock_mimlink_per_point":
        return MimLinkMockDevice(transfer_mode=TransferMode.PER_POINT)
    if config.amp_port == "mock_mimlink_drop_chunk":
        return MimLinkMockDevice(transfer_mode=TransferMode.BULK, drop_chunk_once=True)
    if config.amp_port == "mock_mimlink_drop_point":
        return MimLinkMockDevice(transfer_mode=TransferMode.PER_POINT, drop_point_once=True)
    if config.amp_port == "mock_mimlink_scan_should_fail":
        return MimLinkMockDevice(fail_after=0, transfer_mode=TransferMode.BULK)
    if config.amp_port == "mock_mimlink_fail_first_scan":
        return MimLinkMockDevice(
            fail_after=0,
            n_fails=1,
            transfer_mode=TransferMode.BULK,
        )

    msg = f"Unknown mock device requested: {config.amp_port}. Valid options are: {list_mock_devices()}"
    raise ValueError(msg)
