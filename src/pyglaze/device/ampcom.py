from __future__ import annotations

import contextlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from math import modf
from typing import TYPE_CHECKING, Callable, ClassVar

import numpy as np
import serial
from bitstring import BitArray
from serial import serialutil

from pyglaze.device.configuration import (
    DeviceConfiguration,
    Interval,
    LeDeviceConfiguration,
)
from pyglaze.devtools.mock_device import _mock_device_factory
from pyglaze.helpers.utilities import LOGGER_NAME, _BackoffRetry

if TYPE_CHECKING:
    from pyglaze.devtools.mock_device import LeMockDevice
    from pyglaze.helpers._types import FloatArray


class DeviceComError(Exception):
    """Raised when an error occurs in the communication with the device."""

    def __init__(self: DeviceComError, message: str) -> None:
        super().__init__(message)


@dataclass
class _LeAmpCom:
    config: LeDeviceConfiguration

    __ser: serial.Serial | LeMockDevice = field(init=False)

    ENCODING: ClassVar[str] = "utf-8"

    OK_RESPONSE: ClassVar[str] = "ACK"
    START_COMMAND: ClassVar[str] = "G"
    FETCH_COMMAND: ClassVar[str] = "R"
    STATUS_COMMAND: ClassVar[str] = "H"
    SEND_LIST_COMMAND: ClassVar[str] = "L"
    SEND_SETTINGS_COMMAND: ClassVar[str] = "S"
    SERIAL_NUMBER_COMMAND: ClassVar[str] = "s"
    FIRMWARE_VERSION_COMMAND: ClassVar[str] = "v"

    @cached_property
    def scanning_points(self: _LeAmpCom) -> int:
        return self.config.n_points

    @cached_property
    def scanning_list(self: _LeAmpCom) -> list[float]:
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
    def bytes_to_receive(self: _LeAmpCom) -> int:
        """Number of bytes to receive for a single scan.

        We expect to receive 3 arrays of floats (delays, X and Y), each with self.scanning_points elements.
        """
        return self.scanning_points * 12

    @property
    def serial_number_bytes(self: _LeAmpCom) -> int:
        """Number of bytes to receive for a serial number.

        Serial number has the form "<CHARACTER>-<4_DIGITS>, hence expect 6 bytes."
        """
        return 6

    def __post_init__(self: _LeAmpCom) -> None:
        self.__ser = _serial_factory(self.config)

    def __del__(self: _LeAmpCom) -> None:
        """Closes connection when class instance goes out of scope."""
        self.disconnect()

    def write_all(self: _LeAmpCom) -> list[str]:
        responses: list[str] = []
        responses.append(self.write_list_length_and_integration_periods_and_use_ema())
        responses.append(self.write_list())
        return responses

    def write_list_length_and_integration_periods_and_use_ema(self: _LeAmpCom) -> str:
        self._encode_send_response(self.SEND_SETTINGS_COMMAND)
        self._raw_byte_send_ints(
            [self.scanning_points, self.config.integration_periods, self.config.use_ema]
        )
        return self._get_response(self.SEND_SETTINGS_COMMAND)

    def write_list(self: _LeAmpCom) -> str:
        self._encode_send_response(self.SEND_LIST_COMMAND)
        self._raw_byte_send_floats(self.scanning_list)
        return self._get_response(self.SEND_LIST_COMMAND)

    def start_scan(self: _LeAmpCom) -> tuple[str, np.ndarray, np.ndarray, np.ndarray]:
        self._encode_send_response(self.START_COMMAND)
        self._await_scan_finished()
        times, Xs, Ys = self._read_scan()

        radii, angles = self._convert_to_r_angle(Xs, Ys)
        return self.START_COMMAND, np.array(times), np.array(radii), np.array(angles)

    def disconnect(self: _LeAmpCom) -> None:
        """Closes connection when class instance goes out of scope."""
        with contextlib.suppress(AttributeError):
            # If the serial device does not exist, self.__ser is never created - hence catch
            self.__ser.close()

    def get_serial_number(self: _LeAmpCom) -> str:
        """Get the serial number of the connected device."""
        return "X-9999"
        # self._encode_and_send(self.SERIAL_NUMBER_COMMAND)   # noqa: ERA001
        # return self.__ser.read(self.serial_number_bytes).decode(self.ENCODING)  # noqa: ERA001

    def get_firmware_version(self: _LeAmpCom) -> str:
        """Get the firmware version of the connected device."""
        self._encode_and_send(self.FIRMWARE_VERSION_COMMAND)
        return self.__ser.read_until().decode(self.ENCODING).strip()

    @cached_property
    def _intervals(self: _LeAmpCom) -> list[Interval]:
        """Intervals squished into effective DAC range."""
        return self.config.scan_intervals or [Interval(lower=0.0, upper=1.0)]

    def _convert_to_r_angle(
        self: _LeAmpCom, Xs: list, Ys: list
    ) -> tuple[FloatArray, FloatArray]:
        r = np.sqrt(np.array(Xs) ** 2 + np.array(Ys) ** 2)
        angle = np.arctan2(np.array(Ys), np.array(Xs))
        return r, np.rad2deg(angle)

    def _encode_send_response(self: _LeAmpCom, command: str) -> str:
        self._encode_and_send(command)
        return self._get_response(command)

    def _encode_and_send(self: _LeAmpCom, command: str) -> None:
        self.__ser.write(command.encode(self.ENCODING))

    def _raw_byte_send_ints(self: _LeAmpCom, values: list[int]) -> None:
        c = BitArray()
        for value in values:
            c.append(BitArray(uintle=value, length=16))
        self.__ser.write(c.tobytes())

    def _raw_byte_send_floats(self: _LeAmpCom, values: list[float]) -> None:
        c = BitArray()
        for value in values:
            c.append(BitArray(floatle=value, length=32))
        self.__ser.write(c.tobytes())

    def _await_scan_finished(self: _LeAmpCom) -> None:
        time.sleep(self.config._sweep_length_ms * 1.0e-3)  # noqa: SLF001, access to private attribute for backwards compatibility
        status = self._get_status()

        while status == _LeStatus.SCANNING:
            time.sleep(self.config._sweep_length_ms * 1e-3 * 0.01)  # noqa: SLF001, access to private attribute for backwards compatibility
            status = self._get_status()

    @_BackoffRetry(
        backoff_base=1e-2, max_tries=3, logger=logging.getLogger(LOGGER_NAME)
    )
    def _get_response(self: _LeAmpCom, command: str) -> str:
        response = self.__ser.read_until().decode(self.ENCODING).strip()

        if len(response) == 0:
            msg = f"Command: '{command}'. Empty response received"
            raise serialutil.SerialException(msg)
        if response[: len(self.OK_RESPONSE)] != self.OK_RESPONSE:
            msg = f"Command: '{command}'. Expected response '{self.OK_RESPONSE}', received: '{response}'"
            raise DeviceComError(msg)
        return response

    @_BackoffRetry(
        backoff_base=1e-2, max_tries=5, logger=logging.getLogger(LOGGER_NAME)
    )
    def _read_scan(self: _LeAmpCom) -> tuple[list[float], list[float], list[float]]:
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
        self: _LeAmpCom, scan_bytes: bytes, from_idx: int, to_idx: int
    ) -> list[float]:
        return [
            BitArray(bytes=scan_bytes[d : d + 4]).floatle
            for d in range(from_idx, to_idx, 4)
        ]

    def _get_status(self: _LeAmpCom) -> _LeStatus:
        msg = self._encode_send_response(self.STATUS_COMMAND)
        if msg == _LeStatus.SCANNING.value:
            return _LeStatus.SCANNING
        if msg == _LeStatus.IDLE.value:
            return _LeStatus.IDLE
        msg = f"Unknown status: {msg}"
        raise ValueError(msg)


class _LeStatus(Enum):
    SCANNING = "Error: Scan is ongoing."
    IDLE = "ACK: Idle."


def _serial_factory(config: DeviceConfiguration) -> serial.Serial | LeMockDevice:
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


def _squish_intervals(
    intervals: list[Interval], lower_bound: int, upper_bound: int, bitwidth: int
) -> list[Interval]:
    """Squish scanning intervals into effective DAC range."""
    lower = lower_bound / bitwidth
    upper = upper_bound / bitwidth

    def f(x: float) -> float:
        return lower + (upper - lower) * x

    return [Interval(f(interval.lower), f(interval.upper)) for interval in intervals]


def _delay_from_intervals(
    delayunit: Callable[[FloatArray], FloatArray],
    intervals: list[Interval],
    points_per_interval: list[int],
) -> FloatArray:
    """Convert a list of intervals to a list of delay times."""
    times: list[float] = []
    for interval, n_points in zip(intervals, points_per_interval):
        times.extend(
            delayunit(
                np.linspace(interval.lower, interval.upper, n_points, endpoint=False)
            )
        )
    return np.array(times)
