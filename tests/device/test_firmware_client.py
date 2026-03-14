from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pyglaze.device import CatalogSelectionStatus
from pyglaze.device.exceptions import FirmwareUpdateError
from pyglaze.device.firmware_client import FirmwareClient
from pyglaze.device.transport import MimLinkTransport
from pyglaze.devtools.mock_device import ScriptedTransport
from pyglaze.mimlink import msg_types as mt
from pyglaze.mimlink.codec import EnvelopeCodec
from pyglaze.mimlink.proto import envelope_pb2 as pb

if TYPE_CHECKING:
    from pyglaze.mimlink.proto.envelope_pb2 import Envelope


_FW_CHUNK_SIZE = 256


def _build_scripted_envelopes(codec: EnvelopeCodec, envelopes: list[Envelope]) -> bytes:
    return b"".join(codec.encode(env) for env in envelopes)


def _build_fw_client(data: bytes) -> FirmwareClient:
    conn = ScriptedTransport(data)
    transport = MimLinkTransport(conn=conn)
    return FirmwareClient(transport=transport)


def _fw_start_response(
    codec: EnvelopeCodec, *, accepted: bool, error: str = ""
) -> pb.Envelope:
    env = codec.build_envelope(mt.FW_UPDATE_START_RESPONSE)
    resp = env.fw_update_start_response
    resp.accepted = accepted
    resp.error = error
    return env


def _fw_chunk_ack(
    codec: EnvelopeCodec, index: int, status: pb.FwChunkStatus
) -> pb.Envelope:
    env = codec.build_envelope(mt.FW_UPDATE_CHUNK_ACK)
    ack = env.fw_update_chunk_ack
    ack.chunk_index = index
    ack.status = status
    return env


def _fw_finish_response(
    codec: EnvelopeCodec, *, success: bool, error: str = ""
) -> pb.Envelope:
    env = codec.build_envelope(mt.FW_UPDATE_FINISH_RESPONSE)
    resp = env.fw_update_finish_response
    resp.success = success
    resp.error = error
    return env


def _fw_boot_confirm_response(
    codec: EnvelopeCodec, *, confirmed: bool, version: str
) -> pb.Envelope:
    env = codec.build_envelope(mt.FW_BOOT_CONFIRM_RESPONSE)
    resp = env.fw_boot_confirm_response
    resp.confirmed = confirmed
    resp.version = version
    return env


def _fw_status_response(
    codec: EnvelopeCodec,
    *,
    status: pb.FwUpdateStatus = pb.FW_UPDATE_STATUS_IDLE,
    chunks_received: int = 0,
    total_chunks: int = 0,
    bytes_received: int = 0,
) -> pb.Envelope:
    env = codec.build_envelope(mt.FW_UPDATE_STATUS_RESPONSE)
    resp = env.fw_update_status_response
    resp.status = status
    resp.chunks_received = chunks_received
    resp.total_chunks = total_chunks
    resp.bytes_received = bytes_received
    return env


def _device_info_response(
    codec: EnvelopeCodec,
    *,
    firmware_target: str = "le23-r1",
) -> pb.Envelope:
    env = codec.build_envelope(mt.GET_DEVICE_INFO_RESPONSE)
    resp = env.get_device_info_response
    resp.serial_number = "M-9999"
    resp.firmware_version = "v0.6.0"
    resp.bsp_name = "le23"
    resp.build_type = "Release"
    resp.hardware_type = "carmen"
    resp.hardware_revision = 1
    resp.firmware_target = firmware_target
    return env


def test_update_firmware_success() -> None:
    """Happy path: 512-byte firmware = 2 chunks, all ACK'd OK."""
    firmware = bytes(range(256)) * 2  # 512 bytes
    codec = EnvelopeCodec()

    envelopes = [
        _fw_start_response(codec, accepted=True),
        _fw_chunk_ack(codec, 0, pb.FW_CHUNK_STATUS_OK),
        _fw_chunk_ack(codec, 1, pb.FW_CHUNK_STATUS_OK),
        _fw_finish_response(codec, success=True),
    ]
    data = _build_scripted_envelopes(codec, envelopes)
    client = _build_fw_client(data)

    client.update_firmware(firmware, version="v1.0.0")
    client.close()


def test_update_firmware_rejected() -> None:
    """Device rejects the start request."""
    codec = EnvelopeCodec()
    envelopes = [
        _fw_start_response(codec, accepted=False, error="Firmware size invalid")
    ]
    data = _build_scripted_envelopes(codec, envelopes)
    client = _build_fw_client(data)

    with pytest.raises(FirmwareUpdateError, match="Firmware update rejected"):
        client.update_firmware(b"\x00" * 256)
    client.close()


def test_update_firmware_chunk_crc_mismatch_retries() -> None:
    """Device NAKs chunk 0 with CRC_MISMATCH, then accepts retry."""
    firmware = b"\xab" * 256  # 1 chunk
    codec = EnvelopeCodec()

    envelopes = [
        _fw_start_response(codec, accepted=True),
        _fw_chunk_ack(codec, 0, pb.FW_CHUNK_STATUS_CRC_MISMATCH),  # first attempt
        _fw_chunk_ack(codec, 0, pb.FW_CHUNK_STATUS_OK),  # retry
        _fw_finish_response(codec, success=True),
    ]
    data = _build_scripted_envelopes(codec, envelopes)
    client = _build_fw_client(data)

    client.update_firmware(firmware)
    client.close()


def test_update_firmware_chunk_crc_mismatch_retries_exhausted() -> None:
    """CRC mismatches beyond retry budget raise FirmwareUpdateError."""
    firmware = b"\xab" * 256  # 1 chunk
    codec = EnvelopeCodec()

    envelopes = [
        _fw_start_response(codec, accepted=True),
        _fw_chunk_ack(codec, 0, pb.FW_CHUNK_STATUS_CRC_MISMATCH),
        _fw_chunk_ack(codec, 0, pb.FW_CHUNK_STATUS_CRC_MISMATCH),
        _fw_chunk_ack(codec, 0, pb.FW_CHUNK_STATUS_CRC_MISMATCH),
    ]
    data = _build_scripted_envelopes(codec, envelopes)
    client = _build_fw_client(data)

    with pytest.raises(FirmwareUpdateError, match="CRC mismatch after"):
        client.update_firmware(firmware)
    client.close()


def test_update_firmware_chunk_abort() -> None:
    """Device aborts during chunk transfer."""
    firmware = b"\x00" * 256
    codec = EnvelopeCodec()

    envelopes = [
        _fw_start_response(codec, accepted=True),
        _fw_chunk_ack(codec, 0, pb.FW_CHUNK_STATUS_ABORT),
    ]
    data = _build_scripted_envelopes(codec, envelopes)
    client = _build_fw_client(data)

    with pytest.raises(FirmwareUpdateError, match="aborted"):
        client.update_firmware(firmware)
    client.close()


def test_update_firmware_unexpected_chunk_status() -> None:
    """Unknown chunk ACK status raises FirmwareUpdateError."""
    firmware = b"\x00" * 256
    codec = EnvelopeCodec()

    envelopes = [
        _fw_start_response(codec, accepted=True),
        _fw_chunk_ack(codec, 0, 99),  # type: ignore[arg-type]
    ]
    data = _build_scripted_envelopes(codec, envelopes)
    client = _build_fw_client(data)

    with pytest.raises(FirmwareUpdateError, match="Unexpected chunk status"):
        client.update_firmware(firmware)
    client.close()


def test_update_firmware_finish_failure() -> None:
    """Device reports finish failure (e.g. CRC mismatch on full image)."""
    firmware = b"\x00" * 256
    codec = EnvelopeCodec()

    envelopes = [
        _fw_start_response(codec, accepted=True),
        _fw_chunk_ack(codec, 0, pb.FW_CHUNK_STATUS_OK),
        _fw_finish_response(codec, success=False, error="CRC mismatch"),
    ]
    data = _build_scripted_envelopes(codec, envelopes)
    client = _build_fw_client(data)

    with pytest.raises(FirmwareUpdateError, match="finish failed"):
        client.update_firmware(firmware)
    client.close()


def test_confirm_boot() -> None:
    codec = EnvelopeCodec()
    envelopes = [_fw_boot_confirm_response(codec, confirmed=True, version="v1.2.3")]
    data = _build_scripted_envelopes(codec, envelopes)
    client = _build_fw_client(data)

    version = client.confirm_boot()
    assert version == "v1.2.3"
    client.close()


def test_confirm_boot_rejected() -> None:
    codec = EnvelopeCodec()
    envelopes = [_fw_boot_confirm_response(codec, confirmed=False, version="v1.2.3")]
    data = _build_scripted_envelopes(codec, envelopes)
    client = _build_fw_client(data)

    with pytest.raises(FirmwareUpdateError, match="Firmware boot confirmation failed"):
        client.confirm_boot()
    client.close()


def test_get_firmware_update_status() -> None:
    codec = EnvelopeCodec()
    envelopes = [
        _fw_status_response(
            codec,
            status=pb.FW_UPDATE_STATUS_RECEIVING,
            chunks_received=5,
            total_chunks=10,
            bytes_received=1280,
        )
    ]
    data = _build_scripted_envelopes(codec, envelopes)
    client = _build_fw_client(data)

    status = client.get_firmware_update_status()
    assert status.status == pb.FW_UPDATE_STATUS_RECEIVING
    assert status.chunks_received == 5
    assert status.total_chunks == 10
    assert status.bytes_received == 1280
    client.close()


def test_select_compatible_release() -> None:
    codec = EnvelopeCodec()
    data = _build_scripted_envelopes(codec, [_device_info_response(codec)])
    client = _build_fw_client(data)

    result = client.select_compatible_release(
        {
            "schema_version": 1,
            "product": "mimos",
            "release_version": "1.0.0",
            "channel": "stable",
            "published_at": "2026-03-08T11:00:00Z",
            "targets": [
                {
                    "firmware_target": "le23-r1",
                    "display_name": "Le 2.3.0",
                    "artifact_name": "mimos-le23-r1-v1.0.0.signed.bin",
                    "artifact_url": "https://example.invalid/le23.bin",
                    "sha256": "a" * 64,
                    "size_bytes": 262144,
                    "format": "mcuboot-signed-bin",
                    "minimum_consumer_versions": {"pyglaze": "0.6.0"},
                }
            ],
        }
    )

    assert result.status is CatalogSelectionStatus.SELECTED
    assert result.target is not None
    assert result.target.firmware_target == "le23-r1"
    client.close()


def test_select_compatible_release_reports_unmet_extra_consumer_version() -> None:
    codec = EnvelopeCodec()
    data = _build_scripted_envelopes(codec, [_device_info_response(codec)])
    client = _build_fw_client(data)

    result = client.select_compatible_release(
        {
            "schema_version": 1,
            "product": "mimos",
            "release_version": "1.0.0",
            "channel": "stable",
            "published_at": "2026-03-08T11:00:00Z",
            "targets": [
                {
                    "firmware_target": "le23-r1",
                    "display_name": "Le 2.3.0",
                    "artifact_name": "mimos-le23-r1-v1.0.0.signed.bin",
                    "artifact_url": "https://example.invalid/le23.bin",
                    "sha256": "a" * 64,
                    "size_bytes": 262144,
                    "format": "mcuboot-signed-bin",
                    "minimum_consumer_versions": {
                        "pyglaze": "0.6.0",
                        "glaze-desktop": "1.2.0",
                    },
                }
            ],
        },
        consumer_versions={"glaze-desktop": "1.1.0"},
    )

    assert result.status is CatalogSelectionStatus.CONSUMER_UPGRADE_REQUIRED
    assert result.unmet_consumers == {"glaze-desktop": "1.2.0"}
    client.close()
