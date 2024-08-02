import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest
from pyglaze.datamodels import Pulse


@pytest.mark.parametrize(
    "pulse_name", ["gaussian_deriv_pulse", "gaussian_deriv_pulse_w_errors"]
)
def test_scandata_cut(pulse_name: str, request: pytest.FixtureRequest) -> None:
    scan_data: Pulse = request.getfixturevalue(pulse_name)

    from_, to_ = 0.0, 25.0e-12
    arg_from, arg_to = (
        np.argwhere(scan_data.time == from_),
        np.searchsorted(scan_data.time, to_),
    )
    scan_test = scan_data.cut(from_time=from_, to_time=to_)
    assert scan_test.time[0] == from_
    assert scan_test.signal[0] == scan_data.signal[arg_from]
    assert pytest.approx(scan_test.time[-1], rel=1e-2) == to_
    assert scan_test.signal[-1] == scan_data.signal[arg_to]
    assert isinstance(scan_test.signal_err, type(scan_data.signal_err))
    assert isinstance(scan_test, Pulse)


def test_scandata_average(scan_data: Pulse) -> None:
    avg = scan_data.average([scan_data, scan_data])
    assert avg.signal_err is not None
    assert avg.signal_err.shape == scan_data.signal.shape
    assert np.sum(avg.signal - scan_data.signal) == 0
    assert np.sum(avg.signal_err) == 0


def test_scandata_average_single(scan_data: Pulse) -> None:
    avg = scan_data.average([scan_data])
    assert np.sum(avg.signal - scan_data.signal) == 0


def test_scandata_time_window(scan_data: Pulse) -> None:
    assert scan_data.time_window == scan_data.time[-1] - scan_data.time[0]


def test_from_fft(scan_data: Pulse) -> None:
    fft = scan_data.fft
    from_fft = scan_data.from_fft(scan_data.time, fft)
    np.testing.assert_array_almost_equal(scan_data.signal, from_fft.signal)
    np.testing.assert_array_almost_equal(scan_data.time, from_fft.time)


@pytest.mark.parametrize(
    "pulse_name", ["gaussian_deriv_pulse", "gaussian_deriv_pulse_w_errors"]
)
@pytest.mark.parametrize(
    "tukey_args",
    [
        {"taper_length": 10e-12},
        {"taper_length": 10e-12, "from_time": 10e-12, "to_time": 40e-12},
    ],
)
def test_tukey(
    tukey_args: dict, pulse_name: str, request: pytest.FixtureRequest
) -> None:
    scan_data: Pulse = request.getfixturevalue(pulse_name)
    windowed = scan_data.tukey(**tukey_args)
    assert isinstance(windowed, Pulse)
    assert len(windowed) == len(scan_data)
    assert windowed.signal[0] == 0


def test_tukey_raises_err(gaussian_deriv_pulse: Pulse) -> None:
    with pytest.raises(
        ValueError,
        match="Number of points in Tukey window cannot exceed number of points in scan",
    ):
        gaussian_deriv_pulse.tukey(
            from_time=gaussian_deriv_pulse.time[0]
            - 0.01 * gaussian_deriv_pulse.time_window,
            to_time=gaussian_deriv_pulse.time[-1]
            + 0.01 * gaussian_deriv_pulse.time_window,
            taper_length=gaussian_deriv_pulse.time_window * 0.4,
        )


@pytest.mark.parametrize("shift", [1.5, -1.5])
@pytest.mark.parametrize(
    "pulse_name", ["gaussian_deriv_pulse", "gaussian_deriv_pulse_w_errors"]
)
def test_align(pulse_name: str, shift: float, request: pytest.FixtureRequest) -> None:
    pulse = request.getfixturevalue(pulse_name)
    d1 = deepcopy(pulse)
    d2 = deepcopy(pulse)

    # Misalign the scans
    d2 = Pulse.from_fft(
        d2.time, d2.fft * np.exp(2j * d2.frequency * np.pi * d2.dt * shift)
    )
    aligned = Pulse.align([d1, d2], wrt_max=True)
    argmax_variance = np.abs(np.diff([np.argmax(scan.signal) for scan in aligned]))
    time_variance = np.var([len(s.time) for s in aligned])
    sig_variance = np.var([len(s.signal) for s in aligned])
    assert time_variance == 0.0
    assert sig_variance == 0.0
    assert np.max(argmax_variance) <= 1.0


@pytest.mark.parametrize(
    "pulse_name", ["gaussian_deriv_pulse", "gaussian_deriv_pulse_w_errors"]
)
def test_from_dict(pulse_name: str, request: pytest.FixtureRequest) -> None:
    pulse: Pulse = request.getfixturevalue(pulse_name)
    as_d = asdict(pulse)
    from_d = Pulse.from_dict(as_d)
    for attr in [
        "time",
        "signal",
        "fft",
        "frequency",
        "signal_err",
    ]:
        assert np.all(getattr(pulse, attr) == getattr(from_d, attr))


@pytest.mark.parametrize(
    "pulse_name", ["gaussian_deriv_pulse", "gaussian_deriv_pulse_w_errors"]
)
def test_to_native_dict(pulse_name: str, request: pytest.FixtureRequest) -> None:
    pulse: Pulse = request.getfixturevalue(pulse_name)
    as_d = pulse.to_native_dict()
    from_d = Pulse.from_dict(as_d)  # type: ignore[arg-type]
    for attr in [
        "time",
        "signal",
        "signal_err",
    ]:
        assert np.all(getattr(pulse, attr) == getattr(from_d, attr))

    assert isinstance(as_d["time"], list)
    assert isinstance(as_d["signal"], list)
    if pulse.signal_err is None:
        assert as_d["signal_err"] is None
    else:
        assert isinstance(as_d["signal_err"], list)


def test_spectrum_dB(gaussian_deriv_pulse: Pulse) -> None:
    dB = gaussian_deriv_pulse.spectrum_dB()
    assert len(dB) == len(gaussian_deriv_pulse.frequency)
    assert np.max(dB) == 0
    assert isinstance(dB[0], np.floating)


def test_spectrum_dB_with_offset(gaussian_deriv_pulse_w_errors: Pulse) -> None:
    dB_offset = gaussian_deriv_pulse_w_errors.spectrum_dB(offset_ratio=1e-12)
    dB_no_offset = gaussian_deriv_pulse_w_errors.spectrum_dB()
    assert pytest.approx(np.max(dB_offset), abs=1e-5) == 0
    assert pytest.approx(np.min(dB_offset) - np.min(dB_no_offset), abs=1e-5) == 0


def test_zeropad(gaussian_deriv_pulse: Pulse) -> None:
    n_zeros = 10
    padded = gaussian_deriv_pulse.zeropadded(n_zeros=n_zeros)

    assert len(padded.signal) == len(padded.time)

    assert padded.time[n_zeros] == gaussian_deriv_pulse.time[0]
    assert not np.all(np.diff(padded.time) - gaussian_deriv_pulse.dt)
    np.testing.assert_equal(padded.signal[:n_zeros], np.zeros(n_zeros))
    np.testing.assert_equal(padded.signal[n_zeros:], gaussian_deriv_pulse.signal)


def test_sampling_freq(gaussian_deriv_pulse: Pulse) -> None:
    sampling_freq = 1 / (gaussian_deriv_pulse.time[1] - gaussian_deriv_pulse.time[0])
    assert gaussian_deriv_pulse.sampling_freq == sampling_freq


def test_lowpass_filter(gaussian_deriv_pulse: Pulse) -> None:
    cutoff = 2e12
    filtered = gaussian_deriv_pulse.filter(filtertype="lowpass", cutoff=cutoff, order=1)
    cutoff_idx = np.searchsorted(filtered.frequency, cutoff)
    assert np.abs(gaussian_deriv_pulse.fft[cutoff_idx]) > np.abs(
        filtered.fft[cutoff_idx]
    )


def test_highpass_filter(gaussian_deriv_pulse: Pulse) -> None:
    cutoff = 1e12
    filtered = gaussian_deriv_pulse.filter(
        filtertype="highpass", cutoff=cutoff, order=1
    )
    cutoff_idx = np.searchsorted(filtered.frequency, cutoff)
    assert np.abs(gaussian_deriv_pulse.fft[cutoff_idx // 2]) > np.abs(
        filtered.fft[cutoff_idx // 2]
    )


def test_timeshift(gaussian_deriv_pulse: Pulse) -> None:
    shift, offset = 0.5, 1.0e-12
    shifted = gaussian_deriv_pulse.timeshift(scale=shift, offset=offset)
    assert pytest.approx(shifted.dt, rel=1e-6) == shift * gaussian_deriv_pulse.dt
    assert shifted.time[0] == shift * (gaussian_deriv_pulse.time[0] + offset)


def test_add_white_noise(gaussian_deriv_pulse: Pulse) -> None:
    noisy_pulse = gaussian_deriv_pulse.add_white_noise(1, seed=42)
    ref = np.max(np.abs(gaussian_deriv_pulse.fft))
    assert np.min(gaussian_deriv_pulse.spectrum_dB(reference=ref)) < np.min(
        noisy_pulse.spectrum_dB(reference=ref)
    )


def test_add_white_noise_gives_different_noise(gaussian_deriv_pulse: Pulse) -> None:
    noisy_pulse1 = gaussian_deriv_pulse.add_white_noise(0.01)
    noisy_pulse2 = gaussian_deriv_pulse.add_white_noise(0.01)
    assert noisy_pulse1 != noisy_pulse2


def test_delay_at_max(gaussian_deriv_pulse: Pulse) -> None:
    delay = gaussian_deriv_pulse.time[np.argmax(gaussian_deriv_pulse.signal)]
    assert delay == gaussian_deriv_pulse.delay_at_max


def test_delay_at_min(gaussian_deriv_pulse: Pulse) -> None:
    delay = gaussian_deriv_pulse.time[np.argmin(gaussian_deriv_pulse.signal)]
    assert delay == gaussian_deriv_pulse.delay_at_min


def test_downsample(gaussian_deriv_pulse: Pulse) -> None:
    new_limit = 2.5e12
    downsampled = gaussian_deriv_pulse.downsample(max_frequency=new_limit)
    assert np.min(downsampled.spectrum_dB()) >= np.min(
        gaussian_deriv_pulse.spectrum_dB()
    )
    assert downsampled.time[0] == gaussian_deriv_pulse.time[0]
    assert gaussian_deriv_pulse.time_window == pytest.approx(downsampled.time_window)
    assert downsampled.frequency[-1] <= new_limit


def test_save_and_load_as_json(
    gaussian_deriv_pulse: Pulse, gaussian_deriv_pulse_w_errors: Pulse, tmp_path: Path
) -> None:
    nested_object = {
        "pulses": [
            gaussian_deriv_pulse.to_native_dict(),
            gaussian_deriv_pulse_w_errors.to_native_dict(),
        ]
    }
    _p = "tmp_json_object.json"
    with Path(tmp_path / _p).open("w") as f:
        json.dump(nested_object, f)

    with Path(tmp_path / _p).open() as f:
        loaded_obj = json.load(f)

    for i_pulse in range(len(nested_object["pulses"])):
        assert Pulse.from_dict(nested_object["pulses"][i_pulse]) == Pulse.from_dict(  # type: ignore[arg-type]
            loaded_obj["pulses"][i_pulse]
        )


def test_pulse_equality(
    gaussian_deriv_pulse: Pulse, gaussian_deriv_pulse_w_errors: Pulse
) -> None:
    generator = np.random.default_rng(42)
    random_pulse_1 = Pulse(
        time=generator.uniform(size=100), signal=generator.uniform(size=100)
    )
    random_pulse_2 = Pulse(
        time=generator.uniform(size=100), signal=generator.uniform(size=100)
    )

    random_pulse_3 = Pulse(
        time=random_pulse_2.time[:-1], signal=random_pulse_2.signal[:-1]
    )
    random_pulse_4 = Pulse(
        time=random_pulse_2.time[:-1], signal=random_pulse_2.signal[:-2]
    )
    random_pulse_5 = deepcopy(gaussian_deriv_pulse)
    random_pulse_5.signal_err = np.ones(len(random_pulse_5.signal))

    gaussian_deriv_pulse_copy = deepcopy(gaussian_deriv_pulse)
    scan_data_w_errors_copy = deepcopy(gaussian_deriv_pulse_w_errors)

    assert random_pulse_1 != random_pulse_2
    assert random_pulse_2 != random_pulse_3
    assert random_pulse_3 != random_pulse_4
    assert random_pulse_5 != gaussian_deriv_pulse
    assert gaussian_deriv_pulse == gaussian_deriv_pulse_copy
    assert gaussian_deriv_pulse_w_errors == scan_data_w_errors_copy
    assert gaussian_deriv_pulse != gaussian_deriv_pulse_w_errors
    assert gaussian_deriv_pulse != 1


def test_estimate_bandwidth(gaussian_deriv_pulse: Pulse) -> None:
    pulse_w_noise = gaussian_deriv_pulse.add_white_noise(0.01, seed=42)
    assert pytest.approx(1.71e12, 0.01) == pulse_w_noise.estimate_bandwidth()


def test_estimate_dynamic_range(gaussian_deriv_pulse: Pulse) -> None:
    pulse_w_noise = gaussian_deriv_pulse.add_white_noise(0.01, seed=42)
    assert pytest.approx(28.6, 0.01) == pulse_w_noise.estimate_dynamic_range()


def test_estimate_noise_power(gaussian_deriv_pulse: Pulse) -> None:
    pulse_w_noise = gaussian_deriv_pulse.add_white_noise(0.01, seed=42)
    noise_dB = 20 * np.log10(
        np.sqrt(pulse_w_noise.estimate_avg_noise_power())
        / np.max(np.abs(pulse_w_noise.fft))
    )

    assert pytest.approx(-pulse_w_noise.estimate_dynamic_range(), 0.01) == noise_dB


def test_estimate_SNR(gaussian_deriv_pulse: Pulse) -> None:
    pulse_w_noise = gaussian_deriv_pulse.add_white_noise(0.01, seed=42)
    snr = pulse_w_noise.estimate_SNR()

    assert np.max(snr) == pytest.approx(
        pulse_w_noise.maximum_spectral_density**2
        / pulse_w_noise.estimate_avg_noise_power(),
        1.0,
    )
    bw_idx = np.searchsorted(
        pulse_w_noise.frequency, pulse_w_noise.estimate_bandwidth()
    )
    # SNR changes rapidly close to noisefloor - if the estimate is within a factor 10 at the noisefloor, it is acceptable
    assert snr[bw_idx] == pytest.approx(1.0, 10)


def test_estimate_peak_to_peak(gaussian_deriv_pulse: Pulse) -> None:
    high_accuracy_p2p = gaussian_deriv_pulse.estimate_peak_to_peak(
        delay_tolerance=gaussian_deriv_pulse.dt / 100
    )
    low_accuracy_p2p = gaussian_deriv_pulse.estimate_peak_to_peak()
    assert high_accuracy_p2p > low_accuracy_p2p


def test_center_frequency(gaussian_deriv_pulse: Pulse) -> None:
    center_freq = gaussian_deriv_pulse.center_frequency
    assert center_freq == pytest.approx(
        gaussian_deriv_pulse.frequency[np.argmax(np.abs(gaussian_deriv_pulse.fft))]
    )


def test_df(gaussian_deriv_pulse: Pulse) -> None:
    freq_spacing = gaussian_deriv_pulse.df
    assert freq_spacing == pytest.approx(
        gaussian_deriv_pulse.frequency[1] - gaussian_deriv_pulse.frequency[0]
    )


def test_derivative(gaussian_deriv_pulse: Pulse) -> None:
    derivative = gaussian_deriv_pulse.derivative()
    assert len(derivative) == len(gaussian_deriv_pulse)


def test_estimate_peak_to_peak_raises(gaussian_deriv_pulse: Pulse) -> None:
    with pytest.raises(
        ValueError,
        match="Tolerance must be smaller than the time spacing of the pulse.",
    ):
        gaussian_deriv_pulse.estimate_peak_to_peak(
            delay_tolerance=gaussian_deriv_pulse.dt
        )
