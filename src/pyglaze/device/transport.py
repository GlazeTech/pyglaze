from __future__ import annotations

from typing import Protocol


class TransportBackend(Protocol):
    """Byte-level I/O backend for MimLink transport.

    Any object implementing this protocol can be used as a
    backend for MimLinkClient — serial, USB, TCP, BLE, mock, etc.
    """

    @property
    def in_waiting(self) -> int:
        """Number of bytes waiting in the receive buffer."""
        ...

    def read(self, size: int) -> bytes:
        """Read up to ``size`` bytes. May return fewer."""
        ...

    def write(self, data: bytes) -> int | None:
        """Write ``data`` bytes. Returns number of bytes written."""
        ...

    def reset_input_buffer(self) -> None:
        """Discard any buffered input data."""
        ...

    def close(self) -> None:
        """Release the underlying resource."""
        ...
