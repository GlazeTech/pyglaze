from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

import pytest
from serial import serialutil

from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.device.ampcom import DeviceComError
from pyglaze.scanning import GlazeClient
from pyglaze.scanning.scanner import Scanner

if TYPE_CHECKING:
    from pyglaze.device.configuration import LeDeviceConfiguration


def test_mimlink_bulk_scan_returns_waveform(
    mimlink_device_config: LeDeviceConfiguration,
) -> None:
    scanner = Scanner(mimlink_device_config)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)
    assert len(scan.time) == mimlink_device_config.n_points


def test_mimlink_per_point_scan_returns_waveform(
    mimlink_device_config: LeDeviceConfiguration,
) -> None:
    mimlink_device_config.amp_port = "mock_mimlink_per_point"
    scanner = Scanner(mimlink_device_config)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)
    assert len(scan.time) == mimlink_device_config.n_points


def test_mimlink_bulk_retransmit_chunk_path(
    mimlink_device_config: LeDeviceConfiguration,
) -> None:
    mimlink_device_config.amp_port = "mock_mimlink_drop_chunk"
    scanner = Scanner(mimlink_device_config)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)
    assert len(scan.time) == mimlink_device_config.n_points


def test_mimlink_per_point_retransmit_path(
    mimlink_device_config: LeDeviceConfiguration,
) -> None:
    mimlink_device_config.amp_port = "mock_mimlink_drop_point"
    scanner = Scanner(mimlink_device_config)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)
    assert len(scan.time) == mimlink_device_config.n_points


def test_mimlink_scanner_update_config(
    mimlink_device_config: LeDeviceConfiguration,
) -> None:
    scanner = Scanner(mimlink_device_config)
    new_conf = deepcopy(mimlink_device_config)
    new_conf.amp_port = "mock_mimlink_scan_should_fail"
    scanner.update_config(new_conf)
    assert scanner.config == new_conf


def test_mimlink_client_read(
    mimlink_device_config: LeDeviceConfiguration,
) -> None:
    client = GlazeClient(mimlink_device_config)
    with client as c:
        pulses = c.read(n_pulses=2)
    assert len(pulses) == 2


def test_mimlink_client_scan_failure(
    mimlink_device_config: LeDeviceConfiguration,
) -> None:
    mimlink_device_config.amp_port = "mock_mimlink_scan_should_fail"
    with (
        pytest.raises((serialutil.SerialException, DeviceComError)),
        GlazeClient(mimlink_device_config) as client,
    ):
        client.read(n_pulses=1)


def test_mimlink_device_info(
    mimlink_device_config: LeDeviceConfiguration,
) -> None:
    scanner = Scanner(mimlink_device_config)
    info = scanner.get_device_info()
    assert info.serial_number == "M-9999"
    assert info.firmware_version == "v0.1.0"


def test_mimlink_ping(
    mimlink_device_config: LeDeviceConfiguration,
) -> None:
    scanner = Scanner(mimlink_device_config)
    result = scanner.ping()
    assert result.success is True
    assert result.round_trip_us > 0
