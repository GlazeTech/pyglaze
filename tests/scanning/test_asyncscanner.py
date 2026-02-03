import time

import pytest
from serial.serialutil import SerialException

from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.device.configuration import DeviceConfiguration
from pyglaze.scanning._asyncscanner import _AsyncScanner
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


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_get_phase_estimate_while_scanning(
    config_name: str, request: pytest.FixtureRequest
) -> None:
    """Test getting phase estimate while scanner is running."""
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    scanner = _AsyncScanner()
    scanner.start_scan(device_config)

    # Get a few scans to allow phase estimator to learn
    for _ in range(1):
        scanner.get_next()

    # Should be able to get phase estimate
    phase = scanner.get_phase_estimate()

    assert phase is not None
    assert -3.2 <= phase <= 3.2  # Within (-pi, pi]

    scanner.stop_scan()


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_get_phase_estimate_with_initial_value(
    config_name: str, request: pytest.FixtureRequest
) -> None:
    """Test that initial phase estimate is available immediately."""
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    initial_phase = 1.5
    scanner = _AsyncScanner()
    scanner.start_scan(device_config, initial_phase_estimate=initial_phase)

    # Should be able to get phase estimate immediately
    phase = scanner.get_phase_estimate()
    assert phase is not None
    assert abs(phase - initial_phase) < 1e-6

    scanner.stop_scan()


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_get_phase_estimate_after_stop_works(
    config_name: str, request: pytest.FixtureRequest
) -> None:
    """Test that getting phase estimate after stop still works (returns cached value)."""
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    initial_phase = 1.5
    scanner = _AsyncScanner()
    scanner.start_scan(device_config, initial_phase_estimate=initial_phase)

    # Get at least one scan to ensure cache is populated
    scanner.get_next()

    # Get phase while running
    phase_while_running = scanner.get_phase_estimate()
    assert phase_while_running is not None

    scanner.stop_scan()

    # Should still be able to get cached phase estimate after stopping
    phase_after_stop = scanner.get_phase_estimate()
    assert phase_after_stop is not None
    assert phase_after_stop == phase_while_running


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_get_phase_estimate_doesnt_interfere_with_scanning(
    config_name: str, request: pytest.FixtureRequest
) -> None:
    """Test that requesting phase estimate doesn't interrupt the scanning loop."""
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    scanner = _AsyncScanner()
    scanner.start_scan(device_config, initial_phase_estimate=1.0)

    # Interleave scanning with phase estimate requests
    for _ in range(1):
        scan = scanner.get_next()
        assert isinstance(scan, UnprocessedWaveform)

        phase = scanner.get_phase_estimate()
        assert phase is not None
        assert isinstance(phase, float)

    # Scanner should still be healthy
    assert scanner.is_scanning
    scanner.stop_scan()


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_get_phase_estimate_returns_instantly(
    config_name: str, request: pytest.FixtureRequest
) -> None:
    """Test that get_phase_estimate returns instantly without blocking on scans."""
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    scanner = _AsyncScanner()
    scanner.start_scan(device_config, initial_phase_estimate=1.0)

    # Get one scan to ensure cache is populated
    scanner.get_next()

    # Measure time for multiple get_phase_estimate calls
    start = time.perf_counter()
    for _ in range(10):
        phase = scanner.get_phase_estimate()
        assert phase is not None
    elapsed = time.perf_counter() - start

    # Should complete in well under 10ms (even 1ms is generous for cached access)
    # If it had to wait for scans, this would take 10 * sweep_length_ms
    assert elapsed < 0.01, (
        f"get_phase_estimate took {elapsed * 1000:.2f}ms for 10 calls"
    )

    scanner.stop_scan()
