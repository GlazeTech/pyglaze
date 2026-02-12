"""Public types for native MimLink protocol."""

from __future__ import annotations

from dataclasses import dataclass


class HostError:
    """Host library-compatible error codes."""

    OK: int = 0
    INVALID_ARG: int = -1
    IO_ERROR: int = -2
    PROTOCOL_ERROR: int = -3


class MessageType:
    """Message type enum values (matches proto MsgType)."""

    UNKNOWN: int = 0
    PING: int = 1
    PONG: int = 2
    SET_SETTINGS_REQUEST: int = 3
    SET_SETTINGS_RESPONSE: int = 4
    SET_LIST_START_REQUEST: int = 5
    SET_LIST_START_RESPONSE: int = 6
    LIST_CHUNK: int = 7
    SET_LIST_COMPLETE_RESPONSE: int = 8
    START_SCAN_REQUEST: int = 9
    START_SCAN_RESPONSE: int = 10
    GET_RESULTS_REQUEST: int = 11
    RESULTS_CHUNK: int = 12
    GET_STATUS_REQUEST: int = 13
    GET_STATUS_RESPONSE: int = 14
    GET_SERIAL_REQUEST: int = 15
    GET_SERIAL_RESPONSE: int = 16
    GET_VERSION_REQUEST: int = 17
    GET_VERSION_RESPONSE: int = 18
    REBOOT_REQUEST: int = 19
    GET_TRANSFORMED_LIST_REQUEST: int = 20
    TRANSFORMED_LIST_CHUNK: int = 21
    GET_CAPABILITIES_REQUEST: int = 22
    GET_CAPABILITIES_RESPONSE: int = 23
    RAW_CAPTURE_REQUEST: int = 24
    RAW_CAPTURE_CHUNK: int = 25
    RESULT_POINT: int = 26
    RESULT_POINT_NAK: int = 27
    RESULT_POINT_RETRANSMIT: int = 28
    FW_UPDATE_START_REQUEST: int = 29
    FW_UPDATE_START_RESPONSE: int = 30
    FW_UPDATE_CHUNK: int = 31
    FW_UPDATE_CHUNK_ACK: int = 32
    FW_UPDATE_FINISH_REQUEST: int = 33
    FW_UPDATE_FINISH_RESPONSE: int = 34
    FW_UPDATE_STATUS_REQUEST: int = 35
    FW_UPDATE_STATUS_RESPONSE: int = 36
    FW_BOOT_CONFIRM_REQUEST: int = 37
    FW_BOOT_CONFIRM_RESPONSE: int = 38
    RESULTS_CHUNK_NAK: int = 39
    RESULTS_CHUNK_RETRANSMIT: int = 40


class TransferMode:
    """Transfer mode enum (matches proto TransferMode)."""

    BULK: int = 0
    PER_POINT: int = 1


class FwUpdateStatus:
    """Firmware update status enum (matches proto FwUpdateStatus)."""

    IDLE: int = 0
    RECEIVING: int = 1
    VERIFYING: int = 2
    BOOT_PENDING: int = 3
    CONFIRMED: int = 4


class FwChunkStatus:
    """Firmware chunk status enum (matches proto FwChunkStatus)."""

    OK: int = 0
    CRC_MISMATCH: int = 1
    ABORT: int = 2


@dataclass
class SettingsResponse:
    success: bool


@dataclass
class ListStartResponse:
    ready: bool


@dataclass
class ListCompleteResponse:
    success: bool
    floats_received: int


@dataclass
class ScanResponse:
    started: bool
    error: str | None
    transfer_mode: int = TransferMode.BULK


@dataclass
class ResultsChunk:
    chunk_index: int
    times: list[float]
    x: list[float]
    y: list[float]
    is_last: bool


@dataclass
class StatusResponse:
    scan_ongoing: bool
    list_length: int
    max_list_length: int
    modulation_frequency_hz: int
    settings_valid: bool
    list_valid: bool


@dataclass
class SerialResponse:
    serial: str


@dataclass
class VersionResponse:
    version: str


@dataclass
class TransformedListChunk:
    chunk_index: int
    values: list[int]
    is_last: bool


@dataclass
class CapabilitiesResponse:
    has_external_dac: bool
    has_encoder: bool
    has_i2c1: bool
    has_i2c2: bool
    has_i2c3: bool
    has_power_rails: bool


@dataclass
class RawCaptureChunk:
    chunk_index: int
    samples: list[int]
    is_last: bool


@dataclass
class ResultPoint:
    point_index: int
    time: float
    x: float
    y: float
    is_last: bool
    send_timestamp_us: int = 0


@dataclass
class ResultPointNak:
    point_index: int


@dataclass
class ResultPointRetransmit:
    point_index: int
    available: bool
    time: float
    x: float
    y: float


@dataclass
class ResultsChunkNak:
    chunk_index: int


@dataclass
class ResultsChunkRetransmit:
    chunk_index: int
    times: list[float]
    x: list[float]
    y: list[float]
    is_last: bool
    available: bool


@dataclass
class FwUpdateStartResponse:
    accepted: bool
    error: str | None


@dataclass
class FwUpdateChunkAck:
    chunk_index: int
    status: int


@dataclass
class FwUpdateFinishResponse:
    success: bool
    status: int
    error: str | None


@dataclass
class FwUpdateStatusResponse:
    status: int
    chunks_received: int
    total_chunks: int
    bytes_received: int


@dataclass
class FwBootConfirmResponse:
    confirmed: bool
    version: str
