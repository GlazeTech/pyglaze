import numpy as np
import pytest

from pyglaze.datamodels import Pulse, UnprocessedWaveform
from pyglaze.device import Interval, LeDeviceConfiguration
from pyglaze.devtools.thz_pulse import gaussian_derivative_pulse

DEVICE_CONFIGS = ["le_device_config"]


@pytest.fixture
def le_device_config() -> LeDeviceConfiguration:
    return LeDeviceConfiguration(
        amp_port="mock_device",
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


@pytest.fixture
def unprocessed_waveform_nonuniform() -> UnprocessedWaveform:
    generator = np.random.default_rng(42)
    t = np.linspace(0, 50, 51) + generator.uniform(low=-0.5, high=0.5, size=51)
    sig = np.sin(t)
    return UnprocessedWaveform(t, sig)


@pytest.fixture
def triangular_waveform_up_down() -> UnprocessedWaveform:
    times = np.concatenate(
        (
            np.linspace(np.pi / 2, np.pi, 50, endpoint=False),
            np.linspace(np.pi, 0, 100, endpoint=False),
            np.linspace(0, np.pi / 2, 50, endpoint=False),
        )
    )
    return UnprocessedWaveform(time=2 * times, signal=np.sin(2 * times))


@pytest.fixture
def triangular_waveform_down_up() -> UnprocessedWaveform:
    times = np.concatenate(
        (
            np.linspace(np.pi / 2, 0, 51, endpoint=False),
            np.linspace(0, np.pi, 101, endpoint=False),
            np.linspace(np.pi, np.pi / 2, 51, endpoint=False),
        )
    )
    return UnprocessedWaveform(time=2 * times, signal=np.sin(2 * times))


@pytest.fixture
def gaussian_deriv_pulse() -> Pulse:
    dt = 0.1e-12
    times = np.arange(1000) * dt
    return Pulse(
        time=times,
        signal=gaussian_derivative_pulse(time=times, t0=10e-12, sigma=0.3e-12),
    )


@pytest.fixture
def gaussian_deriv_pulse_w_errors(gaussian_deriv_pulse: Pulse) -> Pulse:
    return gaussian_deriv_pulse.add_white_noise(noise_std=1e-2, seed=42)
