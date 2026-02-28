from __future__ import annotations

import numpy as np
import pytest

from pyglaze.device.configuration import Interval, LeDeviceConfiguration
from pyglaze.device.mimlink_client import DeviceComError, MimLinkClient
from pyglaze.devtools.mock_device import (
    TRANSFER_MODE_BULK,
    TRANSFER_MODE_PER_POINT,
    MimLinkMockDevice,
)
from pyglaze.scanning.scanner import _compute_scanning_list


def _build(
    n_points: int = 100,
    fail_after: float = np.inf,
    *,
    transfer_mode: int = TRANSFER_MODE_BULK,
    drop_retransmit_once: bool = False,
) -> tuple[LeDeviceConfiguration, MimLinkClient]:
    config = LeDeviceConfiguration(
        amp_port="mock_device",
        use_ema=False,
        n_points=n_points,
        scan_intervals=[Interval(0.0, 1.0)],
        integration_periods=1,
    )
    backend = MimLinkMockDevice(
        fail_after=fail_after,
        transfer_mode=transfer_mode,
        drop_retransmit_once=drop_retransmit_once,
    )
    backend.reset_input_buffer()
    client = MimLinkClient(conn=backend, timeout=5.0)
    return config, client


def test_set_settings_and_upload_list() -> None:
    config, client = _build()
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    client.close()


def test_full_scan_bulk() -> None:
    config, client = _build()
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    times, Xs, Ys = client.start_scan(config.n_points, config._sweep_length_ms)
    assert len(times) == config.n_points
    assert len(Xs) == config.n_points
    assert len(Ys) == config.n_points
    client.close()


def test_full_scan_per_point() -> None:
    config, client = _build(transfer_mode=TRANSFER_MODE_PER_POINT)
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    times, Xs, Ys = client.start_scan(config.n_points, config._sweep_length_ms)
    assert len(times) == config.n_points
    assert len(Xs) == config.n_points
    assert len(Ys) == config.n_points
    client.close()


def test_get_device_info() -> None:
    config, client = _build()
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    info = client.get_device_info()
    assert info.serial_number == "M-9999"
    assert info.firmware_version == "v0.1.0"
    client.close()


def test_get_status() -> None:
    config, client = _build()
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    status = client.get_status()
    assert status.scan_ongoing is False
    assert status.list_length == config.n_points
    client.close()


def test_retransmit_missing_chunks() -> None:
    config, client = _build(transfer_mode=TRANSFER_MODE_BULK, drop_retransmit_once=True)
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    times, _Xs, _Ys = client.start_scan(config.n_points, config._sweep_length_ms)
    assert len(times) == config.n_points
    client.close()


def test_retransmit_missing_points() -> None:
    config, client = _build(
        transfer_mode=TRANSFER_MODE_PER_POINT, drop_retransmit_once=True
    )
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    times, _Xs, _Ys = client.start_scan(config.n_points, config._sweep_length_ms)
    assert len(times) == config.n_points
    client.close()


def test_scan_failure() -> None:
    config, client = _build(fail_after=0)
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    with pytest.raises(DeviceComError):
        client.start_scan(config.n_points, config._sweep_length_ms)
    client.close()


def test_ping() -> None:
    _, client = _build()
    nonce = client.ping(0xDEADBEEF)
    assert nonce == 0xDEADBEEF
    client.close()
