"""Incremental parser for MimLink framed byte stream."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyglaze.mimlink.framing import FRAME_DELIMITER

if TYPE_CHECKING:
    from collections.abc import Iterator


class RxFrameStream:
    """Collect serial bytes and yield complete frame blobs."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def push(self, data: bytes) -> Iterator[bytes]:
        """Append bytes and yield full frames including delimiter."""
        if not data:
            return

        self._buffer.extend(data)
        while True:
            try:
                delimiter_idx = self._buffer.index(FRAME_DELIMITER)
            except ValueError:
                break

            frame = bytes(self._buffer[: delimiter_idx + 1])
            del self._buffer[: delimiter_idx + 1]

            # Skip pure delimiters/inter-frame padding.
            if len(frame) == 1:
                continue
            yield frame

    def reset(self) -> None:
        """Discard buffered partial frame state."""
        self._buffer.clear()
