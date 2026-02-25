from __future__ import annotations

import random
import time

from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.device.configuration import DeviceConfiguration, LeDeviceConfiguration
from pyglaze.device.mimlink_transport import (
    MimLinkClient,
    _compute_scanning_list,
    open_client,
)
from pyglaze.helpers._lockin import _LockinPhaseEstimator
from pyglaze.scanning._exceptions import ScanError
from pyglaze.scanning.types import DeviceInfo, DeviceStatus, PingResult


class Scanner:
    """A synchronous scanner for Glaze terahertz devices.

    Args:
        config: Device configuration for the scanner.
        initial_phase_estimate: Optional initial phase estimate in radians for lock-in detection.
            Use this to maintain consistent polarity across scanner instances.
    """

    def __init__(
        self,
        config: DeviceConfiguration,
        initial_phase_estimate: float | None = None,
    ) -> None:
        if not isinstance(config, LeDeviceConfiguration):
            msg = f"Unsupported configuration type: {type(config).__name__}"
            raise TypeError(msg)

        self._config: LeDeviceConfiguration
        self._transport: MimLinkClient | None = None
        self._phase_estimator = _LockinPhaseEstimator(
            initial_phase_estimate=initial_phase_estimate
        )
        self.config = config

    @property
    def config(self) -> LeDeviceConfiguration:
        """Configuration used in the scan."""
        return self._config

    @config.setter
    def config(self, new_config: DeviceConfiguration) -> None:
        if not isinstance(new_config, LeDeviceConfiguration):
            msg = f"Unsupported configuration type: {type(new_config).__name__}"
            raise TypeError(msg)

        old_config = getattr(self, "_config", None)
        port_changed = old_config is None or old_config.amp_port != new_config.amp_port

        if port_changed:
            if self._transport is not None:
                self._transport.close()
            self._transport = open_client(new_config)
            self._transport.set_settings(
                new_config.n_points,
                new_config.integration_periods,
                use_ema=new_config.use_ema,
            )
            scanning_list = _compute_scanning_list(
                new_config.n_points, new_config.scan_intervals
            )
            self._transport.upload_list(scanning_list)
        else:
            settings_changed = (
                old_config.integration_periods != new_config.integration_periods
                or old_config.n_points != new_config.n_points
                or old_config.use_ema != new_config.use_ema
            )
            list_changed = old_config.scan_intervals != new_config.scan_intervals

            if settings_changed:
                self._transport.set_settings(  # type: ignore[union-attr]
                    new_config.n_points,
                    new_config.integration_periods,
                    use_ema=new_config.use_ema,
                )
            if list_changed or settings_changed:
                scanning_list = _compute_scanning_list(
                    new_config.n_points, new_config.scan_intervals
                )
                self._transport.upload_list(scanning_list)  # type: ignore[union-attr]

        self._config = new_config

    def scan(self) -> UnprocessedWaveform:
        """Perform a scan.

        Returns:
            UnprocessedWaveform: A raw waveform.
        """
        if self._transport is None:
            msg = "Scanner not configured"
            raise ScanError(msg)
        times, Xs, Ys = self._transport.start_scan(
            self._config.n_points,
            self._config._sweep_length_ms,  # noqa: SLF001
        )
        self._phase_estimator.update_estimate(Xs=Xs, Ys=Ys)
        return UnprocessedWaveform.from_inphase_quadrature(
            times, Xs, Ys, self._phase_estimator.phase_estimate
        )

    def update_config(self, new_config: DeviceConfiguration) -> None:
        """Update the DeviceConfiguration used in the scan.

        Args:
            new_config (DeviceConfiguration): New configuration for scanner
        """
        self.config = new_config

    def disconnect(self) -> None:
        """Close the device connection."""
        if self._transport is None:
            msg = "Scanner not connected"
            raise ScanError(msg)
        self._transport.close()
        self._transport = None

    def get_device_info(self) -> DeviceInfo:
        """Get device information."""
        if self._transport is None:
            msg = "Scanner not connected"
            raise ScanError(msg)
        resp = self._transport.get_device_info()
        return DeviceInfo(
            serial_number=str(resp.serial_number),
            firmware_version=str(resp.firmware_version),
            bsp_name=str(resp.bsp_name),
            build_type=str(resp.build_type),
            transfer_mode=int(resp.transfer_mode),
            hardware_type=str(resp.hardware_type),
            hardware_revision=int(resp.hardware_revision),
        )

    def get_phase_estimate(self) -> float | None:
        """Get the current phase estimate from the lock-in phase estimator.

        Returns:
            float | None: The current phase estimate in radians, or None if not yet estimated.
        """
        return self._phase_estimator.phase_estimate

    def ping(self) -> PingResult:
        """Send a ping and measure round-trip time."""
        if self._transport is None:
            msg = "Scanner not connected"
            raise ScanError(msg)
        nonce = random.randint(0, 0xFFFFFFFF)  # noqa: S311
        t0 = time.perf_counter_ns()
        echoed = self._transport.ping(nonce)
        rtt_us = (time.perf_counter_ns() - t0) / 1_000
        return PingResult(success=True, round_trip_us=rtt_us, nonce=echoed)

    def get_status(self) -> DeviceStatus:
        """Query device status."""
        if self._transport is None:
            msg = "Scanner not connected"
            raise ScanError(msg)
        resp = self._transport.get_status()
        return DeviceStatus(
            scan_ongoing=bool(resp.scan_ongoing),
            list_length=resp.list_length,
            max_list_length=resp.max_list_length,
            modulation_frequency_hz=resp.modulation_frequency_hz,
            settings_valid=bool(resp.settings_valid),
            list_valid=bool(resp.list_valid),
        )
