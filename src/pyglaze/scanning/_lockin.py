from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from pyglaze.helpers._types import FloatArray


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
        r_argmax = np.argmax(radius)
        r_max = radius[r_argmax]
        theta_at_max = theta[r_argmax]
        if self._radius_of_est is None:
            self._set_estimates(theta_at_max, r_max)
            return

        if r_max > self.r_threshold_for_update * self._radius_of_est or (
            r_max > self._radius_of_est
            and abs(theta_at_max - self.phase_estimate)
            < self.theta_threshold_for_adjustment
        ):
            self._set_estimates(theta_at_max, r_max)

    def _set_estimates(
        self: _LockinPhaseEstimator, phase: float, radius: float
    ) -> None:
        self.phase_estimate = phase
        self._radius_of_est = radius
