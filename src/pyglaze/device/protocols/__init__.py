"""Protocol implementations package.

This package contains concrete implementations of the Protocol ABC for different
firmware versions and provides a factory function for protocol negotiation.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from serial import serialutil

from pyglaze.device.protocols.le_v1 import LeProtocolV1
from pyglaze.device.protocols.le_v2 import LeProtocolV2

if TYPE_CHECKING:
    from pyglaze.device.configuration import DeviceConfiguration, LeDeviceConfiguration
    from pyglaze.device.protocol import Protocol
else:
    from pyglaze.device.configuration import LeDeviceConfiguration

# Protocol registry mapping device types to their protocol versions
PROTOCOL_REGISTRY: dict[str, dict[str, type[Protocol]]] = {
    "Le": {
        "v1": LeProtocolV1,
        "v2": LeProtocolV2,
    },
}

# Supported protocol versions for Le devices in preference order (newest first)
LE_SUPPORTED_VERSIONS = ["v2", "v1"]


def register_protocol(
    device_type: str, version: str, protocol_class: type[Protocol]
) -> None:
    """Register a protocol implementation.

    Args:
        device_type: Device type identifier (e.g., "Le", "Xy").
        version: Version identifier (e.g., "v1", "v2").
        protocol_class: Protocol implementation class.
    """
    if device_type not in PROTOCOL_REGISTRY:
        PROTOCOL_REGISTRY[device_type] = {}
    PROTOCOL_REGISTRY[device_type][version] = protocol_class


def get_protocol(config: DeviceConfiguration, version: str | None = None) -> Protocol:
    """Get a protocol instance for the given configuration.

    Args:
        config: Device configuration.
        version: Specific protocol version to use. If None, will attempt
                version negotiation starting with the newest version.

    Returns:
        Protocol instance for the requested or negotiated version.

    Raises:
        ValueError: If the specified version is not supported.
        RuntimeError: If no protocol versions are available.
        TypeError: If the device type is not supported.
    """
    if not PROTOCOL_REGISTRY:
        msg = "No protocol implementations registered"
        raise RuntimeError(msg)

    # Determine device type from configuration
    if isinstance(config, LeDeviceConfiguration):
        return _get_le_protocol(config, version)

    msg = f"Unsupported device configuration type: {type(config).__name__}"
    raise TypeError(msg)


def _get_le_protocol(
    config: LeDeviceConfiguration, version: str | None = None
) -> Protocol:
    """Get a protocol instance for Le device configuration.

    Args:
        config: Le device configuration.
        version: Specific protocol version to use. If None, will attempt
                version negotiation starting with the newest version.

    Returns:
        Protocol instance for the requested or negotiated version.

    Raises:
        ValueError: If the specified version is not supported.
        RuntimeError: If no protocol versions can successfully connect.
    """
    le_protocols = PROTOCOL_REGISTRY.get("Le", {})

    if not le_protocols:
        msg = "No Le protocol implementations registered"
        raise RuntimeError(msg)

    if version is not None:
        if version not in le_protocols:
            msg = f"Le protocol version '{version}' not supported. Available: {list(le_protocols.keys())}"
            raise ValueError(msg)
        return le_protocols[version](config)

    # Version negotiation for Le devices
    return _negotiate_le_protocol_version(config)


def _negotiate_le_protocol_version(config: LeDeviceConfiguration) -> Protocol:
    """Negotiate the Le protocol version by attempting connections in preference order.

    Tries each supported Le protocol version starting with the newest, falling back
    to older versions if connection or initial command fails. Uses specific commands
    to determine protocol compatibility.

    Args:
        config: Le device configuration.

    Returns:
        Protocol instance for the successfully negotiated version.

    Raises:
        RuntimeError: If no protocol versions can successfully connect.
    """
    logger = logging.getLogger("pyglaze")
    last_error = None
    le_protocols = PROTOCOL_REGISTRY.get("Le", {})

    for version in LE_SUPPORTED_VERSIONS:
        if version not in le_protocols:
            continue

        protocol = _try_le_protocol_version(config, le_protocols[version], version, logger)
        if protocol is not None:
            return protocol

        # Track error for final message
        last_error = f"Version {version} failed"

    # If we get here, no protocol version worked
    available_versions = [v for v in LE_SUPPORTED_VERSIONS if v in le_protocols]
    msg = f"Le protocol negotiation failed for all versions {available_versions}. Last error: {last_error}"
    raise RuntimeError(msg)


def _try_le_protocol_version(
    config: LeDeviceConfiguration,
    protocol_class: type[Protocol],
    version: str,
    logger: logging.Logger,
) -> Protocol | None:
    """Try to connect with a specific Le protocol version.

    Args:
        config: Le device configuration.
        protocol_class: Protocol class to instantiate.
        version: Version string being tested.
        logger: Logger instance for debug messages.

    Returns:
        Protocol instance if successful, None if this version doesn't work.
    """
    try:
        logger.debug("Attempting Le protocol negotiation with version %s", version)
        protocol = protocol_class(config)

        # Attempt to connect and perform a basic operation to verify compatibility
        protocol.connect()
        try:
            # Try version-specific commands to verify the protocol
            # For v1: Try get_status which should return "R" or status
            # For v2: Try ping which is fundamental to v2 header-based protocol
            if version == "v1":
                # Try the status command which is fundamental to v1
                status = protocol.get_status()
                # If we get here without exception, v1 is working
                logger.debug("Le protocol v1 verified with status: %s", status)
            elif version == "v2":
                # Try ping command which verifies v2 header-based protocol
                # We know this is LeProtocolV2, so we can safely access _ping_device
                if hasattr(protocol, '_ping_device'):
                    protocol._ping_device()  # noqa: SLF001
                    # If we get here without exception, v2 is working
                    logger.debug("Le protocol v2 verified with ping command")
                else:
                    # Fallback verification for v2
                    logger.debug("Le protocol v2 connected successfully")

        except Exception:
            # If command fails, disconnect and try next version
            protocol.disconnect()
            raise
        else:
            logger.info("Successfully negotiated Le protocol version %s", version)
            return protocol

    except Exception as e:  # noqa: BLE001
        # If this is a serial exception, re-raise it directly
        # since it indicates a connection problem, not a protocol version issue
        if isinstance(e, (serialutil.SerialException, OSError)):
            raise e from None
        logger.debug("Le protocol version %s failed during negotiation: %s", version, e)
        return None


def list_supported_versions() -> dict[str, list[str]]:
    """Get list of supported protocol versions by device type.

    Returns:
        Dictionary mapping device types to their supported protocol versions.
    """
    return {
        device_type: list(versions.keys())
        for device_type, versions in PROTOCOL_REGISTRY.items()
    }


def detect_protocol_version(config: DeviceConfiguration) -> str:
    """Detect the protocol version supported by the device.

    Attempts version negotiation by trying commands in order to determine the
    protocol version.

    Args:
        config: Device configuration.

    Returns:
        Version string of the detected protocol (e.g., "v1", "v2").

    Raises:
        RuntimeError: If no protocol versions can successfully connect.
        TypeError: If the device type is not supported.
    """
    protocol = get_protocol(config)  # Use the device-aware factory
    try:
        return protocol.protocol_version
    finally:
        # Clean up the connection since we're only detecting
        with contextlib.suppress(Exception):
            protocol.disconnect()


__all__ = [
    "LE_SUPPORTED_VERSIONS",
    "PROTOCOL_REGISTRY",
    "LeProtocolV1",
    "LeProtocolV2",
    "detect_protocol_version",
    "get_protocol",
    "list_supported_versions",
    "register_protocol",
]
