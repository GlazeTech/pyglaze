import time

import numpy as np
import pytest
from serial import SerialException

from pyglaze.device import LeDeviceConfiguration
from pyglaze.device.protocols.le_v1 import LeProtocolV1, _LeStatus


def test_protocol_v1_scanlist_values(le_device_config: LeDeviceConfiguration) -> None:
    protocol = LeProtocolV1(le_device_config)
    protocol.connect()
    assert np.max(protocol.scanning_list) <= 1.0
    assert np.min(protocol.scanning_list) >= 0.0
    protocol.disconnect()


def test_raise_error_on_empty_responses(
    le_device_config: LeDeviceConfiguration,
) -> None:
    le_device_config.amp_port = "mock_device_empty_responses"
    protocol = LeProtocolV1(le_device_config)
    protocol.connect()
    with pytest.raises(SerialException, match="Empty response received"):
        protocol.start_scan()
    protocol.disconnect()


def test_get_status_idle(le_device_config: LeDeviceConfiguration) -> None:
    """Test that get_status returns IDLE when device is not scanning."""
    protocol = LeProtocolV1(le_device_config)
    protocol.connect()
    protocol.write_settings()
    protocol.write_list()

    status = protocol._get_status()
    assert status == _LeStatus.IDLE.value
    protocol.disconnect()


def test_get_status_scanning(le_device_config: LeDeviceConfiguration) -> None:
    """Test that get_status returns SCANNING when device is actively scanning."""
    protocol = LeProtocolV1(le_device_config)
    protocol.connect()
    protocol.write_settings()
    protocol.write_list()

    protocol._encode_send_response(protocol.START_COMMAND)

    status = protocol._get_status()
    assert status == _LeStatus.SCANNING.value
    protocol.disconnect()


def test_scan_status_workflow(le_device_config: LeDeviceConfiguration) -> None:
    """Test the complete scan workflow with status checks."""
    protocol = LeProtocolV1(le_device_config)
    protocol.connect()
    protocol.write_settings()
    protocol.write_list()

    assert protocol._get_status() == _LeStatus.IDLE.value

    protocol._encode_send_response(protocol.START_COMMAND)

    assert protocol._get_status() == _LeStatus.SCANNING.value

    time.sleep(protocol.config._sweep_length_ms * 1.1e-3)

    assert protocol._get_status() == _LeStatus.IDLE.value
    protocol.disconnect()
