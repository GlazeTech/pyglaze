from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from pyglaze.helpers._types import FloatArray


def _wrap_to_pi(a: float) -> float:
    """Map angle (in radians) to (-pi, pi]."""
    return (a + np.pi) % (2 * np.pi) - np.pi


def _angular_distance(a: float, b: float) -> float:
    """Smallest absolute distance between angles a and b (in radians)."""
    return abs(_wrap_to_pi(a - b))


def _choose_pi_branch(theta: float, ref: float) -> float:
    """Choose between theta and theta+pi (mod 2pi) to be closest to ref.

    This prevents accidental polarity flips.
    """
    d0 = _angular_distance(theta, ref)
    d1 = _angular_distance(theta + np.pi, ref)
    return theta if d0 <= d1 else (theta + np.pi)


class _LockinPhaseEstimator:
    def __init__(
        self: _LockinPhaseEstimator,
        r_threshold_for_update: float = 2.0,
        theta_threshold_for_adjustment: float = 1.0,
    ) -> None:
        self.r_threshold_for_update = r_threshold_for_update
        self.theta_threshold_for_adjustment = theta_threshold_for_adjustment
        self.phase_estimate: float | None = None
        self._radius_of_est: float | None = None

    def update_estimate(
        self: _LockinPhaseEstimator, radius: FloatArray, theta: FloatArray
    ) -> None:
        """Update the phase estimate based on new radius and theta data.

        Args:
            radius: Array of radius values from the lock-in amplifier.
            theta: Array of theta values from the lock-in amplifier in radians.
        """
        r_argmax = int(np.argmax(radius))
        r_max = float(radius[r_argmax])
        theta_at_max = float(theta[r_argmax])

        # First estimate
        if self._radius_of_est is None or self.phase_estimate is None:
            self._set_estimates(theta_at_max, r_max)
            return

        # --- critical fix: resolve the pi ambiguity using previous estimate ---
        branched_theta_at_max = _choose_pi_branch(theta_at_max, self.phase_estimate)

        # --- critical fix: circular distance ---
        dtheta = _angular_distance(branched_theta_at_max, self.phase_estimate)

        if r_max > self.r_threshold_for_update * self._radius_of_est or (
            r_max > self._radius_of_est and dtheta < self.theta_threshold_for_adjustment
        ):
            self._set_estimates(branched_theta_at_max, r_max)

    def _set_estimates(
        self: _LockinPhaseEstimator, phase: float, radius: float
    ) -> None:
        self.phase_estimate = _wrap_to_pi(float(phase))
        self._radius_of_est = float(radius)
