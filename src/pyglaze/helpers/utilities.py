from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from functools import wraps
from typing import TYPE_CHECKING, Callable

import serial
import serial.tools.list_ports
from serial import serialutil

if TYPE_CHECKING:
    import logging
    from collections.abc import Sequence

    from pyglaze.helpers._types import P, T

APP_NAME = "Glaze"
LOGGER_NAME = "glaze-logger"


def list_serial_ports() -> list[str]:
    """Lists available serial ports for device conneciton.

    Returns:
        list[str]: Paths to available ports.
    """
    skip_ports_substrings = ["Bluetooth", "debug"]

    ports = []
    for port in serial.tools.list_ports.comports():
        if _should_skip_port(port, skip_ports_substrings=skip_ports_substrings):
            continue
        ports.append(port.device)
    return ports


def auto_detect_glaze_amp_port(  # noqa: PLR0913
    *,
    baudrate: int | None = None,
    expected_responses: Sequence[str] = ("ACK: Idle.", "Error: Scan is ongoing."),
    timeout_seconds: float = 0.25,
    write_timeout_seconds: float = 0.25,
    skip_ports_substrings: Sequence[str] = ("Bluetooth", "debug"),
    probe: bool = True,
) -> str | None:
    """Auto-detect a Glaze serial port (FTDI-first, probe fallback).

    Strategy:
    1) Filter to likely FTDI ports (by VID or textual metadata).
    2) If exactly one candidate remains, return it.
    3) Otherwise, either:
       - If `probe` is True: probe each candidate with the status command ("H") and
         look for `expected_responses`.
       - If `probe` is False: raise and ask the user to specify a port.

    Args:
        baudrate: Baudrate to use when probing.
        expected_responses: Full responses that identify the target device.
        timeout_seconds: Read timeout for probing.
        write_timeout_seconds: Write timeout for probing.
        skip_ports_substrings: Substrings to skip when scanning ports.
        probe: Whether to open ports and probe using the status command.

    Returns:
        The matching port (e.g. "COM3" or "/dev/cu.usbserial-..."), or None if no
        matches are found.

    Raises:
        serialutil.SerialException: If multiple ports match.
    """
    candidates = _list_ftdi_candidate_ports(skip_ports_substrings=skip_ports_substrings)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    if not probe:
        msg = (
            "Multiple FTDI serial ports detected, but probing is disabled. "
            f"Candidates: {candidates}. "
            "Please specify `amp_port` explicitly (or enable probing)."
        )
        raise serialutil.SerialException(msg)
    if baudrate is None:
        msg = "`baudrate` must be provided when `probe=True`."
        raise ValueError(msg)

    matches: list[str] = []
    for candidate in candidates:
        response = _probe_serial_port(
            candidate,
            probe_bytes=b"H",
            baudrate=baudrate,
            timeout_seconds=timeout_seconds,
            write_timeout_seconds=write_timeout_seconds,
        )
        if response in expected_responses:
            matches.append(candidate)

    if not matches:
        return None
    if len(matches) > 1:
        msg = (
            "Multiple serial ports matched the Glaze probe. "
            f"Matches: {matches}. "
            "Please specify `amp_port` explicitly."
        )
        raise serialutil.SerialException(msg)
    return matches[0]


def _list_ftdi_candidate_ports(*, skip_ports_substrings: Sequence[str]) -> list[str]:
    ftdi_vid = 0x0403
    candidates: list[str] = []

    for port in serial.tools.list_ports.comports():
        if _should_skip_port(port, skip_ports_substrings=skip_ports_substrings):
            continue

        vid = getattr(port, "vid", None)
        if vid == ftdi_vid:
            candidates.append(port.device)
            continue

        meta = _port_metadata_string(port).lower()
        if "ftdi" in meta or "ft232" in meta:
            candidates.append(port.device)

    return candidates


def _probe_serial_port(
    port: str,
    *,
    probe_bytes: bytes,
    baudrate: int,
    timeout_seconds: float,
    write_timeout_seconds: float,
) -> str | None:
    try:
        with serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=timeout_seconds,
            write_timeout=write_timeout_seconds,
        ) as ser:
            with contextlib.suppress(Exception):
                ser.reset_input_buffer()
                ser.reset_output_buffer()
            ser.write(probe_bytes)
            raw = ser.read_until()
    except (serialutil.SerialException, OSError):
        return None

    try:
        decoded = raw.decode(errors="ignore").strip()
    except Exception:  # noqa: BLE001
        return None

    return decoded if decoded else None


def _should_skip_port(port: object, *, skip_ports_substrings: Sequence[str]) -> bool:
    haystack = _port_metadata_string(port)
    return any(substring in haystack for substring in skip_ports_substrings)


def _port_metadata_string(port: object) -> str:
    parts = [
        getattr(port, "device", None),
        getattr(port, "name", None),
        getattr(port, "description", None),
        getattr(port, "manufacturer", None),
        getattr(port, "product", None),
        getattr(port, "hwid", None),
    ]
    return " ".join(str(p) for p in parts if p)


@dataclass
class _BackoffRetry:
    """Decorator for retrying a function, using exponential backoff, if it fails.

    Args:
        max_tries: The maximum number of times the function should be tried.
        max_backoff: The maximum backoff time in seconds.
        backoff_base: The base of the exponential backoff.
        logger: A Logger class to use for logging. If None, messages are printed.

    Returns:
        The function that is decorated.
    """

    max_tries: int = 5
    max_backoff: float = 5
    backoff_base: float = 0.01
    logger: logging.Logger | None = None

    def __call__(self: _BackoffRetry, func: Callable[P, T]) -> Callable[P, T]:
        """Try the function `max_tries` times, with exponential backoff if it fails."""

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            func_name = getattr(func, "__name__", "function")
            for tries in range(self.max_tries - 1):
                try:
                    return func(*args, **kwargs)
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as e:  # noqa: BLE001
                    self._log(
                        f"{func_name} failed {tries + 1} time(s) with: '{e}'. Trying again"
                    )
                backoff = min(self.backoff_base * 2**tries, self.max_backoff)
                time.sleep(backoff)
            self._log(f"{func_name}: Last try ({tries + 2}).")
            return func(*args, **kwargs)

        return wrapper

    def _log(self: _BackoffRetry, msg: str) -> None:
        if self.logger:
            self.logger.warning(msg)
        else:
            pass
