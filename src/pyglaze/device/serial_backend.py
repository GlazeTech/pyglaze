from __future__ import annotations

import serial

MIMLINK_BAUDRATE = 1_000_000


class SerialBackend:
    """Serial transport backend for MimLink devices."""

    _READ_TIMEOUT_S = 0.1

    def __init__(self, port: str) -> None:
        self._serial = serial.serial_for_url(
            url=port,
            baudrate=MIMLINK_BAUDRATE,
            timeout=self._READ_TIMEOUT_S,
        )

    @property
    def in_waiting(self) -> int:
        """Number of bytes waiting in the receive buffer."""
        return self._serial.in_waiting

    def read(self, size: int) -> bytes:
        """Read up to ``size`` bytes."""
        return self._serial.read(size)

    def write(self, data: bytes) -> int | None:
        """Write ``data`` bytes."""
        return self._serial.write(data)

    def reset_input_buffer(self) -> None:
        """Discard any buffered input data."""
        self._serial.reset_input_buffer()

    def close(self) -> None:
        """Release the underlying serial port."""
        self._serial.close()
