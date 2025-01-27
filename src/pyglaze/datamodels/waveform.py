from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
from scipy.interpolate import CubicSpline

from .pulse import Pulse

if TYPE_CHECKING:
    from datetime import datetime

    from pyglaze.helpers._types import FloatArray

__all__ = ["UnprocessedWaveform"]

RecoMethod = Literal["cubic_spline"]


@dataclass(frozen=True)
class UnprocessedWaveform:
    """A dataclass representing an unprocessed waveform. No assumptions are made about the delay or signal.

    Args:
        time: The time values recorded by the lock-in amp during the scan.
        signal: The signal values recorded by the lock-in amp during the scan.
    """

    time: FloatArray
    signal: FloatArray

    @classmethod
    def from_polar_coords(
        cls: type[UnprocessedWaveform],
        time: FloatArray,
        radius: FloatArray,
        theta: FloatArray,
        rotation_angle: float | None = None,
    ) -> UnprocessedWaveform:
        """Create an UnprocessedWaveform object from raw lock-in amp output.

        Args:
            time: The time values recorded by the lock-in amp during the scan.
            radius: The radius values recorded by the lock-in amp during the scan.
            theta: The theta values recorded by the lock-in amp during the scan (in degrees).
            rotation_angle: The angle to rotate lockin signal to align along x-axis. If not given, will use the angle at the maximum value of R.
        """
        _rot_ang = (
            theta[np.argmax(radius)] if rotation_angle is None else rotation_angle
        )

        # rotate such that all signal lies along X
        new_theta = theta - _rot_ang
        signal = radius * np.cos(new_theta * np.pi / 180.0)
        return cls(time, signal)

    @classmethod
    def from_dict(
        cls: type[UnprocessedWaveform], d: dict[str, FloatArray | list[float] | None]
    ) -> UnprocessedWaveform:
        """Create an UnprocessedWaveform object from a dictionary.

        Args:
            d: A dictionary containing the keys 'time', 'signal'.
        """
        return UnprocessedWaveform(
            time=np.array(d["time"]), signal=np.array(d["signal"])
        )

    def reconstruct(
        self: UnprocessedWaveform, method: RecoMethod, times: FloatArray | None = None
    ) -> UnprocessedWaveform:
        """Reconstructs the waveform for a specified array of times using a specified method. If no delays are given, linearly spaced times between the maximum and the minimum of the delays will be used.

        Args:
            method: Name of reconstruction method.
            times: Optional array of delay times.

        Raises:
            ValueError: When an unknown reconstruction method is requested
        """
        if times is None:
            times = np.linspace(
                self.time[0], self.time[-1], len(self.time), endpoint=True
            )

        if method == "cubic_spline":
            return UnprocessedWaveform(
                times, CubicSpline(self.time, self.signal)(times)
            )

        msg = f"Unknown reconstruction method: {method}"
        raise ValueError(msg)

    @classmethod
    def average(
        cls: type[UnprocessedWaveform], waveforms: list[UnprocessedWaveform]
    ) -> UnprocessedWaveform:
        """Computes the average of a list of UnprocessedWaveform objects.

        Args:
            waveforms: List of waveforms

        """
        if len(waveforms) == 1:
            return waveforms[0]
        signals = np.array([waveform.signal for waveform in waveforms])
        return UnprocessedWaveform(
            time=waveforms[0].time, signal=np.mean(signals, axis=0)
        )

    def from_triangular_waveform(
        self: UnprocessedWaveform, ramp: Literal["up", "down"]
    ) -> UnprocessedWaveform:
        """Picks out the pulse from a scan with fiberstretchers driven by a triangular waveform.

        Args:
            ramp: Whether to pick out the pulse from the upgoing or downgoing ramp of the triangle wave

        Raises:
            ValueError: If 'ramp' is neither 'up' or 'down'

        Returns:
            Raw waveform
        """
        argmax = np.argmax(self.time)
        argmin = np.argmin(self.time)
        min_before_max = argmin < argmax
        if ramp == "up" and min_before_max:  # down up down
            t = self.time[argmin : argmax + 1]
            s = self.signal[argmin : argmax + 1]
        elif ramp == "up" and not min_before_max:  # up down up
            t = np.concatenate((self.time[argmin:], self.time[: argmax + 1]))
            s = np.concatenate((self.signal[argmin:], self.signal[: argmax + 1]))
        elif ramp == "down" and min_before_max:  # down up down
            t = np.flip(np.concatenate((self.time[argmax:], self.time[: argmin + 1])))
            s = np.flip(
                np.concatenate((self.signal[argmax:], self.signal[: argmin + 1]))
            )
        elif ramp == "down" and not min_before_max:  # up down up
            t = np.flip(self.time[argmax : argmin + 1])
            s = np.flip(self.signal[argmax : argmin + 1])
        else:
            msg = "'ramp' must be either 'up' or 'down'"
            raise ValueError(msg)

        return UnprocessedWaveform(time=t, signal=s)

    def as_pulse(self: UnprocessedWaveform) -> Pulse:
        """Converts the current waveform to a Pulse object."""
        return Pulse(time=self.time, signal=self.signal)


@dataclass
class _TimestampedWaveform:
    """A data class representing a terahertz pulse with a timestamp.

    Args:
        timestamp: The timestamp of the pulse given by the Toptica server.
        waveform: The terahertz pulse received from the Toptica server.
    """

    timestamp: datetime
    waveform: UnprocessedWaveform
