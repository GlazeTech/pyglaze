from __future__ import annotations

from dataclasses import dataclass

import pytest

from pyglaze.device import LeDeviceConfiguration
from pyglaze.device.discovery import (
    DeviceNotFoundError,
    MultipleDevicesError,
    discover,
    discover_one,
    list_serial_ports,
)
from pyglaze.device.scan_client import _connection_factory

_COMPORTS = "pyglaze.device.discovery.serial.tools.list_ports.comports"
_PLATFORM = "pyglaze.device.discovery.sys.platform"


@dataclass
class FakePortInfo:
    device: str
    serial_number: str | None = None
    manufacturer: str = ""
    product: str = ""


def _glaze_port(device: str, serial_number: str | None = None) -> FakePortInfo:
    """Build a FakePortInfo that looks like a real GLAZE device."""
    return FakePortInfo(
        device=device,
        serial_number=serial_number,
        manufacturer="GLAZE Technologies",
        product="Carmen",
    )


def test_discover_finds_glaze_device(monkeypatch: pytest.MonkeyPatch) -> None:
    """A port with matching manufacturer + product is returned; others are ignored."""
    monkeypatch.setattr(
        _COMPORTS,
        lambda: [
            _glaze_port("/dev/ttyUSB0", serial_number="C-0005"),
            FakePortInfo("/dev/ttyUSB1"),
        ],
    )

    assert discover() == ["/dev/ttyUSB0"]


def test_discover_ignores_non_glaze_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """A generic FTDI device is not a GLAZE device."""
    monkeypatch.setattr(
        _COMPORTS,
        lambda: [FakePortInfo("/dev/ttyUSB0", manufacturer="FTDI", product="FT232R")],
    )

    assert discover() == []


def test_discover_ignores_partial_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both manufacturer AND product must match — one alone is not enough."""
    monkeypatch.setattr(
        _COMPORTS,
        lambda: [
            FakePortInfo(
                "/dev/ttyUSB0", manufacturer="GLAZE Technologies", product="Other"
            ),
        ],
    )

    assert discover() == []


def test_discover_returns_empty_when_no_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """No serial ports at all -> empty list."""
    monkeypatch.setattr(_COMPORTS, list)

    assert discover() == []


def test_discover_macos_keeps_cu_drops_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """On macOS, each USB serial chip creates both /dev/cu.* and /dev/tty.*.

    We keep the cu.* variant (non-blocking open) and drop the tty.* duplicate.
    """
    monkeypatch.setattr(
        _COMPORTS,
        lambda: [
            _glaze_port("/dev/cu.usbserial-C0005", serial_number="C-0005"),
            _glaze_port("/dev/tty.usbserial-C0005", serial_number="C-0005"),
        ],
    )
    monkeypatch.setattr(_PLATFORM, "darwin")

    assert discover() == ["/dev/cu.usbserial-C0005"]


def test_discover_macos_deduplicates_multiple_devices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two physical devices -> two results after dedup (one cu.* each)."""
    monkeypatch.setattr(
        _COMPORTS,
        lambda: [
            _glaze_port("/dev/cu.usbserial-C0005", serial_number="C-0005"),
            _glaze_port("/dev/tty.usbserial-C0005", serial_number="C-0005"),
            _glaze_port("/dev/cu.usbserial-C0006", serial_number="C-0006"),
            _glaze_port("/dev/tty.usbserial-C0006", serial_number="C-0006"),
        ],
    )
    monkeypatch.setattr(_PLATFORM, "darwin")

    result = discover()

    assert len(result) == 2
    assert "/dev/cu.usbserial-C0005" in result
    assert "/dev/cu.usbserial-C0006" in result


def test_discover_macos_keeps_both_when_no_serial_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a serial number we can't tell if two ports are the same device.

    Safe fallback: keep both so the user can choose.
    """
    monkeypatch.setattr(
        _COMPORTS,
        lambda: [
            _glaze_port("/dev/cu.usbserial-X", serial_number=None),
            _glaze_port("/dev/tty.usbserial-Y", serial_number=None),
        ],
    )
    monkeypatch.setattr(_PLATFORM, "darwin")

    assert len(discover()) == 2


def test_discover_one_returns_single_device(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _COMPORTS,
        lambda: [_glaze_port("COM3", serial_number="C-0005")],
    )

    assert discover_one() == "COM3"


def test_discover_one_raises_when_no_devices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_COMPORTS, list)

    with pytest.raises(DeviceNotFoundError, match="No GLAZE devices found"):
        discover_one()


def test_discover_one_raises_when_multiple_devices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _COMPORTS,
        lambda: [
            _glaze_port("COM3", serial_number="C-0005"),
            _glaze_port("COM4", serial_number="C-0006"),
        ],
    )

    with pytest.raises(MultipleDevicesError, match="Multiple GLAZE devices"):
        discover_one()


def test_connection_factory_auto_resolves_to_discovered_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When amp_port is 'auto', _connection_factory calls discover_one()
    and opens the returned port.
    """
    monkeypatch.setattr(
        _COMPORTS,
        lambda: [_glaze_port("COM9", serial_number="C-0005")],
    )

    captured: dict[str, object] = {}

    def fake_serial_for_url(
        *,
        url: str,
        baudrate: int,  # noqa: ARG001
        timeout: float | None,  # noqa: ARG001
    ) -> object:
        captured["url"] = url
        return object()

    monkeypatch.setattr(
        "pyglaze.device.scan_client.serial.serial_for_url", fake_serial_for_url
    )

    _connection_factory(LeDeviceConfiguration(amp_port="auto"))

    assert captured["url"] == "COM9"


def test_list_serial_ports_returns_non_junk_ports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regular serial ports are returned."""
    monkeypatch.setattr(
        _COMPORTS,
        lambda: [
            FakePortInfo("/dev/ttyUSB0"),
            FakePortInfo("COM3"),
        ],
    )

    assert list_serial_ports() == ["/dev/ttyUSB0", "COM3"]


def test_list_serial_ports_skips_bluetooth_and_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bluetooth and debug ports are excluded."""
    monkeypatch.setattr(
        _COMPORTS,
        lambda: [
            FakePortInfo("/dev/ttyUSB0"),
            FakePortInfo("/dev/tty.Bluetooth-Incoming-Port"),
            FakePortInfo("/dev/cu.debug-console"),
        ],
    )

    assert list_serial_ports() == ["/dev/ttyUSB0"]


def test_list_serial_ports_deduplicates_macos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On macOS, cu/tty pairs are deduplicated (keeps cu.*)."""
    monkeypatch.setattr(
        _COMPORTS,
        lambda: [
            FakePortInfo("/dev/cu.usbserial-A001", serial_number="A001"),
            FakePortInfo("/dev/tty.usbserial-A001", serial_number="A001"),
        ],
    )
    monkeypatch.setattr(_PLATFORM, "darwin")

    assert list_serial_ports() == ["/dev/cu.usbserial-A001"]
