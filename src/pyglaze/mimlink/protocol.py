"""Pure-Python MimLink protocol endpoint."""

from __future__ import annotations

from typing import Any, Callable

from google.protobuf.message import DecodeError
from typing_extensions import Self

from pyglaze.mimlink.framing import FrameDecodeError, decode_frame, encode_frame
from pyglaze.mimlink.proto import envelope_pb2
from pyglaze.mimlink.rx_stream import RxFrameStream
from pyglaze.mimlink.types import (
    CapabilitiesResponse,
    FwBootConfirmResponse,
    FwUpdateChunkAck,
    FwUpdateFinishResponse,
    FwUpdateStartResponse,
    FwUpdateStatusResponse,
    HostError,
    ListCompleteResponse,
    ListStartResponse,
    MessageType,
    RawCaptureChunk,
    ResultPoint,
    ResultPointNak,
    ResultPointRetransmit,
    ResultsChunk,
    ResultsChunkNak,
    ResultsChunkRetransmit,
    ScanResponse,
    SerialResponse,
    SettingsResponse,
    StatusResponse,
    TransformedListChunk,
    VersionResponse,
)


class ProtocolEndpoint:
    """Protocol endpoint that serializes MimLink protobuf frames in Python."""

    def __init__(
        self,
        on_envelope: Callable[[int, int, object], None] | None = None,
        on_send: Callable[[bytes], int] | None = None,
    ) -> None:
        self._on_envelope = on_envelope
        self._on_send = on_send
        self._tx_seq = 0
        self._destroyed = False
        self._rx_stream = RxFrameStream()

    def _new_envelope(self) -> Any:
        envelope_cls = getattr(envelope_pb2, "Envelope")
        return envelope_cls()

    def _send_envelope(self, env: Any) -> int:
        if self._destroyed:
            return HostError.INVALID_ARG

        try:
            frame = encode_frame(env.SerializeToString())
        except Exception:  # noqa: BLE001
            return HostError.PROTOCOL_ERROR

        self._tx_seq = (self._tx_seq + 1) & 0xFFFFFFFF

        if self._on_send is None:
            return HostError.OK
        return self._on_send(frame)

    def _build_envelope(self, env_type: int) -> Any:
        env = self._new_envelope()
        env.seq = self._tx_seq
        env.type = env_type
        return env

    def _dispatch(self, env: Any) -> None:
        if self._on_envelope is None:
            return
        payload = self._extract_payload(env.type, env)
        self._on_envelope(env.type, env.seq, payload)

    def _extract_payload(self, env_type: int, env: Any) -> object:
        payload = env
        if env_type == MessageType.PING:
            return payload.ping.nonce
        if env_type == MessageType.PONG:
            return payload.pong.nonce
        if env_type == MessageType.SET_SETTINGS_REQUEST:
            req = payload.set_settings_request
            return {
                "list_length": req.list_length,
                "integration_periods": req.integration_periods,
                "use_ema": bool(req.use_ema),
            }
        if env_type == MessageType.SET_SETTINGS_RESPONSE:
            return SettingsResponse(success=bool(payload.set_settings_response.success))
        if env_type == MessageType.SET_LIST_START_REQUEST:
            return {"total_floats": payload.set_list_start_request.total_floats}
        if env_type == MessageType.SET_LIST_START_RESPONSE:
            return ListStartResponse(ready=bool(payload.set_list_start_response.ready))
        if env_type == MessageType.LIST_CHUNK:
            c = payload.list_chunk
            return {
                "chunk_index": c.chunk_index,
                "values": list(c.values),
                "is_last": bool(c.is_last),
            }
        if env_type == MessageType.SET_LIST_COMPLETE_RESPONSE:
            c = payload.set_list_complete_response
            return ListCompleteResponse(
                success=bool(c.success),
                floats_received=c.floats_received,
            )
        if env_type == MessageType.START_SCAN_REQUEST:
            return None
        if env_type == MessageType.START_SCAN_RESPONSE:
            c = payload.start_scan_response
            return ScanResponse(
                started=bool(c.started),
                error=c.error if c.error else None,
                transfer_mode=c.transfer_mode,
            )
        if env_type == MessageType.GET_RESULTS_REQUEST:
            return None
        if env_type == MessageType.RESULTS_CHUNK:
            c = payload.results_chunk
            return ResultsChunk(
                chunk_index=c.chunk_index,
                times=list(c.times),
                x=list(c.x),
                y=list(c.y),
                is_last=bool(c.is_last),
            )
        if env_type == MessageType.GET_STATUS_REQUEST:
            return None
        if env_type == MessageType.GET_STATUS_RESPONSE:
            c = payload.get_status_response
            return StatusResponse(
                scan_ongoing=bool(c.scan_ongoing),
                list_length=c.list_length,
                max_list_length=c.max_list_length,
                modulation_frequency_hz=c.modulation_frequency_hz,
                settings_valid=bool(c.settings_valid),
                list_valid=bool(c.list_valid),
            )
        if env_type == MessageType.GET_SERIAL_REQUEST:
            return None
        if env_type == MessageType.GET_SERIAL_RESPONSE:
            return SerialResponse(serial=payload.get_serial_response.serial)
        if env_type == MessageType.GET_VERSION_REQUEST:
            return None
        if env_type == MessageType.GET_VERSION_RESPONSE:
            return VersionResponse(version=payload.get_version_response.version)
        if env_type == MessageType.REBOOT_REQUEST:
            return None
        if env_type == MessageType.GET_TRANSFORMED_LIST_REQUEST:
            return None
        if env_type == MessageType.TRANSFORMED_LIST_CHUNK:
            c = payload.transformed_list_chunk
            return TransformedListChunk(
                chunk_index=c.chunk_index,
                values=list(c.values),
                is_last=bool(c.is_last),
            )
        if env_type == MessageType.GET_CAPABILITIES_REQUEST:
            return None
        if env_type == MessageType.GET_CAPABILITIES_RESPONSE:
            c = payload.get_capabilities_response
            return CapabilitiesResponse(
                has_external_dac=bool(c.has_external_dac),
                has_encoder=bool(c.has_encoder),
                has_i2c1=bool(c.has_i2c1),
                has_i2c2=bool(c.has_i2c2),
                has_i2c3=bool(c.has_i2c3),
                has_power_rails=bool(c.has_power_rails),
            )
        if env_type == MessageType.RAW_CAPTURE_REQUEST:
            return {"num_samples": payload.raw_capture_request.num_samples}
        if env_type == MessageType.RAW_CAPTURE_CHUNK:
            c = payload.raw_capture_chunk
            return RawCaptureChunk(
                chunk_index=c.chunk_index,
                samples=list(c.samples),
                is_last=bool(c.is_last),
            )
        if env_type == MessageType.RESULT_POINT:
            c = payload.result_point
            return ResultPoint(
                point_index=c.point_index,
                time=c.time,
                x=c.x,
                y=c.y,
                is_last=bool(c.is_last),
                send_timestamp_us=c.send_timestamp_us,
            )
        if env_type == MessageType.RESULT_POINT_NAK:
            return ResultPointNak(point_index=payload.result_point_nak.point_index)
        if env_type == MessageType.RESULT_POINT_RETRANSMIT:
            c = payload.result_point_retransmit
            return ResultPointRetransmit(
                point_index=c.point_index,
                available=bool(c.available),
                time=c.time,
                x=c.x,
                y=c.y,
            )
        if env_type == MessageType.FW_UPDATE_START_REQUEST:
            c = payload.fw_update_start_request
            return {
                "firmware_size": c.firmware_size,
                "firmware_crc": c.firmware_crc,
                "chunk_size": c.chunk_size,
                "version": c.version,
            }
        if env_type == MessageType.FW_UPDATE_START_RESPONSE:
            c = payload.fw_update_start_response
            return FwUpdateStartResponse(
                accepted=bool(c.accepted), error=c.error or None
            )
        if env_type == MessageType.FW_UPDATE_CHUNK:
            c = payload.fw_update_chunk
            return {
                "chunk_index": c.chunk_index,
                "data": bytes(c.data),
                "chunk_crc": c.chunk_crc,
            }
        if env_type == MessageType.FW_UPDATE_CHUNK_ACK:
            c = payload.fw_update_chunk_ack
            return FwUpdateChunkAck(chunk_index=c.chunk_index, status=c.status)
        if env_type == MessageType.FW_UPDATE_FINISH_REQUEST:
            return None
        if env_type == MessageType.FW_UPDATE_FINISH_RESPONSE:
            c = payload.fw_update_finish_response
            return FwUpdateFinishResponse(
                success=bool(c.success),
                status=c.status,
                error=c.error or None,
            )
        if env_type == MessageType.FW_UPDATE_STATUS_REQUEST:
            return None
        if env_type == MessageType.FW_UPDATE_STATUS_RESPONSE:
            c = payload.fw_update_status_response
            return FwUpdateStatusResponse(
                status=c.status,
                chunks_received=c.chunks_received,
                total_chunks=c.total_chunks,
                bytes_received=c.bytes_received,
            )
        if env_type == MessageType.FW_BOOT_CONFIRM_REQUEST:
            return None
        if env_type == MessageType.FW_BOOT_CONFIRM_RESPONSE:
            c = payload.fw_boot_confirm_response
            return FwBootConfirmResponse(confirmed=bool(c.confirmed), version=c.version)
        if env_type == MessageType.RESULTS_CHUNK_NAK:
            return ResultsChunkNak(chunk_index=payload.results_chunk_nak.chunk_index)
        if env_type == MessageType.RESULTS_CHUNK_RETRANSMIT:
            c = payload.results_chunk_retransmit
            return ResultsChunkRetransmit(
                chunk_index=c.chunk_index,
                times=list(c.times),
                x=list(c.x),
                y=list(c.y),
                is_last=bool(c.is_last),
                available=bool(c.available),
            )
        return None

    # --- Ping/Pong ---

    def send_ping(self, nonce: int) -> int:
        env = self._build_envelope(MessageType.PING)
        env.ping.nonce = nonce
        return self._send_envelope(env)

    def send_pong(self, nonce: int) -> int:
        env = self._build_envelope(MessageType.PONG)
        env.pong.nonce = nonce
        return self._send_envelope(env)

    # --- Settings ---

    def send_set_settings(
        self, list_length: int, integration_periods: int, use_ema: bool
    ) -> int:
        env = self._build_envelope(MessageType.SET_SETTINGS_REQUEST)
        req = env.set_settings_request
        req.list_length = list_length
        req.integration_periods = integration_periods
        req.use_ema = use_ema
        return self._send_envelope(env)

    def send_set_settings_response(self, success: bool) -> int:
        env = self._build_envelope(MessageType.SET_SETTINGS_RESPONSE)
        env.set_settings_response.success = success
        return self._send_envelope(env)

    # --- List Upload (Chunked) ---

    def send_set_list_start(self, total_floats: int) -> int:
        env = self._build_envelope(MessageType.SET_LIST_START_REQUEST)
        env.set_list_start_request.total_floats = total_floats
        return self._send_envelope(env)

    def send_set_list_start_response(self, ready: bool) -> int:
        env = self._build_envelope(MessageType.SET_LIST_START_RESPONSE)
        env.set_list_start_response.ready = ready
        return self._send_envelope(env)

    def send_list_chunk(
        self, chunk_index: int, values: list[float], is_last: bool
    ) -> int:
        env = self._build_envelope(MessageType.LIST_CHUNK)
        chunk = env.list_chunk
        chunk.chunk_index = chunk_index
        chunk.values.extend(values)
        chunk.is_last = is_last
        return self._send_envelope(env)

    def send_set_list_complete_response(
        self, success: bool, floats_received: int
    ) -> int:
        env = self._build_envelope(MessageType.SET_LIST_COMPLETE_RESPONSE)
        resp = env.set_list_complete_response
        resp.success = success
        resp.floats_received = floats_received
        return self._send_envelope(env)

    def upload_list(
        self,
        frequencies: list[float],
        chunk_size: int = 50,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> int:
        total = len(frequencies)
        err = self.send_set_list_start(total)
        if err != HostError.OK:
            return err

        total_chunks = (total + chunk_size - 1) // chunk_size
        for i in range(total_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, total)
            chunk = frequencies[start:end]
            is_last = i == total_chunks - 1
            err = self.send_list_chunk(i, chunk, is_last)
            if err != HostError.OK:
                return err
            if on_progress:
                on_progress(i + 1, total_chunks)

        return HostError.OK

    # --- Scan ---

    def send_start_scan(self) -> int:
        env = self._build_envelope(MessageType.START_SCAN_REQUEST)
        env.start_scan_request.SetInParent()
        return self._send_envelope(env)

    def send_start_scan_response(
        self, started: bool, error: str | None, transfer_mode: int
    ) -> int:
        env = self._build_envelope(MessageType.START_SCAN_RESPONSE)
        resp = env.start_scan_response
        resp.started = started
        resp.error = error or ""
        resp.transfer_mode = transfer_mode
        return self._send_envelope(env)

    # --- Results (Chunked) ---

    def send_get_results(self) -> int:
        env = self._build_envelope(MessageType.GET_RESULTS_REQUEST)
        env.get_results_request.SetInParent()
        return self._send_envelope(env)

    def send_results_chunk(
        self,
        chunk_index: int,
        times: list[float],
        x: list[float],
        y: list[float],
        is_last: bool,
    ) -> int:
        env = self._build_envelope(MessageType.RESULTS_CHUNK)
        chunk = env.results_chunk
        chunk.chunk_index = chunk_index
        chunk.times.extend(times)
        chunk.x.extend(x)
        chunk.y.extend(y)
        chunk.is_last = is_last
        return self._send_envelope(env)

    # --- Status ---

    def send_get_status(self) -> int:
        env = self._build_envelope(MessageType.GET_STATUS_REQUEST)
        env.get_status_request.SetInParent()
        return self._send_envelope(env)

    def send_get_status_response(
        self,
        scan_ongoing: bool,
        list_length: int,
        max_list_length: int,
        modulation_frequency_hz: int,
        settings_valid: bool,
        list_valid: bool,
    ) -> int:
        env = self._build_envelope(MessageType.GET_STATUS_RESPONSE)
        resp = env.get_status_response
        resp.scan_ongoing = scan_ongoing
        resp.list_length = list_length
        resp.max_list_length = max_list_length
        resp.modulation_frequency_hz = modulation_frequency_hz
        resp.settings_valid = settings_valid
        resp.list_valid = list_valid
        return self._send_envelope(env)

    # --- Device Info ---

    def send_get_serial(self) -> int:
        env = self._build_envelope(MessageType.GET_SERIAL_REQUEST)
        env.get_serial_request.SetInParent()
        return self._send_envelope(env)

    def send_get_serial_response(self, serial: str) -> int:
        env = self._build_envelope(MessageType.GET_SERIAL_RESPONSE)
        env.get_serial_response.serial = serial
        return self._send_envelope(env)

    def send_get_version(self) -> int:
        env = self._build_envelope(MessageType.GET_VERSION_REQUEST)
        env.get_version_request.SetInParent()
        return self._send_envelope(env)

    def send_get_version_response(self, version: str) -> int:
        env = self._build_envelope(MessageType.GET_VERSION_RESPONSE)
        env.get_version_response.version = version
        return self._send_envelope(env)

    # --- Reboot ---

    def send_reboot(self) -> int:
        env = self._build_envelope(MessageType.REBOOT_REQUEST)
        env.reboot_request.SetInParent()
        return self._send_envelope(env)

    # --- Transformed List ---

    def send_get_transformed_list(self) -> int:
        env = self._build_envelope(MessageType.GET_TRANSFORMED_LIST_REQUEST)
        env.get_transformed_list_request.SetInParent()
        return self._send_envelope(env)

    def send_transformed_list_chunk(
        self, chunk_index: int, values: list[int], is_last: bool
    ) -> int:
        env = self._build_envelope(MessageType.TRANSFORMED_LIST_CHUNK)
        chunk = env.transformed_list_chunk
        chunk.chunk_index = chunk_index
        chunk.values.extend(values)
        chunk.is_last = is_last
        return self._send_envelope(env)

    # --- Capabilities ---

    def send_get_capabilities(self) -> int:
        env = self._build_envelope(MessageType.GET_CAPABILITIES_REQUEST)
        env.get_capabilities_request.SetInParent()
        return self._send_envelope(env)

    def send_get_capabilities_response(
        self,
        has_external_dac: bool,
        has_encoder: bool,
        has_i2c1: bool,
        has_i2c2: bool,
        has_i2c3: bool,
        has_power_rails: bool,
    ) -> int:
        env = self._build_envelope(MessageType.GET_CAPABILITIES_RESPONSE)
        resp = env.get_capabilities_response
        resp.has_external_dac = has_external_dac
        resp.has_encoder = has_encoder
        resp.has_i2c1 = has_i2c1
        resp.has_i2c2 = has_i2c2
        resp.has_i2c3 = has_i2c3
        resp.has_power_rails = has_power_rails
        return self._send_envelope(env)

    # --- Raw Capture ---

    def send_raw_capture(self, num_samples: int = 0) -> int:
        env = self._build_envelope(MessageType.RAW_CAPTURE_REQUEST)
        env.raw_capture_request.num_samples = num_samples
        return self._send_envelope(env)

    def send_raw_capture_chunk(
        self, chunk_index: int, samples: list[int], is_last: bool
    ) -> int:
        env = self._build_envelope(MessageType.RAW_CAPTURE_CHUNK)
        chunk = env.raw_capture_chunk
        chunk.chunk_index = chunk_index
        chunk.samples.extend(samples)
        chunk.is_last = is_last
        return self._send_envelope(env)

    # --- Per-Point Result Streaming ---

    def send_result_point(
        self, point_index: int, time: float, x: float, y: float, is_last: bool
    ) -> int:
        env = self._build_envelope(MessageType.RESULT_POINT)
        p = env.result_point
        p.point_index = point_index
        p.time = time
        p.x = x
        p.y = y
        p.is_last = is_last
        p.send_timestamp_us = 0
        return self._send_envelope(env)

    # --- Reliable Streaming ---

    def send_result_point_nak(self, point_index: int) -> int:
        env = self._build_envelope(MessageType.RESULT_POINT_NAK)
        env.result_point_nak.point_index = point_index
        return self._send_envelope(env)

    def send_result_point_retransmit(
        self,
        point_index: int,
        available: bool,
        time: float,
        x: float,
        y: float,
    ) -> int:
        env = self._build_envelope(MessageType.RESULT_POINT_RETRANSMIT)
        p = env.result_point_retransmit
        p.point_index = point_index
        p.available = available
        p.time = time
        p.x = x
        p.y = y
        return self._send_envelope(env)

    # --- Reliable Bulk Transfer ---

    def send_results_chunk_nak(self, chunk_index: int) -> int:
        env = self._build_envelope(MessageType.RESULTS_CHUNK_NAK)
        env.results_chunk_nak.chunk_index = chunk_index
        return self._send_envelope(env)

    def send_results_chunk_retransmit(
        self,
        chunk_index: int,
        times: list[float],
        x: list[float],
        y: list[float],
        is_last: bool,
        available: bool,
    ) -> int:
        env = self._build_envelope(MessageType.RESULTS_CHUNK_RETRANSMIT)
        c = env.results_chunk_retransmit
        c.chunk_index = chunk_index
        c.times.extend(times)
        c.x.extend(x)
        c.y.extend(y)
        c.is_last = is_last
        c.available = available
        return self._send_envelope(env)

    # --- Firmware Update ---

    def send_fw_update_start(
        self, firmware_size: int, firmware_crc: int, chunk_size: int, version: str
    ) -> int:
        env = self._build_envelope(MessageType.FW_UPDATE_START_REQUEST)
        req = env.fw_update_start_request
        req.firmware_size = firmware_size
        req.firmware_crc = firmware_crc
        req.chunk_size = chunk_size
        req.version = version
        return self._send_envelope(env)

    def send_fw_update_start_response(self, accepted: bool, error: str | None) -> int:
        env = self._build_envelope(MessageType.FW_UPDATE_START_RESPONSE)
        resp = env.fw_update_start_response
        resp.accepted = accepted
        resp.error = error or ""
        return self._send_envelope(env)

    def send_fw_update_chunk(
        self, chunk_index: int, data: bytes, chunk_crc: int
    ) -> int:
        env = self._build_envelope(MessageType.FW_UPDATE_CHUNK)
        chunk = env.fw_update_chunk
        chunk.chunk_index = chunk_index
        chunk.data = data
        chunk.chunk_crc = chunk_crc
        return self._send_envelope(env)

    def send_fw_update_chunk_ack(self, chunk_index: int, status: int) -> int:
        env = self._build_envelope(MessageType.FW_UPDATE_CHUNK_ACK)
        ack = env.fw_update_chunk_ack
        ack.chunk_index = chunk_index
        ack.status = status
        return self._send_envelope(env)

    def send_fw_update_finish(self) -> int:
        env = self._build_envelope(MessageType.FW_UPDATE_FINISH_REQUEST)
        env.fw_update_finish_request.SetInParent()
        return self._send_envelope(env)

    def send_fw_update_finish_response(
        self, success: bool, status: int, error: str | None
    ) -> int:
        env = self._build_envelope(MessageType.FW_UPDATE_FINISH_RESPONSE)
        resp = env.fw_update_finish_response
        resp.success = success
        resp.status = status
        resp.error = error or ""
        return self._send_envelope(env)

    def send_fw_update_status(self) -> int:
        env = self._build_envelope(MessageType.FW_UPDATE_STATUS_REQUEST)
        env.fw_update_status_request.SetInParent()
        return self._send_envelope(env)

    def send_fw_update_status_response(
        self,
        status: int,
        chunks_received: int,
        total_chunks: int,
        bytes_received: int,
    ) -> int:
        env = self._build_envelope(MessageType.FW_UPDATE_STATUS_RESPONSE)
        resp = env.fw_update_status_response
        resp.status = status
        resp.chunks_received = chunks_received
        resp.total_chunks = total_chunks
        resp.bytes_received = bytes_received
        return self._send_envelope(env)

    def send_fw_boot_confirm(self) -> int:
        env = self._build_envelope(MessageType.FW_BOOT_CONFIRM_REQUEST)
        env.fw_boot_confirm_request.SetInParent()
        return self._send_envelope(env)

    def send_fw_boot_confirm_response(self, confirmed: bool, version: str) -> int:
        env = self._build_envelope(MessageType.FW_BOOT_CONFIRM_RESPONSE)
        resp = env.fw_boot_confirm_response
        resp.confirmed = confirmed
        resp.version = version
        return self._send_envelope(env)

    # --- I/O ---

    def on_rx_bytes(self, data: bytes) -> int:
        if self._destroyed:
            return HostError.INVALID_ARG

        for frame in self._rx_stream.push(data):
            try:
                payload = decode_frame(frame)
                env = self._new_envelope()
                env.ParseFromString(payload)
            except (FrameDecodeError, DecodeError):
                continue
            self._dispatch(env)
        return HostError.OK

    def tick(self, ms: int) -> int:
        # Retained for API compatibility with cffi wrapper.
        _ = ms
        if self._destroyed:
            return HostError.INVALID_ARG
        return HostError.OK

    # --- Lifecycle ---

    def destroy(self) -> None:
        self._destroyed = True
        self._rx_stream.reset()

    def __del__(self) -> None:
        self.destroy()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.destroy()
