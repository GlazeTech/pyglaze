from copy import deepcopy
from typing import TYPE_CHECKING

import pytest
from conftest import DEVICE_CONFIGS
from serial import serialutil

from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.scanning._types import DeviceInfo
from pyglaze.scanning.scanner import Scanner

if TYPE_CHECKING:
    from pyglaze.device.configuration import DeviceConfiguration


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_right_data_format(config_name: str, request: pytest.FixtureRequest) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    scanner = Scanner(device_config)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_update_device(config_name: str, request: pytest.FixtureRequest) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    scanner = Scanner(device_config)
    new_conf = deepcopy(device_config)
    new_conf.amp_port = "mock_device_scan_should_fail"
    scanner.update_config(new_conf)
    assert scanner.config == new_conf


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_update_device_v2(config_name: str, request: pytest.FixtureRequest) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    scanner = Scanner(device_config)
    new_conf = deepcopy(device_config)
    new_conf.amp_port = "mock_device_scan_should_fail"
    scanner.config = new_conf
    assert scanner.config == new_conf


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_no_connection_error(config_name: str, request: pytest.FixtureRequest) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    device_config.amp_port = "nonexistent_port"
    with pytest.raises(serialutil.SerialException):
        Scanner(device_config)


def test_invalid_config_type() -> None:
    with pytest.raises(TypeError):
        Scanner("invalid_config")  # type: ignore[type-var]


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_lescanner_get_device_info(
    config_name: str, request: pytest.FixtureRequest
) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    scanner = Scanner(device_config)
    info = scanner.get_device_info()
    assert isinstance(info, DeviceInfo)
    assert info.serial_number != ""
    assert info.firmware_version != ""


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_scanner_with_initial_phase_estimate(
    config_name: str, request: pytest.FixtureRequest
) -> None:
    """Test that Scanner accepts and uses initial_phase_estimate parameter."""
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    initial_phase = 1.5

    scanner = Scanner(device_config, initial_phase_estimate=initial_phase)

    # Phase estimate should be set immediately
    phase = scanner.get_phase_estimate()
    assert phase is not None
    assert abs(phase - initial_phase) < 1e-6

    # Should still work after scanning (phase may be updated if confidence is high)
    _ = scanner.scan()
    phase_after = scanner.get_phase_estimate()
    assert phase_after is not None
    assert isinstance(phase_after, float)


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_scanner_phase_persistence_across_instances(
    config_name: str, request: pytest.FixtureRequest
) -> None:
    """Test that phase can be extracted and reused across scanner instances."""
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)

    # Use a known phase value (since mock device may not learn a phase from random IQ data)
    known_phase = 1.5

    # First scanner with known phase
    scanner1 = Scanner(device_config, initial_phase_estimate=known_phase)
    phase1 = scanner1.get_phase_estimate()
    assert phase1 is not None
    assert abs(phase1 - known_phase) < 1e-6

    # Second scanner starts with the same phase
    scanner2 = Scanner(device_config, initial_phase_estimate=phase1)
    initial_phase2 = scanner2.get_phase_estimate()
    assert initial_phase2 is not None
    assert abs(initial_phase2 - phase1) < 1e-6

    # After scanning, if phase gets updated, it should still be valid
    _ = scanner2.scan()
    phase_after_scan = scanner2.get_phase_estimate()
    assert phase_after_scan is not None
    assert isinstance(phase_after_scan, float)
    assert -3.2 <= phase_after_scan <= 3.2  # Within (-pi, pi]


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_per_point_scan(config_name: str, request: pytest.FixtureRequest) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    device_config.amp_port = "mock_device_per_point"
    scanner = Scanner(device_config)
    scan = scanner.scan()
    assert isinstance(scan, UnprocessedWaveform)
    assert len(scan.time) == device_config.n_points
