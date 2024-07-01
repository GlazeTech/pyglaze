from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from multiprocessing import Event, Pipe, Process, Queue, synchronize
from queue import Empty, Full
from typing import TYPE_CHECKING

from serial import serialutil

from pyglaze.datamodels.waveform import UnprocessedWaveform, _TimestampedWaveform
from pyglaze.scanning.scanner import Scanner

if TYPE_CHECKING:
    import logging
    from multiprocessing.connection import Connection

    from pyglaze.device.configuration import DeviceConfiguration


@dataclass
class _ScannerHealth:
    is_alive: bool
    is_healthy: bool
    error: Exception | None


@dataclass
class _AsyncScanner:
    """Used by GlazeClient to starts a scanner in a new process and read scans from shared memory."""

    queue_maxsize: int = 10
    startup_timeout: float = 30.0
    logger: logging.Logger | None = None
    is_scanning: bool = False
    _child_process: Process = field(init=False)
    _shared_mem: Queue[_TimestampedWaveform] = field(init=False)
    _SCAN_TIMEOUT: float = field(init=False)
    _stop_signal: synchronize.Event = field(init=False)
    _scanner_conn: Connection = field(init=False)

    def start_scan(self: _AsyncScanner, config: DeviceConfiguration) -> None:
        """Starts continuously scanning in new process.

        Args:
            config: Device configurtaion
        """
        self._SCAN_TIMEOUT = config._sweep_length_ms * 2e-3 + 1  # noqa: SLF001, access to private attribute for backwards compatibility
        self._shared_mem = Queue(maxsize=self.queue_maxsize)
        self._stop_signal = Event()
        self._scanner_conn, child_conn = Pipe()
        self._child_process = Process(
            target=_AsyncScanner._run_scanner,
            args=[config, self._shared_mem, self._stop_signal, child_conn],
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

    def stop_scan(self: _AsyncScanner) -> None:
        self._stop_signal.set()
        self._child_process.join()
        self._child_process.close()
        self.is_scanning = False

    def get_scans(self: _AsyncScanner, n_pulses: int) -> list[UnprocessedWaveform]:
        call_time = datetime.now()  # noqa: DTZ005
        stamped_pulse = self._get_scan()

        while stamped_pulse.timestamp < call_time:
            stamped_pulse = self._get_scan()

        return [self._get_scan().waveform for _ in range(n_pulses)]

    def get_next(self: _AsyncScanner, averaged_over_n: int = 1) -> UnprocessedWaveform:
        return UnprocessedWaveform.average(
            [self._get_scan().waveform for _ in range(averaged_over_n)]
        )

    def _get_scan(self: _AsyncScanner) -> _TimestampedWaveform:
        try:
            return self._shared_mem.get(timeout=self._SCAN_TIMEOUT)
        except Empty as err:
            if self._scanner_conn.poll(timeout=self.startup_timeout):
                msg: _ScannerHealth = self._scanner_conn.recv()
                if not msg.is_alive:
                    self.is_scanning = False
                if msg.error:
                    raise msg.error from err
            raise

    @staticmethod
    def _run_scanner(
        config: DeviceConfiguration,
        shared_mem: Queue[_TimestampedWaveform],
        stop_signal: synchronize.Event,
        parent_conn: Connection,
    ) -> None:
        try:
            scanner = Scanner(config=config)
            parent_conn.send(_ScannerHealth(is_alive=True, is_healthy=True, error=None))
        except (serialutil.SerialException, TimeoutError) as e:
            parent_conn.send(_ScannerHealth(is_alive=False, is_healthy=False, error=e))
            return

        while not stop_signal.is_set():
            try:
                waveform = _TimestampedWaveform(datetime.now(), scanner.scan())  # noqa: DTZ005
            except (serialutil.SerialException, TimeoutError) as e:
                parent_conn.send(
                    _ScannerHealth(is_alive=False, is_healthy=False, error=e)
                )
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
