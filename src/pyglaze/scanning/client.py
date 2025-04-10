from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from serial import SerialException, serialutil
from typing_extensions import Self

from ._asyncscanner import _AsyncScanner

if TYPE_CHECKING:
    from pyglaze.datamodels import UnprocessedWaveform
    from pyglaze.device.configuration import DeviceConfiguration


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
        config: Configuration to use for scans
    """

    config: DeviceConfiguration
    _scanner: _AsyncScanner = field(init=False)

    def __enter__(self: Self) -> Self:
        """Start the scanner and return the client."""
        self._scanner = _AsyncScanner()
        try:
            self._scanner.start_scan(self.config)
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

    def get_serial_number(self: GlazeClient) -> str:
        """Get the serial number of the connected device."""
        try:
            return self._scanner.get_serial_number()
        except AttributeError as e:
            msg = "No connection to device."
            raise SerialException(msg) from e

    def get_firmware_version(self: GlazeClient) -> str:
        """Get the firmware version of the connected device."""
        try:
            return self._scanner.get_firmware_version()
        except AttributeError as e:
            msg = "No connection to device."
            raise SerialException(msg) from e
