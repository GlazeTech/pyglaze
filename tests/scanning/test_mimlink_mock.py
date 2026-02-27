from __future__ import annotations

import pytest
from serial import serialutil

from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.device.configuration import Interval, ScannerConfiguration
from pyglaze.device.mimlink_client import DeviceComError
from pyglaze.devtools.mock_device import (
    TRANSFER_MODE_BULK,
    TRANSFER_MODE_PER_POINT,
    mock_transport,
)
from pyglaze.scanning import GlazeClient
from pyglaze.scanning.scanner import Scanner


def test_mimlink_bulk_scan_returns_waveform(
    scanner_config: ScannerConfiguration,
) -> None:
    transport = mock_transport(transfer_mode=TRANSFER_MODE_BULK)
    scanner = Scanner(config=scanner_config, transport=transport)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)
    assert len(scan.time) == scanner_config.n_points


def test_mimlink_per_point_scan_returns_waveform(
    scanner_config: ScannerConfiguration,
) -> None:
    transport = mock_transport(transfer_mode=TRANSFER_MODE_PER_POINT)
    scanner = Scanner(config=scanner_config, transport=transport)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)
    assert len(scan.time) == scanner_config.n_points


def test_mimlink_bulk_retransmit_chunk_path(
    scanner_config: ScannerConfiguration,
) -> None:
    transport = mock_transport(transfer_mode=TRANSFER_MODE_BULK, drop_chunk_once=True)
    scanner = Scanner(config=scanner_config, transport=transport)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)
    assert len(scan.time) == scanner_config.n_points


def test_mimlink_per_point_retransmit_path(
    scanner_config: ScannerConfiguration,
) -> None:
    transport = mock_transport(
        transfer_mode=TRANSFER_MODE_PER_POINT, drop_point_once=True
    )
    scanner = Scanner(config=scanner_config, transport=transport)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)
    assert len(scan.time) == scanner_config.n_points


def test_mimlink_scanner_update_config(
    scanner_config: ScannerConfiguration,
) -> None:
    transport = mock_transport()
    scanner = Scanner(config=scanner_config, transport=transport)
    new_conf = ScannerConfiguration(
        use_ema=False,
        n_points=50,
        scan_intervals=[Interval(0.0, 0.5)],
        integration_periods=2,
    )
    scanner.update_config(new_conf)
    assert scanner.config == new_conf


def test_mimlink_client_read(
    scanner_config: ScannerConfiguration,
) -> None:
    transport = mock_transport()
    client = GlazeClient(transport=transport, config=scanner_config)
    with client as c:
        pulses = c.read(n_pulses=2)
    assert len(pulses) == 2


def test_mimlink_client_scan_failure(
    scanner_config: ScannerConfiguration,
) -> None:
    transport = mock_transport(fail_after=0)
    with (
        pytest.raises((serialutil.SerialException, DeviceComError)),
        GlazeClient(transport=transport, config=scanner_config) as client,
    ):
        client.read(n_pulses=1)


def test_mimlink_device_info(
    scanner_config: ScannerConfiguration,
) -> None:
    transport = mock_transport()
    scanner = Scanner(config=scanner_config, transport=transport)
    info = scanner.get_device_info()
    assert info.serial_number == "M-9999"
    assert info.firmware_version == "v0.1.0"


def test_mimlink_ping(
    scanner_config: ScannerConfiguration,
) -> None:
    transport = mock_transport()
    scanner = Scanner(config=scanner_config, transport=transport)
    result = scanner.ping()
    assert result.success is True
    assert result.round_trip_us > 0
