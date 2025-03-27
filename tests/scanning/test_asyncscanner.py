import pytest
from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.device.configuration import DeviceConfiguration
from pyglaze.scanning._asyncscanner import _AsyncScanner
from serial.serialutil import SerialException

from tests.conftest import DEVICE_CONFIGS


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


@pytest.mark.parametrize("n_scans", [1, 2])
@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_get_next(
    n_scans: int, config_name: str, request: pytest.FixtureRequest
) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    scanner = _AsyncScanner()
    scanner.start_scan(device_config)
    for _ in range(n_scans):
        scan = scanner.get_next()
        assert isinstance(scan, UnprocessedWaveform)
    scanner.stop_scan()


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


def test_recover_from_startup_error(le_device_config: DeviceConfiguration) -> None:
    scanner = _AsyncScanner()
    le_device_config.amp_port = "mock_device_empty_responses"

    with pytest.raises(SerialException, match="Empty response received"):
        scanner.start_scan(le_device_config)
    assert scanner.is_scanning is False

    le_device_config.amp_port = "mock_device"
    scanner.start_scan(le_device_config)
    assert scanner.is_scanning
    scanner.stop_scan()


def test_recover_from_failed_scan(le_device_config: DeviceConfiguration) -> None:
    scanner = _AsyncScanner()
    le_device_config.amp_port = "mock_device_scan_should_fail"
    scanner.start_scan(le_device_config)
    with pytest.raises(SerialException):
        scanner.get_scans(1)
    assert scanner.is_scanning is False

    # Verify that the child process is closed - is_alive raises an error if called on a closed process
    with pytest.raises(ValueError, match="process object is closed"):
        scanner._child_process.is_alive()
    le_device_config.amp_port = "mock_device"
    scanner.start_scan(le_device_config)
    assert scanner.is_scanning
    scanner.stop_scan()
