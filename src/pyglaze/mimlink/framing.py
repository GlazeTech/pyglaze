"""Wire framing for MimLink (COBS + CRC32 + delimiter)."""

from __future__ import annotations

from typing import Final

from cobs import cobs as _cobs
from crccheck.crc import Crc32Mpeg2

FRAME_DELIMITER: Final[int] = 0x00
CRC_SIZE_BYTES: Final[int] = 4


class FrameDecodeError(ValueError):
    """Raised when a frame fails COBS/CRC validation."""


def crc32_stm32(data: bytes) -> int:
    """Compute STM32F4-compatible CRC-32/MPEG-2."""
    return Crc32Mpeg2.calc(data)


def cobs_encode(data: bytes) -> bytes:
    """COBS-encode a payload (without delimiter)."""
    return _cobs.encode(data)


def cobs_decode(data: bytes) -> bytes:
    """COBS-decode a payload (without delimiter)."""
    try:
        return _cobs.decode(data)
    except _cobs.DecodeError as e:
        raise FrameDecodeError(str(e)) from e


def encode_frame(payload: bytes) -> bytes:
    """Build full wire frame: COBS(payload+crc_le) + delimiter."""
    crc = crc32_stm32(payload)
    combined = payload + crc.to_bytes(4, byteorder="little")
    return cobs_encode(combined) + bytes((FRAME_DELIMITER,))


def decode_frame(frame: bytes) -> bytes:
    """Decode a full wire frame into protobuf payload bytes."""
    if not frame:
        msg = "empty frame"
        raise FrameDecodeError(msg)

    raw = frame[:-1] if frame[-1] == FRAME_DELIMITER else frame
    decoded = cobs_decode(raw)

    if len(decoded) < CRC_SIZE_BYTES:
        msg = "frame too short for CRC"
        raise FrameDecodeError(msg)

    payload = decoded[:-CRC_SIZE_BYTES]
    expected_crc = int.from_bytes(decoded[-CRC_SIZE_BYTES:], byteorder="little")
    actual_crc = crc32_stm32(payload)
    if expected_crc != actual_crc:
        msg = "CRC mismatch"
        raise FrameDecodeError(msg)

    return payload
