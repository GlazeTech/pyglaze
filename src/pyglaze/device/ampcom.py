from __future__ import annotations

import contextlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from math import modf
from typing import TYPE_CHECKING, Callable, ClassVar, overload

import numpy as np
import serial
from bitstring import BitArray
from serial import serialutil

from pyglaze.device.configuration import (
    DeviceConfiguration,
    ForceDeviceConfiguration,
    Interval,
    LeDeviceConfiguration,
)
from pyglaze.devtools.mock_device import _mock_device_factory
from pyglaze.helpers.utilities import LOGGER_NAME, _BackoffRetry

if TYPE_CHECKING:
    from pyglaze.devtools.mock_device import (
        ForceMockDevice,
        LeMockDevice,
        MockDevice,
    )
    from pyglaze.helpers.types import FloatArray


@dataclass
class _ForceAmpCom:
    config: ForceDeviceConfiguration
    CONT_SCAN_UPDATE_FREQ: float = 1  # seconds
    __ser: ForceMockDevice | serial.Serial = field(init=False)

    ENCODING: ClassVar[str] = "utf-8"
    OK_RESPONSE: ClassVar[str] = "!A,OK"
    N_POINTS: ClassVar[int] = 10000
    DAC_BITWIDTH: ClassVar[int] = 65535  # bit-width of amp DAC
    # DO NOT change - antennas will break.
    MIN_ALLOWED_MOD_VOLTAGE: ClassVar[float] = -1.0
    MAX_ALLOWED_MOD_VOLTAGE: ClassVar[float] = 0.5

    @cached_property
    def scanning_points(self: _ForceAmpCom) -> int:
        time_pr_point = (
            self.config.integration_periods / self.config.modulation_frequency
        )
        return int(self.config.sweep_length_ms * 1e-3 / time_pr_point)

    @cached_property
    def _squished_intervals(self: _ForceAmpCom) -> list[Interval]:
        """Intervals squished into effective DAC range."""
        return _squish_intervals(
            intervals=self.config.scan_intervals or [Interval(lower=0.0, upper=1.0)],
            lower_bound=self.config.dac_lower_bound,
            upper_bound=self.config.dac_upper_bound,
            bitwidth=self.DAC_BITWIDTH,
        )

    @cached_property
    def times(self: _ForceAmpCom) -> FloatArray:
        return _delay_from_intervals(
            delayunit=lambda x: x,
            intervals=self.config.scan_intervals,
            points_per_interval=_points_per_interval(
                self.scanning_points, self._squished_intervals
            ),
        )

    @cached_property
    def scanning_list(self: _ForceAmpCom) -> list[float]:
        scanning_list: list[float] = []
        for interval, n_points in zip(
            self._squished_intervals,
            _points_per_interval(self.N_POINTS, self._squished_intervals),
        ):
            scanning_list.extend(
                np.linspace(interval.lower, interval.upper, n_points, endpoint=False)
            )

        return scanning_list

    @property
    def datapoints_per_update(self: _ForceAmpCom) -> int:
        return int(
            self.CONT_SCAN_UPDATE_FREQ
            / (self.config.integration_periods / self.config.modulation_frequency)
        )

    def __post_init__(self: _ForceAmpCom) -> None:
        self.__ser = _serial_factory(self.config)

    def __del__(self: _ForceAmpCom) -> None:
        """Closes connection when class instance goes out of scope."""
        with contextlib.suppress(AttributeError):
            # If the serial device does not exist, self.__ser is never created - hence catch
            self.__ser.close()

    def write_all(self: _ForceAmpCom) -> list[str]:
        responses = []
        responses.append(self.write_period_and_frequency())
        responses.append(self.write_sweep_length())
        responses.append(self.write_waveform())
        responses.append(self.write_modulation_voltage())
        responses.extend(self.write_list())
        return responses

    def write_period_and_frequency(self: _ForceAmpCom) -> str:
        s = f"!set timing,{self.config.integration_periods},{self.config.modulation_frequency}\r"
        return self._encode_send_response(s)

    def write_sweep_length(self: _ForceAmpCom) -> str:
        s = f"!set sweep length,{self.config.sweep_length_ms}\r"
        return self._encode_send_response(s)

    def write_waveform(self: _ForceAmpCom) -> str:
        s = f"!set wave,{self.config.modulation_waveform}\r"
        return self._encode_send_response(s)

    def write_modulation_voltage(self: _ForceAmpCom) -> str:
        min_v = self.config.min_modulation_voltage
        max_v = self.config.max_modulation_voltage
        crit1 = self.MIN_ALLOWED_MOD_VOLTAGE <= min_v <= self.MAX_ALLOWED_MOD_VOLTAGE
        crit2 = self.MIN_ALLOWED_MOD_VOLTAGE <= max_v <= self.MAX_ALLOWED_MOD_VOLTAGE

        if crit1 and crit2:
            s = f"!set generator,{min_v},{max_v}\r"
            return self._encode_send_response(s)

        msg = f"Modulation voltages min: {min_v:.1f}, max: {max_v:.1f} not allowed."
        raise ValueError(msg)

    def write_list(self: _ForceAmpCom) -> list[str]:
        for iteration, entry in enumerate(self.scanning_list):
            string = f"!lut,{iteration},{entry}\r"
            self._encode_and_send(string)
        return self._get_response().split("\r")

    def start_scan(self: _ForceAmpCom) -> tuple[str, np.ndarray]:
        start_command = "!s,\r"
        self._encode_and_send(start_command)
        responses = self._get_response().split("\r")
        output_array = np.zeros((self.scanning_points, 3))
        output_array[:, 0] = self.times
        iteration = 0
        for entry in responses:
            if "!R" in entry:
                radius, angle = self._format_output(entry)
                output_array[iteration, 1] = radius
                output_array[iteration, 2] = angle
                iteration += 1
            elif "!D" in entry:
                break
        return start_command, output_array

    def start_continuous_scan(self: _ForceAmpCom) -> tuple[str, list[str]]:
        start_command = "!dat,1\r"
        self._encode_and_send(start_command)
        # Call self._read_until() twice, because amp returns !A,OK twice for
        # continuous output (for some unknown reason)
        responses = [self._read_until(expected=b"\r") for _ in range(2)]
        return start_command, responses

    def stop_continuous_scan(self: _ForceAmpCom) -> tuple[str, str]:
        start_command = "!dat,0\r"
        self._encode_and_send(start_command)
        response = self._read_until(expected=b"!A,OK\r")
        return start_command, response

    def read_continuous_data(self: _ForceAmpCom) -> FloatArray:
        output_array = np.zeros((self.datapoints_per_update, 3))
        output_array[:, 0] = np.linspace(0, 1, self.datapoints_per_update)
        for iteration in range(self.datapoints_per_update):
            amp_output = self._read_until(expected=b"\r")
            radius, angle = self._format_output(amp_output)
            output_array[iteration, 1] = radius
            output_array[iteration, 2] = angle
        return output_array

    def _encode_send_response(self: _ForceAmpCom, command: str) -> str:
        self._encode_and_send(command)
        return self._get_response()

    def _encode_and_send(self: _ForceAmpCom, command: str) -> None:
        self.__ser.write(command.encode(self.ENCODING))

    @_BackoffRetry(backoff_base=0.2, logger=logging.getLogger(LOGGER_NAME))
    def _get_response(self: _ForceAmpCom) -> str:
        r = self.__ser.readline().decode(self.ENCODING).strip()
        if r[: len(self.OK_RESPONSE)] != self.OK_RESPONSE:
            msg = f"Expected response '{self.OK_RESPONSE}', received: '{r}'"
            raise serialutil.SerialException(msg)

        return r

    def _read_until(self: _ForceAmpCom, expected: bytes) -> str:
        return self.__ser.read_until(expected=expected).decode(self.ENCODING).strip()

    def _format_output(self: _ForceAmpCom, amp_output: str) -> tuple[float, float]:
        """Format output from Force LIA to radius and angle."""
        response_list = amp_output.split(",")
        return float(response_list[1]), float(response_list[2])


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

    def __post_init__(self: _LeAmpCom) -> None:
        self.__ser = _serial_factory(self.config)

    def __del__(self: _LeAmpCom) -> None:
        """Closes connection when class instance goes out of scope."""
        with contextlib.suppress(AttributeError):
            # If the serial device does not exist, self.__ser is never created - hence catch
            self.__ser.close()

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
        return self._get_response()

    def write_list(self: _LeAmpCom) -> str:
        self._encode_send_response(self.SEND_LIST_COMMAND)
        self._raw_byte_send_floats(self.scanning_list)
        return self._get_response()

    def start_scan(self: _LeAmpCom) -> tuple[str, np.ndarray, np.ndarray, np.ndarray]:
        self._encode_send_response(self.START_COMMAND)
        self._await_scan_finished()
        times, Xs, Ys = self._read_scan()

        radii, angles = self._convert_to_r_angle(Xs, Ys)
        return self.START_COMMAND, np.array(times), np.array(radii), np.array(angles)

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
        return self._get_response()

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

    @_BackoffRetry(backoff_base=0.05, logger=logging.getLogger(LOGGER_NAME))
    def _get_response(self: _LeAmpCom) -> str:
        return self.__ser.read_until().decode(self.ENCODING).strip()

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


@overload
def _serial_factory(
    config: ForceDeviceConfiguration,
) -> serial.Serial | ForceMockDevice: ...


@overload
def _serial_factory(config: LeDeviceConfiguration) -> serial.Serial | LeMockDevice: ...


def _serial_factory(config: DeviceConfiguration) -> serial.Serial | MockDevice:
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
