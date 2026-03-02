from __future__ import annotations

from dataclasses import dataclass

import pytest

from pyglaze.device import LeDeviceConfiguration
from pyglaze.device.discovery import (
    DeviceNotFoundError,
    MultipleDevicesError,
    _deduplicate_macos,
    discover,
    discover_one,
)
from pyglaze.device.mimlink_client import _connection_factory


@dataclass
class FakePortInfo:
    device: str
    vid: int | None = None
    serial_number: str | None = None
    description: str = ""
    manufacturer: str = ""
    product: str = ""
    hwid: str = ""


_COMPORTS_PATH = "pyglaze.device.discovery.serial.tools.list_ports.comports"


class TestDiscover:
    def test_finds_ftdi_by_vid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ports = [
            FakePortInfo("/dev/ttyUSB0", vid=0x0403, serial_number="A1"),
            FakePortInfo("/dev/ttyUSB1", vid=0x1234),
        ]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)

        result = discover()

        assert result == ["/dev/ttyUSB0"]

    def test_finds_ftdi_by_textual_metadata(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ports = [
            FakePortInfo(
                "/dev/ttyUSB0", vid=None, description="FTDI USB Serial Device"
            ),
        ]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)

        result = discover()

        assert result == ["/dev/ttyUSB0"]

    def test_finds_ftdi_by_ft232_in_product(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ports = [
            FakePortInfo("/dev/ttyUSB0", vid=None, product="FT232R"),
        ]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)

        result = discover()

        assert result == ["/dev/ttyUSB0"]

    def test_skips_bluetooth_ports(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ports = [
            FakePortInfo("/dev/cu.Bluetooth-Incoming-Port", vid=0x0403),
        ]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)

        assert discover() == []

    def test_skips_debug_ports(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ports = [
            FakePortInfo("/dev/cu.debug-console", vid=0x0403),
        ]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)

        assert discover() == []

    def test_returns_empty_when_no_devices(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_COMPORTS_PATH, list)

        assert discover() == []

    def test_ignores_non_ftdi_ports(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ports = [
            FakePortInfo("/dev/ttyUSB0", vid=0x1234, description="Some other device"),
        ]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)

        assert discover() == []

    def test_macos_deduplication(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ports = [
            FakePortInfo("/dev/cu.usbserial-A1", vid=0x0403, serial_number="A1"),
            FakePortInfo("/dev/tty.usbserial-A1", vid=0x0403, serial_number="A1"),
        ]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)
        monkeypatch.setattr("pyglaze.device.discovery.sys.platform", "darwin")

        result = discover()

        assert result == ["/dev/cu.usbserial-A1"]

    def test_macos_no_serial_number_keeps_both(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ports = [
            FakePortInfo("/dev/cu.usbserial-X", vid=0x0403, serial_number=None),
            FakePortInfo("/dev/tty.usbserial-Y", vid=0x0403, serial_number=None),
        ]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)
        monkeypatch.setattr("pyglaze.device.discovery.sys.platform", "darwin")

        result = discover()

        assert len(result) == 2


class TestDiscoverOne:
    def test_single_device(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ports = [FakePortInfo("COM3", vid=0x0403, serial_number="A1")]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)

        assert discover_one() == "COM3"

    def test_no_devices_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_COMPORTS_PATH, list)

        with pytest.raises(DeviceNotFoundError, match="No GLAZE devices found"):
            discover_one()

    def test_multiple_devices_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ports = [
            FakePortInfo("COM3", vid=0x0403, serial_number="A1"),
            FakePortInfo("COM4", vid=0x0403, serial_number="A2"),
        ]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)

        with pytest.raises(MultipleDevicesError, match="Multiple GLAZE devices"):
            discover_one()


class TestDeduplicateMacos:
    def test_keeps_cu_over_tty(self) -> None:
        candidates = [
            ("/dev/cu.usbserial-A1", "A1"),
            ("/dev/tty.usbserial-A1", "A1"),
        ]

        result = _deduplicate_macos(candidates)

        assert result == [("/dev/cu.usbserial-A1", "A1")]

    def test_keeps_both_when_no_serial_number(self) -> None:
        candidates = [
            ("/dev/cu.usbserial-X", None),
            ("/dev/tty.usbserial-Y", None),
        ]

        result = _deduplicate_macos(candidates)

        assert len(result) == 2

    def test_multiple_devices_deduplicates_each(self) -> None:
        candidates = [
            ("/dev/cu.usbserial-A1", "A1"),
            ("/dev/tty.usbserial-A1", "A1"),
            ("/dev/cu.usbserial-B2", "B2"),
            ("/dev/tty.usbserial-B2", "B2"),
        ]

        result = _deduplicate_macos(candidates)

        devices = [d for d, _ in result]
        assert "/dev/cu.usbserial-A1" in devices
        assert "/dev/cu.usbserial-B2" in devices
        assert len(result) == 2


class TestConnectionFactoryAuto:
    def test_resolves_auto_to_discovered_port(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "pyglaze.device.discovery.serial.tools.list_ports.comports",
            lambda: [FakePortInfo("COM9", vid=0x0403, serial_number="X1")],
        )

        captured: dict[str, object] = {}

        def fake_serial_for_url(
            *, url: str, baudrate: int, timeout: float | None  # noqa: ARG001
        ) -> object:
            captured["url"] = url
            return object()

        monkeypatch.setattr(
            "pyglaze.device.mimlink_client.serial.serial_for_url", fake_serial_for_url
        )

        config = LeDeviceConfiguration(amp_port="auto")
        _connection_factory(config)

        assert captured["url"] == "COM9"
