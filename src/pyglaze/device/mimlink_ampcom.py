from __future__ import annotations

import contextlib
import math
import time
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

import numpy as np
import serial

from mimlink import MessageType, ProtocolEndpoint
from mimlink.types import (
    ListCompleteResponse,
    ListStartResponse,
    ResultsChunk,
    ResultsChunkRetransmit,
    ScanResponse,
    SerialResponse,
    SettingsResponse,
    StatusResponse,
    VersionResponse,
)

from pyglaze.device.ampcom import DeviceComError, _points_per_interval
from pyglaze.device.configuration import Interval, LeDeviceConfiguration


@dataclass
class _MimLinkAmpCom:
    config: LeDeviceConfiguration

    _ser: serial.Serial = field(init=False, repr=False)
    _endpoint: ProtocolEndpoint = field(init=False, repr=False)
    _response: Any = field(init=False, default=None, repr=False)
    _result_chunks: list[ResultsChunk] = field(
        init=False, default_factory=list, repr=False
    )
    _results_complete: bool = field(init=False, default=False, repr=False)

    def __post_init__(self: _MimLinkAmpCom) -> None:
        self._ser = serial.serial_for_url(
            url=self.config.amp_port,
            baudrate=self.config.amp_baudrate,
            timeout=self.config.amp_timeout_seconds,
        )
        self._ser.reset_input_buffer()
        self._endpoint = ProtocolEndpoint(
            on_envelope=self._on_envelope,
            on_send=self._on_send,
        )

    def __del__(self: _MimLinkAmpCom) -> None:
        self.disconnect()

    def _on_send(self: _MimLinkAmpCom, data: bytes) -> int:
        self._ser.write(data)
        return 0

    def _on_envelope(
        self: _MimLinkAmpCom, env_type: int, seq: int, payload: Any
    ) -> None:
        if env_type == MessageType.RESULTS_CHUNK:
            self._result_chunks.append(payload)
            if payload.is_last:
                self._results_complete = True
        elif env_type == MessageType.RESULTS_CHUNK_RETRANSMIT:
            if payload.available:
                self._result_chunks.append(ResultsChunk(
                    chunk_index=payload.chunk_index,
                    times=payload.times,
                    x=payload.x,
                    y=payload.y,
                    is_last=payload.is_last,
                ))
            self._response = payload
        else:
            self._response = payload

    def _pump_until(
        self: _MimLinkAmpCom,
        predicate: Any,
        timeout: float | None = None,
    ) -> None:
        """Read serial bytes and feed to endpoint until predicate() is True."""
        if timeout is None:
            timeout = self.config.amp_timeout_seconds or 5.0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            available = self._ser.in_waiting
            if available > 0:
                data = self._ser.read(available)
            else:
                data = self._ser.read(1)
                if not data:
                    continue
            self._endpoint.on_rx_bytes(data)
            if predicate():
                return
        msg = "Timeout waiting for device response"
        raise DeviceComError(msg)

    def _wait_for_response(
        self: _MimLinkAmpCom, timeout: float | None = None
    ) -> Any:
        self._response = None
        self._pump_until(lambda: self._response is not None, timeout)
        return self._response

    @cached_property
    def scanning_points(self: _MimLinkAmpCom) -> int:
        return self.config.n_points

    @cached_property
    def scanning_list(self: _MimLinkAmpCom) -> list[float]:
        scanning_list: list[float] = []
        for interval, n_points in zip(
            self._intervals,
            _points_per_interval(self.scanning_points, self._intervals),
        ):
            scanning_list.extend(
                np.linspace(
                    interval.lower,
                    interval.upper,
                    n_points,
                    endpoint=len(self._intervals) == 1,
                ),
            )
        return scanning_list

    @cached_property
    def _intervals(self: _MimLinkAmpCom) -> list[Interval]:
        return self.config.scan_intervals or [Interval(lower=0.0, upper=1.0)]

    def write_all(self: _MimLinkAmpCom) -> None:
        self.write_settings()
        self.write_list()

    def write_settings(self: _MimLinkAmpCom) -> None:
        self._endpoint.send_set_settings(
            list_length=self.scanning_points,
            integration_periods=self.config.integration_periods,
            use_ema=self.config.use_ema,
        )
        resp = self._wait_for_response()
        if not isinstance(resp, SettingsResponse) or not resp.success:
            msg = f"Failed to set settings: {resp}"
            raise DeviceComError(msg)

    def write_list(self: _MimLinkAmpCom) -> None:
        self._endpoint.send_set_list_start(len(self.scanning_list))
        resp = self._wait_for_response()
        if not isinstance(resp, ListStartResponse) or not resp.ready:
            msg = f"Failed to start list upload: {resp}"
            raise DeviceComError(msg)

        chunk_size = 50
        total = len(self.scanning_list)
        total_chunks = (total + chunk_size - 1) // chunk_size
        for i in range(total_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, total)
            chunk = self.scanning_list[start:end]
            is_last = i == total_chunks - 1
            self._endpoint.send_list_chunk(i, chunk, is_last)

        resp = self._wait_for_response()
        if not isinstance(resp, ListCompleteResponse) or not resp.success:
            msg = f"Failed to upload list: {resp}"
            raise DeviceComError(msg)

    def start_scan(
        self: _MimLinkAmpCom,
    ) -> tuple[str, np.ndarray, np.ndarray, np.ndarray]:
        self._result_chunks.clear()
        self._results_complete = False

        self._endpoint.send_start_scan()
        resp = self._wait_for_response()
        if not isinstance(resp, ScanResponse) or not resp.started:
            msg = f"Failed to start scan: {resp}"
            raise DeviceComError(msg)

        self._await_scan_complete()

        self._endpoint.send_get_results()
        try:
            self._pump_until(lambda: self._results_complete, timeout=10.0)
        except DeviceComError:
            if not self._result_chunks:
                raise

        self._retransmit_missing_chunks()

        self._result_chunks.sort(key=lambda c: c.chunk_index)
        times = np.concatenate([np.array(c.times) for c in self._result_chunks])
        Xs = np.concatenate([np.array(c.x) for c in self._result_chunks])
        Ys = np.concatenate([np.array(c.y) for c in self._result_chunks])

        return "G", times, Xs, Ys

    _MAX_RETRANSMIT_ATTEMPTS: int = 3
    _RESULTS_CHUNK_SIZE: int = 20

    def _retransmit_missing_chunks(self: _MimLinkAmpCom) -> None:
        """NAK and re-request any chunks missing from the bulk transfer."""
        expected_count = math.ceil(self.scanning_points / self._RESULTS_CHUNK_SIZE)
        received = {c.chunk_index for c in self._result_chunks}
        missing = set(range(expected_count)) - received
        if not missing:
            return

        for idx in sorted(missing):
            for attempt in range(self._MAX_RETRANSMIT_ATTEMPTS):
                self._endpoint.send_results_chunk_nak(idx)
                resp = self._wait_for_response(timeout=5.0)
                if isinstance(resp, ResultsChunkRetransmit) and resp.available:
                    break
            else:
                msg = f"Chunk {idx} unavailable after {self._MAX_RETRANSMIT_ATTEMPTS} attempts"
                raise DeviceComError(msg)

    def _await_scan_complete(self: _MimLinkAmpCom) -> None:
        """Wait for scan to complete by polling device status."""
        time.sleep(self.config._sweep_length_ms * 1e-3)  # noqa: SLF001
        self._endpoint.send_get_status()
        resp = self._wait_for_response()
        while isinstance(resp, StatusResponse) and resp.scan_ongoing:
            time.sleep(self.config._sweep_length_ms * 1e-3 * 0.01)  # noqa: SLF001
            self._endpoint.send_get_status()
            resp = self._wait_for_response()

    def get_serial_number(self: _MimLinkAmpCom) -> str:
        self._endpoint.send_get_serial()
        resp = self._wait_for_response()
        if not isinstance(resp, SerialResponse):
            msg = f"Failed to get serial number: {resp}"
            raise DeviceComError(msg)
        return resp.serial

    def get_firmware_version(self: _MimLinkAmpCom) -> str:
        self._endpoint.send_get_version()
        resp = self._wait_for_response()
        if not isinstance(resp, VersionResponse):
            msg = f"Failed to get firmware version: {resp}"
            raise DeviceComError(msg)
        return resp.version

    def disconnect(self: _MimLinkAmpCom) -> None:
        with contextlib.suppress(AttributeError):
            self._endpoint.destroy()
        with contextlib.suppress(AttributeError):
            self._ser.close()
