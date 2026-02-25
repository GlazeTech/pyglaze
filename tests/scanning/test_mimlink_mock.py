from __future__ import annotations

import pytest
from serial import serialutil

from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.device.ampcom import DeviceComError
from pyglaze.device.configuration import Interval, ScannerConfiguration
from pyglaze.device.transport import ConnectionInfo
from pyglaze.scanning import GlazeClient
from pyglaze.scanning.scanner import Scanner


def test_mimlink_bulk_scan_returns_waveform(
    mimlink_device_config: tuple[ConnectionInfo, ScannerConfiguration],
) -> None:
    connection, config = mimlink_device_config
    scanner = Scanner(connection, config)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)
    assert len(scan.time) == config.n_points


def test_mimlink_per_point_scan_returns_waveform(
    mimlink_device_config: tuple[ConnectionInfo, ScannerConfiguration],
) -> None:
    connection, config = mimlink_device_config
    connection = ConnectionInfo("mock_mimlink_per_point")
    scanner = Scanner(connection, config)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)
    assert len(scan.time) == config.n_points


def test_mimlink_bulk_retransmit_chunk_path(
    mimlink_device_config: tuple[ConnectionInfo, ScannerConfiguration],
) -> None:
    _, config = mimlink_device_config
    connection = ConnectionInfo("mock_mimlink_drop_chunk")
    scanner = Scanner(connection, config)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)
    assert len(scan.time) == config.n_points


def test_mimlink_per_point_retransmit_path(
    mimlink_device_config: tuple[ConnectionInfo, ScannerConfiguration],
) -> None:
    _, config = mimlink_device_config
    connection = ConnectionInfo("mock_mimlink_drop_point")
    scanner = Scanner(connection, config)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)
    assert len(scan.time) == config.n_points


def test_mimlink_scanner_update_config(
    mimlink_device_config: tuple[ConnectionInfo, ScannerConfiguration],
) -> None:
    connection, config = mimlink_device_config
    scanner = Scanner(connection, config)
    new_conf = ScannerConfiguration(
        use_ema=False,
        n_points=50,
        scan_intervals=[Interval(0.0, 0.5)],
        integration_periods=2,
    )
    scanner.update_config(new_conf)
    assert scanner.config == new_conf


def test_mimlink_client_read(
    mimlink_device_config: tuple[ConnectionInfo, ScannerConfiguration],
) -> None:
    connection, config = mimlink_device_config
    client = GlazeClient(connection, config)
    with client as c:
        pulses = c.read(n_pulses=2)
    assert len(pulses) == 2


def test_mimlink_client_scan_failure(
    mimlink_device_config: tuple[ConnectionInfo, ScannerConfiguration],
) -> None:
    _, config = mimlink_device_config
    connection = ConnectionInfo("mock_mimlink_scan_should_fail")
    with (
        pytest.raises((serialutil.SerialException, DeviceComError)),
        GlazeClient(connection, config) as client,
    ):
        client.read(n_pulses=1)


def test_mimlink_device_info(
    mimlink_device_config: tuple[ConnectionInfo, ScannerConfiguration],
) -> None:
    connection, config = mimlink_device_config
    scanner = Scanner(connection, config)
    info = scanner.get_device_info()
    assert info.serial_number == "M-9999"
    assert info.firmware_version == "v0.1.0"


def test_mimlink_ping(
    mimlink_device_config: tuple[ConnectionInfo, ScannerConfiguration],
) -> None:
    connection, config = mimlink_device_config
    scanner = Scanner(connection, config)
    result = scanner.ping()
    assert result.success is True
    assert result.round_trip_us > 0
