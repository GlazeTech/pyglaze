from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pyglaze.device.exceptions import FirmwareUpdateError
from pyglaze.device.firmware import MCUBOOT_IMAGE_MAGIC, FirmwareUpdater
from pyglaze.device.firmware_client import FirmwareClient
from pyglaze.device.transport import MimLinkTransport
from pyglaze.devtools.mock_device import ScriptedTransport
from pyglaze.mimlink import msg_types as mt
from pyglaze.mimlink.codec import EnvelopeCodec
from pyglaze.mimlink.proto import envelope_pb2 as pb

if TYPE_CHECKING:
    from pathlib import Path

    from pyglaze.mimlink.proto.envelope_pb2 import Envelope


def _device_info_env(*, firmware_version: str = "v0.1.0") -> Envelope:
    codec = EnvelopeCodec()
    env = codec.build_envelope(mt.GET_DEVICE_INFO_RESPONSE)
    resp = env.get_device_info_response
    resp.serial_number = "M-TEST"
    resp.firmware_version = firmware_version
    resp.operational_state = pb.OPERATIONAL_STATE_NORMAL
    resp.config_status_reason = pb.CONFIG_STATUS_REASON_NONE
    return env


def _fw_status_env(*, status: pb.FwUpdateStatus = pb.FW_UPDATE_STATUS_IDLE) -> Envelope:
    codec = EnvelopeCodec()
    env = codec.build_envelope(mt.FW_UPDATE_STATUS_RESPONSE)
    env.fw_update_status_response.status = status
    return env


def _boot_confirm_env(*, version: str) -> Envelope:
    codec = EnvelopeCodec()
    env = codec.build_envelope(mt.FW_BOOT_CONFIRM_RESPONSE)
    env.fw_boot_confirm_response.confirmed = True
    env.fw_boot_confirm_response.version = version
    return env


def _upload_response_envs() -> list[Envelope]:
    """Responses for a successful 1-chunk firmware upload."""
    codec = EnvelopeCodec()
    start = codec.build_envelope(mt.FW_UPDATE_START_RESPONSE)
    start.fw_update_start_response.accepted = True
    ack = codec.build_envelope(mt.FW_UPDATE_CHUNK_ACK)
    ack.fw_update_chunk_ack.chunk_index = 0
    ack.fw_update_chunk_ack.status = pb.FW_CHUNK_STATUS_OK
    finish = codec.build_envelope(mt.FW_UPDATE_FINISH_RESPONSE)
    finish.fw_update_finish_response.success = True
    return [start, ack, finish]


def _rejected_upload_envs(*, error: str = "rejected") -> list[Envelope]:
    codec = EnvelopeCodec()
    start = codec.build_envelope(mt.FW_UPDATE_START_RESPONSE)
    start.fw_update_start_response.accepted = False
    start.fw_update_start_response.error = error
    return [start]


def _encode(*envelopes: Envelope) -> bytes:
    codec = EnvelopeCodec()
    return b"".join(codec.encode(env) for env in envelopes)


def _scripted_client(*envelopes: Envelope) -> FirmwareClient:
    """Build a FirmwareClient backed by pre-scripted protobuf responses."""
    transport = MimLinkTransport(
        conn=ScriptedTransport(_encode(*envelopes)),
        command_timeout_s=0.1,
    )
    return FirmwareClient(transport=transport)


def _timeout_client() -> FirmwareClient:
    """Client that times out on any operation (empty transport)."""
    transport = MimLinkTransport(
        conn=ScriptedTransport(b""),
        command_timeout_s=0.005,
    )
    return FirmwareClient(transport=transport)


class _Factory:
    def __init__(self, clients: list[FirmwareClient]) -> None:
        self._clients = clients
        self.calls = 0
        self.issued: list[FirmwareClient] = []

    def __call__(self) -> FirmwareClient:
        self.calls += 1
        if not self._clients:
            msg = "factory exhausted"
            raise RuntimeError(msg)
        client = self._clients.pop(0)
        self.issued.append(client)
        return client


def _signed_image(path: Path) -> Path:
    payload = MCUBOOT_IMAGE_MAGIC.to_bytes(4, "little") + b"\x00" * 32
    path.write_bytes(payload)
    return path


def test_update_happy_path(tmp_path: Path) -> None:
    firmware_path = _signed_image(tmp_path / "firmware.bin")

    clients = [
        # 1. get_boot_info preflight: device_info + fw_status
        _scripted_client(
            _device_info_env(firmware_version="v1.0.0"),
            _fw_status_env(),
        ),
        # 2. upload firmware (1-chunk image)
        _scripted_client(*_upload_response_envs()),
        # 3. _wait_until_status_reachable: timeout, then succeed
        _timeout_client(),
        _scripted_client(_fw_status_env(status=pb.FW_UPDATE_STATUS_BOOT_PENDING)),
        # 4. confirm_boot
        _scripted_client(_boot_confirm_env(version="v1.1.0")),
        # 5. final fw status
        _scripted_client(_fw_status_env(status=pb.FW_UPDATE_STATUS_CONFIRMED)),
    ]
    factory = _Factory(clients)
    updater = FirmwareUpdater(
        client_factory=factory,
        reboot_wait_s=0.0,
        reconnect_timeout_s=0.5,
        reconnect_interval_s=0.0,
    )

    stages: list[str] = []
    result = updater.update(firmware_path, version="v1.1.0", on_progress=stages.append)

    assert result.previous_version == "v1.0.0"
    assert result.confirmed_version == "v1.1.0"
    assert result.final_status == 4
    assert stages == ["uploading", "reconnecting", "confirming", "done"]
    assert factory.calls == 6


def test_update_rejects_unsigned_image(tmp_path: Path) -> None:
    firmware_path = tmp_path / "unsigned.bin"
    firmware_path.write_bytes(b"\x01\x02\x03\x04")

    updater = FirmwareUpdater(client_factory=_Factory([]))
    with pytest.raises(FirmwareUpdateError, match="not MCUboot-signed"):
        updater.update(firmware_path)


def test_update_rejects_too_small_image(tmp_path: Path) -> None:
    firmware_path = tmp_path / "tiny.bin"
    firmware_path.write_bytes(b"\x01\x02\x03")

    updater = FirmwareUpdater(client_factory=_Factory([]))
    with pytest.raises(FirmwareUpdateError, match="too small"):
        updater.update(firmware_path)


def test_update_wraps_file_read_errors() -> None:
    updater = FirmwareUpdater(client_factory=_Factory([]))

    with pytest.raises(FirmwareUpdateError, match="Failed to read firmware image"):
        updater.update("/definitely/missing/firmware.bin")


def test_update_preflight_unreachable_continues(tmp_path: Path) -> None:
    firmware_path = _signed_image(tmp_path / "firmware.bin")
    clients = [
        # 1. get_boot_info preflight — times out, caught by _try_get_boot_info
        _timeout_client(),
        # 2. upload firmware
        _scripted_client(*_upload_response_envs()),
        # 3. _wait_until_status_reachable
        _scripted_client(_fw_status_env(status=pb.FW_UPDATE_STATUS_BOOT_PENDING)),
        # 4. confirm_boot
        _scripted_client(_boot_confirm_env(version="v2.0.0")),
        # 5. final fw status
        _scripted_client(_fw_status_env(status=pb.FW_UPDATE_STATUS_CONFIRMED)),
    ]
    factory = _Factory(clients)
    updater = FirmwareUpdater(
        client_factory=factory,
        reboot_wait_s=0.0,
        reconnect_timeout_s=0.5,
        reconnect_interval_s=0.0,
    )

    result = updater.update(firmware_path, version="v2.0.0")
    assert result.previous_version == ""
    assert result.confirmed_version == "v2.0.0"
    assert result.final_status == 4


def test_update_reconnect_timeout_raises(tmp_path: Path) -> None:
    firmware_path = _signed_image(tmp_path / "firmware.bin")
    clients = [
        # 1. get_boot_info preflight
        _scripted_client(_device_info_env(firmware_version="v1.0.0"), _fw_status_env()),
        # 2. upload firmware
        _scripted_client(*_upload_response_envs()),
        # 3. _wait_until_status_reachable — all timeout
        *[_timeout_client() for _ in range(20)],
    ]
    factory = _Factory(clients)
    updater = FirmwareUpdater(
        client_factory=factory,
        reboot_wait_s=0.0,
        reconnect_timeout_s=0.05,
        reconnect_interval_s=0.0,
    )

    with pytest.raises(
        FirmwareUpdateError,
        match="Timed out waiting for device to reconnect after firmware upload",
    ):
        updater.update(firmware_path)


def test_update_confirm_timeout_raises(tmp_path: Path) -> None:
    firmware_path = _signed_image(tmp_path / "firmware.bin")
    clients = [
        # 1. get_boot_info preflight
        _scripted_client(_device_info_env(firmware_version="v1.0.0"), _fw_status_env()),
        # 2. upload firmware
        _scripted_client(*_upload_response_envs()),
        # 3. _wait_until_status_reachable
        _scripted_client(_fw_status_env(status=pb.FW_UPDATE_STATUS_BOOT_PENDING)),
        # 4. confirm_boot — all timeout
        *[_timeout_client() for _ in range(20)],
    ]
    factory = _Factory(clients)
    updater = FirmwareUpdater(
        client_factory=factory,
        reboot_wait_s=0.0,
        reconnect_timeout_s=0.05,
        reconnect_interval_s=0.0,
    )

    with pytest.raises(
        FirmwareUpdateError,
        match="Timed out confirming boot after firmware upload",
    ):
        updater.update(firmware_path)


def test_update_final_status_timeout_raises(tmp_path: Path) -> None:
    firmware_path = _signed_image(tmp_path / "firmware.bin")
    clients = [
        # 1. get_boot_info preflight
        _scripted_client(_device_info_env(firmware_version="v1.0.0"), _fw_status_env()),
        # 2. upload firmware
        _scripted_client(*_upload_response_envs()),
        # 3. _wait_until_status_reachable
        _scripted_client(_fw_status_env(status=pb.FW_UPDATE_STATUS_BOOT_PENDING)),
        # 4. confirm_boot
        _scripted_client(_boot_confirm_env(version="v1.1.0")),
        # 5. final fw status — all timeout
        *[_timeout_client() for _ in range(20)],
    ]
    factory = _Factory(clients)
    updater = FirmwareUpdater(
        client_factory=factory,
        reboot_wait_s=0.0,
        reconnect_timeout_s=0.05,
        reconnect_interval_s=0.0,
    )

    with pytest.raises(
        FirmwareUpdateError,
        match="Timed out reading firmware status after boot confirmation",
    ):
        updater.update(firmware_path)


def test_update_upload_error_propagates(tmp_path: Path) -> None:
    firmware_path = _signed_image(tmp_path / "firmware.bin")
    clients = [
        # 1. get_boot_info preflight
        _scripted_client(_device_info_env(firmware_version="v1.0.0"), _fw_status_env()),
        # 2. upload firmware — rejected by device
        _scripted_client(*_rejected_upload_envs(error="Device aborted")),
    ]
    factory = _Factory(clients)
    updater = FirmwareUpdater(
        client_factory=factory,
        reboot_wait_s=0.0,
        reconnect_timeout_s=0.5,
        reconnect_interval_s=0.0,
    )
    stages: list[str] = []

    with pytest.raises(FirmwareUpdateError, match="Firmware update rejected"):
        updater.update(firmware_path, on_progress=stages.append)

    assert stages == ["uploading"]
