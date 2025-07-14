from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal, cast

import numpy as np
from scipy import optimize as opt
from scipy import signal
from scipy.stats import linregress

from pyglaze.interpolation import ws_interpolate

if TYPE_CHECKING:
    from pyglaze.helpers._types import ComplexArray, FloatArray

__all__ = ["Pulse"]


@dataclass(frozen=True)
class Pulse:
    """Data class for a THz pulse. The pulse is expected to be preprocessed such that times are uniformly spaced.

    Args:
        time: The time values recorded by the lock-in amp during the scan.
        signal: The signal values recorded by the lock-in amp during the scan.
    """

    time: FloatArray
    signal: FloatArray

    def __len__(self: Pulse) -> int:  # noqa: D105
        return len(self.time)

    def __eq__(self: Pulse, obj: object) -> bool:
        """Check if two pulses are equal."""
        if not isinstance(obj, Pulse):
            return False

        return bool(
            np.array_equal(self.time, obj.time)
            and np.array_equal(self.signal, obj.signal)
        )

    def __hash__(self: Pulse) -> int:
        """Return a hash based on the contents of ``time`` and ``signal``.

        The hash combines shape, dtype and raw bytes of both arrays, ensuring that
        two :class:`Pulse` instances that compare equal also have identical hashes.

        """
        return hash(
            (
                self.time.shape,
                self.time.dtype.str,
                self.time.tobytes(),
                self.signal.shape,
                self.signal.dtype.str,
                self.signal.tobytes(),
            )
        )

    @property
    def fft(self: Pulse) -> ComplexArray:
        """Return the Fourier Transform of a signal."""
        return np.fft.rfft(self.signal, norm="forward")

    @property
    def frequency(self: Pulse) -> FloatArray:
        """Return the Fourier Transform sample frequencies."""
        return np.fft.rfftfreq(len(self.signal), d=self.time[1] - self.time[0])

    @property
    def time_window(self: Pulse) -> float:
        """The scan time window size in seconds."""
        return float(self.time[-1] - self.time[0])

    @property
    def sampling_freq(self: Pulse) -> float:
        """The sampling frequency in Hz of the scan."""
        return float(1 / (self.time[1] - self.time[0]))

    @property
    def dt(self: Pulse) -> float:
        """Time spacing."""
        return float(self.time[1] - self.time[0])

    @property
    def df(self: Pulse) -> float:
        """Frequency spacing."""
        return float(self.frequency[1] - self.frequency[0])

    @property
    def center_frequency(self: Pulse) -> float:
        """The frequency of the pulse with the highest spectral desnity."""
        return float(self.frequency[np.argmax(np.abs(self.fft))])

    @property
    def maximum_spectral_density(self: Pulse) -> float:
        """The maximum spectral density of the pulse."""
        return float(np.max(np.abs(self.fft)))

    @property
    def delay_at_max(self: Pulse) -> float:
        """Time delay at the maximum value of the pulse."""
        return float(self.time[np.argmax(self.signal)])

    @property
    def delay_at_min(self: Pulse) -> float:
        """Time delay at the minimum value of the pulse."""
        return float(self.time[np.argmin(self.signal)])

    @property
    def energy(self: Pulse) -> float:
        """Energy of the pulse.

        Note that the energy is not the same as the physical energy of the pulse, but rather the integral of the square of the pulse.
        """
        return cast("float", np.trapezoid(self.signal * self.signal, x=self.time))  # type: ignore[attr-defined, unused-ignore]

    @classmethod
    def from_dict(
        cls: type[Pulse], d: dict[str, FloatArray | list[float] | None]
    ) -> Pulse:
        """Create a Pulse object from a dictionary.

        Args:
            d: A dictionary containing the keys 'time', 'signal'.
        """
        return Pulse(time=np.array(d["time"]), signal=np.array(d["signal"]))

    @classmethod
    def from_fft(cls: type[Pulse], time: FloatArray, fft: ComplexArray) -> Pulse:
        """Creates a Pulse object from an array of times and a Fourier spectrum.

        Args:
            time: Time series of pulse related to the Fourier spectrum
            fft: Fourier spectrum of pulse

        """
        sig = np.fft.irfft(fft, norm="forward", n=len(time), axis=0)
        return cls(time, sig)

    @classmethod
    def average(cls: type[Pulse], scans: list[Pulse]) -> Pulse:
        """Creates a Pulse object containing the average scan from a list of scans along with uncertainties. Errors are calculated as the standard errors on the means.

        Args:
            scans: List of scans to calculate average from

        """
        if len(scans) == 1:
            return scans[0]
        signals = np.array([scan.signal for scan in scans])
        mean_signal = np.mean(signals, axis=0)
        return Pulse(scans[0].time, mean_signal)

    @classmethod
    def align(
        cls: type[Pulse],
        scans: list[Pulse],
        *,
        wrt_max: bool = True,
        translate_to_zero: bool = True,
    ) -> list[Pulse]:
        """Aligns a list of pulses with respect to the zerocrossings of their main pulse.

        Args:
            scans: List of scans
            wrt_max: Whether to perform rough alignment with respect to their maximum (true) or minimum(false). Defaults to True.
            translate_to_zero: Whether to translate all scans to t[0] = 0. Defaults to True.

        Returns:
            list[Pulse]: Aligned scans.
        """
        extrema = [scan._get_min_or_max_idx(wrt_max=wrt_max) for scan in scans]  # noqa: SLF001
        n_before = min(extrema)
        n_after = min(len(scan) - index - 1 for scan, index in zip(scans, extrema))
        roughly_aligned = [
            cls._from_slice(scan, slice(index - n_before, index + n_after))
            for index, scan in zip(extrema, scans)
        ]

        if translate_to_zero:
            roughly_aligned = [
                s.timeshift(scale=1.0, offset=-s.time[0]) for s in roughly_aligned
            ]

        zerocrossings = [p.estimate_zero_crossing() for p in roughly_aligned]
        mean_zerocrossing = cast("float", np.mean(zerocrossings))

        return [
            p.propagate(mean_zerocrossing - zc)
            for p, zc in zip(roughly_aligned, zerocrossings)
        ]

    @classmethod
    def _from_slice(cls: type[Pulse], scan: Pulse, indices: slice) -> Pulse:
        return cls(scan.time[indices], scan.signal[indices])

    def cut(self: Pulse, from_time: float, to_time: float) -> Pulse:
        """Create a Pulse object by cutting out a specific section of the scan.

        Args:
            from_time: Time in seconds where cut should be made from
            to_time: Time in seconds where cut should be made to
        """
        from_idx = int(np.searchsorted(self.time, from_time))
        to_idx = int(np.searchsorted(self.time, to_time, side="right"))
        return Pulse(self.time[from_idx:to_idx], self.signal[from_idx:to_idx])

    def fft_at_f(self: Pulse, f: float) -> complex:
        """Returns the Fourier Transform at a specific frequency.

        Args:
            f: Frequency in Hz

        Returns:
            complex: Fourier Transform at the given frequency
        """
        return cast("complex", self.fft[np.searchsorted(self.frequency, f)])

    def timeshift(self: Pulse, scale: float, offset: float = 0) -> Pulse:
        """Rescales and offsets the time axis as.

        new_times = scale*(t + offset)

        Args:
            scale: Rescaling factor
            offset: Offset. Defaults to 0.

        Returns:
            Timeshifted pulse
        """
        return Pulse(time=scale * (self.time + offset), signal=self.signal)

    def add_white_noise(
        self: Pulse, noise_std: float, seed: int | None = None
    ) -> Pulse:
        """Adds Gaussian noise to each timedomain measurements with a standard deviation given by `noise_std`.

        Args:
            noise_std: noise standard deviation
            seed: Seed for the random number generator. If none, a random seed is used.

        Returns:
            Pulse with noise
        """
        return Pulse(
            time=self.time,
            signal=self.signal
            + np.random.default_rng(seed).normal(
                loc=0, scale=noise_std, size=len(self)
            ),
        )

    def zeropadded(self: Pulse, n_zeros: int) -> Pulse:
        """Returns a new, zero-padded pulse.

        Args:
            n_zeros: number of zeros to add

        Returns:
            Zero-padded pulse
        """
        zeropadded_signal = np.concatenate((np.zeros(n_zeros), self.signal))
        zeropadded_time = np.concatenate(
            (self.time[0] + np.arange(n_zeros, 0, -1) * -self.dt, self.time)
        )
        return Pulse(time=zeropadded_time, signal=zeropadded_signal)

    def signal_at_t(self: Pulse, t: float) -> float:
        """Returns the signal at a specific time using Whittaker Shannon interpolation.

        Args:
            t: Time in seconds

        Returns:
            Signal at the given time
        """
        return cast("float", ws_interpolate(self.time, self.signal, np.array([t]))[0])

    def subtract_mean(self: Pulse, fraction: float = 0.99) -> Pulse:
        """Subtracts the mean of the pulse.

        Args:
            fraction: Fraction of the mean to subtract. Defaults to 0.99.

        Returns:
            Pulse with the mean subtracted
        """
        return Pulse(self.time, self.signal - fraction * np.mean(self.signal))

    def tukey(
        self: Pulse,
        taper_length: float,
        from_time: float | None = None,
        to_time: float | None = None,
    ) -> Pulse:
        """Applies a Tukey window and returns a new Pulse object - see https://en.wikipedia.org/wiki/Window_function.

        Args:
            taper_length: Length in seconds of the cosine tapering length, i.e. half a cosine cycle
            from_time: Left edge in seconds at which the window becomes 0
            to_time: Right edge in seconds at which the window becomes 0
        """
        N = len(self)
        _to_time = to_time or self.time[-1]
        _from_time = from_time or self.time[0]
        _tukey_window_length = _to_time - _from_time

        # NOTE: See https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.windows.tukey.html#scipy.signal.windows.tukey
        M = int(N * _tukey_window_length / self.time_window)
        if M > N:
            msg = "Number of points in Tukey window cannot exceed number of points in scan"
            raise ValueError(msg)
        alpha = 2 * taper_length / _tukey_window_length
        _tukey_window = signal.windows.tukey(M=M, alpha=alpha)

        window = np.zeros(N)
        from_time_idx = np.searchsorted(self.time, _from_time)
        window[from_time_idx : M + from_time_idx] = _tukey_window

        return Pulse(self.time, self.signal * window)

    def derivative(self: Pulse) -> Pulse:
        """Calculates the derivative of the pulse.

        Returns:
            Pulse: New Pulse object containing the derivative
        """
        return Pulse(time=self.time, signal=np.gradient(self.signal))

    def downsample(self: Pulse, max_frequency: float) -> Pulse:
        """Downsamples the pulse by inverse Fourier transforming the spectrum cut at the supplied `max_frequency`.

        Args:
            max_frequency: Maximum frequency bin after downsampling

        Returns:
            Pulse: Downsampled pulse
        """
        idx = np.searchsorted(self.frequency, max_frequency)
        new_fft = self.fft[:idx]
        new_dt = 1 / (2 * self.frequency[:idx][-1])
        new_times = np.arange(2 * (len(new_fft) - 1)) * new_dt + self.time[0]
        return Pulse.from_fft(time=new_times, fft=new_fft)

    def filter(
        self: Pulse,
        filtertype: Literal["highpass", "lowpass"],
        cutoff: float,
        order: int,
    ) -> Pulse:
        """Applies a highpass filter to the signal.

        Args:
            filtertype: Type of filter
            cutoff: Frequency, where the filter response has dropped 3 dB
            order: Order of the highpass filter

        Returns:
            Highpassed pulse
        """
        sos = signal.butter(
            N=order, Wn=cutoff, btype=filtertype, fs=self.sampling_freq, output="sos"
        )
        return Pulse(self.time, np.asarray(signal.sosfilt(sos, self.signal)))

    def spectrum_dB(
        self: Pulse, reference: float | None = None, offset_ratio: float | None = None
    ) -> FloatArray:
        """Calculates the spectral density in decibel.

        Args:
            reference: Reference spectral amplitude. If none, the maximum of the FFT is used.
            offset_ratio: Offset in decibel relative to the maximum of the FFT to avoid taking the logarithm of 0. If none, no offset is applied.

        Returns:
            FloatArray: Spectral density in decibel
        """
        abs_spectrum = np.abs(self.fft)
        offset = 0 if offset_ratio is None else offset_ratio * np.max(abs_spectrum)
        ref = reference or np.max(abs_spectrum)

        return np.asarray(
            20 * np.log10((abs_spectrum + offset) / ref), dtype=np.float64
        )

    def estimate_bandwidth(self: Pulse, linear_segments: int = 1) -> float:
        """Estimates the bandwidth of the pulse.

        The bandwidth is estimated by modelling the log of the pulse's spectrum above the center frequency as a constant noisefloor and n linear segments of equal size. The bandwidth is then defined as the frequency at which the noisefloor is reached.

        Args:
            linear_segments: Number of linear segments to fit to the spectrum. Defaults to 1.

        Returns:
            float: Estimated bandwidth in Hz
        """
        return self._estimate_pulse_properties(linear_segments)[0]

    def estimate_dynamic_range(self: Pulse, linear_segments: int = 1) -> float:
        """Estimates the dynamic range of the pulse.

        The dynamic range is estimated by modelling the log of the pulse's spectrum above the center frequency as a constant noisefloor and n linear segments of equal size. The dynamic range is then calculated as the maximum of the spectrum minus the noisefloor.

        Args:
            linear_segments: Number of linear segments to fit to the spectrum. Defaults to 1.

        Returns:
            float: Estimated dynamic range in dB
        """
        return self._estimate_pulse_properties(linear_segments)[1]

    def estimate_avg_noise_power(self: Pulse, linear_segments: int = 1) -> float:
        """Estimates the noise power.

        The noise power is estimated by modelling the the log of pulse's spectrum above the center frequency as a constant noisefloor and n linear segments of equal size. Noise power is then calculated as the mean of the absolute square of the spectral bins above the frequency at which the noise floor is reached.

        Args:
            linear_segments: Number of linear segments to fit to the spectrum. Defaults to 1.

        Returns:
            float: Estimated noise power.
        """
        return self._estimate_pulse_properties(linear_segments)[2]

    def estimate_SNR(self: Pulse, linear_segments: int = 1) -> FloatArray:
        """Estimates the signal-to-noise ratio.

        Estimates the SNR, assuming white noise. The noisefloor is estimated by modelling the log of the pulse's spectrum above the center frequency as a constant noisefloor and n linear segments of equal size. Noise power is then calculated as the mean of the absolute square of the spectral bins above the frequency at which the noise floor is reached. The signal power is then extrapolated above the bandwidth by fitting a second order polynomial to the spectrum above the noisefloor.

        Args:
            linear_segments: Number of linear segments to fit to the spectrum. Defaults to 1.

        Returns:
            float: Estimated signal-to-noise ratio.
        """
        # Get spectrum between maximum and noisefloor
        _from = np.argmax(self.spectrum_dB())
        _to = np.searchsorted(
            self.frequency, self.estimate_bandwidth(linear_segments=linear_segments)
        )
        x = self.frequency[_from:_to]
        y = self.spectrum_dB()[_from:_to]

        # Fit a second order polynomial to the spectrum above the noisefloor
        poly_fit = np.polynomial.Polynomial.fit(x, y, deg=2)

        # Combine signal before spectrum maximum with interpolated values
        y_values = cast(
            "FloatArray",
            np.concatenate(
                [
                    self.spectrum_dB()[:_from],
                    poly_fit(self.frequency[_from:]),
                ]
            ),
        )
        signal_power = 10 ** (y_values / 10) * self.maximum_spectral_density**2
        return signal_power / self.estimate_avg_noise_power(
            linear_segments=linear_segments
        )

    def estimate_peak_to_peak(
        self: Pulse,
        delay_tolerance: float | None = None,
        strategy: Callable[
            [FloatArray, FloatArray, FloatArray], FloatArray
        ] = ws_interpolate,
    ) -> float:
        """Estimates the peak-to-peak value of the pulse.

        If a delay tolerance is provided, the peak-to-peak value is estimated by interpolating the pulse at the maximum and minimum values such that the minimum and maximum values of the pulse fall within the given delay tolerance. A lower tolerance will give a more accurate estimate.

        Args:
            delay_tolerance: Tolerance for peak detection. Defaults to None.
            strategy: Interpolation strategy. Defaults to Whittaker-Shannon interpolation

        Returns:
            float: Estimated peak-to-peak value.
        """
        if delay_tolerance is None:
            return float(np.max(self.signal) - np.min(self.signal))

        if delay_tolerance >= self.dt:
            msg = "Tolerance must be smaller than the time spacing of the pulse."
            raise ValueError(msg)

        max_estimate = strategy(
            self.time,
            self.signal,
            np.linspace(
                self.delay_at_max - self.dt,
                self.delay_at_max + self.dt,
                num=1 + int(self.dt / delay_tolerance),
                endpoint=True,
            ),
        )

        min_estimate = strategy(
            self.time,
            self.signal,
            np.linspace(
                self.delay_at_min - self.dt,
                self.delay_at_min + self.dt,
                num=1 + int(self.dt / delay_tolerance),
                endpoint=True,
            ),
        )

        return cast("float", np.max(max_estimate) - np.min(min_estimate))

    def estimate_zero_crossing(self: Pulse) -> float:
        """Estimates the zero crossing of the pulse between the maximum and minimum value.

        Returns:
            float: Estimated zero crossing.
        """
        argmax = np.argmax(self.signal)
        argmin = np.argmin(self.signal)
        if argmax < argmin:
            idx = np.searchsorted(-self.signal[argmax:argmin], 0) + argmax - 1
        else:
            idx = np.searchsorted(self.signal[argmin:argmax], 0) + argmin - 1

        # To find the zero crossing, solve 0 = s1 + a * (t - t1) for t: t = t1 - s1 / a
        t1, s1 = self.time[idx], self.signal[idx]
        a = (self.signal[idx + 1] - self.signal[idx]) / self.dt
        return cast("float", t1 - s1 / a)

    def propagate(self: Pulse, time: float) -> Pulse:
        """Propagates the pulse in time by a given amount.

        Args:
            time: Time in seconds to propagate the pulse by

        Returns:
            Pulse: Propagated pulse
        """
        return Pulse.from_fft(
            time=self.time,
            fft=self.fft * np.exp(-1j * 2 * np.pi * self.frequency * time),
        )

    def to_native_dict(self: Pulse) -> dict[str, list[float] | None]:
        """Converts the Pulse object to a native dictionary.

        Returns:
            Native dictionary representation of the Pulse object.
        """
        return {"time": list(self.time), "signal": list(self.signal)}

    def _get_min_or_max_idx(self: Pulse, *, wrt_max: bool) -> int:
        return int(np.argmax(self.signal)) if wrt_max else int(np.argmin(self.signal))

    def _estimate_pulse_properties(
        self: Pulse, linear_segments: int
    ) -> tuple[float, float, float]:
        mean_substracted = self.subtract_mean()
        argmax = np.argmax(np.abs(mean_substracted.fft))
        freqs = mean_substracted.frequency[argmax:]
        abs_spectrum = np.abs(mean_substracted.fft[argmax:])
        bw_idx_estimate = _estimate_bw_idx(freqs, abs_spectrum, linear_segments)
        avg_noise_power = np.mean(abs_spectrum[bw_idx_estimate:] ** 2)
        noisefloor = np.sqrt(avg_noise_power)
        bandwidth = freqs[bw_idx_estimate]
        dynamic_range_dB = 20 * np.log10(
            mean_substracted.maximum_spectral_density / noisefloor
        )
        return bandwidth, dynamic_range_dB, avg_noise_power


def _estimate_bw_idx(x: FloatArray, y: FloatArray, segments: int) -> int:
    """Estimate the noise floor of a spectrum.

    Args:
        x: Frequency values
        y: Spectrum values
        segments: Number of linear segments to fit

    Returns:
        float: Estimated noise floor
    """
    target = np.log(y)

    def L1(x: FloatArray, y: FloatArray) -> FloatArray:
        return np.sum(np.abs(y - x))  # type: ignore[no-any-return]

    def model(pars: list[float]) -> FloatArray:
        idx = np.searchsorted(x, pars[0])
        x_before = x[:idx]
        x_after = x[idx:]
        target_before = target[:idx]
        target_after = target[idx:]
        y_fit = _fit_linear_segments(x_before, target_before, segments)
        noise = np.ones(len(x_after)) * y_fit[-1]
        return L1(y_fit, target_before) + L1(noise, target_after)

    BW_estimate = opt.minimize(
        fun=model, x0=[x[len(x) // 2]], bounds=[(x[0], x[-1])], method="Nelder-Mead"
    ).x[0]

    return cast("int", x.searchsorted(BW_estimate))


def _fit_linear_segments(x: FloatArray, y: FloatArray, n_segments: int) -> FloatArray:
    """Fit a pulse with a piecewise linear function.

    Args:
        x: Time values
        y: Signal values
        n_segments: Number of segments to fit

    Returns:
        FloatArray: Fitted signal
    """
    segment_indices = np.linspace(0, len(x), n_segments + 1, dtype=int)
    y_fit = np.zeros_like(y)

    for i in range(n_segments):
        # Get the indices for this segment
        start, end = segment_indices[i], segment_indices[i + 1]
        x_segment = x[start:end]
        y_segment = y[start:end]

        # Fit a linear function to this segment
        slope, intercept, _, _, _ = linregress(x_segment, y_segment)
        y_fit[start:end] = slope * x_segment + intercept
    return y_fit
