from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyglaze.device.configuration import DeviceConfiguration
    from pyglaze.helpers._types import FloatArray


class Protocol(ABC):
    """Abstract base class for device communication protocols.

    This class defines the interface that all protocol implementations must follow.
    Protocol versions can implement different communication methods while maintaining
    a consistent interface for higher-level code.
    """

    def __init__(self: Protocol, config: DeviceConfiguration) -> None:
        """Initialize the protocol with device configuration.

        Args:
            config: Device configuration containing connection parameters.
        """
        self.config = config

    @property
    @abstractmethod
    def protocol_version(self: Protocol) -> str:
        """Get the protocol version identifier.

        Returns:
            String identifying the protocol version (e.g., "v1", "v2").
        """

    @abstractmethod
    def connect(self: Protocol) -> None:
        """Establish connection to the device.

        Raises:
            DeviceComError: If connection fails.
        """

    @abstractmethod
    def disconnect(self: Protocol) -> None:
        """Close connection to the device."""

    @abstractmethod
    def write_settings(self: Protocol) -> str:
        """Write device settings (list length, integration periods, use_ema).

        Returns:
            Device response string.

        Raises:
            DeviceComError: If command fails.
        """

    @abstractmethod
    def write_list(self: Protocol) -> str:
        """Write scanning list to device.

        Returns:
            Device response string.

        Raises:
            DeviceComError: If command fails.
        """

    @abstractmethod
    def start_scan(self: Protocol) -> tuple[str, FloatArray, FloatArray, FloatArray]:
        """Start a scan and return the results.

        Returns:
            Tuple containing (command, times, radii, angles) arrays.

        Raises:
            DeviceComError: If scan fails.
        """

    @abstractmethod
    def get_status(self: Protocol) -> str:
        """Get current device status.

        Returns:
            Status string from device.

        Raises:
            DeviceComError: If status check fails.
        """

    @abstractmethod
    def fetch_data(self: Protocol) -> tuple[list[float], list[float], list[float]]:
        """Fetch scan data from device.

        Returns:
            Tuple containing (times, X_values, Y_values) lists.

        Raises:
            DeviceComError: If data fetch fails.
        """

    @abstractmethod
    def get_serial_number(self: Protocol) -> str:
        """Get device serial number.

        Returns:
            Serial number string.

        Raises:
            DeviceComError: If command fails.
        """

    @abstractmethod
    def get_firmware_version(self: Protocol) -> str:
        """Get device firmware version.

        Returns:
            Firmware version string.

        Raises:
            DeviceComError: If command fails.
        """

    def supports_feature(self: Protocol, feature_name: str) -> bool:  # noqa: ARG002
        """Check if this protocol version supports a specific feature.

        Args:
            feature_name: Name of the feature to check.

        Returns:
            True if feature is supported, False otherwise.
        """
        # Default implementation - subclasses should override
        return False
