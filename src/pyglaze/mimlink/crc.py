from __future__ import annotations

import zlib

from crccheck.crc import Crc32Mpeg2


def crc32_stm32(data: bytes) -> int:
    """Compute CRC-32/MPEG-2, compatible with the STM32F4 hardware CRC peripheral.

    Used for MimLink wire-frame checksums (envelope framing).
    """
    return Crc32Mpeg2.calc(data)


def crc32(data: bytes) -> int:
    """Compute standard CRC-32 (ISO 3309).

    Used for firmware image and chunk integrity during OTA updates.
    """
    return zlib.crc32(data) & 0xFFFFFFFF
