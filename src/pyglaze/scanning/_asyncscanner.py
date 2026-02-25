from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from multiprocessing import Event, Pipe, Process, Queue, synchronize
from queue import Empty, Full
from typing import TYPE_CHECKING, Any

from serial import SerialException, serialutil

from pyglaze.datamodels.waveform import UnprocessedWaveform, _TimestampedWaveform
from pyglaze.device.ampcom import DeviceComError
from pyglaze.scanning.scanner import Scanner

if TYPE_CHECKING:
    import logging
    from multiprocessing.connection import Connection

    from pyglaze.device.configuration import DeviceConfiguration
    from pyglaze.scanning.types import DeviceInfo, DeviceStatus, PingResult


class _CommandType(enum.Enum):
    PING = "ping"
    GET_STATUS = "get_status"


@dataclass
class _ScannerHealth:
    is_alive: bool
    is_healthy: bool
    error: Exception | None


@dataclass
class _ScannerMetadata:
    device_info: DeviceInfo


@dataclass
class _Command:
    type: _CommandType


@dataclass
class _CommandResponse:
    result: object
    error: Exception | None = None


@dataclass
class _ScannerIPC:
    """Bundles the multiprocessing primitives for the scanner child process."""

    shared_mem: Queue[_TimestampedWaveform]
    stop_signal: synchronize.Event
    parent_conn: Connection
    cmd_conn: Connection


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
    _cmd_conn: Connection = field(init=False)
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
        cmd_parent_conn, cmd_child_conn = Pipe()
        self._cmd_conn = cmd_parent_conn
        ipc = _ScannerIPC(
            shared_mem=self._shared_mem,
            stop_signal=self._stop_signal,
            parent_conn=child_conn,
            cmd_conn=cmd_child_conn,
        )
        self._child_process = Process(
            target=_AsyncScanner._run_scanner,
            args=[config, ipc, initial_phase_estimate],
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

    def ping(self: _AsyncScanner) -> PingResult:
        """Send a ping command to the scanner child process."""
        return self._send_command(_Command(_CommandType.PING))

    def get_status(self: _AsyncScanner) -> DeviceStatus:
        """Query device status via the scanner child process."""
        return self._send_command(_Command(_CommandType.GET_STATUS))

    def _send_command(self: _AsyncScanner, cmd: _Command) -> Any:  # noqa: ANN401
        if not self.is_scanning:
            msg = "Scanner not connected"
            raise SerialException(msg)
        self._cmd_conn.send(cmd)
        if not self._cmd_conn.poll(timeout=5.0):
            msg = "Command timed out"
            raise TimeoutError(msg)
        resp: _CommandResponse = self._cmd_conn.recv()
        if resp.error:
            raise resp.error
        return resp.result

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
        ipc: _ScannerIPC,
        initial_phase_estimate: float | None = None,
    ) -> None:
        try:
            scanner = Scanner(
                config=config, initial_phase_estimate=initial_phase_estimate
            )
            metadata = _ScannerMetadata(device_info=scanner.get_device_info())
            ipc.parent_conn.send(
                _ScannerHealth(is_alive=True, is_healthy=True, error=None)
            )
            ipc.parent_conn.send(metadata)
        except (serialutil.SerialException, TimeoutError, DeviceComError) as e:
            ipc.parent_conn.send(
                _ScannerHealth(is_alive=False, is_healthy=False, error=e)
            )
            return

        _AsyncScanner._scan_loop(scanner, ipc)

    @staticmethod
    def _scan_loop(scanner: Scanner, ipc: _ScannerIPC) -> None:
        while not ipc.stop_signal.is_set():
            _AsyncScanner._process_commands(scanner, ipc.cmd_conn)

            try:
                scanned_waveform = scanner.scan()
                phase = scanner.get_phase_estimate()
                waveform = _TimestampedWaveform(
                    datetime.now(tz=timezone.utc),
                    scanned_waveform,
                    phase,
                )
            except Exception as e:  # noqa: BLE001
                ipc.parent_conn.send(
                    _ScannerHealth(is_alive=False, is_healthy=False, error=e)
                )
                scanner.disconnect()
                break

            try:
                ipc.shared_mem.put_nowait(waveform)
            except Full:
                ipc.shared_mem.get_nowait()
                ipc.shared_mem.put_nowait(waveform)

        # Empty queue before shutting down
        try:
            while 1:
                ipc.shared_mem.get_nowait()
        except Empty:
            # this call required - see https://docs.python.org/3.9/library/multiprocessing.html#programming-guidelines
            ipc.shared_mem.cancel_join_thread()
            ipc.parent_conn.close()
            ipc.cmd_conn.close()

    @staticmethod
    def _process_commands(scanner: Scanner, cmd_conn: Connection) -> None:
        while cmd_conn.poll(0):
            cmd: _Command = cmd_conn.recv()
            try:
                if cmd.type == _CommandType.PING:
                    result = scanner.ping()
                elif cmd.type == _CommandType.GET_STATUS:
                    result = scanner.get_status()
                else:
                    result = None
                cmd_conn.send(_CommandResponse(result=result))
            except Exception as e:  # noqa: BLE001
                cmd_conn.send(_CommandResponse(result=None, error=e))
