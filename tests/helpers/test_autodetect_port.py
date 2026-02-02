from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pytest
from serial import serialutil
from typing_extensions import Self

from pyglaze.device import LeDeviceConfiguration
from pyglaze.device.ampcom import _serial_factory
from pyglaze.helpers.utilities import auto_detect_glaze_amp_port


@dataclass
class _FakePort:
    device: str
    vid: int | None = None
    description: str = ""
    manufacturer: str = ""
    product: str = ""
    hwid: str = ""


class _FakeSerial:
    RESPONSES: ClassVar[dict[str, bytes]] = {}

    def __init__(
        self, *, port: str, baudrate: int, timeout: float, write_timeout: float
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def reset_input_buffer(self) -> None:
        return None

    def reset_output_buffer(self) -> None:
        return None

    def write(self, data: bytes) -> int:
        return len(data)

    def read_until(self) -> bytes:
        return self.RESPONSES.get(self.port, b"")


def test_auto_detect_glaze_amp_port_picks_single_ftdi_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ports = [
        _FakePort("COM7", vid=0x0403, description="USB Serial Port"),
        _FakePort("COM1", vid=None, description="Something else"),
    ]
    monkeypatch.setattr(
        "pyglaze.helpers.utilities.serial.tools.list_ports.comports", lambda: ports
    )
    monkeypatch.setattr("pyglaze.helpers.utilities.serial.Serial", _FakeSerial)

    detected = auto_detect_glaze_amp_port(baudrate=1_000_000)
    assert detected == "COM7"


def test_auto_detect_glaze_amp_port_probes_multiple_ftdi_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ports = [
        _FakePort("COM7", vid=0x0403),
        _FakePort("COM8", vid=0x0403),
    ]
    monkeypatch.setattr(
        "pyglaze.helpers.utilities.serial.tools.list_ports.comports", lambda: ports
    )
    monkeypatch.setattr("pyglaze.helpers.utilities.serial.Serial", _FakeSerial)

    _FakeSerial.RESPONSES = {"COM8": b"ACK: Idle.\n"}

    detected = auto_detect_glaze_amp_port(baudrate=1_000_000)
    assert detected == "COM8"


def test_auto_detect_glaze_amp_port_raises_on_multiple_probe_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ports = [
        _FakePort("COM7", vid=0x0403),
        _FakePort("COM8", vid=0x0403),
    ]
    monkeypatch.setattr(
        "pyglaze.helpers.utilities.serial.tools.list_ports.comports", lambda: ports
    )
    monkeypatch.setattr("pyglaze.helpers.utilities.serial.Serial", _FakeSerial)

    _FakeSerial.RESPONSES = {"COM7": b"ACK: Idle.\n", "COM8": b"ACK: Idle.\n"}

    with pytest.raises(serialutil.SerialException, match="Multiple serial ports matched"):
        auto_detect_glaze_amp_port(baudrate=1_000_000)


def test_auto_detect_glaze_amp_port_raises_when_probe_disabled_and_multiple_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ports = [
        _FakePort("COM7", vid=0x0403),
        _FakePort("COM8", vid=0x0403),
    ]
    monkeypatch.setattr(
        "pyglaze.helpers.utilities.serial.tools.list_ports.comports", lambda: ports
    )

    with pytest.raises(serialutil.SerialException, match="probing is disabled"):
        auto_detect_glaze_amp_port(probe=False)


def test_serial_factory_uses_auto_detect_when_amp_port_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = LeDeviceConfiguration(amp_port="auto")

    monkeypatch.setattr("pyglaze.device.ampcom.auto_detect_glaze_amp_port", lambda **_: "COM9")

    captured: dict[str, object] = {}

    def _fake_serial_for_url(
        *, url: str, baudrate: int, timeout: float | None
    ) -> object:
        captured["url"] = url
        captured["baudrate"] = baudrate
        captured["timeout"] = timeout
        return object()

    monkeypatch.setattr("pyglaze.device.ampcom.serial.serial_for_url", _fake_serial_for_url)

    _serial_factory(config)
    assert captured["url"] == "COM9"
