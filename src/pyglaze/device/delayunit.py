from __future__ import annotations

import pickle
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable, cast
from uuid import UUID, uuid4

import numpy as np

if TYPE_CHECKING:
    from pyglaze.helpers.types import FloatArray

__all__ = ["UniformDelay", "NonuniformDelay", "list_delayunits", "load_delayunit"]

_DELAYUNITS_PATH = Path(__file__).parent / "_delayunit_data"


def validate_delayunit(name: str) -> None:
    delayunits = list_delayunits()
    if name not in delayunits:
        msg = f"Unknown delayunit '{name}'. Valid options are: {', '.join(delayunits)}."
        raise ValueError(msg)


def list_delayunits() -> list[str]:
    """List all available delayunits.

    Returns:
        A list of all available delayunits.

    """
    return [delayunit.stem for delayunit in _DELAYUNITS_PATH.iterdir()]


def load_delayunit(name: str) -> Delay:
    """Load a delayunit by name.

    Args:
        name: The name of the delayunit to load.

    Returns:
        The loaded delayunit.
    """
    try:
        return _load_delayunit_from_path(_DELAYUNITS_PATH / f"{name}.pickle")
    except FileNotFoundError as e:
        msg = f"Unknown delayunit requested ('{name}'). Known units are: {list_delayunits()}"
        raise NameError(msg) from e


def _load_delayunit_from_path(path: Path) -> Delay:
    with Path(path).open("rb") as f:
        _dict: dict = pickle.load(f)
    delay_type = _dict.pop("type")
    return cast(Delay, globals()[delay_type](**_dict))


@dataclass(frozen=True)
class Delay(ABC):
    friendly_name: str
    unique_id: UUID
    creation_time: datetime

    def __call__(self: Delay, x: FloatArray) -> FloatArray:
        if np.max(x) > 1.0 or np.min(x) < 0.0:
            msg = "All values of 'x' must be between 0 and 1."
            raise ValueError(msg)

        return self._call(x)

    @property
    def filename(self: Delay) -> str:
        return f"{self.friendly_name}-{self.creation_time.strftime('%Y-%m-%d')}.pickle"

    @abstractmethod
    def _call(self: Delay, x: FloatArray) -> FloatArray: ...

    def save(self: Delay, path: Path) -> None:
        with Path(path).open("wb") as f:
            pickle.dump({"type": self.__class__.__name__, **asdict(self)}, f)


@dataclass(frozen=True)
class UniformDelay(Delay):
    """A delay calculator that calculates equidisant delays."""

    time_window: float

    def _call(self: UniformDelay, x: FloatArray) -> FloatArray:
        return x * self.time_window

    @classmethod
    def new(cls: type[UniformDelay], time_window: float, friendly_name: str) -> Delay:
        """Create a new Delay object.

        Args:
            time_window: The time window for the delay.
            friendly_name: The friendly name of the delay.

        Returns:
            Delay: The newly created Delay object.
        """
        return cls(
            friendly_name=friendly_name,
            unique_id=uuid4(),
            creation_time=datetime.now(),  # noqa: DTZ005
            time_window=time_window,
        )


@dataclass(frozen=True)
class NonuniformDelay(Delay):
    """A delay calculator that calculates non-equidistant delays."""

    time_window: float
    residual_interpolator: Callable[[FloatArray], FloatArray]

    def _call(self: NonuniformDelay, x: FloatArray) -> FloatArray:
        return (
            x * self.time_window
            + self.residual_interpolator(x)
            - self.residual_interpolator(np.asarray(0.0))
        )

    @classmethod
    def new(
        cls: type[NonuniformDelay],
        friendly_name: str,
        time_window: float,
        residual_interpolator: Callable[[FloatArray], FloatArray],
    ) -> Delay:
        """Create a new NonuniformDelay object.

        Args:
            friendly_name: The friendly name of the NonuniformDelay object.
            time_window: The time window of the pulse.
            residual_interpolator: a residual interpolator for calculating the nonuniform part of the delay.

        Returns:
            Delay: The newly created Delay object.
        """
        return cls(
            friendly_name=friendly_name,
            unique_id=uuid4(),
            creation_time=datetime.now(),  # noqa: DTZ005
            time_window=time_window,
            residual_interpolator=residual_interpolator,
        )
