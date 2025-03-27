import numpy as np
import pytest
from pyglaze.device import LeDeviceConfiguration
from pyglaze.device.ampcom import _LeAmpCom
from serial import SerialException


def test_ampcom_scanlist_values(le_device_config: LeDeviceConfiguration) -> None:
    amp = _LeAmpCom(le_device_config)
    assert np.max(amp.scanning_list) <= 1.0
    assert np.min(amp.scanning_list) >= 0.0


def test_raise_error_on_empty_responses(
    le_device_config: LeDeviceConfiguration,
) -> None:
    le_device_config.amp_port = "mock_device_empty_responses"
    amp = _LeAmpCom(le_device_config)
    with pytest.raises(SerialException, match="Empty response received"):
        amp.start_scan()
