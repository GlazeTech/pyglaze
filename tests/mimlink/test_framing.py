import pytest

from pyglaze.mimlink.framing import (
    FRAME_DELIMITER,
    FrameDecodeError,
    cobs_decode,
    cobs_encode,
    crc32_stm32,
    decode_frame,
    encode_frame,
)
from pyglaze.mimlink.rx_stream import RxFrameStream


def test_crc32_vectors() -> None:
    assert crc32_stm32(b"123456789") == 0x0376E6E7
    assert crc32_stm32(b"") == 0xFFFFFFFF
    assert crc32_stm32(b"\x00\x00\x00\x00") == 0xC704DD7B


def test_cobs_roundtrip_with_zeros() -> None:
    payload = bytes([0, 0x11, 0x22, 0, 0x33, 0, 0x44])
    encoded = cobs_encode(payload)
    assert 0 not in encoded
    assert cobs_decode(encoded) == payload


def test_frame_roundtrip() -> None:
    payload = b"hello-mimlink"
    frame = encode_frame(payload)
    assert frame.endswith(b"\x00")
    assert decode_frame(frame) == payload


def test_frame_crc_failure() -> None:
    payload = b"abc"
    frame = bytearray(encode_frame(payload))
    frame[2] ^= 0x01
    with pytest.raises(FrameDecodeError):
        decode_frame(bytes(frame))


def test_cobs_decode_invalid_bytes() -> None:
    with pytest.raises(FrameDecodeError):
        cobs_decode(b"\x00")


def test_decode_frame_empty() -> None:
    with pytest.raises(FrameDecodeError, match="empty frame"):
        decode_frame(b"")


def test_decode_frame_too_short_for_crc() -> None:
    # Encode a 1-byte payload normally, then tamper: replace the COBS body
    # with something that decodes to fewer than 4 bytes.
    short_cobs = cobs_encode(b"\x01\x02") + bytes([FRAME_DELIMITER])
    with pytest.raises(FrameDecodeError, match="too short"):
        decode_frame(short_cobs)


# --- RxFrameStream tests ---


def test_rx_stream_push_empty() -> None:
    stream = RxFrameStream()
    assert list(stream.push(b"")) == []


def test_rx_stream_consecutive_delimiters() -> None:
    stream = RxFrameStream()
    frame = encode_frame(b"payload")
    # Prepend extra delimiters — they should be skipped.
    data = bytes([FRAME_DELIMITER, FRAME_DELIMITER]) + frame
    frames = list(stream.push(data))
    assert len(frames) == 1
    assert decode_frame(frames[0]) == b"payload"
