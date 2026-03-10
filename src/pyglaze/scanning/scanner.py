from __future__ import annotations

from abc import ABC, abstractmethod
from math import modf
from typing import TYPE_CHECKING, Generic, TypeVar

import numpy as np

from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.device.configuration import DeviceConfiguration, LeDeviceConfiguration
from pyglaze.device.mimlink_client import ScanClient
from pyglaze.helpers._lockin import _LockinPhaseEstimator
from pyglaze.scanning._exceptions import ScanError
from pyglaze.scanning._types import DeviceInfo

if TYPE_CHECKING:
    from pyglaze.device.configuration import Interval

TConfig = TypeVar("TConfig", bound=DeviceConfiguration)


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


def _compute_scanning_list(n_points: int, intervals: list[Interval]) -> list[float]:
    """Compute the scanning frequency list from config."""
    scanning_list: list[float] = []
    for interval, pts in zip(
        intervals,
        _points_per_interval(n_points, intervals),
    ):
        scanning_list.extend(
            np.linspace(
                interval.lower,
                interval.upper,
                pts,
                endpoint=len(intervals) == 1,
            ),
        )
    return scanning_list


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
    def get_device_info(self: _ScannerImplementation) -> DeviceInfo:
        pass

    @abstractmethod
    def get_phase_estimate(self: _ScannerImplementation) -> float | None:
        pass


class Scanner:
    """A synchronous scanner for Glaze terahertz devices.

    Args:
        config: Device configuration for the scanner.
        initial_phase_estimate: Optional initial phase estimate in radians for lock-in detection.
            Use this to maintain consistent polarity across scanner instances.
    """

    def __init__(
        self: Scanner,
        config: TConfig,
        initial_phase_estimate: float | None = None,
    ) -> None:
        self._scanner_impl: _ScannerImplementation[DeviceConfiguration] = (
            _scanner_factory(config, initial_phase_estimate)
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

    def get_device_info(self: Scanner) -> DeviceInfo:
        """Get device information.

        Returns:
            DeviceInfo: Device identification and capabilities.
        """
        return self._scanner_impl.get_device_info()

    def get_phase_estimate(self: Scanner) -> float | None:
        """Get the current phase estimate from the lock-in phase estimator.

        Returns:
            float | None: The current phase estimate in radians, or None if not yet estimated.
        """
        return self._scanner_impl.get_phase_estimate()


class LeScanner(_ScannerImplementation[LeDeviceConfiguration]):
    """Perform synchronous terahertz scanning using a given DeviceConfiguration.

    Args:
        config: A DeviceConfiguration to use for the scan.
        initial_phase_estimate: Optional initial phase estimate in radians for lock-in detection.
            Use this to maintain consistent polarity across scanner instances.
    """

    def __init__(
        self: LeScanner,
        config: LeDeviceConfiguration,
        initial_phase_estimate: float | None = None,
    ) -> None:
        self._config: LeDeviceConfiguration
        self._client: ScanClient | None = None
        self.config = config
        self._phase_estimator = _LockinPhaseEstimator(
            initial_phase_estimate=initial_phase_estimate
        )

    @property
    def config(self: LeScanner) -> LeDeviceConfiguration:
        """The device configuration to use for the scan.

        Returns:
            DeviceConfiguration: a DeviceConfiguration.
        """
        return self._config

    @config.setter
    def config(self: LeScanner, new_config: LeDeviceConfiguration) -> None:
        new_client = self._create_initialized_client(new_config)
        old_client = self._client
        self._client = new_client
        self._config = new_config
        if old_client is not None:
            old_client.close()

    def _create_initialized_client(
        self: LeScanner, new_config: LeDeviceConfiguration
    ) -> ScanClient:
        """Build and initialize a client for a prospective scanner config."""
        new_client = ScanClient.from_config(new_config)
        try:
            settings_changed, list_changed = self._config_change_flags(new_config)
            self._initialize_client(
                new_client,
                new_config,
                settings_changed=settings_changed,
                list_changed=list_changed,
            )
        except Exception:
            new_client.close()
            raise
        return new_client

    def _config_change_flags(
        self: LeScanner, new_config: LeDeviceConfiguration
    ) -> tuple[bool, bool]:
        """Report whether device settings or scan-list inputs changed."""
        if not getattr(self, "_config", None):
            return True, True

        settings_changed = (
            self._config.integration_periods != new_config.integration_periods
            or self._config.n_points != new_config.n_points
            or self._config.use_ema != new_config.use_ema
        )
        list_changed = self._config.scan_intervals != new_config.scan_intervals
        return settings_changed, list_changed

    def _initialize_client(
        self: LeScanner,
        client: ScanClient,
        new_config: LeDeviceConfiguration,
        *,
        settings_changed: bool,
        list_changed: bool,
    ) -> None:
        """Apply the required device settings and scan list to a new client."""
        if settings_changed:
            client.set_settings(
                new_config.n_points,
                new_config.integration_periods,
                use_ema=new_config.use_ema,
            )
        if list_changed or settings_changed:
            scanning_list = _compute_scanning_list(
                new_config.n_points, new_config.scan_intervals
            )
            client.upload_list(scanning_list)

    def scan(self: LeScanner) -> UnprocessedWaveform:
        """Perform a scan.

        Returns:
            Unprocessed scan.
        """
        if self._client is None:
            msg = "Scanner not configured"
            raise ScanError(msg)
        times, Xs, Ys = self._client.start_scan()
        self._phase_estimator.update_estimate(Xs=Xs, Ys=Ys)
        return UnprocessedWaveform.from_inphase_quadrature(
            times, Xs, Ys, self._phase_estimator.phase_estimate
        )

    def update_config(self: LeScanner, new_config: LeDeviceConfiguration) -> None:
        """Update the DeviceConfiguration used in the scan.

        Args:
            new_config: A DeviceConfiguration to use for the scan.
        """
        self.config = new_config

    def disconnect(self: LeScanner) -> None:
        """Close serial connection."""
        if self._client is None:
            msg = "Scanner not connected"
            raise ScanError(msg)
        self._client.close()
        self._client = None

    def get_device_info(self: LeScanner) -> DeviceInfo:
        """Get device information."""
        if self._client is None:
            msg = "Scanner not connected"
            raise ScanError(msg)
        resp = self._client.get_device_info()
        return DeviceInfo(
            serial_number=str(resp.serial_number),
            firmware_version=str(resp.firmware_version),
            firmware_target=str(resp.firmware_target),
            bsp_name=str(resp.bsp_name),
            build_type=str(resp.build_type),
            transfer_mode=resp.transfer_mode,
            hardware_type=str(resp.hardware_type),
            hardware_revision=int(resp.hardware_revision),
        )

    def get_phase_estimate(self: LeScanner) -> float | None:
        """Get the current phase estimate from the lock-in phase estimator.

        Returns:
            float | None: The current phase estimate in radians, or None if not yet estimated.
        """
        return self._phase_estimator.phase_estimate


def _scanner_factory(
    config: DeviceConfiguration, initial_phase_estimate: float | None = None
) -> _ScannerImplementation:
    if isinstance(config, LeDeviceConfiguration):
        return LeScanner(config, initial_phase_estimate)

    msg = f"Unsupported configuration type: {type(config).__name__}"
    raise TypeError(msg)
