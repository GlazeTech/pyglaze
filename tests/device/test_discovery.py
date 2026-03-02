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
    serial_number: str | None = None
    manufacturer: str = ""
    product: str = ""


def _glaze_port(device: str, serial_number: str | None = None) -> FakePortInfo:
    return FakePortInfo(
        device=device,
        serial_number=serial_number,
        manufacturer="GLAZE Technologies",
        product="THz-CCS",
    )


_COMPORTS_PATH = "pyglaze.device.discovery.serial.tools.list_ports.comports"


class TestDiscover:
    def test_finds_glaze_device(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ports = [
            _glaze_port("/dev/ttyUSB0", serial_number="C-0005"),
            FakePortInfo("/dev/ttyUSB1"),
        ]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)

        assert discover() == ["/dev/ttyUSB0"]

    def test_returns_empty_when_no_devices(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_COMPORTS_PATH, list)

        assert discover() == []

    def test_ignores_non_glaze_ports(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ports = [
            FakePortInfo("/dev/ttyUSB0", manufacturer="FTDI", product="FT232R"),
        ]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)

        assert discover() == []

    def test_ignores_partial_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ports = [
            FakePortInfo(
                "/dev/ttyUSB0", manufacturer="GLAZE Technologies", product="Other"
            ),
        ]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)

        assert discover() == []

    def test_macos_deduplication(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ports = [
            _glaze_port("/dev/cu.usbserial-C0005", serial_number="C-0005"),
            _glaze_port("/dev/tty.usbserial-C0005", serial_number="C-0005"),
        ]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)
        monkeypatch.setattr("pyglaze.device.discovery.sys.platform", "darwin")

        assert discover() == ["/dev/cu.usbserial-C0005"]

    def test_macos_no_serial_number_keeps_both(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ports = [
            _glaze_port("/dev/cu.usbserial-X", serial_number=None),
            _glaze_port("/dev/tty.usbserial-Y", serial_number=None),
        ]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)
        monkeypatch.setattr("pyglaze.device.discovery.sys.platform", "darwin")

        assert len(discover()) == 2


class TestDiscoverOne:
    def test_single_device(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ports = [_glaze_port("COM3", serial_number="C-0005")]
        monkeypatch.setattr(_COMPORTS_PATH, lambda: ports)

        assert discover_one() == "COM3"

    def test_no_devices_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_COMPORTS_PATH, list)

        with pytest.raises(DeviceNotFoundError, match="No GLAZE devices found"):
            discover_one()

    def test_multiple_devices_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ports = [
            _glaze_port("COM3", serial_number="C-0005"),
            _glaze_port("COM4", serial_number="C-0006"),
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

        assert _deduplicate_macos(candidates) == [("/dev/cu.usbserial-A1", "A1")]

    def test_keeps_both_when_no_serial_number(self) -> None:
        candidates = [
            ("/dev/cu.usbserial-X", None),
            ("/dev/tty.usbserial-Y", None),
        ]

        assert len(_deduplicate_macos(candidates)) == 2

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
            _COMPORTS_PATH,
            lambda: [_glaze_port("COM9", serial_number="C-0005")],
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
