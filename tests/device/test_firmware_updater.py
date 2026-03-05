from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import pytest

from pyglaze.device.firmware import MCUBOOT_IMAGE_MAGIC, FirmwareUpdater
from pyglaze.device.mimlink_client import FirmwareUpdateError

if TYPE_CHECKING:
    from pathlib import Path
    from collections.abc import Callable

    from pyglaze.device.mimlink_client import MimLinkClient


@dataclass(frozen=True)
class _DeviceInfo:
    firmware_version: str


@dataclass(frozen=True)
class _FwStatus:
    status: int


@dataclass
class _FakeClient:
    firmware_version: str = "v0.1.0"
    status: int = 0
    confirm_version: str = "v0.2.0"
    fail_on_get_info: bool = False
    updated: list[tuple[bytes, str]] | None = None
    closed: bool = False

    def get_device_info(self) -> _DeviceInfo:
        if self.fail_on_get_info:
            msg = "not reachable"
            raise RuntimeError(msg)
        return _DeviceInfo(firmware_version=self.firmware_version)

    def get_firmware_update_status(self) -> _FwStatus:
        return _FwStatus(status=self.status)

    def update_firmware(self, firmware: bytes, *, version: str = "") -> None:
        if self.updated is not None:
            self.updated.append((firmware, version))

    def confirm_boot(self) -> str:
        return self.confirm_version

    def close(self) -> None:
        self.closed = True


class _Factory:
    def __init__(self, clients: list[_FakeClient]) -> None:
        self._clients = clients
        self.calls = 0

    def __call__(self) -> _FakeClient:
        self.calls += 1
        if not self._clients:
            msg = "factory exhausted"
            raise RuntimeError(msg)
        return self._clients.pop(0)


def _signed_image(path: Path) -> Path:
    payload = MCUBOOT_IMAGE_MAGIC.to_bytes(4, "little") + b"\x00" * 32
    path.write_bytes(payload)
    return path


def test_update_happy_path(tmp_path: Path) -> None:
    firmware_path = _signed_image(tmp_path / "firmware.bin")
    uploaded: list[tuple[bytes, str]] = []

    clients = [
        _FakeClient(firmware_version="v1.0.0", status=0),
        _FakeClient(updated=uploaded),
        _FakeClient(fail_on_get_info=True),
        _FakeClient(firmware_version="v1.1.0", status=3),
        _FakeClient(status=4, confirm_version="v1.1.0"),
    ]
    factory = _Factory(clients)
    updater = FirmwareUpdater(
        client_factory=cast("Callable[[], MimLinkClient]", factory),
        reboot_wait_s=0.0,
        reconnect_timeout_s=0.1,
        reconnect_interval_s=0.0,
    )

    stages: list[str] = []
    result = updater.update(firmware_path, version="v1.1.0", on_progress=stages.append)

    assert result.previous_version == "v1.0.0"
    assert result.confirmed_version == "v1.1.0"
    assert result.final_status == 4
    assert uploaded
    assert uploaded[0][1] == "v1.1.0"
    assert stages == ["uploading", "reconnecting", "confirming", "done"]
    assert factory.calls == 5


def test_update_rejects_unsigned_image(tmp_path: Path) -> None:
    firmware_path = tmp_path / "unsigned.bin"
    firmware_path.write_bytes(b"\x01\x02\x03\x04")

    updater = FirmwareUpdater(
        client_factory=cast("Callable[[], MimLinkClient]", _Factory([]))
    )
    with pytest.raises(FirmwareUpdateError, match="not MCUboot-signed"):
        updater.update(firmware_path)
