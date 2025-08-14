from __future__ import annotations

import logging
import struct
from functools import cached_property
from typing import TYPE_CHECKING, ClassVar

import numpy as np
import serial

from pyglaze.device.configuration import Interval, LeDeviceConfiguration
from pyglaze.device.protocol import Protocol
from pyglaze.devtools.mock_device import _mock_device_factory
from pyglaze.helpers.utilities import LOGGER_NAME

if TYPE_CHECKING:
    from pyglaze.devtools.mock_device import LeMockDevice
    from pyglaze.helpers._types import FloatArray


class DeviceComError(Exception):
    """Raised when an error occurs in the communication with the device."""

    def __init__(self: DeviceComError, message: str) -> None:
        super().__init__(message)


class ProtocolError(Exception):
    """Raised when a protocol-level error occurs."""

    def __init__(self: ProtocolError, message: str) -> None:
        super().__init__(message)


class LeProtocolV2(Protocol):
    """Protocol version 2 implementation based on MimOS firmware.

    This protocol uses a header-based message format with 16-bit instruction codes.
    Header format: ['A', 'B', 0, protocol_version, size_MSB, size_LSB, instruction_MSB, instruction_LSB]
    """

    # Protocol constants
    ENCODING: ClassVar[str] = "utf-8"
    HEADER_SIZE: ClassVar[int] = 8
    HEADER_PREFIX: ClassVar[bytes] = b"AB"
    PROTOCOL_VERSION: ClassVar[int] = 1
    TIMEOUT_MS: ClassVar[int] = 150

    # Instruction codes from MimOS firmware
    INST_SYS_PING: ClassVar[int] = 0x0000
    INST_ERROR: ClassVar[int] = 0xF000
    INST_WARNING: ClassVar[int] = 0xF001
    INST_INFO: ClassVar[int] = 0xF002

    INST_UINT8: ClassVar[int] = 0xF003
    INST_UINT16: ClassVar[int] = 0xF004
    INST_UINT32: ClassVar[int] = 0xF005
    INST_FLOAT: ClassVar[int] = 0xF006
    INST_STRING: ClassVar[int] = 0xF007
    INST_HEX: ClassVar[int] = 0xF008
    INST_BIT: ClassVar[int] = 0xF009

    INST_SYS_RESET: ClassVar[int] = 0xA000
    INST_SYS_CLOCK: ClassVar[int] = 0xA001

    INST_OS_THREADS: ClassVar[int] = 0xA100
    INST_OS_STACKS: ClassVar[int] = 0xA101
    INST_OS_HEAPS: ClassVar[int] = 0xA102
    INST_OS_USAGE: ClassVar[int] = 0xA103
    INST_OS_UPTIME: ClassVar[int] = 0xA104

    INST_LED_TOGGLE: ClassVar[int] = 0xA200
    INST_LED_ON: ClassVar[int] = 0xA201
    INST_LED_OFF: ClassVar[int] = 0xA202

    INST_RECEIVER_DAC_TABLE: ClassVar[int] = 0xA300
    INST_RECEIVER_ADC_ARRAY: ClassVar[int] = 0xA301
    INST_RECEIVER_FILTER_ARRAY: ClassVar[int] = 0xA302
    INST_RECEIVER_SET_AMPLITUDE: ClassVar[int] = 0xA303
    INST_RECEIVER_SET_FILTER_CALLS: ClassVar[int] = 0xA304

    INST_DRIVER_MOVE: ClassVar[int] = 0xA400
    INST_DRIVER_MOVEMENT_ARRAY: ClassVar[int] = 0xA401
    INST_DRIVER_SET: ClassVar[int] = 0xA402
    INST_DRIVER_DELAY_ARRAY: ClassVar[int] = 0xA403

    INST_MEMORY_SEND: ClassVar[int] = 0xA500

    INST_MANAGER_CALL: ClassVar[int] = 0xA600
    INST_MANAGER_DATA: ClassVar[int] = 0xA601
    INST_MANAGER_SETUP: ClassVar[int] = 0xA602
    INST_MANAGER_MEASURE: ClassVar[int] = 0xA603

    def __init__(self: LeProtocolV2, config: LeDeviceConfiguration) -> None:
        """Initialize protocol with device configuration."""
        super().__init__(config)
        self.config: LeDeviceConfiguration = config
        self.__ser: serial.Serial | LeMockDevice | None = None
        self._logger = logging.getLogger(LOGGER_NAME)

    @property
    def protocol_version(self: LeProtocolV2) -> str:
        """Get the protocol version identifier."""
        return "v2"

    @cached_property
    def scanning_points(self: LeProtocolV2) -> int:
        """Number of scanning points."""
        return self.config.n_points

    @cached_property
    def _intervals(self: LeProtocolV2) -> list[Interval]:
        """Intervals squished into effective DAC range."""
        return self.config.scan_intervals or [Interval(lower=0.0, upper=1.0)]

    @cached_property
    def scanning_list(self: LeProtocolV2) -> list[float]:
        """Generate scanning list from intervals."""
        scanning_list: list[float] = []
        for interval, n_points in zip(
            self._intervals,
            self._points_per_interval(self.scanning_points, self._intervals),
        ):
            scanning_list.extend(
                np.linspace(
                    interval.lower,
                    interval.upper,
                    n_points,
                    endpoint=len(self._intervals) == 1,
                ),
            )
        return scanning_list

    @cached_property
    def bytes_to_receive(self: LeProtocolV2) -> int:
        """Number of bytes to receive for a single scan.

        In V2, we receive cos and sin arrays separately, each with scanning_points floats.
        """
        return self.scanning_points * 4  # Single float array per response

    def supports_feature(self: LeProtocolV2, feature_name: str) -> bool:
        """Check if the protocol supports a specific feature."""
        v2_features = {
            "header_based_protocol",
            "structured_messages",
            "16bit_instructions",
            "amplitude_control",
            "system_diagnostics",
            "real_time_data",
        }
        return feature_name in v2_features

    def _raise_unexpected_instruction_error(
        self: LeProtocolV2, expected: int, received: int, context: str = ""
    ) -> None:
        """Helper to raise ProtocolError for unexpected instruction."""
        prefix = f"{context}: " if context else ""
        msg = f"{prefix}expected {expected:#06x}, got {received:#06x}"
        raise ProtocolError(msg)

    def _raise_data_size_error(self: LeProtocolV2, expected: int, received: int) -> None:
        """Helper to raise ProtocolError for unexpected data size."""
        msg = f"Unexpected data size: expected {expected} points, got {received}"
        raise ProtocolError(msg)

    def _raise_array_mismatch_error(self: LeProtocolV2, cos_size: int, sin_size: int) -> None:
        """Helper to raise ProtocolError for mismatched array sizes."""
        msg = f"Mismatched array sizes: cos={cos_size}, sin={sin_size}"
        raise ProtocolError(msg)

    def _build_header(self: LeProtocolV2, payload_size: int, instruction: int) -> bytes:
        """Build 8-byte header for message transmission.

        Header format: ['A', 'B', 0, protocol_version, size_MSB, size_LSB, instruction_MSB, instruction_LSB]
        """
        header = bytearray(8)
        header[0:2] = self.HEADER_PREFIX
        header[2] = 0
        header[3] = self.PROTOCOL_VERSION

        # Big-endian encoding for 16-bit values
        size_bytes = struct.pack(">H", payload_size)
        header[4:6] = size_bytes

        instruction_bytes = struct.pack(">H", instruction)
        header[6:8] = instruction_bytes

        return bytes(header)

    def _parse_header(self: LeProtocolV2, header: bytes) -> tuple[int, int]:
        """Parse 8-byte header to extract payload size and instruction.

        Returns:
            Tuple of (payload_size, instruction)

        Raises:
            ProtocolError: If header format is invalid
        """
        if len(header) != self.HEADER_SIZE:
            msg = f"Invalid header size: expected {self.HEADER_SIZE}, got {len(header)}"
            raise ProtocolError(msg)

        if header[0:2] != self.HEADER_PREFIX:
            msg = f"Invalid header prefix: expected {self.HEADER_PREFIX!r}, got {header[0:2]!r}"
            raise ProtocolError(msg)

        if header[2] != 0:
            msg = f"Invalid header byte 2: expected 0, got {header[2]}"
            raise ProtocolError(msg)

        if header[3] != self.PROTOCOL_VERSION:
            msg = f"Invalid protocol version: expected {self.PROTOCOL_VERSION}, got {header[3]}"
            raise ProtocolError(msg)

        # Extract payload size and instruction (big-endian)
        payload_size = struct.unpack(">H", header[4:6])[0]
        instruction = struct.unpack(">H", header[6:8])[0]

        return payload_size, instruction

    def _send_message(self: LeProtocolV2, payload: bytes, instruction: int) -> None:
        """Send a message with header and payload."""
        if self.__ser is None:
            msg = "Device not connected"
            raise DeviceComError(msg)

        header = self._build_header(len(payload), instruction)

        # Send header
        self.__ser.write(header)

        # Send payload if present
        if payload:
            self.__ser.write(payload)

    def _receive_message(
        self: LeProtocolV2, timeout: float | None = None
    ) -> tuple[bytes, int]:
        """Receive a message and return payload and instruction.

        Returns:
            Tuple of (payload, instruction)

        Raises:
            DeviceComError: If communication fails
            ProtocolError: If protocol format is invalid
        """
        if self.__ser is None:
            msg = "Device not connected"
            raise DeviceComError(msg)

        if timeout is None:
            timeout = self.TIMEOUT_MS / 1000.0

        original_timeout = getattr(self.__ser, "timeout", None)
        try:
            if hasattr(self.__ser, "timeout"):
                self.__ser.timeout = timeout

            # Read header
            header = self.__ser.read(self.HEADER_SIZE)
            if len(header) != self.HEADER_SIZE:
                msg = f"Failed to read complete header: expected {self.HEADER_SIZE} bytes, got {len(header)}"
                raise DeviceComError(msg)

            payload_size, instruction = self._parse_header(header)

            # Check for error response
            if instruction == self.INST_ERROR:
                # Read error message
                error_payload = (
                    self.__ser.read(payload_size) if payload_size > 0 else b""
                )
                error_msg = error_payload.decode(self.ENCODING, errors="replace")
                device_error_msg = f"Device error: {error_msg}"
                raise DeviceComError(device_error_msg)

            # Read payload
            payload = b""
            if payload_size > 0:
                payload = self.__ser.read(payload_size)
                if len(payload) != payload_size:
                    msg = f"Failed to read complete payload: expected {payload_size} bytes, got {len(payload)}"
                    raise DeviceComError(msg)

            return payload, instruction

        finally:
            if hasattr(self.__ser, "timeout") and original_timeout is not None:
                self.__ser.timeout = original_timeout

    def connect(self: LeProtocolV2) -> None:
        """Connect to the device and verify protocol compatibility."""
        self._logger.info("Connecting to device with Protocol V2...")

        if self.__ser is not None:
            self._logger.warning("Already connected to device")
            return

        try:
            if "mock_device" in self.config.amp_port:
                self.__ser = _mock_device_factory(self.config)
            else:
                self.__ser = serial.Serial(
                    port=self.config.amp_port,
                    baudrate=self.config.amp_baudrate,
                    timeout=self.config.amp_timeout_seconds,
                )

            # Verify connection with ping
            self._ping_device()
            self._logger.info("Successfully connected with Protocol V2")

        except Exception as e:
            if self.__ser is not None:
                self.__ser.close()
                self.__ser = None
            msg = f"Failed to connect to device: {e}"
            raise DeviceComError(msg) from e

    def disconnect(self: LeProtocolV2) -> None:
        """Disconnect from the device."""
        if self.__ser is not None:
            self._logger.info("Disconnecting from device...")
            self.__ser.close()
            self.__ser = None
            self._logger.info("Disconnected from device")

    def _ping_device(self: LeProtocolV2) -> None:
        """Send a ping command to verify device is responding with V2 protocol."""
        try:
            # Send ping with empty payload
            self._send_message(b"", self.INST_SYS_PING)

            # Expect echo response
            payload, instruction = self._receive_message()

            if instruction != self.INST_SYS_PING:
                self._raise_unexpected_instruction_error(
                    self.INST_SYS_PING, instruction, "Unexpected ping response instruction"
                )

            self._logger.debug("Device ping successful")

        except Exception as e:
            msg = f"Device ping failed: {e}"
            raise DeviceComError(msg) from e

    def write_settings(self: LeProtocolV2) -> str:
        """Write device settings using the V2 protocol.

        In V2, settings are sent using specific instruction codes:
        - INST_RECEIVER_SET_FILTER_CALLS for integration periods
        """
        self._logger.info("Writing device settings...")

        try:
            # Send integration periods (equivalent to V1 'S' command)
            integration_periods = self.config.integration_periods
            payload = struct.pack("<H", integration_periods)  # Little-endian uint16
            self._send_message(payload, self.INST_RECEIVER_SET_FILTER_CALLS)

            # Note: V2 protocol doesn't send immediate ACK like V1
            # The device processes the setting internally

        except Exception as e:
            msg = f"Failed to write settings: {e}"
            raise DeviceComError(msg) from e
        else:
            result_msg = f"Settings written: integration_periods={integration_periods}"
            self._logger.info(result_msg)
            return result_msg

    def write_list(self: LeProtocolV2) -> str:
        """Write scanning list to device using INST_DRIVER_SET.

        In V2, the scanning list is sent as an array of floats.
        """
        self._logger.info("Writing scanning list...")

        try:
            # Prepare scanning list as float array
            scanning_list = self.scanning_list

            # Pack as array of little-endian floats
            payload = b"".join(struct.pack("<f", point) for point in scanning_list)

            self._send_message(payload, self.INST_DRIVER_SET)

        except Exception as e:
            msg = f"Failed to write scanning list: {e}"
            raise DeviceComError(msg) from e
        else:
            result = f"Scanning list written: {len(scanning_list)} points"
            self._logger.info(result)
            return result

    def start_scan(
        self: LeProtocolV2,
    ) -> tuple[str, FloatArray, FloatArray, FloatArray]:
        """Start scanning using INST_MANAGER_CALL and return results.

        In V2, the scan is started and then we fetch the results.
        """
        self._logger.info("Starting scan...")

        try:
            # Send start scan command with empty payload
            self._send_message(b"", self.INST_MANAGER_CALL)

            # Unlike V1, V2 doesn't send an immediate ACK response
            # The device begins scanning asynchronously
            self._logger.info("Scan started, fetching data...")

            # Get the scan data
            times, cos_data, sin_data = self.fetch_data()

            # Convert to numpy arrays for calculations
            cos_array = np.array(cos_data)
            sin_array = np.array(sin_data)

            # Convert to radii and angles (same logic as V1)
            radii = np.sqrt(cos_array**2 + sin_array**2)
            angles = np.arctan2(sin_array, cos_array)

            self._logger.info("Scan completed successfully")

            return "G", np.array(times), radii, angles

        except Exception as e:
            msg = f"Failed to start scan: {e}"
            raise DeviceComError(msg) from e

    def fetch_data(self: LeProtocolV2) -> tuple[list[float], list[float], list[float]]:
        """Fetch scan data using INST_MANAGER_DATA.

        In V2, the device sends cos and sin arrays as separate messages.
        We request the data and receive two responses.

        Returns:
            Tuple containing (times, X_values, Y_values) lists
        """
        self._logger.info("Fetching scan data...")

        try:
            # Request scan data
            self._send_message(b"", self.INST_MANAGER_DATA)

            # Receive cos data response
            cos_payload, cos_instruction = self._receive_message()
            if cos_instruction != self.INST_MANAGER_DATA:
                self._raise_unexpected_instruction_error(
                    self.INST_MANAGER_DATA, cos_instruction, "Unexpected cos data instruction"
                )

            # Receive sin data response
            sin_payload, sin_instruction = self._receive_message()
            if sin_instruction != self.INST_MANAGER_DATA:
                self._raise_unexpected_instruction_error(
                    self.INST_MANAGER_DATA, sin_instruction, "Unexpected sin data instruction"
                )

            # Unpack float arrays (little-endian)
            n_cos_floats = len(cos_payload) // 4
            n_sin_floats = len(sin_payload) // 4

            if n_cos_floats != n_sin_floats:
                self._raise_array_mismatch_error(n_cos_floats, n_sin_floats)

            if n_cos_floats != self.scanning_points:
                self._raise_data_size_error(self.scanning_points, n_cos_floats)

            cos_data = struct.unpack(f"<{n_cos_floats}f", cos_payload)
            sin_data = struct.unpack(f"<{n_sin_floats}f", sin_payload)

            # Create delays array (V2 doesn't include delays in response, so we use scanning list)
            times = self.scanning_list

            self._logger.info("Scan data fetched: %d points", len(cos_data))

            return list(times), list(cos_data), list(sin_data)

        except Exception as e:
            msg = f"Failed to fetch scan data: {e}"
            raise DeviceComError(msg) from e

    def get_serial_number(self: LeProtocolV2) -> str:
        """Get device serial number using INST_MEMORY_SEND."""
        self._logger.info("Getting device serial number...")

        try:
            # Request serial number
            self._send_message(b"", self.INST_MEMORY_SEND)

            # Receive serial number response
            payload, instruction = self._receive_message()
            if instruction != self.INST_MEMORY_SEND:
                self._raise_unexpected_instruction_error(
                    self.INST_MEMORY_SEND, instruction, "Unexpected serial number instruction"
                )

            # Decode serial number
            serial_number = payload.decode(self.ENCODING, errors="replace").rstrip(
                "\x00"
            )

        except Exception as e:
            msg = f"Failed to get serial number: {e}"
            raise DeviceComError(msg) from e
        else:
            self._logger.info("Device serial number: %s", serial_number)
            return serial_number

    def get_status(self: LeProtocolV2) -> str:
        """Get device status.

        V2 protocol doesn't have a direct status command like V1.
        We can implement this by checking if device is responsive via ping.
        """
        self._logger.info("Getting device status...")

        try:
            # Use ping to check if device is responsive
            self._ping_device()
        except (DeviceComError, ProtocolError) as e:
            # If ping fails, assume device might be scanning or have an error
            self._logger.warning("Status check failed: %s", e)
            return "UNKNOWN"
        else:
            return "IDLE"  # If ping succeeds, device is idle and ready

    def get_firmware_version(self: LeProtocolV2) -> str:
        """Get firmware version.

        V2 protocol identifies itself through the protocol version.
        Based on MimOS firmware, version is "UART-OS V0.1".
        """
        return "UART-OS V0.1"

    # Helper method from V1 protocol
    def _points_per_interval(
        self: LeProtocolV2, total_points: int, intervals: list
    ) -> list[int]:
        """Calculate points per interval, same logic as V1."""
        if len(intervals) == 1:
            return [total_points]

        # Distribute points proportionally to interval sizes
        interval_sizes = [
            abs(interval.upper - interval.lower) for interval in intervals
        ]
        total_size = sum(interval_sizes)

        points_per_interval = []
        allocated_points = 0

        for _i, size in enumerate(interval_sizes[:-1]):
            points = int(total_points * size / total_size)
            points_per_interval.append(points)
            allocated_points += points

        # Assign remaining points to last interval
        points_per_interval.append(total_points - allocated_points)

        return points_per_interval
