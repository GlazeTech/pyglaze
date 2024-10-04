import numpy as np
import pytest
from serial import SerialException

from pyglaze.device import ForceDeviceConfiguration, Interval, LeDeviceConfiguration
from pyglaze.device.ampcom import _ForceAmpCom, _LeAmpCom


@pytest.mark.parametrize("p", [(-1.1, 0.4), (-1.0, 0.6), (-1.1, 0.6)])
def test_forbidden_modulation_voltage(
    p: tuple[float, float], force_device_config: ForceDeviceConfiguration
) -> None:
    force_device_config.min_modulation_voltage = p[0]
    force_device_config.max_modulation_voltage = p[1]
    with pytest.raises(
        ValueError,
        match=f"Modulation voltages min: {p[0]:.1f}, max: {p[1]:.1f} not allowed.",
    ):
        _ForceAmpCom(force_device_config).write_modulation_voltage()


def test_ampcom_times_length(force_device_config: ForceDeviceConfiguration) -> None:
    force_device_config.scan_intervals = [
        Interval(0.0, 0.12),
        Interval(0.13456, 0.20986),
        Interval(0.23, 0.93232),
        Interval(0.94, 0.9999),
    ]
    amp = _ForceAmpCom(force_device_config)

    assert len(amp.times) == amp.scanning_points


def test_ampcom_scanlist_length(force_device_config: ForceDeviceConfiguration) -> None:
    force_device_config.scan_intervals = [
        Interval(0.0, 0.12),
        Interval(0.13456, 0.20986),
        Interval(0.23, 0.93232),
        Interval(0.94, 0.9999),
    ]
    amp = _ForceAmpCom(force_device_config)

    assert len(amp.scanning_list) == amp.N_POINTS


def test_ampcom_scanlist_values(le_device_config: LeDeviceConfiguration) -> None:
    amp = _LeAmpCom(le_device_config)
    assert np.max(amp.scanning_list) <= 1.0
    assert np.min(amp.scanning_list) >= 0.0


def test_evenly_distanced_times(force_device_config: ForceDeviceConfiguration) -> None:
    amp = _ForceAmpCom(force_device_config)
    time_spacings = np.diff(amp.times)
    np.testing.assert_allclose(time_spacings[0], time_spacings)


def test_raise_error_on_empty_responses(
    le_device_config: LeDeviceConfiguration,
) -> None:
    le_device_config.amp_port = "mock_device_empty_responses"
    amp = _LeAmpCom(le_device_config)
    with pytest.raises(SerialException, match="Empty response received"):
        amp.start_scan()
