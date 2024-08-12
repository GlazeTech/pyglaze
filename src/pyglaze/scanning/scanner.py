from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, TypeVar

import numpy as np

from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.device.ampcom import _ForceAmpCom, _LeAmpCom
from pyglaze.device.configuration import (
    DeviceConfiguration,
    ForceDeviceConfiguration,
    LeDeviceConfiguration,
)

if TYPE_CHECKING:
    from pyglaze.helpers.types import FloatArray

TConfig = TypeVar("TConfig", bound=DeviceConfiguration)


class _ScannerImplementation(ABC, Generic[TConfig]):
    @abstractmethod
    def __init__(self: _ScannerImplementation, config: TConfig) -> None:
        pass

    @property
    @abstractmethod
    def config(self: _ScannerImplementation) -> TConfig:
        pass

    @config.setter
    @abstractmethod
    def config(self: _ScannerImplementation, new_config: TConfig) -> None:
        pass

    @abstractmethod
    def scan(self: _ScannerImplementation) -> UnprocessedWaveform:
        pass

    @abstractmethod
    def update_config(self: _ScannerImplementation, new_config: TConfig) -> None:
        pass


class Scanner:
    """A synchronous scanner for Glaze terahertz devices."""

    def __init__(self: Scanner, config: TConfig) -> None:
        self._scanner_impl: _ScannerImplementation[DeviceConfiguration] = (
            _scanner_factory(config)
        )

    @property
    def config(self: Scanner) -> DeviceConfiguration:
        """Configuration used in the scan."""
        return self._scanner_impl.config

    @config.setter
    def config(self: Scanner, new_config: DeviceConfiguration) -> None:
        self._scanner_impl.config = new_config

    def scan(self: Scanner) -> UnprocessedWaveform:
        """Perform a scan.

        Returns:
            UnprocessedWaveform: A raw waveform.
        """
        return self._scanner_impl.scan()

    def update_config(self: Scanner, new_config: DeviceConfiguration) -> None:
        """Update the DeviceConfiguration used in the scan.

        Args:
            new_config (DeviceConfiguration): New configuration for scanner
        """
        self._scanner_impl.update_config(new_config)


class ForceScanner(_ScannerImplementation[ForceDeviceConfiguration]):
    """Perform synchronous terahertz scanning using a given DeviceConfiguration.

    Args:
        config: A DeviceConfiguration to use for the scan.

    """

    def __init__(self: ForceScanner, config: ForceDeviceConfiguration) -> None:
        self._config: ForceDeviceConfiguration
        self._ampcom: _ForceAmpCom
        self.config = config
        self._phase_estimator = _LockinPhaseEstimator()

    @property
    def config(self: ForceScanner) -> ForceDeviceConfiguration:
        """The device configuration to use for the scan.

        Returns:
            DeviceConfiguration: a DeviceConfiguration.
        """
        return self._config

    @config.setter
    def config(self: ForceScanner, new_config: ForceDeviceConfiguration) -> None:
        amp = _ForceAmpCom(new_config)
        if getattr(self, "_config", None):
            if (
                self._config.integration_periods != new_config.integration_periods
                or self._config.modulation_frequency != new_config.modulation_frequency
            ):
                amp.write_period_and_frequency()
            if self._config.sweep_length_ms != new_config.sweep_length_ms:
                amp.write_sweep_length()
            if self._config.modulation_waveform != new_config.modulation_waveform:
                amp.write_waveform()
            if (
                self._config.min_modulation_voltage != new_config.min_modulation_voltage
                or self._config.max_modulation_voltage
                != new_config.max_modulation_voltage
            ):
                amp.write_modulation_voltage()
            if self._config.scan_intervals != new_config.scan_intervals:
                amp.write_list()
        else:
            amp.write_all()

        self._config = new_config
        self._ampcom = amp

    def scan(self: ForceScanner) -> UnprocessedWaveform:
        """Perform a scan.

        Returns:
            Unprocessed scan.
        """
        _, responses = self._ampcom.start_scan()

        time = responses[:, 0]
        radius = responses[:, 1]
        theta = responses[:, 2]
        self._phase_estimator.update_estimate(radius=radius, theta=theta)

        return UnprocessedWaveform.from_polar_coords(
            time, radius, theta, self._phase_estimator.phase_estimate
        )

    def update_config(self: ForceScanner, new_config: ForceDeviceConfiguration) -> None:
        """Update the DeviceConfiguration used in the scan.

        Args:
            new_config: A DeviceConfiguration to use for the scan.
        """
        self.config = new_config


class LeScanner(_ScannerImplementation[LeDeviceConfiguration]):
    """Perform synchronous terahertz scanning using a given DeviceConfiguration.

    Args:
        config: A DeviceConfiguration to use for the scan.
    """

    def __init__(self: LeScanner, config: LeDeviceConfiguration) -> None:
        self._config: LeDeviceConfiguration
        self._ampcom: _LeAmpCom
        self.config = config
        self._phase_estimator = _LockinPhaseEstimator()

    @property
    def config(self: LeScanner) -> LeDeviceConfiguration:
        """The device configuration to use for the scan.

        Returns:
            DeviceConfiguration: a DeviceConfiguration.
        """
        return self._config

    @config.setter
    def config(self: LeScanner, new_config: LeDeviceConfiguration) -> None:
        amp = _LeAmpCom(new_config)
        if getattr(self, "_config", None):
            if (
                self._config.integration_periods != new_config.integration_periods
                or self._config.n_points != new_config.n_points
            ):
                amp.write_list_length_and_integration_periods_and_use_ema()
            if self._config.scan_intervals != new_config.scan_intervals:
                amp.write_list()
        else:
            amp.write_all()

        self._config = new_config
        self._ampcom = amp

    def scan(self: LeScanner) -> UnprocessedWaveform:
        """Perform a scan.

        Returns:
            Unprocessed scan.
        """
        _, time, radius, theta = self._ampcom.start_scan()
        self._phase_estimator.update_estimate(radius=radius, theta=theta)

        return UnprocessedWaveform.from_polar_coords(
            time, radius, theta, self._phase_estimator.phase_estimate
        )

    def update_config(self: LeScanner, new_config: LeDeviceConfiguration) -> None:
        """Update the DeviceConfiguration used in the scan.

        Args:
            new_config: A DeviceConfiguration to use for the scan.
        """
        self.config = new_config


def _scanner_factory(config: DeviceConfiguration) -> _ScannerImplementation:
    if isinstance(config, ForceDeviceConfiguration):
        return ForceScanner(config)
    if isinstance(config, LeDeviceConfiguration):
        return LeScanner(config)

    msg = f"Unsupported configuration type: {type(config).__name__}"
    raise TypeError(msg)


class _LockinPhaseEstimator:
    def __init__(
        self: _LockinPhaseEstimator, r_threshold_for_update: float = 2.0
    ) -> None:
        self.phase_estimate: float | None = None
        self.r_threshold_for_update = r_threshold_for_update
        self._radius_of_est: float | None = None

    def update_estimate(
        self: _LockinPhaseEstimator, radius: FloatArray, theta: FloatArray
    ) -> None:
        r_argmax = np.argmax(radius)
        r_max = radius[r_argmax]
        theta_at_max = theta[r_argmax]
        if self._radius_of_est is None:
            self._set_estimates(theta_at_max, r_max)
            return

        if r_max > self.r_threshold_for_update * self._radius_of_est:
            self._set_estimates(theta_at_max, r_max)

    def _set_estimates(
        self: _LockinPhaseEstimator, phase: float, radius: float
    ) -> None:
        self.phase_estimate = phase
        self._radius_of_est = radius
