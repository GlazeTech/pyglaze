from __future__ import annotations

import random
import time
from math import modf
from typing import TYPE_CHECKING

import numpy as np

from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.device.mimlink_client import MimLinkClient
from pyglaze.helpers._lockin import _LockinPhaseEstimator
from pyglaze.scanning.types import DeviceInfo, DeviceStatus, PingResult

if TYPE_CHECKING:
    from pyglaze.device.configuration import Interval, ScannerConfiguration
    from pyglaze.device.transport import TransportFactory


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


class Scanner:
    """A synchronous scanner for Glaze terahertz devices.

    Args:
        config: Scan parameters for the scanner.
        transport: A callable that creates a ``TransportBackend`` instance.
            Use ``serial_transport(port)`` for serial connections.
        initial_phase_estimate: Optional initial phase estimate in radians for lock-in detection.
            Use this to maintain consistent polarity across scanner instances.
    """

    def __init__(
        self,
        config: ScannerConfiguration,
        transport: TransportFactory,
        initial_phase_estimate: float | None = None,
    ) -> None:
        self._config = config
        self._phase_estimator = _LockinPhaseEstimator(
            initial_phase_estimate=initial_phase_estimate
        )

        protocol_timeout = config._sweep_length_ms * 2e-3 + 1  # noqa: SLF001

        _transport = transport()
        _transport.reset_input_buffer()
        self._client = MimLinkClient(transport=_transport, timeout=protocol_timeout)
        self._client.set_settings(
            config.n_points,
            config.integration_periods,
            use_ema=config.use_ema,
        )
        scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
        self._client.upload_list(scanning_list)

    @property
    def config(self) -> ScannerConfiguration:
        """Configuration used in the scan."""
        return self._config

    def scan(self) -> UnprocessedWaveform:
        """Perform a scan.

        Returns:
            UnprocessedWaveform: A raw waveform.
        """
        times, Xs, Ys = self._client.start_scan(
            self._config.n_points,
            self._config._sweep_length_ms,  # noqa: SLF001
        )
        self._phase_estimator.update_estimate(Xs=Xs, Ys=Ys)
        return UnprocessedWaveform.from_inphase_quadrature(
            times, Xs, Ys, self._phase_estimator.phase_estimate
        )

    def update_config(self, new_config: ScannerConfiguration) -> None:
        """Update scan parameters over the existing connection.

        Re-sends settings and scanning list to the device. Does not reconnect.

        Args:
            new_config: New scan configuration.
        """
        settings_changed = (
            self._config.integration_periods != new_config.integration_periods
            or self._config.n_points != new_config.n_points
            or self._config.use_ema != new_config.use_ema
        )
        list_changed = self._config.scan_intervals != new_config.scan_intervals

        if settings_changed:
            self._client.set_settings(
                new_config.n_points,
                new_config.integration_periods,
                use_ema=new_config.use_ema,
            )
        if list_changed or settings_changed:
            scanning_list = _compute_scanning_list(
                new_config.n_points, new_config.scan_intervals
            )
            self._client.upload_list(scanning_list)

        self._config = new_config

    def disconnect(self) -> None:
        """Close the device connection."""
        self._client.close()

    def get_device_info(self) -> DeviceInfo:
        """Get device information."""
        resp = self._client.get_device_info()
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
        nonce = random.randint(0, 0xFFFFFFFF)  # noqa: S311
        t0 = time.perf_counter_ns()
        echoed = self._client.ping(nonce)
        rtt_us = (time.perf_counter_ns() - t0) / 1_000
        return PingResult(success=True, round_trip_us=rtt_us, nonce=echoed)

    def get_status(self) -> DeviceStatus:
        """Query device status."""
        resp = self._client.get_status()
        return DeviceStatus(
            scan_ongoing=bool(resp.scan_ongoing),
            list_length=resp.list_length,
            max_list_length=resp.max_list_length,
            modulation_frequency_hz=resp.modulation_frequency_hz,
            settings_valid=bool(resp.settings_valid),
            list_valid=bool(resp.list_valid),
        )
