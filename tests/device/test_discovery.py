from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

import pytest

from pyglaze.device.discovery import (
    FTDI_VENDOR_ID,
    DeviceNotFoundError,
    MultipleDevicesError,
    _deduplicate_cu_tty,
    discover,
    discover_one,
)


@dataclass
class FakePortInfo:
    device: str
    vid: int | None = None
    pid: int | None = None
    serial_number: str | None = None
    manufacturer: str | None = None
    product: str | None = None


@patch("pyglaze.device.discovery.serial.tools.list_ports.comports")
def test_discover_finds_ftdi_devices(mock_comports: object) -> None:
    mock_comports.return_value = [  # type: ignore[union-attr]
        FakePortInfo(
            device="/dev/cu.usbserial-FT123", vid=FTDI_VENDOR_ID, serial_number="FT123"
        ),
    ]
    result = discover()
    assert result == ["/dev/cu.usbserial-FT123"]


@patch("pyglaze.device.discovery.serial.tools.list_ports.comports")
def test_discover_filters_non_ftdi(mock_comports: object) -> None:
    mock_comports.return_value = [  # type: ignore[union-attr]
        FakePortInfo(device="/dev/ttyACM0", vid=0x1234, serial_number="ABC"),
    ]
    result = discover()
    assert result == []


@patch("pyglaze.device.discovery.serial.tools.list_ports.comports")
def test_discover_returns_empty_when_no_devices(mock_comports: object) -> None:
    mock_comports.return_value = []  # type: ignore[union-attr]
    result = discover()
    assert result == []


@patch("pyglaze.device.discovery.serial.tools.list_ports.comports")
def test_discover_one_single_device(mock_comports: object) -> None:
    mock_comports.return_value = [  # type: ignore[union-attr]
        FakePortInfo(device="COM3", vid=FTDI_VENDOR_ID, serial_number="FT456"),
    ]
    result = discover_one()
    assert result == "COM3"


@patch("pyglaze.device.discovery.serial.tools.list_ports.comports")
def test_discover_one_no_devices(mock_comports: object) -> None:
    mock_comports.return_value = []  # type: ignore[union-attr]
    with pytest.raises(DeviceNotFoundError):
        discover_one()


@patch("pyglaze.device.discovery.serial.tools.list_ports.comports")
def test_discover_one_multiple_devices(mock_comports: object) -> None:
    mock_comports.return_value = [  # type: ignore[union-attr]
        FakePortInfo(device="COM3", vid=FTDI_VENDOR_ID, serial_number="FT1"),
        FakePortInfo(device="COM4", vid=FTDI_VENDOR_ID, serial_number="FT2"),
    ]
    with pytest.raises(MultipleDevicesError):
        discover_one()


def test_macos_deduplication() -> None:
    candidates = [
        ("/dev/cu.usbserial-FT123", "FT123"),
        ("/dev/tty.usbserial-FT123", "FT123"),
    ]
    result = _deduplicate_cu_tty(candidates)
    assert len(result) == 1
    assert result[0][0] == "/dev/cu.usbserial-FT123"


def test_macos_deduplication_no_serial_number() -> None:
    candidates = [
        ("/dev/cu.usbserial-unknown1", None),
        ("/dev/tty.usbserial-unknown2", None),
    ]
    result = _deduplicate_cu_tty(candidates)
    assert len(result) == 2
