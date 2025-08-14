from __future__ import annotations

import contextlib
import logging
import time
from enum import Enum
from functools import cached_property
from math import modf
from typing import TYPE_CHECKING, ClassVar

import numpy as np
import serial
from bitstring import BitArray
from serial import serialutil

from pyglaze.device.configuration import Interval, LeDeviceConfiguration
from pyglaze.device.protocol import Protocol
from pyglaze.devtools.mock_device import _mock_device_factory
from pyglaze.helpers.utilities import LOGGER_NAME, _BackoffRetry

if TYPE_CHECKING:
    from pyglaze.devtools.mock_device import LeMockDevice
    from pyglaze.helpers._types import FloatArray


class DeviceComError(Exception):
    """Raised when an error occurs in the communication with the device."""

    def __init__(self: DeviceComError, message: str) -> None:
        super().__init__(message)


class _LeStatus(Enum):
    SCANNING = "Error: Scan is ongoing."
    IDLE = "ACK: Idle."


class LeProtocolV1(Protocol):
    """Protocol version 1 implementation based on LeAmpCom logic.

    This is the current protocol used by deployed devices.
    """

    ENCODING: ClassVar[str] = "utf-8"
    OK_RESPONSE: ClassVar[str] = "ACK"
    START_COMMAND: ClassVar[str] = "G"
    FETCH_COMMAND: ClassVar[str] = "R"
    STATUS_COMMAND: ClassVar[str] = "H"
    SEND_LIST_COMMAND: ClassVar[str] = "L"
    SEND_SETTINGS_COMMAND: ClassVar[str] = "S"
    SERIAL_NUMBER_COMMAND: ClassVar[str] = "s"
    FIRMWARE_VERSION_COMMAND: ClassVar[str] = "v"

    def __init__(self: LeProtocolV1, config: LeDeviceConfiguration) -> None:
        """Initialize protocol with device configuration."""
        super().__init__(config)
        self.config: LeDeviceConfiguration = config
        self.__ser: serial.Serial | LeMockDevice | None = None

    @property
    def protocol_version(self: LeProtocolV1) -> str:
        """Get the protocol version identifier."""
        return "v1"

    @cached_property
    def scanning_points(self: LeProtocolV1) -> int:
        """Number of scanning points."""
        return self.config.n_points

    @cached_property
    def scanning_list(self: LeProtocolV1) -> list[float]:
        """Generate scanning list from intervals."""
        scanning_list: list[float] = []
        for interval, n_points in zip(
            self._intervals,
            _points_per_interval(self.scanning_points, self._intervals),
        ):
            scanning_list.extend(
                np.linspace(
                    interval.lower,
                    interval.upper,
                    n_points,
                    endpoint=len(self._intervals) == 1,
                ),
            )
        return scanning_list

    @cached_property
    def bytes_to_receive(self: LeProtocolV1) -> int:
        """Number of bytes to receive for a single scan.

        We expect to receive 3 arrays of floats (delays, X and Y), each with self.scanning_points elements.
        """
        return self.scanning_points * 12

    @property
    def serial_number_bytes(self: LeProtocolV1) -> int:
        """Number of bytes to receive for a serial number.

        Serial number has the form "<CHARACTER>-<4_DIGITS>, hence expect 6 bytes."
        """
        return 6

    @cached_property
    def _intervals(self: LeProtocolV1) -> list[Interval]:
        """Intervals squished into effective DAC range."""
        return self.config.scan_intervals or [Interval(lower=0.0, upper=1.0)]

    def connect(self: LeProtocolV1) -> None:
        """Establish connection to the device."""
        self.__ser = _serial_factory(self.config)

    def disconnect(self: LeProtocolV1) -> None:
        """Close connection to the device."""
        with contextlib.suppress(AttributeError):
            if self.__ser is not None:
                self.__ser.close()
                self.__ser = None

    def write_settings(self: LeProtocolV1) -> str:
        """Write device settings (list length, integration periods, use_ema)."""
        if self.__ser is None:
            msg = "Device not connected. Call connect() first."
            raise DeviceComError(msg)

        self._encode_send_response(self.SEND_SETTINGS_COMMAND)
        self._raw_byte_send_ints(
            [self.scanning_points, self.config.integration_periods, self.config.use_ema]
        )
        return self._get_response(self.SEND_SETTINGS_COMMAND)

    def write_list(self: LeProtocolV1) -> str:
        """Write scanning list to device."""
        if self.__ser is None:
            msg = "Device not connected. Call connect() first."
            raise DeviceComError(msg)

        self._encode_send_response(self.SEND_LIST_COMMAND)
        self._raw_byte_send_floats(self.scanning_list)
        return self._get_response(self.SEND_LIST_COMMAND)

    def start_scan(
        self: LeProtocolV1,
    ) -> tuple[str, FloatArray, FloatArray, FloatArray]:
        """Start a scan and return the results."""
        if self.__ser is None:
            msg = "Device not connected. Call connect() first."
            raise DeviceComError(msg)

        self._encode_send_response(self.START_COMMAND)
        self._await_scan_finished()
        times, Xs, Ys = self._read_scan()

        radii, angles = self._convert_to_r_angle(Xs, Ys)
        return self.START_COMMAND, np.array(times), np.array(radii), np.array(angles)

    def get_status(self: LeProtocolV1) -> str:
        """Get current device status."""
        if self.__ser is None:
            msg = "Device not connected. Call connect() first."
            raise DeviceComError(msg)

        response = self._encode_send_response(self.STATUS_COMMAND, check_ack=False)

        if response == _LeStatus.SCANNING.value:
            return _LeStatus.SCANNING.value
        if response == _LeStatus.IDLE.value:
            return _LeStatus.IDLE.value
        msg = f"Unknown status: {response}"
        raise DeviceComError(msg)

    def fetch_data(self: LeProtocolV1) -> tuple[list[float], list[float], list[float]]:
        """Fetch scan data from device."""
        if self.__ser is None:
            msg = "Device not connected. Call connect() first."
            raise DeviceComError(msg)

        return self._read_scan()

    def get_serial_number(self: LeProtocolV1) -> str:
        """Get device serial number."""
        return "X-9999"
        # self._encode_and_send(self.SERIAL_NUMBER_COMMAND)   # noqa: ERA001
        # return self.__ser.read(self.serial_number_bytes).decode(self.ENCODING)  # noqa: ERA001

    def get_firmware_version(self: LeProtocolV1) -> str:
        """Get device firmware version."""
        if self.__ser is None:
            msg = "Device not connected. Call connect() first."
            raise DeviceComError(msg)

        self._encode_and_send(self.FIRMWARE_VERSION_COMMAND)
        return self.__ser.read_until().decode(self.ENCODING).strip()

    def supports_feature(self: LeProtocolV1, feature_name: str) -> bool:
        """Check if this protocol version supports a specific feature."""
        # Protocol v1 supports basic features
        v1_features = {
            "basic_scanning",
            "settings_write",
            "list_write",
            "status_check",
            "firmware_version",
            "serial_number",
        }
        return feature_name in v1_features

    def _convert_to_r_angle(
        self: LeProtocolV1, Xs: list, Ys: list
    ) -> tuple[FloatArray, FloatArray]:
        """Convert X,Y coordinates to radius and angle."""
        r = np.sqrt(np.array(Xs) ** 2 + np.array(Ys) ** 2)
        angle = np.arctan2(np.array(Ys), np.array(Xs))
        return r, np.rad2deg(angle)

    def _encode_send_response(
        self: LeProtocolV1, command: str, *, check_ack: bool = True
    ) -> str:
        """Send command and get response."""
        self._encode_and_send(command)
        return self._get_response(command, check_ack=check_ack)

    def _encode_and_send(self: LeProtocolV1, command: str) -> None:
        """Encode and send command to device."""
        if self.__ser is None:
            msg = "Device not connected. Call connect() first."
            raise DeviceComError(msg)
        self.__ser.write(command.encode(self.ENCODING))

    def _raw_byte_send_ints(self: LeProtocolV1, values: list[int]) -> None:
        """Send integer values as raw bytes."""
        if self.__ser is None:
            msg = "Device not connected. Call connect() first."
            raise DeviceComError(msg)
        c = BitArray()
        for value in values:
            c.append(BitArray(uintle=value, length=16))
        self.__ser.write(c.tobytes())

    def _raw_byte_send_floats(self: LeProtocolV1, values: list[float]) -> None:
        """Send float values as raw bytes."""
        if self.__ser is None:
            msg = "Device not connected. Call connect() first."
            raise DeviceComError(msg)
        c = BitArray()
        for value in values:
            c.append(BitArray(floatle=value, length=32))
        self.__ser.write(c.tobytes())

    def _await_scan_finished(self: LeProtocolV1) -> None:
        """Wait for scan to finish."""
        time.sleep(self.config._sweep_length_ms * 1.0e-3)  # noqa: SLF001
        status = self._get_status()

        while status == _LeStatus.SCANNING.value:
            time.sleep(self.config._sweep_length_ms * 1e-3 * 0.01)  # noqa: SLF001
            status = self._get_status()

    @_BackoffRetry(
        backoff_base=1e-2, max_tries=3, logger=logging.getLogger(LOGGER_NAME)
    )
    def _get_response(
        self: LeProtocolV1, command: str, *, check_ack: bool = True
    ) -> str:
        """Get response from device with retry logic."""
        if self.__ser is None:
            msg = "Device not connected. Call connect() first."
            raise DeviceComError(msg)

        response = self.__ser.read_until().decode(self.ENCODING).strip()

        if len(response) == 0:
            msg = f"Command: '{command}'. Empty response received"
            raise serialutil.SerialException(msg)
        if check_ack and response[: len(self.OK_RESPONSE)] != self.OK_RESPONSE:
            msg = f"Command: '{command}'. Expected response '{self.OK_RESPONSE}', received: '{response}'"
            raise DeviceComError(msg)
        return response

    @_BackoffRetry(
        backoff_base=1e-2, max_tries=5, logger=logging.getLogger(LOGGER_NAME)
    )
    def _read_scan(self: LeProtocolV1) -> tuple[list[float], list[float], list[float]]:
        """Read scan data from device."""
        if self.__ser is None:
            msg = "Device not connected. Call connect() first."
            raise DeviceComError(msg)

        self._encode_and_send(self.FETCH_COMMAND)
        scan_bytes = self.__ser.read(self.bytes_to_receive)

        if len(scan_bytes) != self.bytes_to_receive:
            msg = f"received {len(scan_bytes)} bytes, expected {self.bytes_to_receive}"
            raise serialutil.SerialException(msg)

        times = self._bytes_to_floats(scan_bytes, 0, self.scanning_points * 4)
        Xs = self._bytes_to_floats(
            scan_bytes, self.scanning_points * 4, self.scanning_points * 8
        )
        Ys = self._bytes_to_floats(
            scan_bytes, self.scanning_points * 8, self.scanning_points * 12
        )
        return times, Xs, Ys

    def _bytes_to_floats(
        self: LeProtocolV1, scan_bytes: bytes, from_idx: int, to_idx: int
    ) -> list[float]:
        """Convert bytes to float values."""
        return [
            BitArray(bytes=scan_bytes[d : d + 4]).floatle
            for d in range(from_idx, to_idx, 4)
        ]

    def _get_status(self: LeProtocolV1) -> str:
        """Get device status with internal response handling."""
        return self._encode_send_response(self.STATUS_COMMAND, check_ack=False)


def _serial_factory(config: LeDeviceConfiguration) -> serial.Serial | LeMockDevice:
    """Create serial connection or mock device based on config."""
    if "mock_device" in config.amp_port:
        return _mock_device_factory(config)

    return serial.Serial(
        port=config.amp_port,
        baudrate=config.amp_baudrate,
        timeout=config.amp_timeout_seconds,
    )


def _points_per_interval(n_points: int, intervals: list[Interval]) -> list[int]:
    """Divides a total number of points between intervals."""
    interval_lengths = [interval.length for interval in intervals]
    total_length = sum(interval_lengths)

    points_per_interval_floats = [
        n_points * length / total_length for length in interval_lengths
    ]
    points_per_interval = [int(e) for e in points_per_interval_floats]

    # We must distribute the remainder from the int operation to get the right amount of total points
    remainders = [modf(num)[0] for num in points_per_interval_floats]
    sorted_indices = np.flip(np.argsort(remainders))
    for i in range(int(0.5 + np.sum(remainders))):
        points_per_interval[sorted_indices[i]] += 1

    return points_per_interval
