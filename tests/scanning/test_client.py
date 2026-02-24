from typing import TYPE_CHECKING

import pytest
from serial import serialutil

from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.device.ampcom import DeviceComError
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
    device_config.amp_port = "mock_mimlink_scan_should_fail"
    with (
        pytest.raises((serialutil.SerialException, DeviceComError)),
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


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_get_phase_estimate_while_active(
    config_name: str, request: pytest.FixtureRequest
) -> None:
    """Test getting phase estimate while client is active."""
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    client = GlazeClient(device_config)
    with client as c:
        # Get a few scans to allow phase estimator to learn
        c.read(n_pulses=1)

        # Should be able to get phase estimate
        phase = c.get_phase_estimate()
        assert phase is not None
        assert -3.2 <= phase <= 3.2  # Within (-pi, pi]


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_get_phase_estimate_after_stop_works(
    config_name: str, request: pytest.FixtureRequest
) -> None:
    """Test that getting phase estimate after context exit still works (returns cached value)."""
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    initial_phase = 1.5
    client = GlazeClient(device_config, initial_phase_estimate=initial_phase)

    with client as c:
        # Get a scan to ensure cache is populated
        c.read(n_pulses=1)
        phase_while_active = c.get_phase_estimate()
        assert phase_while_active is not None

    # Should still be able to get cached phase estimate after stopping
    phase_after_stop = client.get_phase_estimate()
    assert phase_after_stop is not None
    assert phase_after_stop == phase_while_active
