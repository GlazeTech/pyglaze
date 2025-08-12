import time

import numpy as np
import pytest
from serial import SerialException

from pyglaze.device import LeDeviceConfiguration
from pyglaze.device.ampcom import _LeAmpCom, _LeStatus


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


def test_get_status_idle(le_device_config: LeDeviceConfiguration) -> None:
    """Test that _get_status returns IDLE when device is not scanning."""
    amp = _LeAmpCom(le_device_config)
    amp.write_all()

    status = amp._get_status()
    assert status == _LeStatus.IDLE


def test_get_status_scanning(le_device_config: LeDeviceConfiguration) -> None:
    """Test that _get_status returns SCANNING when device is actively scanning."""
    amp = _LeAmpCom(le_device_config)
    amp.write_all()

    amp._encode_send_response(amp.START_COMMAND)

    status = amp._get_status()
    assert status == _LeStatus.SCANNING


def test_scan_status_workflow(le_device_config: LeDeviceConfiguration) -> None:
    """Test the complete scan workflow with status checks."""
    amp = _LeAmpCom(le_device_config)
    amp.write_all()

    assert amp._get_status() == _LeStatus.IDLE

    amp._encode_send_response(amp.START_COMMAND)

    assert amp._get_status() == _LeStatus.SCANNING

    time.sleep(amp.config._sweep_length_ms * 1.1e-3)

    assert amp._get_status() == _LeStatus.IDLE
