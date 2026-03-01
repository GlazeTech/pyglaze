from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from multiprocessing import Event, Pipe, Process, Queue, synchronize
from queue import Empty, Full
from typing import TYPE_CHECKING

from serial import SerialException, serialutil

from pyglaze.datamodels.waveform import UnprocessedWaveform, _TimestampedWaveform
from pyglaze.device.mimlink_client import DeviceComError
from pyglaze.scanning.scanner import Scanner

if TYPE_CHECKING:
    import logging
    from multiprocessing.connection import Connection

    from pyglaze.device.configuration import DeviceConfiguration
    from pyglaze.scanning.types import DeviceInfo


@dataclass
class _ScannerHealth:
    is_alive: bool
    is_healthy: bool
    error: Exception | None


@dataclass
class _ScannerMetadata:
    device_info: DeviceInfo


@dataclass
class _AsyncScanner:
    """Used by GlazeClient to starts a scanner in a new process and read scans from shared memory."""

    queue_maxsize: int = 10
    startup_timeout: float = 30.0
    logger: logging.Logger | None = None
    is_scanning: bool = False
    _child_process: Process = field(init=False)
    _metadata: _ScannerMetadata = field(init=False)
    _shared_mem: Queue[_TimestampedWaveform] = field(init=False)
    _SCAN_TIMEOUT: float = field(init=False)
    _stop_signal: synchronize.Event = field(init=False)
    _scanner_conn: Connection = field(init=False)
    _initial_phase_estimate: float | None = field(init=False, default=None)
    _cached_phase_estimate: float | None = field(init=False, default=None)

    def start_scan(
        self: _AsyncScanner,
        config: DeviceConfiguration,
        initial_phase_estimate: float | None = None,
    ) -> None:
        """Starts continuously scanning in new process.

        Args:
            config: Device configuration
            initial_phase_estimate: Optional initial phase estimate in radians for lock-in detection.
                Use this to maintain consistent polarity across scanner instances.
        """
        self._initial_phase_estimate = initial_phase_estimate
        self._cached_phase_estimate = (
            initial_phase_estimate  # Initialize cache with initial value
        )
        self._SCAN_TIMEOUT = config._sweep_length_ms * 2e-3 + 1  # noqa: SLF001, access to private attribute for backwards compatibility
        self._shared_mem = Queue(maxsize=self.queue_maxsize)
        self._stop_signal = Event()
        self._scanner_conn, child_conn = Pipe()
        self._child_process = Process(
            target=_AsyncScanner._run_scanner,
            args=[
                config,
                self._shared_mem,
                self._stop_signal,
                child_conn,
                initial_phase_estimate,
            ],
        )
        self._child_process.start()

        # Wait for scanner to start
        if not self._scanner_conn.poll(timeout=self.startup_timeout):
            self.stop_scan()
            err_msg = "Scanner timed out"
            raise TimeoutError(err_msg)

        msg: _ScannerHealth = self._scanner_conn.recv()
        if msg.is_healthy and msg.is_alive:
            self.is_scanning = True
        else:
            self.stop_scan()

        if msg.error:
            if self.logger:
                self.logger.error(str(msg.error))
            raise msg.error

        # As part of startup, metadata is sent from scanner
        metadata: _ScannerMetadata = self._scanner_conn.recv()
        self._metadata = metadata

    def stop_scan(self: _AsyncScanner) -> None:
        self._stop_signal.set()
        self._child_process.join()
        self._child_process.close()
        self.is_scanning = False

    def get_scans(self: _AsyncScanner, n_pulses: int) -> list[UnprocessedWaveform]:
        call_time = datetime.now(tz=timezone.utc)
        stamped_pulse = self._get_scan()

        while stamped_pulse.timestamp < call_time:
            stamped_pulse = self._get_scan()

        return [self._get_scan().waveform for _ in range(n_pulses)]

    def get_next(self: _AsyncScanner) -> UnprocessedWaveform:
        return self._get_scan().waveform

    def get_device_info(self: _AsyncScanner) -> DeviceInfo:
        if not self.is_scanning:
            msg = "Scanner not connected"
            raise SerialException(msg)
        return self._metadata.device_info

    def get_phase_estimate(self: _AsyncScanner) -> float | None:
        """Get the current phase estimate from the scanner.

        Returns the cached phase estimate from the most recently received waveform.
        This method returns instantly without blocking and can be called even after
        the scanner has stopped, allowing phase estimates to be extracted and reused.

        Returns:
            float | None: The current phase estimate in radians, or None if not yet estimated.
        """
        return self._cached_phase_estimate

    def _get_scan(self: _AsyncScanner) -> _TimestampedWaveform:
        try:
            waveform = self._shared_mem.get(timeout=self._SCAN_TIMEOUT)
            # Cache the phase estimate from this waveform
            self._cached_phase_estimate = waveform.phase_estimate
        except Exception as err:
            scanner_err: Exception | None = None
            if self._scanner_conn.poll(timeout=self.startup_timeout):
                msg: _ScannerHealth = self._scanner_conn.recv()
                if msg.error:
                    scanner_err = msg.error
            self.stop_scan()
            if scanner_err:
                raise scanner_err from err
            raise
        else:
            return waveform

    @staticmethod
    def _run_scanner(
        config: DeviceConfiguration,
        shared_mem: Queue[_TimestampedWaveform],
        stop_signal: synchronize.Event,
        parent_conn: Connection,
        initial_phase_estimate: float | None = None,
    ) -> None:
        try:
            scanner = Scanner(
                config=config, initial_phase_estimate=initial_phase_estimate
            )
            device_metadata = _ScannerMetadata(
                device_info=scanner.get_device_info(),
            )
            parent_conn.send(_ScannerHealth(is_alive=True, is_healthy=True, error=None))
            parent_conn.send(device_metadata)
        except (serialutil.SerialException, TimeoutError, DeviceComError) as e:
            parent_conn.send(_ScannerHealth(is_alive=False, is_healthy=False, error=e))
            return

        while not stop_signal.is_set():
            try:
                scanned_waveform = scanner.scan()
                phase = scanner.get_phase_estimate()
                waveform = _TimestampedWaveform(
                    datetime.now(tz=timezone.utc),
                    scanned_waveform,
                    phase,
                )
            except Exception as e:  # noqa: BLE001
                parent_conn.send(
                    _ScannerHealth(is_alive=False, is_healthy=False, error=e)
                )
                scanner.disconnect()
                break

            try:
                shared_mem.put_nowait(waveform)
            except Full:
                # when full, remove the oldest scan from the list before putting a new
                shared_mem.get_nowait()
                shared_mem.put_nowait(waveform)

        # Empty queue before shutting down
        try:
            while 1:
                shared_mem.get_nowait()
        except Empty:
            # this call required - see https://docs.python.org/3.9/library/multiprocessing.html#programming-guidelines
            shared_mem.cancel_join_thread()
            parent_conn.close()
            shared_mem.cancel_join_thread()
            parent_conn.close()
