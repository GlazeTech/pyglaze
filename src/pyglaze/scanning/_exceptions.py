from __future__ import annotations


class ScanError(Exception):
    """Exception raised when an error while scanning occurs."""

    def __init__(self: ScanError, msg: str) -> None:
        super().__init__(msg)
