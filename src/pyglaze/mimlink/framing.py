"""Wire framing for MimLink (COBS + CRC32 + delimiter)."""

from __future__ import annotations

from typing import Final

CRC32_POLYNOMIAL: Final[int] = 0x04C11DB7
CRC32_INITIAL: Final[int] = 0xFFFFFFFF
FRAME_DELIMITER: Final[int] = 0x00
COBS_MAX_CODE: Final[int] = 0xFF
CRC_SIZE_BYTES: Final[int] = 4


class FrameDecodeError(ValueError):
    """Raised when a frame fails COBS/CRC validation."""


def crc32_stm32(data: bytes) -> int:
    """Compute STM32F4-compatible CRC-32/MPEG-2."""
    crc = CRC32_INITIAL
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ CRC32_POLYNOMIAL) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc


def cobs_encode(data: bytes) -> bytes:
    """COBS-encode a payload (without delimiter)."""
    out = bytearray()
    code_idx = 0
    out.append(0)
    code = 1

    for byte in data:
        if byte == 0:
            out[code_idx] = code
            code_idx = len(out)
            out.append(0)
            code = 1
        else:
            out.append(byte)
            code += 1
            if code == COBS_MAX_CODE:
                out[code_idx] = code
                code_idx = len(out)
                out.append(0)
                code = 1

    out[code_idx] = code
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    """COBS-decode a payload (without delimiter)."""
    if not data:
        msg = "empty COBS payload"
        raise FrameDecodeError(msg)

    out = bytearray()
    index = 0
    length = len(data)

    while index < length:
        code = data[index]
        if code == 0:
            msg = "invalid COBS code 0"
            raise FrameDecodeError(msg)
        index += 1

        run_end = index + code - 1
        if run_end > length:
            msg = "COBS run exceeds input length"
            raise FrameDecodeError(msg)

        out.extend(data[index:run_end])
        index = run_end

        if code != COBS_MAX_CODE and index < length:
            out.append(0)

    return bytes(out)


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
