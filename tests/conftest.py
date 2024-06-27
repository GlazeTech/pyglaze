import numpy as np
import pytest

from pyglaze.datamodels import Pulse, UnprocessedWaveform
from pyglaze.device import ForceDeviceConfiguration, Interval, LeDeviceConfiguration
from pyglaze.devtools.thz_pulse import gaussian_derivative_pulse

DEVICE_CONFIGS = ["force_device_config", "le_device_config"]


@pytest.fixture()
def force_device_config() -> ForceDeviceConfiguration:
    return ForceDeviceConfiguration(
        amp_port="mock_device",
        delayunit="mock_delay",
        integration_periods=100,
        modulation_frequency=10000,
        sweep_length_ms=100,
        dac_lower_bound=6400,
        dac_upper_bound=59300,
        min_modulation_voltage=-1.0,  # V,
        max_modulation_voltage=0.5,  # V,
        modulation_waveform="square",
        amp_timeout_seconds=0.05,  # s,
        scan_intervals=[Interval(0.0, 1.0)],
    )


@pytest.fixture()
def le_device_config() -> LeDeviceConfiguration:
    return LeDeviceConfiguration(
        amp_port="mock_device",
        delayunit="mock_delay",
        use_ema=True,
        n_points=100,
        scan_intervals=[Interval(0.0, 1.0)],
        integration_periods=1,
        amp_timeout_seconds=7,
    )


@pytest.fixture(scope="session")
def scan_data() -> Pulse:
    t = np.linspace(0, 50, 51)
    sig = np.sin(t)
    return Pulse(t, sig)


@pytest.fixture()
def unprocessed_waveform_nonuniform() -> UnprocessedWaveform:
    generator = np.random.default_rng(42)
    t = np.linspace(0, 50, 51) + generator.uniform(low=-0.5, high=0.5, size=51)
    sig = np.sin(t)
    return UnprocessedWaveform(t, sig)


@pytest.fixture()
def triangular_waveform_up_down() -> UnprocessedWaveform:
    times = np.concatenate(
        (
            np.linspace(np.pi / 2, np.pi, 50, endpoint=False),
            np.linspace(np.pi, 0, 100, endpoint=False),
            np.linspace(0, np.pi / 2, 50, endpoint=False),
        )
    )
    return UnprocessedWaveform(time=2 * times, signal=np.sin(2 * times))


@pytest.fixture()
def triangular_waveform_down_up() -> UnprocessedWaveform:
    times = np.concatenate(
        (
            np.linspace(np.pi / 2, 0, 51, endpoint=False),
            np.linspace(0, np.pi, 101, endpoint=False),
            np.linspace(np.pi, np.pi / 2, 51, endpoint=False),
        )
    )
    return UnprocessedWaveform(time=2 * times, signal=np.sin(2 * times))


@pytest.fixture()
def gaussian_deriv_pulse() -> Pulse:
    dt = 0.1e-12
    times = np.arange(1000) * dt
    return Pulse(
        time=times,
        signal=gaussian_derivative_pulse(time=times, t0=10e-12, sigma=0.3e-12),
    )


@pytest.fixture()
def gaussian_deriv_pulse_w_errors(gaussian_deriv_pulse: Pulse) -> Pulse:
    return gaussian_deriv_pulse.add_white_noise(noise_std=1e-2, seed=42)
