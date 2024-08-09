from copy import deepcopy
from typing import TYPE_CHECKING

import pytest
from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.scanning.scanner import Scanner
from serial import serialutil

from tests.conftest import DEVICE_CONFIGS

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


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_succeed_on_single_failure(
    config_name: str, request: pytest.FixtureRequest
) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    device_config.amp_port = "mock_device_fail_first_scan"
    scanner = Scanner(device_config)
    _ = scanner.scan()


def test_invalid_config_type() -> None:
    with pytest.raises(TypeError):
        Scanner("invalid_config")  # type: ignore[type-var]
