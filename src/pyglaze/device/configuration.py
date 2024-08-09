from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, ClassVar, TypeVar

if TYPE_CHECKING:
    from pathlib import Path

T = TypeVar("T", bound="DeviceConfiguration")


@dataclass
class Interval:
    """An interval with a lower and upper bounds between 0 and 1 to scan."""

    lower: float
    upper: float

    @property
    def length(self: Interval) -> float:
        """The length of the interval."""
        return abs(self.upper - self.lower)

    @classmethod
    def from_dict(cls: type[Interval], d: dict) -> Interval:
        """Create an instance of the Interval class from a dictionary.

        Args:
            d (dict): The dictionary containing the interval data.

        Returns:
            Interval: An instance of the Interval class.
        """
        return cls(**d)

    def __post_init__(self: Interval) -> None:  # noqa: D105
        if not 0.0 <= self.lower <= 1.0:
            msg = "Interval: Bounds must be between 0 and 1"
            raise ValueError(msg)
        if not 0.0 <= self.upper <= 1.0:
            msg = "Interval: Bounds must be between 0 and 1"
            raise ValueError(msg)
        if self.upper == self.lower:
            msg = "Interval: Bounds cannot be equal"
            raise ValueError(msg)


class DeviceConfiguration(ABC):
    """Base class for device configurations."""

    amp_timeout_seconds: float
    amp_port: str
    amp_baudrate: ClassVar[int]

    @property
    @abstractmethod
    def _sweep_length_ms(self: DeviceConfiguration) -> float:
        """The length of the sweep in milliseconds."""

    @abstractmethod
    def save(self: DeviceConfiguration, path: Path) -> str:
        """Save a DeviceConfiguration to a file."""

    @classmethod
    @abstractmethod
    def from_dict(cls: type[T], amp_config: dict) -> T:
        """Create a DeviceConfiguration from a dict."""

    @classmethod
    @abstractmethod
    def load(cls: type[T], file_path: Path) -> T:
        """Load a DeviceConfiguration from a file."""


@dataclass
class ForceDeviceConfiguration(DeviceConfiguration):
    """Represents a configuration that can be sent to the lock-in amp for scans.

    Args:
        amp_port: The name of the serial port the amp is connected to.
        sweep_length_ms: The length of the sweep in milliseconds.
        scan_intervals: The intervals to scan.
        integration_periods: The number of integration periods to use.
        modulation_frequency: The frequency of the modulation in Hz.
        dac_lower_bound: The lower bound of the modulation voltage in bits.
        dac_upper_bound: The upper bound of the modulation voltage in bits.
        min_modulation_voltage: The minimum modulation voltage in volts.
        max_modulation_voltage: The maximum modulation voltage in volts.
        modulation_waveform: The waveform to use for modulation.
        amp_timeout_seconds: The timeout for the amp in seconds.
    """

    amp_port: str
    sweep_length_ms: float
    scan_intervals: list[Interval] = field(default_factory=lambda: [Interval(0.0, 1.0)])
    integration_periods: int = 100
    modulation_frequency: int = 10000  # Hz
    dac_lower_bound: int = 6400
    dac_upper_bound: int = 59300
    min_modulation_voltage: float = -1.0  # V
    max_modulation_voltage: float = 0.5  # V
    modulation_waveform: str = "square"
    amp_timeout_seconds: float = 0.05

    amp_baudrate: ClassVar[int] = 1200000  # bit/s

    @property
    def _sweep_length_ms(self: ForceDeviceConfiguration) -> float:
        return self.sweep_length_ms

    def save(self: ForceDeviceConfiguration, path: Path) -> str:
        """Save a DeviceConfiguration to a file.

        Args:
            path: The path to save the configuration to.

        Returns:
            str: Final path component of the saved file, without the extension.

        """
        with path.open("w") as f:
            json.dump(asdict(self), f, indent=4, sort_keys=True)

        return path.stem

    @classmethod
    def from_dict(
        cls: type[ForceDeviceConfiguration], amp_config: dict
    ) -> ForceDeviceConfiguration:
        """Create a DeviceConfiguration from a dict.

        Args:
            amp_config: An amp configuration in dict form.

        Raises:
            ValueError: If the dictionary is empty.

        Returns:
            DeviceConfiguration: A DeviceConfiguration object.
        """
        return _config_w_intervals_from_dict(cls, amp_config)

    @classmethod
    def load(
        cls: type[ForceDeviceConfiguration], file_path: Path
    ) -> ForceDeviceConfiguration:
        """Load a DeviceConfiguration from a file.

        Args:
            file_path: The path to the file to load.

        Returns:
            DeviceConfiguration: A DeviceConfiguration object.
        """
        with file_path.open() as f:
            configuration_dict = json.load(f)
        return cls.from_dict(configuration_dict)


@dataclass
class LeDeviceConfiguration(DeviceConfiguration):
    """Represents a configuration that can be sent to a Le-type lock-in amp for scans.

    Args:
        amp_port: The name of the serial port the amp is connected to.
        use_ema: Whether to use en exponentially moving average filter during lockin detection.
        n_points: The number of points to scan.
        scan_intervals: The intervals to scan.
        integration_periods: The number of integration periods per datapoint to use.
        amp_timeout_seconds: The timeout for the connection to the amp in seconds.
    """

    amp_port: str
    use_ema: bool = True
    n_points: int = 1000
    scan_intervals: list[Interval] = field(default_factory=lambda: [Interval(0.0, 1.0)])
    integration_periods: int = 10
    amp_timeout_seconds: float = 0.2
    modulation_frequency: int = 10000  # Hz

    amp_baudrate: ClassVar[int] = 1000000  # bit/s

    @property
    def _sweep_length_ms(self: LeDeviceConfiguration) -> float:
        return self.n_points * self._time_constant_ms

    @property
    def _time_constant_ms(self: LeDeviceConfiguration) -> float:
        return 1e3 * self.integration_periods / self.modulation_frequency

    def save(self: LeDeviceConfiguration, path: Path) -> str:
        """Save a LeDeviceConfiguration to a file.

        Args:
            path: The path to save the configuration to.

        Returns:
            str: Final path component of the saved file, without the extension.

        """
        with path.open("w") as f:
            json.dump(asdict(self), f, indent=4, sort_keys=True)

        return path.stem

    @classmethod
    def from_dict(
        cls: type[LeDeviceConfiguration], amp_config: dict
    ) -> LeDeviceConfiguration:
        """Create a LeDeviceConfiguration from a dict.

        Args:
            amp_config: An amp configuration in dict form.

        Raises:
            ValueError: If the dictionary is empty.

        Returns:
            DeviceConfiguration: A DeviceConfiguration object.
        """
        return _config_w_intervals_from_dict(cls, amp_config)

    @classmethod
    def load(
        cls: type[LeDeviceConfiguration], file_path: Path
    ) -> LeDeviceConfiguration:
        """Load a LeDeviceConfiguration from a file.

        Args:
            file_path: The path to the file to load.

        Returns:
            DeviceConfiguration: A DeviceConfiguration object.
        """
        with file_path.open() as f:
            configuration_dict = json.load(f)
        return cls.from_dict(configuration_dict)


C = TypeVar("C", LeDeviceConfiguration, ForceDeviceConfiguration)


def _config_w_intervals_from_dict(cls: type[C], amp_config: dict) -> C:
    if amp_config:
        config = cls(**amp_config)
        config.scan_intervals = [Interval.from_dict(d) for d in config.scan_intervals]  # type: ignore[arg-type]
        return config

    msg = "'amp_config' is empty."
    raise ValueError(msg)
