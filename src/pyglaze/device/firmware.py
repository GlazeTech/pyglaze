from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from serial import SerialException

from pyglaze.device.configuration import AMP_BAUDRATE
from pyglaze.device.mimlink_client import (
    DeviceComError,
    FirmwareUpdateError,
    MimLinkClient,
)

if TYPE_CHECKING:
    from collections.abc import Callable

MCUBOOT_IMAGE_MAGIC = 0x96F3B83D
_MCUBOOT_MAGIC_BYTES = 4
_FW_STATUS_UNKNOWN = -1


class FirmwareClient(Protocol):
    """Protocol for the client surface used by FirmwareUpdater."""

    def get_device_info(self) -> DeviceInfoPayload:
        """Query device metadata."""

    def get_firmware_update_status(self) -> FirmwareStatusPayload:
        """Query firmware update state."""

    def update_firmware(self, firmware: bytes, *, version: str = "") -> None:
        """Upload a firmware image."""

    def confirm_boot(self) -> str:
        """Confirm a pending boot image and return firmware version."""

    def close(self) -> None:
        """Close underlying transport resources."""


class DeviceInfoPayload(Protocol):
    """Subset of device info used by firmware updater."""

    firmware_version: str


class FirmwareStatusPayload(Protocol):
    """Subset of firmware status used by firmware updater."""

    status: int


@dataclass(frozen=True)
class BootInfo:
    """Minimal firmware state reported by the device."""

    firmware_version: str
    update_status: int


@dataclass(frozen=True)
class FirmwareUpdateResult:
    """Summary of a completed firmware update cycle."""

    firmware_path: Path
    firmware_size: int
    previous_version: str
    confirmed_version: str
    final_status: int


class FirmwareUpdater:
    """High-level firmware update orchestrator built on MimLinkClient."""

    def __init__(
        self,
        *,
        client_factory: Callable[[], FirmwareClient],
        reboot_wait_s: float = 2.0,
        reconnect_timeout_s: float = 20.0,
        reconnect_interval_s: float = 0.5,
    ) -> None:
        self._client_factory = client_factory
        self._reboot_wait_s = reboot_wait_s
        self._reconnect_timeout_s = reconnect_timeout_s
        self._reconnect_interval_s = reconnect_interval_s

    @classmethod
    def from_port(
        cls,
        port: str,
        *,
        baudrate: int = AMP_BAUDRATE,
        timeout_s: float = 0.1,
    ) -> FirmwareUpdater:
        """Create a firmware updater that opens MimLinkClient on a serial port.

        Args:
            port: Serial port path.
            baudrate: UART baud rate.
            timeout_s: Serial read timeout in seconds.

        Returns:
            FirmwareUpdater configured to open a fresh client per operation.
        """
        return cls(
            client_factory=lambda: MimLinkClient.from_port(
                port=port,
                baudrate=baudrate,
                timeout_s=timeout_s,
            ),
        )

    def get_boot_info(self) -> BootInfo:
        """Get the currently running firmware version and update state.

        Returns:
            BootInfo: Current firmware version and firmware-update status.
        """
        client = self._client_factory()
        try:
            info = client.get_device_info()
            status = client.get_firmware_update_status()
            return BootInfo(
                firmware_version=str(info.firmware_version),
                update_status=int(status.status),
            )
        finally:
            client.close()

    def update(
        self,
        firmware_path: str | Path,
        *,
        version: str = "",
        on_progress: Callable[[str], None] | None = None,
    ) -> FirmwareUpdateResult:
        """Upload signed firmware, wait for reboot, then confirm the new boot image.

        Args:
            firmware_path: Path to a pre-signed MCUboot image.
            version: Optional version string passed to the device update start request.
            on_progress: Optional callback receiving progress stages.

        Returns:
            FirmwareUpdateResult: Summary of the update lifecycle and final status.

        Raises:
            FirmwareUpdateError: If validation fails, transfer fails, or reconnect times out.
        """
        path = Path(firmware_path)
        firmware = path.read_bytes()
        self._validate_signed_image(firmware)

        previous = self._try_get_boot_info()
        self._emit_progress(on_progress, "uploading")

        client = self._client_factory()
        try:
            client.update_firmware(firmware, version=version)
        finally:
            client.close()

        self._emit_progress(on_progress, "reconnecting")
        time.sleep(self._reboot_wait_s)
        self._wait_until_status_reachable()

        self._emit_progress(on_progress, "confirming")
        client = self._client_factory()
        try:
            confirmed_version = client.confirm_boot()
            final_status = int(client.get_firmware_update_status().status)
        finally:
            client.close()

        self._emit_progress(on_progress, "done")
        return FirmwareUpdateResult(
            firmware_path=path,
            firmware_size=len(firmware),
            previous_version=previous.firmware_version,
            confirmed_version=confirmed_version,
            final_status=final_status,
        )

    def _try_get_boot_info(self) -> BootInfo:
        """Try to read boot info without failing the update preflight."""
        try:
            return self.get_boot_info()
        except (DeviceComError, SerialException, OSError):
            return BootInfo(firmware_version="", update_status=_FW_STATUS_UNKNOWN)

    @staticmethod
    def _emit_progress(
        on_progress: Callable[[str], None] | None, stage: str
    ) -> None:
        if on_progress is not None:
            on_progress(stage)

    @staticmethod
    def _validate_signed_image(firmware: bytes) -> None:
        if len(firmware) < _MCUBOOT_MAGIC_BYTES:
            msg = "Firmware image is too small"
            raise FirmwareUpdateError(msg)
        magic = int.from_bytes(firmware[:4], byteorder="little", signed=False)
        if magic != MCUBOOT_IMAGE_MAGIC:
            msg = (
                "Firmware image is not MCUboot-signed. "
                "Expected MCUboot magic in image header."
            )
            raise FirmwareUpdateError(msg)

    def _wait_until_status_reachable(self) -> None:
        deadline = time.monotonic() + self._reconnect_timeout_s
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            client: FirmwareClient | None = None
            try:
                client = self._client_factory()
                client.get_firmware_update_status()
            except (DeviceComError, SerialException, OSError) as e:
                last_error = e
                time.sleep(self._reconnect_interval_s)
            else:
                return
            finally:
                if client is not None:
                    client.close()

        msg = "Timed out waiting for device to reconnect after firmware upload"
        raise FirmwareUpdateError(msg) from last_error
