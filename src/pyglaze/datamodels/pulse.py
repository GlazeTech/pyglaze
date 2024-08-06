from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import Literal, cast

import numpy as np
from scipy import signal

from pyglaze.helpers.types import ComplexArray, FloatArray
from pyglaze.interpolation import ws_interpolate

__all__ = ["Pulse"]


@dataclass
class Pulse:
    """Data class for a THz pulse. The pulse is expected to be preprocessed such that times are uniformly spaced.

    Args:
        time: The time values recorded by the lock-in amp during the scan.
        signal: The signal values recorded by the lock-in amp during the scan.
        signal_err: Potential errors on signal
    """

    time: FloatArray
    signal: FloatArray
    signal_err: FloatArray | None = None

    def __len__(self: Pulse) -> int:  # noqa: D105
        return len(self.time)

    def __eq__(self: Pulse, obj: object) -> bool:
        """Check if two pulses are equal."""
        if not isinstance(obj, Pulse):
            return False

        return bool(
            np.array_equal(self.time, obj.time)
            and np.array_equal(self.signal, obj.signal)
            and np.array_equal(self.signal_err, obj.signal_err)  # type: ignore[arg-type]
        )

    @cached_property
    def fft(self: Pulse) -> ComplexArray:
        """Return the Fourier Transform of a signal."""
        return np.fft.rfft(self.signal, norm="forward")

    @cached_property
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

    @classmethod
    def from_dict(
        cls: type[Pulse], d: dict[str, FloatArray | list[float] | None]
    ) -> Pulse:
        """Create a Pulse object from a dictionary.

        Args:
            d: A dictionary containing the keys 'time', 'signal' and potentially 'signal_err'.
        """
        err = np.array(d["signal_err"]) if d.get("signal_err") is not None else None
        return Pulse(
            time=np.array(d["time"]), signal=np.array(d["signal"]), signal_err=err
        )

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

        root_n_scans = np.sqrt(len(scans))
        std_signal = np.std(signals, axis=0, ddof=1) / root_n_scans
        return Pulse(scans[0].time, mean_signal, signal_err=std_signal)

    @classmethod
    def align(
        cls: type[Pulse],
        scans: list[Pulse],
        *,
        wrt_max: bool = True,
        translate_to_zero: bool = True,
    ) -> list[Pulse]:
        """Aligns a list of scan with respect to their individual maxima or minima.

        Args:
            scans: List of scans
            wrt_max: Whether to align with respect to maximum. Defaults to True.
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
            for scan in roughly_aligned:
                scan.time = scan.time - scan.time[0]

        ref = roughly_aligned[len(roughly_aligned) // 2]
        extremum = extrema[len(roughly_aligned) // 2]
        return _match_templates(extremum, ref, roughly_aligned)

    @classmethod
    def _from_slice(cls: type[Pulse], scan: Pulse, indices: slice) -> Pulse:
        err = scan.signal_err[indices] if scan.signal_err is not None else None
        return cls(scan.time[indices], scan.signal[indices], err)

    def cut(self: Pulse, from_time: float, to_time: float) -> Pulse:
        """Create a Pulse object by cutting out a specific section of the scan.

        Args:
            from_time: Time in seconds where cut should be made from
            to_time: Time in seconds where cut should be made to
        """
        from_idx = int(np.searchsorted(self.time, from_time))
        to_idx = int(np.searchsorted(self.time, to_time, side="right"))
        return Pulse(
            self.time[from_idx:to_idx],
            self.signal[from_idx:to_idx],
            None if self.signal_err is None else self.signal_err[from_idx:to_idx],
        )

    def timeshift(self: Pulse, scale: float, offset: float = 0) -> Pulse:
        """Rescales and offsets the time axis as.

        new_times = scale*(t + offset)

        Args:
            scale: Rescaling factor
            offset: Offset. Defaults to 0.

        Returns:
            Timeshifted pulse
        """
        return Pulse(
            time=scale * (self.time + offset),
            signal=self.signal,
            signal_err=self.signal_err,
        )

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
            signal_err=np.ones(len(self)) * noise_std,
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

    def estimate_bandwidth(self: Pulse, omega_power: int = 3) -> float:
        """Estimates the bandwidth of the pulse.

        Uses the approach described in [Algorithm for Determination of Cutoff Frequency of Noise Floor Level for Terahertz Time-Domain Signals](https://doi.org/10.1007/s10762-022-00886-y).

        Args:
            omega_power: power to raise omega to before estimating the bandwidth. Defaults to 3

        Returns:
            float: Estimated bandwidth in Hz
        """
        return self._estimate_pulse_properties(omega_power)[0]

    def estimate_dynamic_range(self: Pulse, omega_power: int = 3) -> float:
        """Estimates the dynamic range of the pulse.

        Uses the approach described in [Algorithm for Determination of Cutoff Frequency of Noise Floor Level for Terahertz Time-Domain Signals](https://doi.org/10.1007/s10762-022-00886-y).

        Args:
            omega_power: power to raise omega to before estimating the dynamic range. Defaults to 3

        Returns:
            float: Estimated dynamic range in dB
        """
        return self._estimate_pulse_properties(omega_power)[1]

    def estimate_avg_noise_power(self: Pulse, omega_power: int = 3) -> float:
        """Estimates the noise power.

        Noise power is defined as the mean of the absolute square of the noise floor.
        Uses the approach described in [Algorithm for Determination of Cutoff Frequency of Noise Floor Level for Terahertz Time-Domain Signals](https://doi.org/10.1007/s10762-022-00886-y).

        Args:
            omega_power: power to raise omega to before estimating the noisepower. Defaults to 3

        Returns:
            float: Estimated noise power.
        """
        return self._estimate_pulse_properties(omega_power)[2]

    def estimate_SNR(self: Pulse, omega_power: int = 3) -> FloatArray:
        """Estimates the signal-to-noise ratio.

        Estimates the SNR, assuming white noise. Uses the approach described in [Algorithm for Determination of Cutoff Frequency of Noise Floor Level for Terahertz Time-Domain Signals](https://doi.org/10.1007/s10762-022-00886-y) to estimate the noise power. The signal power is then extrapolated above the bandwidth by fitting a second order polynomial to the spectrum above the noisefloor.

        Args:
            omega_power: power to raise omega to before estimating the signal-to-noise ratio. Defaults to 3

        Returns:
            float: Estimated signal-to-noise ratio.
        """
        # Get spectrum between maximum and noisefloor
        _from = np.argmax(self.spectrum_dB())
        _to = np.searchsorted(
            self.frequency, self.estimate_bandwidth(omega_power=omega_power)
        )
        x = self.frequency[_from:_to]
        y = self.spectrum_dB()[_from:_to]

        # Fit a second order polynomial to the spectrum above the noisefloor
        poly_fit = np.polynomial.Polynomial.fit(x, y, deg=2)

        # Combine signal before spectrum maximum with interpolated values
        y_values = cast(
            FloatArray,
            np.concatenate(
                [
                    self.spectrum_dB()[:_from],
                    poly_fit(self.frequency[_from:]),
                ]
            ),
        )
        signal_power = 10 ** (y_values / 10) * self.maximum_spectral_density**2
        return signal_power / self.estimate_avg_noise_power(omega_power=omega_power)

    def estimate_peak_to_peak(
        self: Pulse, delay_tolerance: float | None = None
    ) -> float:
        """Estimates the peak-to-peak value of the pulse.

        If a delay tolerance is provided, the peak-to-peak value is estimated by interpolating the pulse at the maximum and minimum values such that the minimum and maximum values of the pulse fall within the given delay tolerance. A lower tolerance will give a more accurate estimate.

        Args:
            delay_tolerance: Tolerance for peak detection. Defaults to None.

        Returns:
            float: Estimated peak-to-peak value.
        """
        if delay_tolerance is None:
            return float(np.max(self.signal) - np.min(self.signal))

        if delay_tolerance >= self.dt:
            msg = "Tolerance must be smaller than the time spacing of the pulse."
            raise ValueError(msg)

        max_estimate = ws_interpolate(
            times=self.time,
            pulse=self.signal,
            interp_times=np.linspace(
                self.delay_at_max - self.dt,
                self.delay_at_max + self.dt,
                num=1 + int(self.dt / delay_tolerance),
                endpoint=True,
            ),
        )

        min_estimate = ws_interpolate(
            times=self.time,
            pulse=self.signal,
            interp_times=np.linspace(
                self.delay_at_min - self.dt,
                self.delay_at_min + self.dt,
                num=1 + int(self.dt / delay_tolerance),
                endpoint=True,
            ),
        )

        return cast(float, np.max(max_estimate) - np.min(min_estimate))

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
        return cast(float, t1 - s1 / a)

    def to_native_dict(self: Pulse) -> dict[str, list[float] | None]:
        """Converts the Pulse object to a native dictionary.

        Returns:
            Native dictionary representation of the Pulse object.
        """
        return {
            "time": list(self.time),
            "signal": list(self.signal),
            "signal_err": None if self.signal_err is None else list(self.signal_err),
        }

    def _get_min_or_max_idx(self: Pulse, *, wrt_max: bool) -> int:
        return int(np.argmax(self.signal)) if wrt_max else int(np.argmin(self.signal))

    def _estimate_pulse_properties(
        self: Pulse, omega_power: int
    ) -> tuple[float, float, float]:
        argmax = np.argmax(np.abs(self.fft))
        freqs = self.frequency[argmax:]
        abs_spectrum = np.abs(self.fft[argmax:])

        noisefloor_idx_estimate = np.argmin(abs_spectrum * freqs**omega_power)
        avg_noise_power = np.mean(abs_spectrum[noisefloor_idx_estimate:] ** 2)
        noisefloor = np.sqrt(avg_noise_power)

        # Search for the first index, where the spectrum is above the noise floor
        # by flipping the spectrum to get a pseudo-increasing array, then convert back
        # to an index in the original array
        cutoff_idx = noisefloor_idx_estimate - np.searchsorted(
            np.flip(abs_spectrum[: noisefloor_idx_estimate + 1]),
            noisefloor,
            side="right",
        )
        bandwidth = freqs[cutoff_idx]
        dynamic_range_dB = 20 * np.log10(self.maximum_spectral_density / noisefloor)
        return bandwidth, dynamic_range_dB, avg_noise_power


def _match_templates(
    extremum: int, ref: Pulse, roughly_aligned: list[Pulse]
) -> list[Pulse]:
    # corresponds to a template of length 8 - chosen as a compromise between speed and accuracy
    window_size = 4
    ref_slice = slice(extremum - window_size, extremum + window_size)

    def correlate(x1: FloatArray, x2: FloatArray) -> float:
        return float(np.sum(x1 * x2 / (np.linalg.norm(x1) * np.linalg.norm(x2))))

    cut_candidates = [-2, -1, 0, 1, 2]
    cuts = np.empty(len(roughly_aligned), dtype=int)
    for i_scan, scan in enumerate(roughly_aligned):
        slices = [
            slice(extremum - window_size + i, extremum + window_size + i)
            for i in cut_candidates
        ]
        cuts[i_scan] = cut_candidates[
            np.argmax(
                [correlate(scan.signal[s], ref.signal[ref_slice]) for s in slices]
            )
        ]

    max_cut = np.max(np.abs(cuts))
    new_length = len(ref) - max_cut
    aligned = []
    for scan, cut in zip(roughly_aligned, cuts):
        if cut >= 0:
            aligned.append(
                Pulse(
                    time=ref.time[:new_length],
                    signal=scan.signal[cut : cut + new_length],
                )
            )
        else:
            aligned.append(
                Pulse(
                    time=ref.time[:new_length],
                    signal=scan.signal[cut - new_length : cut],
                )
            )

    return aligned
