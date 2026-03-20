from __future__ import annotations

import pytest

from pyglaze.mimlink import msg_types as mt
from pyglaze.mimlink.codec import EnvelopeCodec
from pyglaze.mimlink.framing import FrameDecodeError, encode_frame
from pyglaze.mimlink.proto.envelope_pb2 import TRANSFER_MODE_BULK


def test_roundtrip_settings_response() -> None:
    codec = EnvelopeCodec()
    env = codec.build_envelope(mt.SET_SETTINGS_RESPONSE)
    env.set_settings_response.success = True
    frame = codec.encode(env)

    decoded = codec.decode(frame)
    assert decoded.set_settings_response.success is True


def test_roundtrip_results_chunk() -> None:
    codec = EnvelopeCodec()
    env = codec.build_envelope(mt.RESULTS_CHUNK)
    chunk = env.results_chunk
    chunk.chunk_index = 3
    chunk.times.extend([1.0, 2.0])
    chunk.x.extend([3.0, 4.0])
    chunk.y.extend([5.0, 6.0])
    chunk.is_last = True
    frame = codec.encode(env)

    decoded = codec.decode(frame)
    assert decoded.results_chunk.chunk_index == 3
    assert list(decoded.results_chunk.times) == [1.0, 2.0]
    assert decoded.results_chunk.is_last is True


def test_roundtrip_device_info_response() -> None:
    codec = EnvelopeCodec()
    env = codec.build_envelope(mt.GET_DEVICE_INFO_RESPONSE)
    resp = env.get_device_info_response
    resp.serial_number = "M-1234"
    resp.firmware_version = "v1.0.0"
    resp.firmware_target = "le23-r1"
    resp.bsp_name = "test_bsp"
    resp.build_type = "Release"
    resp.transfer_mode = TRANSFER_MODE_BULK
    resp.hardware_type = "rev_a"
    resp.hardware_revision = 2
    frame = codec.encode(env)

    decoded = codec.decode(frame)
    assert decoded.get_device_info_response.serial_number == "M-1234"
    assert decoded.get_device_info_response.firmware_target == "le23-r1"
    assert decoded.get_device_info_response.hardware_revision == 2


def test_sequence_numbers_increment() -> None:
    codec = EnvelopeCodec()
    frames = []
    for _ in range(3):
        env = codec.build_envelope(mt.SET_SETTINGS_RESPONSE)
        env.set_settings_response.success = True
        frames.append(codec.encode(env))

    seqs = [codec.decode(f).seq for f in frames]
    assert seqs == [0, 1, 2]


def test_decode_garbage_protobuf() -> None:
    garbage = b"\xff\xfe\xfd\xfc\xfb"
    frame = encode_frame(garbage)
    codec = EnvelopeCodec()
    with pytest.raises(FrameDecodeError, match="protobuf"):
        codec.decode(frame)
