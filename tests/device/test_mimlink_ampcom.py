from __future__ import annotations

import pytest

from pyglaze.device.ampcom import DeviceComError
from pyglaze.device.configuration import Interval, LeDeviceConfiguration
from pyglaze.device.mimlink_ampcom import _MimLinkAmpCom
from pyglaze.mimlink.types import (
    ResultPoint,
    ResultPointRetransmit,
    ResultsChunk,
    ResultsChunkRetransmit,
)


class _FakeEndpoint:
    def __init__(self) -> None:
        self.point_naks: list[int] = []
        self.chunk_naks: list[int] = []

    def send_result_point_nak(self, point_index: int) -> int:
        self.point_naks.append(point_index)
        return 0

    def send_results_chunk_nak(self, chunk_index: int) -> int:
        self.chunk_naks.append(chunk_index)
        return 0


def _build_config(n_points: int) -> LeDeviceConfiguration:
    return LeDeviceConfiguration(
        amp_port="mock_device",
        use_ema=False,
        n_points=n_points,
        scan_intervals=[Interval(0.0, 1.0)],
        integration_periods=1,
        amp_timeout_seconds=1,
    )


def test_retransmit_missing_points_success() -> None:
    endpoint = _FakeEndpoint()
    amp = object.__new__(_MimLinkAmpCom)
    amp.config = _build_config(3)
    amp._result_points = [
        ResultPoint(point_index=0, time=0.0, x=1.0, y=2.0, is_last=False),
        ResultPoint(point_index=2, time=2.0, x=3.0, y=4.0, is_last=False),
    ]
    amp._endpoint = endpoint

    def _wait_for_response(timeout: float | None = None) -> ResultPointRetransmit:
        _ = timeout
        idx = endpoint.point_naks[-1]
        return ResultPointRetransmit(
            point_index=idx, available=True, time=1.0, x=1.0, y=1.0
        )

    amp._wait_for_response = _wait_for_response

    amp._retransmit_missing_points()

    assert endpoint.point_naks == [1]


def test_retransmit_missing_chunks_success() -> None:
    endpoint = _FakeEndpoint()
    amp = object.__new__(_MimLinkAmpCom)
    amp.config = _build_config(40)
    amp._result_chunks = [
        ResultsChunk(chunk_index=0, times=[0.0], x=[1.0], y=[2.0], is_last=False),
    ]
    amp._endpoint = endpoint

    def _wait_for_response(timeout: float | None = None) -> ResultsChunkRetransmit:
        _ = timeout
        idx = endpoint.chunk_naks[-1]
        return ResultsChunkRetransmit(
            chunk_index=idx,
            times=[1.0],
            x=[2.0],
            y=[3.0],
            is_last=True,
            available=True,
        )

    amp._wait_for_response = _wait_for_response

    amp._retransmit_missing_chunks()

    assert endpoint.chunk_naks == [1]


def test_retransmit_missing_points_raises_on_exhausted_retries() -> None:
    endpoint = _FakeEndpoint()
    amp = object.__new__(_MimLinkAmpCom)
    amp.config = _build_config(2)
    amp._result_points = [
        ResultPoint(point_index=0, time=0.0, x=1.0, y=2.0, is_last=False),
    ]
    amp._endpoint = endpoint

    def _wait_for_response(timeout: float | None = None) -> ResultPointRetransmit:
        _ = timeout
        idx = endpoint.point_naks[-1]
        return ResultPointRetransmit(
            point_index=idx, available=False, time=0.0, x=0.0, y=0.0
        )

    amp._wait_for_response = _wait_for_response

    with pytest.raises(DeviceComError):
        amp._retransmit_missing_points()
