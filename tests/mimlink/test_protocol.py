from __future__ import annotations

from typing import Any, Callable

import pytest

from pyglaze.mimlink import MessageType, ProtocolEndpoint
from pyglaze.mimlink.framing import decode_frame
from pyglaze.mimlink.proto import envelope_pb2
from pyglaze.mimlink.types import FwChunkStatus, FwUpdateStatus, TransferMode


def _decode_type(frame: bytes) -> int:
    payload = decode_frame(frame)
    envelope_cls = getattr(envelope_pb2, "Envelope")
    env = envelope_cls()
    env.ParseFromString(payload)
    return env.type


def test_endpoint_loopback_ping() -> None:
    a_wire: list[bytes] = []
    b_wire: list[bytes] = []
    received_a: list[tuple[int, int, Any]] = []
    received_b: list[tuple[int, int, Any]] = []

    endpoint_a = ProtocolEndpoint(
        on_envelope=lambda env_type, seq, payload: received_a.append(
            (env_type, seq, payload)
        ),
        on_send=lambda data: b_wire.append(data) or 0,
    )
    endpoint_b = ProtocolEndpoint(
        on_envelope=lambda env_type, seq, payload: received_b.append(
            (env_type, seq, payload)
        ),
        on_send=lambda data: a_wire.append(data) or 0,
    )

    assert endpoint_a.send_ping(0x12345678) == 0
    for frame in b_wire:
        endpoint_b.on_rx_bytes(frame)

    assert received_b
    assert received_b[0][0] == MessageType.PING
    assert received_b[0][2] == 0x12345678


def test_invalid_frame_dropped_and_parser_recovers() -> None:
    wire: list[bytes] = []
    received: list[int] = []

    endpoint = ProtocolEndpoint(
        on_envelope=lambda env_type, _seq, _payload: received.append(env_type),
        on_send=lambda data: wire.append(data) or 0,
    )

    endpoint.send_ping(42)
    valid = wire.pop()

    corrupted = bytearray(valid)
    corrupted[1] ^= 0x01

    endpoint.on_rx_bytes(bytes(corrupted))
    endpoint.on_rx_bytes(valid)

    assert received == [MessageType.PING]


_SEND_CASES: list[tuple[int, Callable[[ProtocolEndpoint], int]]] = [
    (MessageType.PING, lambda ep: ep.send_ping(1)),
    (MessageType.PONG, lambda ep: ep.send_pong(1)),
    (MessageType.SET_SETTINGS_REQUEST, lambda ep: ep.send_set_settings(100, 2, True)),
    (MessageType.SET_SETTINGS_RESPONSE, lambda ep: ep.send_set_settings_response(True)),
    (MessageType.SET_LIST_START_REQUEST, lambda ep: ep.send_set_list_start(100)),
    (
        MessageType.SET_LIST_START_RESPONSE,
        lambda ep: ep.send_set_list_start_response(True),
    ),
    (MessageType.LIST_CHUNK, lambda ep: ep.send_list_chunk(0, [1.0, 2.0], False)),
    (
        MessageType.SET_LIST_COMPLETE_RESPONSE,
        lambda ep: ep.send_set_list_complete_response(True, 2),
    ),
    (MessageType.START_SCAN_REQUEST, lambda ep: ep.send_start_scan()),
    (
        MessageType.START_SCAN_RESPONSE,
        lambda ep: ep.send_start_scan_response(True, None, 1),
    ),
    (MessageType.GET_RESULTS_REQUEST, lambda ep: ep.send_get_results()),
    (
        MessageType.RESULTS_CHUNK,
        lambda ep: ep.send_results_chunk(0, [0.1], [1.0], [2.0], True),
    ),
    (MessageType.GET_STATUS_REQUEST, lambda ep: ep.send_get_status()),
    (
        MessageType.GET_STATUS_RESPONSE,
        lambda ep: ep.send_get_status_response(True, 1, 10, 500, True, True),
    ),
    (MessageType.GET_SERIAL_REQUEST, lambda ep: ep.send_get_serial()),
    (MessageType.GET_SERIAL_RESPONSE, lambda ep: ep.send_get_serial_response("SN123")),
    (MessageType.GET_VERSION_REQUEST, lambda ep: ep.send_get_version()),
    (MessageType.GET_VERSION_RESPONSE, lambda ep: ep.send_get_version_response("v1")),
    (MessageType.REBOOT_REQUEST, lambda ep: ep.send_reboot()),
    (
        MessageType.GET_TRANSFORMED_LIST_REQUEST,
        lambda ep: ep.send_get_transformed_list(),
    ),
    (
        MessageType.TRANSFORMED_LIST_CHUNK,
        lambda ep: ep.send_transformed_list_chunk(0, [1, 2], True),
    ),
    (MessageType.GET_CAPABILITIES_REQUEST, lambda ep: ep.send_get_capabilities()),
    (
        MessageType.GET_CAPABILITIES_RESPONSE,
        lambda ep: ep.send_get_capabilities_response(
            bsp_name="test", build_type="Debug", transfer_mode=TransferMode.BULK
        ),
    ),
    (MessageType.RAW_CAPTURE_REQUEST, lambda ep: ep.send_raw_capture(256)),
    (
        MessageType.RAW_CAPTURE_CHUNK,
        lambda ep: ep.send_raw_capture_chunk(0, [1, 2, 3], True),
    ),
    (
        MessageType.RESULT_POINT,
        lambda ep: ep.send_result_point(0, 1.0, 2.0, 3.0, False),
    ),
    (MessageType.RESULT_POINT_NAK, lambda ep: ep.send_result_point_nak(1)),
    (
        MessageType.RESULT_POINT_RETRANSMIT,
        lambda ep: ep.send_result_point_retransmit(1, True, 1.0, 2.0, 3.0),
    ),
    (
        MessageType.FW_UPDATE_START_REQUEST,
        lambda ep: ep.send_fw_update_start(100, 0xAABBCCDD, 256, "v2"),
    ),
    (
        MessageType.FW_UPDATE_START_RESPONSE,
        lambda ep: ep.send_fw_update_start_response(True, None),
    ),
    (
        MessageType.FW_UPDATE_CHUNK,
        lambda ep: ep.send_fw_update_chunk(0, b"abc", 0x12345678),
    ),
    (
        MessageType.FW_UPDATE_CHUNK_ACK,
        lambda ep: ep.send_fw_update_chunk_ack(0, FwChunkStatus.OK),
    ),
    (MessageType.FW_UPDATE_FINISH_REQUEST, lambda ep: ep.send_fw_update_finish()),
    (
        MessageType.FW_UPDATE_FINISH_RESPONSE,
        lambda ep: ep.send_fw_update_finish_response(
            True, FwUpdateStatus.CONFIRMED, None
        ),
    ),
    (MessageType.FW_UPDATE_STATUS_REQUEST, lambda ep: ep.send_fw_update_status()),
    (
        MessageType.FW_UPDATE_STATUS_RESPONSE,
        lambda ep: ep.send_fw_update_status_response(
            FwUpdateStatus.RECEIVING, 1, 4, 512
        ),
    ),
    (MessageType.FW_BOOT_CONFIRM_REQUEST, lambda ep: ep.send_fw_boot_confirm()),
    (
        MessageType.FW_BOOT_CONFIRM_RESPONSE,
        lambda ep: ep.send_fw_boot_confirm_response(True, "v2"),
    ),
    (MessageType.RESULTS_CHUNK_NAK, lambda ep: ep.send_results_chunk_nak(1)),
    (
        MessageType.RESULTS_CHUNK_RETRANSMIT,
        lambda ep: ep.send_results_chunk_retransmit(1, [0.1], [1.0], [2.0], True, True),
    ),
]


@pytest.mark.parametrize(("expected_type", "send_fn"), _SEND_CASES)
def test_all_message_types_are_serialized(
    expected_type: int, send_fn: Callable[[ProtocolEndpoint], int]
) -> None:
    wire: list[bytes] = []
    endpoint = ProtocolEndpoint(on_send=lambda data: wire.append(data) or 0)

    assert send_fn(endpoint) == 0
    assert wire
    assert _decode_type(wire[-1]) == expected_type


def test_all_message_types_are_decoded_to_callback() -> None:
    received_types: list[int] = []
    wire: list[bytes] = []

    endpoint = ProtocolEndpoint(
        on_envelope=lambda env_type, _seq, _payload: received_types.append(env_type),
        on_send=lambda data: wire.append(data) or 0,
    )

    for _, send_fn in _SEND_CASES:
        assert send_fn(endpoint) == 0
        endpoint.on_rx_bytes(wire[-1])

    assert received_types == [case[0] for case in _SEND_CASES]
