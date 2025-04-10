from typing import TYPE_CHECKING

import pytest
from serial import serialutil

from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.scanning import GlazeClient
from tests.conftest import DEVICE_CONFIGS

if TYPE_CHECKING:
    from pyglaze.device.configuration import DeviceConfiguration


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_read_scans(config_name: str, request: pytest.FixtureRequest) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    n_pulses = 2
    client = GlazeClient(device_config)
    with client as c:
        pulses = c.read(n_pulses=n_pulses)

    assert client._scanner.is_scanning is False
    assert isinstance(pulses, list)
    assert len(pulses) == n_pulses
    for pulse in pulses:
        assert isinstance(pulse, UnprocessedWaveform)


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_wrong_address_handling(
    config_name: str, request: pytest.FixtureRequest
) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    device_config.amp_port = "nonexisting_port"
    with pytest.raises(serialutil.SerialException), GlazeClient(device_config) as _:
        pass


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_raises_error_when_scan_fails(
    config_name: str, request: pytest.FixtureRequest
) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    device_config.amp_port = "mock_device_scan_should_fail"
    with (
        pytest.raises(serialutil.SerialException),
        GlazeClient(device_config) as client,
    ):
        client.read(n_pulses=1)


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_get_serial_number(config_name: str, request: pytest.FixtureRequest) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    client = GlazeClient(device_config)
    with client as c:
        serial_number = c.get_serial_number()

    assert isinstance(serial_number, str)
    assert serial_number != ""


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_get_firmware_version(config_name: str, request: pytest.FixtureRequest) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    client = GlazeClient(device_config)
    with client as c:
        firmware_version = c.get_firmware_version()

    assert isinstance(firmware_version, str)
    assert firmware_version != ""
