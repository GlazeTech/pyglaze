from __future__ import annotations

from math import modf
from typing import TYPE_CHECKING, Callable

import numpy as np

from pyglaze.device.configuration import Interval

if TYPE_CHECKING:
    from pyglaze.helpers._types import FloatArray


class DeviceComError(Exception):
    """Raised when an error occurs in the communication with the device."""

    def __init__(self: DeviceComError, message: str) -> None:
        super().__init__(message)


def _points_per_interval(n_points: int, intervals: list[Interval]) -> list[int]:
    """Divides a total number of points between intervals."""
    interval_lengths = [interval.length for interval in intervals]
    total_length = sum(interval_lengths)

    points_per_interval_floats = [
        n_points * length / total_length for length in interval_lengths
    ]
    points_per_interval = [int(e) for e in points_per_interval_floats]

    # We must distribute the remainder from the int operation to get the right amount of total points
    remainders = [modf(num)[0] for num in points_per_interval_floats]
    sorted_indices = np.flip(np.argsort(remainders))
    for i in range(int(0.5 + np.sum(remainders))):
        points_per_interval[sorted_indices[i]] += 1

    return points_per_interval


def _squish_intervals(
    intervals: list[Interval], lower_bound: int, upper_bound: int, bitwidth: int
) -> list[Interval]:
    """Squish scanning intervals into effective DAC range."""
    lower = lower_bound / bitwidth
    upper = upper_bound / bitwidth

    def f(x: float) -> float:
        return lower + (upper - lower) * x

    return [Interval(f(interval.lower), f(interval.upper)) for interval in intervals]


def _delay_from_intervals(
    delayunit: Callable[[FloatArray], FloatArray],
    intervals: list[Interval],
    points_per_interval: list[int],
) -> FloatArray:
    """Convert a list of intervals to a list of delay times."""
    times: list[float] = []
    for interval, n_points in zip(intervals, points_per_interval):
        times.extend(
            delayunit(
                np.linspace(interval.lower, interval.upper, n_points, endpoint=False)
            )
        )
    return np.array(times)
