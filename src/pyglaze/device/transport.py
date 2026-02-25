from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class ConnectionInfo:
    """Picklable description of how to connect to a device.

    Args:
        port: Device address (serial port path, USB endpoint, etc.)
        transport: Transport type. Only "serial" is supported currently.
    """

    port: str
    transport: str = "serial"
