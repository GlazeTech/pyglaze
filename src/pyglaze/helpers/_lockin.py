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


def _rotate_inphase(X: FloatArray, Y: FloatArray, phi: float) -> FloatArray:
    """Compute in-phase after rotation by phi."""
    return X * np.cos(phi) + Y * np.sin(phi)


def _polar_to_IQ(r: FloatArray, theta: FloatArray) -> tuple[FloatArray, FloatArray]:
    """Convert polar coordinates to IQ (X,Y) coordinates."""
    X = r * np.cos(theta)
    Y = r * np.sin(theta)
    return X, Y


def _choose_branch_by_strongest_point(
    theta: float, X: FloatArray, Y: FloatArray, strength: FloatArray | None = None
) -> float:
    """Choose between theta and theta+pi so the strongest sample projects positive on the in-phase axis.

    strength can be r or r² because only ordering matters
    """
    if strength is None:
        strength = X * X + Y * Y
    k = int(np.argmax(strength))
    proj = X[k] * np.cos(theta) + Y[k] * np.sin(theta)  # in-phase at strongest point
    return theta if proj >= 0 else (theta + np.pi)


def _eigenvalues_symmetric_2D(
    Sxx: float, Sxy: float, Syy: float
) -> tuple[float, float]:
    """Compute the eigenvalues of a symmetric 2D matrix."""
    trace = Sxx + Syy
    D = float(np.sqrt((Sxx - Syy) ** 2 + 4.0 * (Sxy**2)))
    eig1 = 0.5 * (trace + D)
    eig2 = 0.5 * (trace - D)
    # Numerical hygiene: symmetric PSD should be >=0, but float noise can create tiny negatives
    eig1 = float(max(eig1, 0.0))
    eig2 = float(max(eig2, 0.0))
    return eig1, eig2


def _estimate_IQ_phase(
    X: FloatArray, Y: FloatArray, w: FloatArray | None = None
) -> tuple[float, float]:
    """Estimate the constant lock-in phase (orientation, modulo π) from many (X, Y) lock-in samples by fitting the dominant axis of the IQ cloud.

    This treats each sample as a point in the IQ plane: z_i = X_i + j Y_i, and
    finds the rotation angle φ such that rotating all points by -φ makes the
    energy in the quadrature channel minimal (equivalently: maximizes the energy
    along the in-phase axis). Because this estimates an *axis* rather than a
    directed angle, the result is naturally defined modulo π.

    Estimates phase by calculating a weighted PCA / eigenvector estimate of the first
    principal component direction in 2D. The angle of this direction is the estimated
    lock-in phase.
    """
    # Weighted second moment matrix components - a weighted, scaled covariance matrix without mean subtraction
    if w is None:
        w = X * X + Y * Y

    Sxx = np.sum(w * X * X)
    Sxy = np.sum(w * X * Y)
    Syy = np.sum(w * Y * Y)

    # weighted cov matrix defines an ellipse; find its principal axis angle (see: https://en.wikipedia.org/wiki/Ellipse#General_ellipse)
    phi_estimate = 0.5 * np.arctan2(2.0 * Sxy, (Sxx - Syy))

    # The squareroot of the eigenvalues correspond to the semi-axis lengths of the ellipse defined by the weighted cov matrix
    # When very line-like, we've succesfully mapped all signal into one axis, corresponding to high confidence in phase estimate
    eig1, eig2 = _eigenvalues_symmetric_2D(Sxx, Sxy, Syy)

    # If the matrix is (near) zero or non-finite, the phase is not meaningful
    if not np.isfinite(eig1) or not np.isfinite(eig2) or eig1 <= 0.0:
        return phi_estimate, 0.0

    axis_ratio = float(np.sqrt(eig2 / eig1))  # in [0, 1] ideally
    if not np.isfinite(axis_ratio):
        return phi_estimate, 0.0

    confidence = np.clip(1.0 - axis_ratio, 0, 1)  # 0 (circle) to 1 (line)

    return phi_estimate, confidence


class _LockinPhaseEstimator:
    def __init__(
        self: _LockinPhaseEstimator,
        confidence_threshold: float = 0.8,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.phase_estimate: float | None = None

    def update_estimate(
        self: _LockinPhaseEstimator, Xs: FloatArray, Ys: FloatArray
    ) -> None:
        """Update the phase estimate based on new in-phase (X) and quadrature (Y) data.

        Args:
            Xs: Array of in-phase (X) values from the lock-in amplifier.
            Ys: Array of quadrature (Y) values from the lock-in amplifier.
        """
        r_squared = Xs * Xs + Ys * Ys
        phase_estimate, confidence = _estimate_IQ_phase(Xs, Ys, r_squared)

        # Don't update if confidence is too low
        if confidence < self.confidence_threshold:
            return

        # First estimate
        if self.phase_estimate is None:
            self._set_estimate(
                _choose_branch_by_strongest_point(phase_estimate, Xs, Ys, r_squared)
            )
            return

        # Resolve the pi ambiguity using previous estimate
        branched_phase_estimate = _choose_pi_branch(phase_estimate, self.phase_estimate)
        self._set_estimate(branched_phase_estimate)

    def _set_estimate(self: _LockinPhaseEstimator, phase: float) -> None:
        self.phase_estimate = _wrap_to_pi(float(phase))
