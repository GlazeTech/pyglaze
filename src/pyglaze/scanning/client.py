from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from serial import SerialException, serialutil
from typing_extensions import Self

from ._asyncscanner import _AsyncScanner

if TYPE_CHECKING:
    from pyglaze.datamodels import UnprocessedWaveform
    from pyglaze.device.configuration import ScannerConfiguration
    from pyglaze.device.transport import ConnectionInfo
    from pyglaze.scanning.types import DeviceInfo, DeviceStatus, PingResult


class ScannerStartupError(Exception):
    """Raised when the scanner could not be started."""

    def __init__(self: ScannerStartupError) -> None:
        super().__init__(
            "Scanner could not be started. Please check the internal server error messages."
        )


@dataclass
class GlazeClient:
    """Open a connection to and start continuously scanning using the Glaze device.

    Args:
        connection: Connection info describing how to reach the device.
        config: Scan configuration to use.
        initial_phase_estimate: Optional initial phase estimate in radians for lock-in detection.
            Use this to maintain consistent polarity across scanning sessions.
    """

    connection: ConnectionInfo
    config: ScannerConfiguration
    initial_phase_estimate: float | None = None
    _scanner: _AsyncScanner = field(init=False)

    def __enter__(self: Self) -> Self:
        """Start the scanner and return the client."""
        self._scanner = _AsyncScanner()
        try:
            self._scanner.start_scan(
                self.connection, self.config, self.initial_phase_estimate
            )
        except (TimeoutError, serialutil.SerialException) as e:
            self.__exit__(e)
        return self

    def __exit__(self: GlazeClient, *args: object) -> None:
        """Stop the scanner and close the connection."""
        if self._scanner.is_scanning:
            self._scanner.stop_scan()
        # Exit is only called with arguments when an error occurs - hence raise.
        if args[0]:
            raise

    def read(self: GlazeClient, n_pulses: int) -> list[UnprocessedWaveform]:
        """Read a number of pulses from the Glaze system.

        Args:
            n_pulses: The number of terahertz pulses to read from the CCS server.
        """
        return self._scanner.get_scans(n_pulses)

    def get_device_info(self: GlazeClient) -> DeviceInfo:
        """Get device information."""
        try:
            return self._scanner.get_device_info()
        except AttributeError as e:
            msg = "No connection to device."
            raise SerialException(msg) from e

    def get_phase_estimate(self: GlazeClient) -> float | None:
        """Get the current phase estimate from the lock-in phase estimator.

        Can be called even after the client has been stopped, allowing phase estimates
        to be extracted and reused for maintaining consistent polarity across sessions.

        Returns:
            float | None: The current phase estimate in radians, or None if not yet estimated.

        Raises:
            SerialException: If the scanner was never started.
        """
        try:
            return self._scanner.get_phase_estimate()
        except AttributeError as e:
            msg = "No connection to device."
            raise SerialException(msg) from e

    def ping(self: GlazeClient) -> PingResult:
        """Send a ping and measure round-trip time."""
        try:
            return self._scanner.ping()
        except AttributeError as e:
            msg = "No connection to device."
            raise SerialException(msg) from e

    def get_status(self: GlazeClient) -> DeviceStatus:
        """Query device status."""
        try:
            return self._scanner.get_status()
        except AttributeError as e:
            msg = "No connection to device."
            raise SerialException(msg) from e
