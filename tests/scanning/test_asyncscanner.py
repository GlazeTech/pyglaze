from typing import TYPE_CHECKING

import pytest
from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.scanning._asyncscanner import _AsyncScanner
from serial.serialutil import SerialException

from tests.conftest import DEVICE_CONFIGS

if TYPE_CHECKING:
    from pyglaze.device.configuration import DeviceConfiguration


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_start_stop(config_name: str, request: pytest.FixtureRequest) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    scanner = _AsyncScanner()
    scanner.start_scan(device_config)
    assert scanner._child_process.is_alive()
    assert scanner.is_scanning

    scanner.stop_scan()
    assert scanner._child_process._closed  # type: ignore[attr-defined]
    assert scanner.is_scanning is False


@pytest.mark.parametrize("averaged_over", [1, 2])
@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_get_next(
    averaged_over: int, config_name: str, request: pytest.FixtureRequest
) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    scanner = _AsyncScanner()
    scanner.start_scan(device_config)
    scan = scanner.get_next(averaged_over_n=averaged_over)
    scanner.stop_scan()
    assert isinstance(scan, UnprocessedWaveform)


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_raise_timeout(config_name: str, request: pytest.FixtureRequest) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    scanner = _AsyncScanner(startup_timeout=0.0)
    with pytest.raises(TimeoutError):
        scanner.start_scan(device_config)
    assert scanner.is_scanning is False


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_scanner_wrong_port(config_name: str, request: pytest.FixtureRequest) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    device_config.amp_port = "Nonexisting"
    scanner = _AsyncScanner()
    with pytest.raises(SerialException):
        scanner.start_scan(device_config)
    assert scanner.is_scanning is False
