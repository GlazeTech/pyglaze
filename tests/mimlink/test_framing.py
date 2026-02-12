import pytest

from pyglaze.mimlink.framing import (
    FrameDecodeError,
    cobs_decode,
    cobs_encode,
    crc32_stm32,
    decode_frame,
    encode_frame,
)


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
