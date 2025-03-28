from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, TypeVar

import numpy as np

from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.device.ampcom import _LeAmpCom
from pyglaze.device.configuration import DeviceConfiguration, LeDeviceConfiguration
from pyglaze.scanning._exceptions import ScanError

if TYPE_CHECKING:
    from pyglaze.helpers._types import FloatArray

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

    @abstractmethod
    def disconnect(self: _ScannerImplementation) -> None:
        pass

    @abstractmethod
    def get_serial_number(self: _ScannerImplementation) -> str:
        pass

    @abstractmethod
    def get_firmware_version(self: _ScannerImplementation) -> str:
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

    def disconnect(self: Scanner) -> None:
        """Close serial connection."""
        self._scanner_impl.disconnect()

    def get_serial_number(self: Scanner) -> str:
        """Get the serial number of the connected device.

        Returns:
            str: The serial number of the connected device.
        """
        return self._scanner_impl.get_serial_number()

    def get_firmware_version(self: Scanner) -> str:
        """Get the firmware version of the connected device.

        Returns:
            str: The firmware version of the connected device.
        """
        return self._scanner_impl.get_firmware_version()


class LeScanner(_ScannerImplementation[LeDeviceConfiguration]):
    """Perform synchronous terahertz scanning using a given DeviceConfiguration.

    Args:
        config: A DeviceConfiguration to use for the scan.
    """

    def __init__(self: LeScanner, config: LeDeviceConfiguration) -> None:
        self._config: LeDeviceConfiguration
        self._ampcom: _LeAmpCom | None = None
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
        if self._ampcom is None:
            msg = "Scanner not configured"
            raise ScanError(msg)
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

    def disconnect(self: LeScanner) -> None:
        """Close serial connection."""
        if self._ampcom is None:
            msg = "Scanner not connected"
            raise ScanError(msg)
        self._ampcom.disconnect()
        self._ampcom = None

    def get_serial_number(self: LeScanner) -> str:
        """Get the serial number of the connected device.

        Returns:
            str: The serial number of the connected device.
        """
        if self._ampcom is None:
            msg = "Scanner not connected"
            raise ScanError(msg)
        return self._ampcom.get_serial_number()

    def get_firmware_version(self: LeScanner) -> str:
        """Get the firmware version of the connected device.

        Returns:
            str: The firmware version of the connected device.
        """
        if self._ampcom is None:
            msg = "Scanner not connected"
            raise ScanError(msg)
        return self._ampcom.get_firmware_version()


def _scanner_factory(config: DeviceConfiguration) -> _ScannerImplementation:
    if isinstance(config, LeDeviceConfiguration):
        return LeScanner(config)

    msg = f"Unsupported configuration type: {type(config).__name__}"
    raise TypeError(msg)


class _LockinPhaseEstimator:
    def __init__(
        self: _LockinPhaseEstimator,
        r_threshold_for_update: float = 2.0,
        theta_threshold_for_adjustment: float = 1.0,
    ) -> None:
        self.r_threshold_for_update = r_threshold_for_update
        self.theta_threshold_for_adjustment = theta_threshold_for_adjustment
        self.phase_estimate: float | None = None
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

        if r_max > self.r_threshold_for_update * self._radius_of_est or (
            r_max > self._radius_of_est
            and abs(theta_at_max - self.phase_estimate)
            < self.theta_threshold_for_adjustment
        ):
            self._set_estimates(theta_at_max, r_max)

    def _set_estimates(
        self: _LockinPhaseEstimator, phase: float, radius: float
    ) -> None:
        self.phase_estimate = phase
        self._radius_of_est = radius
