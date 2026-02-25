from __future__ import annotations

from pyglaze.mimlink.codec import EnvelopeCodec
from pyglaze.mimlink.proto import envelope_pb2


def _msg_type(name: str) -> int:
    return getattr(envelope_pb2, "MsgType").Value(name)


def test_roundtrip_ping() -> None:
    codec = EnvelopeCodec()
    env = codec.build_envelope(_msg_type("MSG_TYPE_PING"))
    env.ping.nonce = 0xDEADBEEF
    frame = codec.encode(env)

    decoded = codec.decode(frame)
    assert decoded.type == _msg_type("MSG_TYPE_PING")
    assert decoded.ping.nonce == 0xDEADBEEF


def test_roundtrip_settings_response() -> None:
    codec = EnvelopeCodec()
    env = codec.build_envelope(_msg_type("MSG_TYPE_SET_SETTINGS_RESPONSE"))
    env.set_settings_response.success = True
    frame = codec.encode(env)

    decoded = codec.decode(frame)
    assert decoded.set_settings_response.success is True


def test_roundtrip_results_chunk() -> None:
    codec = EnvelopeCodec()
    env = codec.build_envelope(_msg_type("MSG_TYPE_RESULTS_CHUNK"))
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
    env = codec.build_envelope(_msg_type("MSG_TYPE_GET_DEVICE_INFO_RESPONSE"))
    resp = env.get_device_info_response
    resp.serial_number = "M-1234"
    resp.firmware_version = "v1.0.0"
    resp.bsp_name = "test_bsp"
    resp.build_type = "Release"
    resp.transfer_mode = 0
    resp.hardware_type = "rev_a"
    resp.hardware_revision = 2
    frame = codec.encode(env)

    decoded = codec.decode(frame)
    assert decoded.get_device_info_response.serial_number == "M-1234"
    assert decoded.get_device_info_response.hardware_revision == 2


def test_sequence_numbers_increment() -> None:
    codec = EnvelopeCodec()
    frames = []
    for _ in range(3):
        env = codec.build_envelope(_msg_type("MSG_TYPE_PING"))
        env.ping.nonce = 42
        frames.append(codec.encode(env))

    seqs = [codec.decode(f).seq for f in frames]
    assert seqs == [0, 1, 2]
