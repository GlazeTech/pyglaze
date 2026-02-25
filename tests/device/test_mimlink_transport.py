from __future__ import annotations

import pytest

from pyglaze.device.ampcom import DeviceComError
from pyglaze.device.configuration import Interval, LeDeviceConfiguration
from pyglaze.device.mimlink_transport import _compute_scanning_list, open_client


def _build_config(
    port: str = "mock_mimlink_device", n_points: int = 100
) -> LeDeviceConfiguration:
    return LeDeviceConfiguration(
        amp_port=port,
        use_ema=False,
        n_points=n_points,
        scan_intervals=[Interval(0.0, 1.0)],
        integration_periods=1,
        amp_timeout_seconds=7,
    )


def test_set_settings_and_upload_list() -> None:
    config = _build_config()
    transport = open_client(config)
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    transport.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    transport.upload_list(scanning_list)
    transport.close()


def test_full_scan_bulk() -> None:
    config = _build_config()
    transport = open_client(config)
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    transport.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    transport.upload_list(scanning_list)
    times, Xs, Ys = transport.start_scan(config.n_points, config._sweep_length_ms)
    assert len(times) == config.n_points
    assert len(Xs) == config.n_points
    assert len(Ys) == config.n_points
    transport.close()


def test_full_scan_per_point() -> None:
    config = _build_config(port="mock_mimlink_per_point")
    transport = open_client(config)
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    transport.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    transport.upload_list(scanning_list)
    times, Xs, Ys = transport.start_scan(config.n_points, config._sweep_length_ms)
    assert len(times) == config.n_points
    assert len(Xs) == config.n_points
    assert len(Ys) == config.n_points
    transport.close()


def test_get_device_info() -> None:
    config = _build_config()
    transport = open_client(config)
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    transport.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    transport.upload_list(scanning_list)
    info = transport.get_device_info()
    assert info.serial_number == "M-9999"
    assert info.firmware_version == "v0.1.0"
    transport.close()


def test_get_status() -> None:
    config = _build_config()
    transport = open_client(config)
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    transport.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    transport.upload_list(scanning_list)
    status = transport.get_status()
    assert status.scan_ongoing is False
    assert status.list_length == config.n_points
    transport.close()


def test_retransmit_missing_chunks() -> None:
    config = _build_config(port="mock_mimlink_drop_chunk")
    transport = open_client(config)
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    transport.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    transport.upload_list(scanning_list)
    times, _Xs, _Ys = transport.start_scan(config.n_points, config._sweep_length_ms)
    assert len(times) == config.n_points
    transport.close()


def test_retransmit_missing_points() -> None:
    config = _build_config(port="mock_mimlink_drop_point")
    transport = open_client(config)
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    transport.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    transport.upload_list(scanning_list)
    times, _Xs, _Ys = transport.start_scan(config.n_points, config._sweep_length_ms)
    assert len(times) == config.n_points
    transport.close()


def test_scan_failure() -> None:
    config = _build_config(port="mock_mimlink_scan_should_fail")
    transport = open_client(config)
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    transport.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    transport.upload_list(scanning_list)
    with pytest.raises(DeviceComError):
        transport.start_scan(config.n_points, config._sweep_length_ms)
    transport.close()


def test_ping() -> None:
    config = _build_config()
    transport = open_client(config)
    nonce = transport.ping(0xDEADBEEF)
    assert nonce == 0xDEADBEEF
    transport.close()
