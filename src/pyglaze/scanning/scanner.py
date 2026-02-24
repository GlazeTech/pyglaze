from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

import serial

from pyglaze.datamodels import UnprocessedWaveform
from pyglaze.device.ampcom import _LeAmpCom
from pyglaze.device.configuration import DeviceConfiguration, LeDeviceConfiguration
from pyglaze.device.mimlink_ampcom import _MimLinkAmpCom
from pyglaze.helpers._lockin import _LockinPhaseEstimator
from pyglaze.scanning._exceptions import ScanError

TConfig = TypeVar("TConfig", bound=DeviceConfiguration)


@dataclass
class PingResult:
    """Result of a ping operation."""

    success: bool
    round_trip_us: float
    nonce: int


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

    def get_phase_estimate(self: Scanner) -> float | None:
        """Get the current phase estimate from the lock-in phase estimator.

        Returns:
            float | None: The current phase estimate in radians, or None if not yet estimated.
        """
        return self._scanner_impl.get_phase_estimate()

    def ping(self: Scanner) -> PingResult:
        """Send a ping and measure round-trip time."""
        return self._scanner_impl.ping()

    def get_capabilities(self: Scanner) -> dict[str, bool]:
        """Query device hardware capabilities."""
        return self._scanner_impl.get_capabilities()

    def get_status(self: Scanner) -> dict[str, bool]:
        """Query device status."""
        return self._scanner_impl.get_status()


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
        self._ampcom: _LeAmpCom | None = None
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
        _, time, Xs, Ys = self._ampcom.start_scan()
        self._phase_estimator.update_estimate(Xs=Xs, Ys=Ys)
        return UnprocessedWaveform.from_inphase_quadrature(
            time, Xs, Ys, self._phase_estimator.phase_estimate
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

    def get_phase_estimate(self: LeScanner) -> float | None:
        """Get the current phase estimate from the lock-in phase estimator.

        Returns:
            float | None: The current phase estimate in radians, or None if not yet estimated.
        """
        return self._phase_estimator.phase_estimate


class MimLinkScanner(_ScannerImplementation[LeDeviceConfiguration]):
    """Perform synchronous terahertz scanning via MimLink binary protocol.

    Args:
        config: A LeDeviceConfiguration to use for the scan.
        initial_phase_estimate: Optional initial phase estimate in radians for lock-in detection.
    """

    def __init__(
        self: MimLinkScanner,
        config: LeDeviceConfiguration,
        initial_phase_estimate: float | None = None,
    ) -> None:
        self._config: LeDeviceConfiguration
        self._ampcom: _MimLinkAmpCom | None = None
        self.config = config
        self._phase_estimator = _LockinPhaseEstimator(
            initial_phase_estimate=initial_phase_estimate
        )

    @property
    def config(self: MimLinkScanner) -> LeDeviceConfiguration:
        """The MimLink device configuration used for scanning."""
        return self._config

    @config.setter
    def config(self: MimLinkScanner, new_config: LeDeviceConfiguration) -> None:
        amp = _MimLinkAmpCom(new_config)
        if getattr(self, "_config", None):
            if (
                self._config.integration_periods != new_config.integration_periods
                or self._config.n_points != new_config.n_points
            ):
                amp.write_settings()
            if self._config.scan_intervals != new_config.scan_intervals:
                amp.write_list()
        else:
            amp.write_all()

        self._config = new_config
        self._ampcom = amp

    def scan(self: MimLinkScanner) -> UnprocessedWaveform:
        """Perform a scan and return the unprocessed waveform."""
        if self._ampcom is None:
            msg = "Scanner not configured"
            raise ScanError(msg)
        _, time, Xs, Ys = self._ampcom.start_scan()
        self._phase_estimator.update_estimate(Xs=Xs, Ys=Ys)
        return UnprocessedWaveform.from_inphase_quadrature(
            time, Xs, Ys, self._phase_estimator.phase_estimate
        )

    def update_config(self: MimLinkScanner, new_config: LeDeviceConfiguration) -> None:
        """Update scanner configuration."""
        self.config = new_config

    def disconnect(self: MimLinkScanner) -> None:
        """Close the MimLink connection."""
        if self._ampcom is None:
            msg = "Scanner not connected"
            raise ScanError(msg)
        self._ampcom.disconnect()
        self._ampcom = None

    def get_serial_number(self: MimLinkScanner) -> str:
        """Get device serial number."""
        if self._ampcom is None:
            msg = "Scanner not connected"
            raise ScanError(msg)
        return self._ampcom.get_serial_number()

    def get_firmware_version(self: MimLinkScanner) -> str:
        """Get firmware version string."""
        if self._ampcom is None:
            msg = "Scanner not connected"
            raise ScanError(msg)
        return self._ampcom.get_firmware_version()

    def get_phase_estimate(self: MimLinkScanner) -> float | None:
        """Return the lock-in phase estimate in radians, if available."""
        return self._phase_estimator.phase_estimate

    def ping(self: MimLinkScanner) -> PingResult:
        """Ping via MimLink protocol."""
        if self._ampcom is None:
            msg = "Scanner not connected"
            raise ScanError(msg)
        nonce = random.randint(0, 0xFFFFFFFF)
        t0 = time.perf_counter_ns()
        echoed = self._ampcom.ping(nonce)
        rtt_us = (time.perf_counter_ns() - t0) / 1_000
        return PingResult(success=True, round_trip_us=rtt_us, nonce=echoed)

    def get_capabilities(self: MimLinkScanner) -> dict[str, bool]:
        """Query device hardware capabilities."""
        if self._ampcom is None:
            msg = "Scanner not connected"
            raise ScanError(msg)
        resp = self._ampcom.get_capabilities()
        return {
            "has_external_dac": resp.has_external_dac,
            "has_encoder": resp.has_encoder,
            "has_i2c1": resp.has_i2c1,
            "has_i2c2": resp.has_i2c2,
            "has_i2c3": resp.has_i2c3,
            "has_power_rails": resp.has_power_rails,
        }

    def get_status(self: MimLinkScanner) -> dict[str, bool]:
        """Query device status."""
        if self._ampcom is None:
            msg = "Scanner not connected"
            raise ScanError(msg)
        resp = self._ampcom.get_status()
        return {"scan_ongoing": resp.scan_ongoing}


def _detect_protocol(config: LeDeviceConfiguration) -> str:
    """Detect whether a device speaks legacy ASCII or MimLink binary protocol.

    Sends a single 'H' (legacy status command). Legacy devices respond with
    ASCII text ending in newline. MimLink devices silently discard the stray
    byte (COBS framing rejects it), so we time out.
    """
    if "mock_mimlink" in config.amp_port:
        return "mimlink"

    detection_timeout = 0.5
    try:
        ser = serial.serial_for_url(
            config.amp_port,
            baudrate=config.amp_baudrate,
            timeout=detection_timeout,
        )
        ser.reset_input_buffer()
        ser.write(b"H")
        response = ser.read_until()
        ser.close()
        text = response.decode("utf-8", errors="replace").strip()
    except Exception:  # noqa: BLE001
        return "legacy"
    else:
        if "ACK" in text or "Error" in text:
            return "legacy"
        return "mimlink"


def _scanner_factory(
    config: DeviceConfiguration, initial_phase_estimate: float | None = None
) -> _ScannerImplementation:
    if isinstance(config, LeDeviceConfiguration):
        if "mock_mimlink" in config.amp_port:
            return MimLinkScanner(config, initial_phase_estimate)
        if "mock_device" in config.amp_port:
            return LeScanner(config, initial_phase_estimate)
        protocol = _detect_protocol(config)
        if protocol == "mimlink":
            return MimLinkScanner(config, initial_phase_estimate)
        return LeScanner(config, initial_phase_estimate)

    msg = f"Unsupported configuration type: {type(config).__name__}"
    raise TypeError(msg)
