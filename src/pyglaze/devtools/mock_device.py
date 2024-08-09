from __future__ import annotations

import json
import struct
import time
from abc import ABC, abstractmethod
from enum import Enum, auto
from pathlib import Path
from time import sleep

import numpy as np
from serial import serialutil

from pyglaze.device.configuration import (
    DeviceConfiguration,
    ForceDeviceConfiguration,
    LeDeviceConfiguration,
)


class MockDevice(ABC):
    """Base class for Mock devices for testing purposes."""

    @abstractmethod
    def __init__(
        self: MockDevice,
        fail_after: float = np.inf,
        n_fails: float = np.inf,
    ) -> None:
        pass


class ForceMockDevice(MockDevice):
    """Mock device for devices using a FORCE lockin for testing purposes."""

    CONFIG_PATH = Path(__file__).parents[1] / "devtools" / "mockup_config.json"
    ENCODING: str = "utf-8"

    def __init__(
        self: ForceMockDevice,
        fail_after: float = np.inf,
        n_fails: float = np.inf,
    ) -> None:
        self.fail_after = fail_after
        self.fails_wanted = n_fails
        self.n_failures = 0
        self.n_scans = 0
        self.rng = np.random.default_rng()
        self.valid_input = True
        self.experiment_running = False

        self._periods = None
        self._frequency = None
        self._sweep_length = None
        if not self.CONFIG_PATH.exists():
            conf = {"periods": None, "frequency": None, "sweep_length_ms": None}
            self.__save(conf)

    @property
    def periods(self: ForceMockDevice) -> int:
        """Number of integration periods."""
        return int(self.__get_val("periods"))

    @periods.setter
    def periods(self: ForceMockDevice, value: int) -> None:
        self.__set_val("periods", value)

    @property
    def frequency(self: ForceMockDevice) -> int:
        """Modulation frequency in Hz."""
        return int(self.__get_val("frequency"))

    @frequency.setter
    def frequency(self: ForceMockDevice, value: int) -> None:
        self.__set_val("frequency", value)

    @property
    def sweep_length(self: ForceMockDevice) -> int:
        """Total sweep length for one pulse."""
        return int(self.__get_val("sweep_length"))

    @sweep_length.setter
    def sweep_length(self: ForceMockDevice, value: int) -> None:
        self.__set_val("sweep_length", value)

    def close(self: ForceMockDevice) -> None:
        """Mock-close the serial connection."""

    def write(self: ForceMockDevice, input_string: bytes) -> None:
        """Mock-write to the serial connection."""
        decoded_input_string = input_string.decode("utf-8")
        split_input_string = decoded_input_string.split(",")
        cmd = split_input_string[0]
        if cmd == "!set timing":
            self.periods = int(split_input_string[1])
            self.frequency = int(split_input_string[2])
        elif cmd == "!set sweep length":
            self.sweep_length = int(split_input_string[1])
        elif cmd == "!s":
            time_pr_point = self.periods / self.frequency
            self.in_waiting = int(self.sweep_length * 1e-3 / time_pr_point)
            self.experiment_running = True
        elif cmd in ["!lut", "!set wave", "!set generator"]:
            pass
        elif cmd != "!dat":
            self.valid_input = False

    def readline(self: ForceMockDevice) -> bytes:
        """Mock-readline from the serial connection."""
        if self.valid_input:
            return self.__run_experiment() if self.experiment_running else b"!A,OK\r"

        return b"A,FAULT\r"

    def read_until(self: ForceMockDevice, expected: bytes = b"\r") -> bytes:  # noqa: ARG002
        """Mock-read_until from the serial connection."""
        random_datapoint = self.__create_random_datapoint
        return random_datapoint.encode(self.ENCODING)

    def __run_experiment(self: ForceMockDevice) -> bytes:
        return_string = "!A,OK\\r"
        return_string += (
            f"!S,ip: {self.periods}, "
            f"Freq: {self.frequency}, "
            f"sl: {self.sweep_length}, "
            f"from: 0.0000, "
            f"to:1.0000\r"
        )
        for _ in range(self.in_waiting):
            return_string += self.__create_random_datapoint
        return_string += "!D,DONE\\r"
        sleep(self.sweep_length * 1e-3)
        self.n_scans += 1
        if self.n_scans > self.fail_after and self.n_failures < self.fails_wanted:
            self.n_failures += 1
            msg = "MOCK_DEVICE: scan failed"
            raise serialutil.SerialException(msg)

        return return_string.encode("utf-8")

    @property
    def __create_random_datapoint(self: ForceMockDevice) -> str:
        radius = self.rng.random() * 10
        theta = self.rng.random() * 360
        return f"!R,{radius},{theta}\r"

    def __save(self: ForceMockDevice, conf: dict) -> None:
        with self.CONFIG_PATH.open("w") as f:
            json.dump(conf, f)

    def __get_val(self: ForceMockDevice, key: str) -> int:
        val: int = getattr(self, f"_{key}")
        if not val:
            with self.CONFIG_PATH.open() as f:
                val = json.load(f)[key]
        return val

    def __set_val(self: ForceMockDevice, key: str, val: str | float) -> None:
        with self.CONFIG_PATH.open() as f:
            config = json.load(f)
            config[key] = val
        setattr(self, f"_{key}", val)
        self.__save(config)


class _LeMockState(Enum):
    IDLE = auto()
    WAITING_FOR_SETTINGS = auto()
    WAITING_FOR_LIST = auto()
    RECEIVED_SETTINGS = auto()
    RECEIVED_LIST = auto()
    RECEIVED_STATUS_REQUEST = auto()
    STARTING_SCAN = auto()
    SCANNING = auto()


class LeMockDevice(MockDevice):
    """Mock device for devices using a Le lockin for testing purposes."""

    ENCODING = "utf-8"
    LI_MODULATION_FREQUENCY = 10000
    TIME_WINDOW = 100e-12
    DAC_BITWIDTH = 2**12

    def __init__(
        self: LeMockDevice, fail_after: float = np.inf, n_fails: float = np.inf
    ) -> None:
        self.fail_after = fail_after
        self.fails_wanted = n_fails
        self.n_failures = 0
        self.n_scans = 0
        self.rng = np.random.default_rng()
        self.state = _LeMockState.IDLE
        self.is_scanning = False
        self.n_scanning_points: int | None = None
        self.integration_periods: int | None = None
        self.use_ema: bool | None = None
        self.scanning_list: list[float] | None = None
        self._scan_start_time: float | None = None

    def write(self: LeMockDevice, input_bytes: bytes) -> None:
        """Mock-write to the serial connection."""
        if self.state == _LeMockState.WAITING_FOR_SETTINGS:
            self._handle_waiting_for_settings(input_bytes)
            return
        if self.state == _LeMockState.WAITING_FOR_LIST:
            self._handle_waiting_for_list(input_bytes)
            return
        if self.state == _LeMockState.IDLE:
            self._handle_idle(input_bytes)
            return
        if self.state == _LeMockState.SCANNING:
            self._handle_scanning(input_bytes)
            return

        raise NotImplementedError

    def read(self: LeMockDevice, size: int) -> bytes:
        """Mock-read from the serial connection."""
        if self.state == _LeMockState.IDLE:
            return self._create_scan_bytes(n_bytes=size)
        raise NotImplementedError

    def read_until(self: LeMockDevice, _: bytes = b"\r") -> bytes:  # noqa: PLR0911
        """Mock-read_until from the serial connection."""
        if self.state == _LeMockState.WAITING_FOR_SETTINGS:
            return "ACK: Ready to receive settings.".encode(self.ENCODING)
        if self.state == _LeMockState.RECEIVED_SETTINGS:
            self.state = _LeMockState.IDLE
            return "ACK: Settings received.".encode(self.ENCODING)
        if self.state == _LeMockState.WAITING_FOR_LIST:
            return "ACK: Ready to receive list.".encode(self.ENCODING)
        if self.state == _LeMockState.RECEIVED_LIST:
            self.state = _LeMockState.IDLE
            return "ACK: List received.".encode(self.ENCODING)
        if self.state == _LeMockState.STARTING_SCAN:
            self.state = _LeMockState.SCANNING
            self.is_scanning = True
            return "ACK: Scan started.".encode(self.ENCODING)
        if self.state == _LeMockState.RECEIVED_STATUS_REQUEST:
            if self._scan_has_finished():
                self.state = _LeMockState.IDLE
                return "ACK: Idle.".encode(self.ENCODING)

            self.state = _LeMockState.SCANNING
            return "Error: Scan is ongoing.".encode(self.ENCODING)

        msg = f"Unknown state: {self.state}"
        raise NotImplementedError(msg)

    def close(self: LeMockDevice) -> None:
        """Mock-close the serial connection."""

    @property
    def _scanning_time(self: LeMockDevice) -> float:
        if self.n_scanning_points and self.integration_periods:
            return (
                self.n_scanning_points
                * self.integration_periods
                / self.LI_MODULATION_FREQUENCY
            )
        msg = "Cannot calculate scanning time when n_scanning_points or integration_periods is None"
        raise ValueError(msg)

    def _handle_idle(self: LeMockDevice, input_bytes: bytes) -> None:
        msg = input_bytes.decode("utf-8")
        if msg == "S":
            self.state = _LeMockState.WAITING_FOR_SETTINGS
        elif msg == "L":
            self.state = _LeMockState.WAITING_FOR_LIST
        elif msg == "G":
            self.state = _LeMockState.STARTING_SCAN
            self._scan_start_time = time.time()
        elif msg == "R":
            self._scan_has_finished()
        else:
            msg = f"Unknown message: {msg}"
            raise NotImplementedError(msg)

    def _handle_scanning(self: LeMockDevice, input_bytes: bytes) -> None:
        msg = input_bytes.decode("utf-8")
        if msg == "H":
            self.state = _LeMockState.RECEIVED_STATUS_REQUEST
            return
        if msg == "R":
            if self._scan_has_finished():
                self.state = _LeMockState.IDLE
            return

        raise NotImplementedError

    def _handle_waiting_for_settings(self: LeMockDevice, input_bytes: bytes) -> None:
        ints = self._decode_ints(input_bytes)
        self.n_scanning_points = ints[0]
        self.integration_periods = ints[1]
        self.use_ema = bool(ints[2])
        self.state = _LeMockState.RECEIVED_SETTINGS

    def _handle_waiting_for_list(self: LeMockDevice, input_bytes: bytes) -> None:
        self.scanning_list = self._decode_floats(input_bytes)
        self.state = _LeMockState.RECEIVED_LIST

    def _decode_ints(self: LeMockDevice, input_bytes: bytes) -> list[int]:
        # Convert every two bytes to a 16-bit integer (assuming little-endian format)
        return [
            struct.unpack("<H", input_bytes[i : i + 2])[0]
            for i in range(0, len(input_bytes), 2)
        ]

    def _decode_floats(self: LeMockDevice, input_bytes: bytes) -> list[float]:
        # Convert every four bytes to a 32-bit float (assuming little-endian format)
        return [
            struct.unpack("<f", input_bytes[i : i + 4])[0]
            for i in range(0, len(input_bytes), 4)
        ]

    def _scan_has_finished(self: LeMockDevice) -> bool:
        if not self.is_scanning:
            return True
        if self._scan_start_time is None:
            msg = "Scan start time is None"
            raise ValueError(msg)
        scan_finished = time.time() - self._scan_start_time > self._scanning_time
        if scan_finished:
            self.is_scanning = False
            self._scan_start_time = None
        return scan_finished

    def _create_scan_bytes(self: LeMockDevice, n_bytes: int) -> bytes:  # noqa: ARG002
        if self.scanning_list is None:
            msg = "Scanning list is None"
            raise ValueError(msg)

        self.n_scans += 1
        if self.n_scans > self.fail_after and self.n_failures < self.fails_wanted:
            self.n_failures += 1
            numbers = np.array([])
        else:
            numbers = np.concatenate(
                (
                    np.array(self.scanning_list) * 100e-12,  # mock time values
                    self.rng.random(2 * len(self.scanning_list)),
                )
            )

        # Each scanning point will generate an X and a Y value (lockin detection)
        return struct.pack("<" + "f" * len(numbers), *numbers)


def list_mock_devices() -> list[str]:
    """List all available mock devices."""
    return [
        "mock_device",
        "mock_device_scan_should_fail",
        "mock_device_fail_first_scan",
    ]


def _mock_device_factory(config: DeviceConfiguration) -> MockDevice:
    mock_class = _get_mock_class(config)
    if config.amp_port == "mock_device_scan_should_fail":
        return mock_class(fail_after=0)
    if config.amp_port == "mock_device":
        return mock_class()
    if config.amp_port == "mock_device_fail_first_scan":
        return mock_class(fail_after=0, n_fails=1)

    msg = f"Unknown mock device requested: {config.amp_port}. Valid options are: {list_mock_devices()}"
    raise ValueError(msg)


def _get_mock_class(config: DeviceConfiguration) -> type[MockDevice]:
    if isinstance(config, ForceDeviceConfiguration):
        return ForceMockDevice
    if isinstance(config, LeDeviceConfiguration):
        return LeMockDevice

    msg = f"Unsupported configuration type: {type(config).__name__}"
    raise ValueError(msg)
