from copy import deepcopy

import pytest
from serial import serialutil

from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.device import ConfigStatusReason, DeviceStateError, OperationalState
from pyglaze.device.configuration import DeviceConfiguration
from pyglaze.scanning import GlazeClient
from pyglaze.scanning._types import DeviceInfo
from tests.conftest import DEVICE_CONFIGS


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
def test_get_device_info(config_name: str, request: pytest.FixtureRequest) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    client = GlazeClient(device_config)
    with client as c:
        info = c.get_device_info()

    assert isinstance(info, DeviceInfo)
    assert info.serial_number != ""
    assert info.firmware_version != ""
    assert info.firmware_target != ""
    assert info.operational_state is OperationalState.NORMAL
    assert info.config_status_reason is ConfigStatusReason.NONE


@pytest.mark.parametrize(
    ("amp_port", "config_status_reason", "expected_state_kind"),
    [
        ("mock_device_commissioning_idle", ConfigStatusReason.NONE, "commissioning"),
        ("mock_device_invalid_config", ConfigStatusReason.INVALID_CONFIG, "recovery"),
    ],
)
def test_client_startup_surfaces_blocked_device_state(
    amp_port: str,
    config_status_reason: ConfigStatusReason,
    expected_state_kind: str,
    le_device_config: DeviceConfiguration,
) -> None:
    device_config = deepcopy(le_device_config)
    device_config.amp_port = amp_port

    with pytest.raises(DeviceStateError) as excinfo, GlazeClient(device_config):
        pass

    assert excinfo.value.state.operational_state is OperationalState.COMMISSIONING_IDLE
    assert excinfo.value.state.config_status_reason is config_status_reason
    assert excinfo.value.state.is_recovery_idle is (expected_state_kind == "recovery")


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
