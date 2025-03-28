from __future__ import annotations

import time
from dataclasses import dataclass
from functools import wraps
from typing import TYPE_CHECKING, Callable, cast

import serial
import serial.tools.list_ports

if TYPE_CHECKING:
    import logging

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
        if any(substring in port.device for substring in skip_ports_substrings):
            continue
        ports.append(port.device)
    return ports


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
            for tries in range(self.max_tries - 1):
                try:
                    return cast("T", func(*args, **kwargs))
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as e:  # noqa: BLE001
                    self._log(
                        f"{func.__name__} failed {tries + 1} time(s) with: '{e}'. Trying again"
                    )
                backoff = min(self.backoff_base * 2**tries, self.max_backoff)
                time.sleep(backoff)
            self._log(f"{func.__name__}: Last try ({tries + 2}).")
            return cast("T", func(*args, **kwargs))

        return wrapper

    def _log(self: _BackoffRetry, msg: str) -> None:
        if self.logger:
            self.logger.warning(msg)
        else:
            pass
