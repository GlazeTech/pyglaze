from __future__ import annotations

import pytest
from serial import serialutil

from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.device.configuration import Interval, LeDeviceConfiguration
from pyglaze.device.mimlink_client import DeviceComError, MimLinkClient
from pyglaze.devtools.mock_device import (
    TRANSFER_MODE_BULK,
    TRANSFER_MODE_PER_POINT,
    MimLinkMockDevice,
)
from pyglaze.scanning import GlazeClient
from pyglaze.scanning.scanner import Scanner, _compute_scanning_list


def test_mimlink_bulk_scan_returns_waveform(
    le_device_config: LeDeviceConfiguration,
) -> None:
    scanner = Scanner(config=le_device_config)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)
    assert len(scan.time) == le_device_config.n_points


def test_mimlink_per_point_scan_returns_waveform(
    le_device_config: LeDeviceConfiguration,
) -> None:
    le_device_config.amp_port = "mock_device_per_point"
    scanner = Scanner(config=le_device_config)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)
    assert len(scan.time) == le_device_config.n_points


def test_mimlink_bulk_retransmit_chunk_path(
    le_device_config: LeDeviceConfiguration,
) -> None:
    """Protocol-level test: verify bulk retransmit via MimLinkClient + MimLinkMockDevice."""
    backend = MimLinkMockDevice(
        transfer_mode=TRANSFER_MODE_BULK, drop_retransmit_once=True
    )
    backend.reset_input_buffer()
    client = MimLinkClient(conn=backend, timeout=5.0)
    scanning_list = _compute_scanning_list(
        le_device_config.n_points, le_device_config.scan_intervals
    )
    client.set_settings(
        le_device_config.n_points,
        le_device_config.integration_periods,
        use_ema=le_device_config.use_ema,
    )
    client.upload_list(scanning_list)
    times, _Xs, _Ys = client.start_scan(
        le_device_config.n_points, le_device_config._sweep_length_ms
    )
    assert len(times) == le_device_config.n_points
    client.close()


def test_mimlink_per_point_retransmit_path(
    le_device_config: LeDeviceConfiguration,
) -> None:
    """Protocol-level test: verify per-point retransmit via MimLinkClient + MimLinkMockDevice."""
    backend = MimLinkMockDevice(
        transfer_mode=TRANSFER_MODE_PER_POINT, drop_retransmit_once=True
    )
    backend.reset_input_buffer()
    client = MimLinkClient(conn=backend, timeout=5.0)
    scanning_list = _compute_scanning_list(
        le_device_config.n_points, le_device_config.scan_intervals
    )
    client.set_settings(
        le_device_config.n_points,
        le_device_config.integration_periods,
        use_ema=le_device_config.use_ema,
    )
    client.upload_list(scanning_list)
    times, _Xs, _Ys = client.start_scan(
        le_device_config.n_points, le_device_config._sweep_length_ms
    )
    assert len(times) == le_device_config.n_points
    client.close()


def test_mimlink_scanner_update_config(
    le_device_config: LeDeviceConfiguration,
) -> None:
    scanner = Scanner(config=le_device_config)
    new_conf = LeDeviceConfiguration(
        amp_port="mock_device",
        use_ema=False,
        n_points=50,
        scan_intervals=[Interval(0.0, 0.5)],
        integration_periods=2,
    )
    scanner.update_config(new_conf)
    assert scanner.config == new_conf


def test_mimlink_client_read(
    le_device_config: LeDeviceConfiguration,
) -> None:
    client = GlazeClient(config=le_device_config)
    with client as c:
        pulses = c.read(n_pulses=2)
    assert len(pulses) == 2


def test_mimlink_client_scan_failure(
    le_device_config: LeDeviceConfiguration,
) -> None:
    le_device_config.amp_port = "mock_device_scan_should_fail"
    with (
        pytest.raises((serialutil.SerialException, DeviceComError)),
        GlazeClient(config=le_device_config) as client,
    ):
        client.read(n_pulses=1)


def test_mimlink_device_info(
    le_device_config: LeDeviceConfiguration,
) -> None:
    scanner = Scanner(config=le_device_config)
    info = scanner.get_device_info()
    assert info.serial_number == "M-9999"
    assert info.firmware_version == "v0.1.0"


