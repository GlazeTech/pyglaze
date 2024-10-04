from typing import Literal  # noqa: N999

import numpy as np
import pytest

from pyglaze.datamodels import Pulse, UnprocessedWaveform


def test_from_polar_output(gaussian_deriv_pulse_w_errors: Pulse) -> None:
    # Convert a pulse to a raw output
    radius = np.abs(gaussian_deriv_pulse_w_errors.signal)
    sign = np.clip(np.sign(gaussian_deriv_pulse_w_errors.signal), a_min=0, a_max=1)
    argmax_sign = sign[np.argmax(radius)]
    angle = np.zeros(len(sign))
    angle[sign == argmax_sign] = 120
    angle[sign != argmax_sign] = 120 + 180
    from_raw = UnprocessedWaveform.from_polar_coords(
        time=gaussian_deriv_pulse_w_errors.time, radius=radius, theta=angle
    )
    # -1, since the maximum R is negative
    assert np.all(gaussian_deriv_pulse_w_errors.signal == -1 * from_raw.signal)


def test_reconstruct_cubic_spline(
    unprocessed_waveform_nonuniform: UnprocessedWaveform,
) -> None:
    processed_waveform = unprocessed_waveform_nonuniform.reconstruct(
        method="cubic_spline"
    )

    assert isinstance(processed_waveform, UnprocessedWaveform)
    np.allclose(
        np.diff(processed_waveform.time),
        processed_waveform.time[1] - processed_waveform.time[0],
    )


def test_reconstruct_unknown_method(
    unprocessed_waveform_nonuniform: UnprocessedWaveform,
) -> None:
    with pytest.raises(ValueError, match="Unknown reconstruction*"):
        unprocessed_waveform_nonuniform.reconstruct(method="unknown_method")  # type: ignore[arg-type]


def test_as_pulse(unprocessed_waveform_nonuniform: UnprocessedWaveform) -> None:
    assert isinstance(unprocessed_waveform_nonuniform.as_pulse(), Pulse)


def test_waveform_average(unprocessed_waveform_nonuniform: UnprocessedWaveform) -> None:
    avg = UnprocessedWaveform.average(
        [unprocessed_waveform_nonuniform, unprocessed_waveform_nonuniform]
    )
    assert np.sum(avg.signal - unprocessed_waveform_nonuniform.signal) == 0
    assert isinstance(avg, UnprocessedWaveform)


@pytest.mark.parametrize(
    "waveform_name", ["triangular_waveform_up_down", "triangular_waveform_down_up"]
)
@pytest.mark.parametrize("ramp", ["up", "down"])
def test_from_triangular_waveform_length(
    waveform_name: str, ramp: Literal["up", "down"], request: pytest.FixtureRequest
) -> None:
    waveform: UnprocessedWaveform = request.getfixturevalue(waveform_name)
    picked = waveform.from_triangular_waveform(ramp=ramp)

    np.allclose(np.diff(picked.time), waveform.time[1] - waveform.time[0])


def test_from_triangular_raises(
    unprocessed_waveform_nonuniform: UnprocessedWaveform,
) -> None:
    with pytest.raises(ValueError, match="'ramp' must be either 'up' or 'down'"):
        unprocessed_waveform_nonuniform.from_triangular_waveform("wrong")  # type: ignore[arg-type]


def test_from_dict() -> None:
    d: dict[str, list[float]] = {"time": [0.0, 1.0, 2.0], "signal": [0.1, 0.2, 0.3]}
    waveform = UnprocessedWaveform.from_dict(d)  # type: ignore[arg-type]
    assert np.array_equal(waveform.time, np.array([0.0, 1.0, 2.0]))
    assert np.array_equal(waveform.signal, np.array([0.1, 0.2, 0.3]))
