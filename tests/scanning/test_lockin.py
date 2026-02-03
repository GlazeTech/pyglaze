import numpy as np

from pyglaze.datamodels import Pulse
from pyglaze.helpers._lockin import (
    _angular_distance,
    _LockinPhaseEstimator,
    _rotate_inphase,
)


def _make_iq(
    s: np.ndarray, phi: float, noise_std: float, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Generate synthetic IQ data: (X,Y) = s * (cos phi, sin phi) + isotropic noise."""
    c, ss = np.cos(phi), np.sin(phi)
    X = s * c + rng.normal(0.0, noise_std, size=s.shape)
    Y = s * ss + rng.normal(0.0, noise_std, size=s.shape)
    return X, Y


def _project_strongest_positive(X: np.ndarray, Y: np.ndarray, phi: float) -> float:
    """Projection of the strongest sample onto the in-phase axis defined by phi."""
    r2 = X * X + Y * Y
    k = int(np.argmax(r2))
    return float(X[k] * np.cos(phi) + Y[k] * np.sin(phi))


def test_first_update_sets_polarity_by_strongest_point() -> None:
    rng = np.random.default_rng(0)

    # Construct a waveform where the *largest magnitude* sample is negative.
    # That forces the estimator to choose the +pi branch so that sample becomes positive in-phase.
    n = 600
    s = np.zeros(n)
    s[250] = -1.0  # strongest (negative)
    s[300] = +0.7  # smaller positive lobe

    # Pick a "true axis" where the PCA orientation would naturally be near the [-pi/2, pi/2] representative.
    # Doesn't really matter; the strongest-point rule is what we are testing.
    phi_true = 0.3

    X, Y = _make_iq(s, phi_true, noise_std=0.01, rng=rng)

    est = _LockinPhaseEstimator()
    est.update_estimate(X, Y)

    assert est.phase_estimate is not None

    # Strongest point should be positive in-phase by construction of branch choice.
    proj = _project_strongest_positive(X, Y, est.phase_estimate)
    assert proj >= 0.0


def test_consecutive_scans_keep_same_branch_near_pi_wrap() -> None:
    rng = np.random.default_rng(1)

    # Make a waveform with strongest magnitude negative (so first estimate chooses +pi branch).
    n = 600
    s = np.zeros(n)
    s[200] = -1.0
    s[260] = +0.6

    # Choose a true axis near +pi, which is equivalent (mod pi) to a small negative angle.
    # This is exactly where accidental branch flips usually happen if you don't resolve pi ambiguity.
    phi_true = np.pi - 0.12  # ~3.0216 rad

    X1, Y1 = _make_iq(s, phi_true, noise_std=0.01, rng=rng)
    X2, Y2 = _make_iq(s, phi_true, noise_std=0.01, rng=rng)

    est = _LockinPhaseEstimator()

    est.update_estimate(X1, Y1)
    phi1 = est.phase_estimate
    assert phi1 is not None

    # First scan should enforce strongest-sample polarity.
    assert _project_strongest_positive(X1, Y1, phi1) >= 0.0

    est.update_estimate(X2, Y2)
    phi2 = est.phase_estimate
    assert phi2 is not None

    # The estimator should not flip by ~pi between scans.
    # Use the estimator's own distance function (wrap-aware).
    assert _angular_distance(phi2, phi1) < np.deg2rad(10.0)

    # And polarity should stay consistent: strongest sample projects positive in-phase.
    assert _project_strongest_positive(X2, Y2, phi2) >= 0.0


def test_recovered_inphase_has_consistent_sign_across_scans() -> None:
    rng = np.random.default_rng(2)

    # A crude "THz-like" bipolar pulse (derivative-ish): big negative then positive.
    # Key: max |s| is negative so the chosen polarity is deterministic.
    t = np.linspace(-3, 3, 600)
    s = (
        -np.exp(-(t**2)) * t
    )  # proportional to -d/dt exp(-t^2); largest magnitude is negative for this sampling

    phi_true = 1.1

    X1, Y1 = _make_iq(s, phi_true, noise_std=0.02, rng=rng)
    X2, Y2 = _make_iq(s, phi_true, noise_std=0.02, rng=rng)

    est = _LockinPhaseEstimator()

    est.update_estimate(X1, Y1)
    phi1 = est.phase_estimate
    assert phi1 is not None
    rec1 = _rotate_inphase(X1, Y1, phi1)

    est.update_estimate(X2, Y2)
    phi2 = est.phase_estimate
    assert phi2 is not None
    rec2 = _rotate_inphase(X2, Y2, phi2)

    # Polarity consistency check: both recovered signals should correlate with the same reference sign.
    # We don't care about absolute scaling, so use dot products.
    assert float(np.dot(rec1, s)) > 0.0
    assert float(np.dot(rec2, s)) > 0.0

    # And they should correlate with each other positively (no sign flip).
    assert float(np.dot(rec1, rec2)) > 0.0


def test_consecutive_scans_keep_same_branch(gaussian_deriv_pulse: Pulse) -> None:
    rng = np.random.default_rng(2)
    phi = np.pi / 4
    X1, Y1 = _make_iq(gaussian_deriv_pulse.signal, phi=phi, noise_std=0.01, rng=rng)

    # Create a second scan with the same underlying signal but shifted by pi in phase.
    X2, Y2 = _make_iq(
        gaussian_deriv_pulse.signal, phi=phi + np.pi, noise_std=0.01, rng=rng
    )
    est = _LockinPhaseEstimator()
    est.update_estimate(X1, Y1)
    phase1 = est.phase_estimate
    assert phase1 is not None
    est.update_estimate(X2, Y2)
    phase2 = est.phase_estimate
    assert phase2 is not None
    # The estimator should not flip by ~pi between scans.
    # Use the estimator's own distance function (wrap-aware).
    assert _angular_distance(phase2, phase1) < np.deg2rad(5.0)


def test_initial_phase_estimate_prevents_polarity_flip() -> None:
    """Test that providing an initial phase estimate maintains polarity across scanner instances."""
    rng = np.random.default_rng(3)

    # Create a waveform
    n = 600
    s = np.zeros(n)
    s[250] = -1.0
    s[300] = +0.7

    # First scanner learns the phase
    phi_true = 0.3
    X1, Y1 = _make_iq(s, phi_true, noise_std=0.01, rng=rng)

    est1 = _LockinPhaseEstimator()
    est1.update_estimate(X1, Y1)
    learned_phase = est1.phase_estimate
    assert learned_phase is not None

    # Second scanner with same initial phase should produce consistent results
    X2, Y2 = _make_iq(s, phi_true, noise_std=0.01, rng=rng)

    est2 = _LockinPhaseEstimator(initial_phase_estimate=learned_phase)
    est2.update_estimate(X2, Y2)
    phase2 = est2.phase_estimate
    assert phase2 is not None

    # Phases should be very close (no flip)
    assert _angular_distance(phase2, learned_phase) < np.deg2rad(10.0)

    # Both should produce positive projection for strongest point
    assert _project_strongest_positive(X1, Y1, learned_phase) >= 0.0
    assert _project_strongest_positive(X2, Y2, phase2) >= 0.0


def test_initial_phase_estimate_wraps_to_pi() -> None:
    """Test that initial phase estimates outside (-pi, pi] are wrapped correctly."""
    # Test a value > pi
    est1 = _LockinPhaseEstimator(initial_phase_estimate=4.0)
    assert est1.phase_estimate is not None
    assert -np.pi < est1.phase_estimate <= np.pi

    # Test a value < -pi
    est2 = _LockinPhaseEstimator(initial_phase_estimate=-5.0)
    assert est2.phase_estimate is not None
    assert -np.pi < est2.phase_estimate <= np.pi
