from __future__ import annotations

from typing import TYPE_CHECKING, cast

import numpy as np

if TYPE_CHECKING:
    from pyglaze.helpers._types import FloatArray


def gaussian_derivative_pulse(
    time: FloatArray,
    t0: float,
    sigma: float,
    signal_to_noise: float | None = None,
) -> FloatArray:
    """Simulates a THz pulse as the derivative of a Gaussian.

    Args:
        time: Times to evaluate pulse at
        t0: Center position of pulse
        sigma: Standard deviation of Gaussian
        signal_to_noise: Ratio between peak of pulse and standard deviation of noise

    Returns:
        Simulated pulse
    """
    signal: np.ndarray = (time - t0) * np.exp(-0.5 * ((time - t0) / sigma) ** 2)
    noise = (
        0.0
        if signal_to_noise is None
        else np.random.default_rng().normal(
            scale=1.0 / signal_to_noise, size=len(signal)
        )
    )
    return cast("FloatArray", signal / np.max(signal) + noise)
