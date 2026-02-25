from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


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


@dataclass
class ScannerConfiguration:
    """Scan parameters for Glaze terahertz devices.

    Args:
        use_ema: Whether to use an exponentially moving average filter during lockin detection.
        n_points: The number of points to scan.
        scan_intervals: The intervals to scan.
        integration_periods: The number of integration periods per datapoint to use.
        modulation_frequency: The modulation frequency in Hz.
    """

    use_ema: bool = True
    n_points: int = 1000
    scan_intervals: list[Interval] = field(default_factory=lambda: [Interval(0.0, 1.0)])
    integration_periods: int = 10
    modulation_frequency: int = 10000

    @property
    def _sweep_length_ms(self: ScannerConfiguration) -> float:
        return self.n_points * self._time_constant_ms

    @property
    def _time_constant_ms(self: ScannerConfiguration) -> float:
        return 1e3 * self.integration_periods / self.modulation_frequency

    def save(self: ScannerConfiguration, path: Path) -> str:
        """Save a ScannerConfiguration to a file.

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
        cls: type[ScannerConfiguration], amp_config: dict
    ) -> ScannerConfiguration:
        """Create a ScannerConfiguration from a dict.

        Args:
            amp_config: A configuration in dict form.

        Raises:
            ValueError: If the dictionary is empty.

        Returns:
            ScannerConfiguration: A ScannerConfiguration object.
        """
        if not amp_config:
            msg = "'amp_config' is empty."
            raise ValueError(msg)

        config = cls(**amp_config)
        config.scan_intervals = [Interval.from_dict(d) for d in config.scan_intervals]  # type: ignore[arg-type]
        return config

    @classmethod
    def load(cls: type[ScannerConfiguration], file_path: Path) -> ScannerConfiguration:
        """Load a ScannerConfiguration from a file.

        Args:
            file_path: The path to the file to load.

        Returns:
            ScannerConfiguration: A ScannerConfiguration object.
        """
        with file_path.open() as f:
            configuration_dict = json.load(f)
        return cls.from_dict(configuration_dict)
