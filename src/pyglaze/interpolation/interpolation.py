from typing import cast

import numpy as np
from scipy.interpolate import CubicSpline

from pyglaze.helpers._types import FloatArray


def ws_interpolate(
    times: FloatArray, pulse: FloatArray, interp_times: FloatArray
) -> FloatArray:
    """Performs Whittaker-Shannon interpolation at the supplied times given a pulse.

    Args:
        times: Sampling times
        pulse: A sampled pulse satisfying the Nyquist criterion
        interp_times: Array of times at which to interpolate

    Returns:
        FloatArray: Interpolated values
    """
    dt = times[1] - times[0]
    _range = np.arange(len(pulse))
    # times must be zero-centered for formula to work
    sinc = np.sinc((interp_times[:, np.newaxis] - times[0] - dt * _range) / dt)

    return cast("FloatArray", np.sum(pulse * sinc, axis=1))


def cubic_spline_interpolate(
    times: FloatArray, pulse: FloatArray, interp_times: FloatArray
) -> FloatArray:
    """Performs cubic spline interpolation at the supplied times given a pulse.

    Args:
        times: Sampling times
        pulse: A sampled pulse satisfying the Nyquist criterion
        interp_times: Array of times at which to interpolate

    Returns:
        FloatArray: Interpolated values
    """
    spline = CubicSpline(times, pulse, bc_type="natural")
    return cast("FloatArray", spline(interp_times))
