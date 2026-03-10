from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MsgType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MSG_TYPE_UNKNOWN: _ClassVar[MsgType]
    MSG_TYPE_PING: _ClassVar[MsgType]
    MSG_TYPE_PONG: _ClassVar[MsgType]
    MSG_TYPE_SET_SETTINGS_REQUEST: _ClassVar[MsgType]
    MSG_TYPE_SET_SETTINGS_RESPONSE: _ClassVar[MsgType]
    MSG_TYPE_SET_LIST_START_REQUEST: _ClassVar[MsgType]
    MSG_TYPE_SET_LIST_START_RESPONSE: _ClassVar[MsgType]
    MSG_TYPE_LIST_CHUNK: _ClassVar[MsgType]
    MSG_TYPE_SET_LIST_COMPLETE_RESPONSE: _ClassVar[MsgType]
    MSG_TYPE_START_SCAN_REQUEST: _ClassVar[MsgType]
    MSG_TYPE_START_SCAN_RESPONSE: _ClassVar[MsgType]
    MSG_TYPE_GET_RESULTS_REQUEST: _ClassVar[MsgType]
    MSG_TYPE_RESULTS_CHUNK: _ClassVar[MsgType]
    MSG_TYPE_GET_STATUS_REQUEST: _ClassVar[MsgType]
    MSG_TYPE_GET_STATUS_RESPONSE: _ClassVar[MsgType]
    MSG_TYPE_REBOOT_REQUEST: _ClassVar[MsgType]
    MSG_TYPE_GET_TRANSFORMED_LIST_REQUEST: _ClassVar[MsgType]
    MSG_TYPE_TRANSFORMED_LIST_CHUNK: _ClassVar[MsgType]
    MSG_TYPE_GET_DEVICE_INFO_REQUEST: _ClassVar[MsgType]
    MSG_TYPE_GET_DEVICE_INFO_RESPONSE: _ClassVar[MsgType]
    MSG_TYPE_RAW_CAPTURE_REQUEST: _ClassVar[MsgType]
    MSG_TYPE_RAW_CAPTURE_CHUNK: _ClassVar[MsgType]
    MSG_TYPE_RESULT_POINT: _ClassVar[MsgType]
    MSG_TYPE_RESULT_POINT_NAK: _ClassVar[MsgType]
    MSG_TYPE_RESULT_POINT_RETRANSMIT: _ClassVar[MsgType]
    MSG_TYPE_FW_UPDATE_START_REQUEST: _ClassVar[MsgType]
    MSG_TYPE_FW_UPDATE_START_RESPONSE: _ClassVar[MsgType]
    MSG_TYPE_FW_UPDATE_CHUNK: _ClassVar[MsgType]
    MSG_TYPE_FW_UPDATE_CHUNK_ACK: _ClassVar[MsgType]
    MSG_TYPE_FW_UPDATE_FINISH_REQUEST: _ClassVar[MsgType]
    MSG_TYPE_FW_UPDATE_FINISH_RESPONSE: _ClassVar[MsgType]
    MSG_TYPE_FW_UPDATE_STATUS_REQUEST: _ClassVar[MsgType]
    MSG_TYPE_FW_UPDATE_STATUS_RESPONSE: _ClassVar[MsgType]
    MSG_TYPE_FW_BOOT_CONFIRM_REQUEST: _ClassVar[MsgType]
    MSG_TYPE_FW_BOOT_CONFIRM_RESPONSE: _ClassVar[MsgType]
    MSG_TYPE_RESULTS_CHUNK_NAK: _ClassVar[MsgType]
    MSG_TYPE_RESULTS_CHUNK_RETRANSMIT: _ClassVar[MsgType]

class TransferMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TRANSFER_MODE_BULK: _ClassVar[TransferMode]
    TRANSFER_MODE_PER_POINT: _ClassVar[TransferMode]

class FwUpdateStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FW_UPDATE_STATUS_IDLE: _ClassVar[FwUpdateStatus]
    FW_UPDATE_STATUS_RECEIVING: _ClassVar[FwUpdateStatus]
    FW_UPDATE_STATUS_VERIFYING: _ClassVar[FwUpdateStatus]
    FW_UPDATE_STATUS_BOOT_PENDING: _ClassVar[FwUpdateStatus]
    FW_UPDATE_STATUS_CONFIRMED: _ClassVar[FwUpdateStatus]

class FwChunkStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FW_CHUNK_STATUS_OK: _ClassVar[FwChunkStatus]
    FW_CHUNK_STATUS_CRC_MISMATCH: _ClassVar[FwChunkStatus]
    FW_CHUNK_STATUS_ABORT: _ClassVar[FwChunkStatus]
MSG_TYPE_UNKNOWN: MsgType
MSG_TYPE_PING: MsgType
MSG_TYPE_PONG: MsgType
MSG_TYPE_SET_SETTINGS_REQUEST: MsgType
MSG_TYPE_SET_SETTINGS_RESPONSE: MsgType
MSG_TYPE_SET_LIST_START_REQUEST: MsgType
MSG_TYPE_SET_LIST_START_RESPONSE: MsgType
MSG_TYPE_LIST_CHUNK: MsgType
MSG_TYPE_SET_LIST_COMPLETE_RESPONSE: MsgType
MSG_TYPE_START_SCAN_REQUEST: MsgType
MSG_TYPE_START_SCAN_RESPONSE: MsgType
MSG_TYPE_GET_RESULTS_REQUEST: MsgType
MSG_TYPE_RESULTS_CHUNK: MsgType
MSG_TYPE_GET_STATUS_REQUEST: MsgType
MSG_TYPE_GET_STATUS_RESPONSE: MsgType
MSG_TYPE_REBOOT_REQUEST: MsgType
MSG_TYPE_GET_TRANSFORMED_LIST_REQUEST: MsgType
MSG_TYPE_TRANSFORMED_LIST_CHUNK: MsgType
MSG_TYPE_GET_DEVICE_INFO_REQUEST: MsgType
MSG_TYPE_GET_DEVICE_INFO_RESPONSE: MsgType
MSG_TYPE_RAW_CAPTURE_REQUEST: MsgType
MSG_TYPE_RAW_CAPTURE_CHUNK: MsgType
MSG_TYPE_RESULT_POINT: MsgType
MSG_TYPE_RESULT_POINT_NAK: MsgType
MSG_TYPE_RESULT_POINT_RETRANSMIT: MsgType
MSG_TYPE_FW_UPDATE_START_REQUEST: MsgType
MSG_TYPE_FW_UPDATE_START_RESPONSE: MsgType
MSG_TYPE_FW_UPDATE_CHUNK: MsgType
MSG_TYPE_FW_UPDATE_CHUNK_ACK: MsgType
MSG_TYPE_FW_UPDATE_FINISH_REQUEST: MsgType
MSG_TYPE_FW_UPDATE_FINISH_RESPONSE: MsgType
MSG_TYPE_FW_UPDATE_STATUS_REQUEST: MsgType
MSG_TYPE_FW_UPDATE_STATUS_RESPONSE: MsgType
MSG_TYPE_FW_BOOT_CONFIRM_REQUEST: MsgType
MSG_TYPE_FW_BOOT_CONFIRM_RESPONSE: MsgType
MSG_TYPE_RESULTS_CHUNK_NAK: MsgType
MSG_TYPE_RESULTS_CHUNK_RETRANSMIT: MsgType
TRANSFER_MODE_BULK: TransferMode
TRANSFER_MODE_PER_POINT: TransferMode
FW_UPDATE_STATUS_IDLE: FwUpdateStatus
FW_UPDATE_STATUS_RECEIVING: FwUpdateStatus
FW_UPDATE_STATUS_VERIFYING: FwUpdateStatus
FW_UPDATE_STATUS_BOOT_PENDING: FwUpdateStatus
FW_UPDATE_STATUS_CONFIRMED: FwUpdateStatus
FW_CHUNK_STATUS_OK: FwChunkStatus
FW_CHUNK_STATUS_CRC_MISMATCH: FwChunkStatus
FW_CHUNK_STATUS_ABORT: FwChunkStatus

class Ping(_message.Message):
    __slots__ = ()
    NONCE_FIELD_NUMBER: _ClassVar[int]
    nonce: int
    def __init__(self, nonce: _Optional[int] = ...) -> None: ...

class Pong(_message.Message):
    __slots__ = ()
    NONCE_FIELD_NUMBER: _ClassVar[int]
    nonce: int
    def __init__(self, nonce: _Optional[int] = ...) -> None: ...

class SetSettingsRequest(_message.Message):
    __slots__ = ()
    LIST_LENGTH_FIELD_NUMBER: _ClassVar[int]
    INTEGRATION_PERIODS_FIELD_NUMBER: _ClassVar[int]
    USE_EMA_FIELD_NUMBER: _ClassVar[int]
    list_length: int
    integration_periods: int
    use_ema: bool
    def __init__(self, list_length: _Optional[int] = ..., integration_periods: _Optional[int] = ..., use_ema: _Optional[bool] = ...) -> None: ...

class SetSettingsResponse(_message.Message):
    __slots__ = ()
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: _Optional[bool] = ...) -> None: ...

class SetListStartRequest(_message.Message):
    __slots__ = ()
    TOTAL_FLOATS_FIELD_NUMBER: _ClassVar[int]
    total_floats: int
    def __init__(self, total_floats: _Optional[int] = ...) -> None: ...

class SetListStartResponse(_message.Message):
    __slots__ = ()
    READY_FIELD_NUMBER: _ClassVar[int]
    ready: bool
    def __init__(self, ready: _Optional[bool] = ...) -> None: ...

class ListChunk(_message.Message):
    __slots__ = ()
    CHUNK_INDEX_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    IS_LAST_FIELD_NUMBER: _ClassVar[int]
    chunk_index: int
    values: _containers.RepeatedScalarFieldContainer[float]
    is_last: bool
    def __init__(self, chunk_index: _Optional[int] = ..., values: _Optional[_Iterable[float]] = ..., is_last: _Optional[bool] = ...) -> None: ...

class SetListCompleteResponse(_message.Message):
    __slots__ = ()
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    FLOATS_RECEIVED_FIELD_NUMBER: _ClassVar[int]
    success: bool
    floats_received: int
    def __init__(self, success: _Optional[bool] = ..., floats_received: _Optional[int] = ...) -> None: ...

class StartScanRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StartScanResponse(_message.Message):
    __slots__ = ()
    STARTED_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    TRANSFER_MODE_FIELD_NUMBER: _ClassVar[int]
    started: bool
    error: str
    transfer_mode: TransferMode
    def __init__(self, started: _Optional[bool] = ..., error: _Optional[str] = ..., transfer_mode: _Optional[_Union[TransferMode, str]] = ...) -> None: ...

class GetResultsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ResultsChunk(_message.Message):
    __slots__ = ()
    CHUNK_INDEX_FIELD_NUMBER: _ClassVar[int]
    TIMES_FIELD_NUMBER: _ClassVar[int]
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    IS_LAST_FIELD_NUMBER: _ClassVar[int]
    chunk_index: int
    times: _containers.RepeatedScalarFieldContainer[float]
    x: _containers.RepeatedScalarFieldContainer[float]
    y: _containers.RepeatedScalarFieldContainer[float]
    is_last: bool
    def __init__(self, chunk_index: _Optional[int] = ..., times: _Optional[_Iterable[float]] = ..., x: _Optional[_Iterable[float]] = ..., y: _Optional[_Iterable[float]] = ..., is_last: _Optional[bool] = ...) -> None: ...

class GetStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetStatusResponse(_message.Message):
    __slots__ = ()
    SCAN_ONGOING_FIELD_NUMBER: _ClassVar[int]
    LIST_LENGTH_FIELD_NUMBER: _ClassVar[int]
    MAX_LIST_LENGTH_FIELD_NUMBER: _ClassVar[int]
    MODULATION_FREQUENCY_HZ_FIELD_NUMBER: _ClassVar[int]
    SETTINGS_VALID_FIELD_NUMBER: _ClassVar[int]
    LIST_VALID_FIELD_NUMBER: _ClassVar[int]
    scan_ongoing: bool
    list_length: int
    max_list_length: int
    modulation_frequency_hz: int
    settings_valid: bool
    list_valid: bool
    def __init__(self, scan_ongoing: _Optional[bool] = ..., list_length: _Optional[int] = ..., max_list_length: _Optional[int] = ..., modulation_frequency_hz: _Optional[int] = ..., settings_valid: _Optional[bool] = ..., list_valid: _Optional[bool] = ...) -> None: ...

class GetDeviceInfoRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetDeviceInfoResponse(_message.Message):
    __slots__ = ()
    SERIAL_NUMBER_FIELD_NUMBER: _ClassVar[int]
    FIRMWARE_VERSION_FIELD_NUMBER: _ClassVar[int]
    BSP_NAME_FIELD_NUMBER: _ClassVar[int]
    BUILD_TYPE_FIELD_NUMBER: _ClassVar[int]
    TRANSFER_MODE_FIELD_NUMBER: _ClassVar[int]
    HARDWARE_TYPE_FIELD_NUMBER: _ClassVar[int]
    HARDWARE_REVISION_FIELD_NUMBER: _ClassVar[int]
    serial_number: str
    firmware_version: str
    bsp_name: str
    build_type: str
    transfer_mode: TransferMode
    hardware_type: str
    hardware_revision: int
    def __init__(self, serial_number: _Optional[str] = ..., firmware_version: _Optional[str] = ..., bsp_name: _Optional[str] = ..., build_type: _Optional[str] = ..., transfer_mode: _Optional[_Union[TransferMode, str]] = ..., hardware_type: _Optional[str] = ..., hardware_revision: _Optional[int] = ...) -> None: ...

class RebootRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetTransformedListRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class TransformedListChunk(_message.Message):
    __slots__ = ()
    CHUNK_INDEX_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    IS_LAST_FIELD_NUMBER: _ClassVar[int]
    chunk_index: int
    values: _containers.RepeatedScalarFieldContainer[int]
    is_last: bool
    def __init__(self, chunk_index: _Optional[int] = ..., values: _Optional[_Iterable[int]] = ..., is_last: _Optional[bool] = ...) -> None: ...

class RawCaptureRequest(_message.Message):
    __slots__ = ()
    NUM_SAMPLES_FIELD_NUMBER: _ClassVar[int]
    num_samples: int
    def __init__(self, num_samples: _Optional[int] = ...) -> None: ...

class RawCaptureChunk(_message.Message):
    __slots__ = ()
    CHUNK_INDEX_FIELD_NUMBER: _ClassVar[int]
    SAMPLES_FIELD_NUMBER: _ClassVar[int]
    IS_LAST_FIELD_NUMBER: _ClassVar[int]
    chunk_index: int
    samples: _containers.RepeatedScalarFieldContainer[int]
    is_last: bool
    def __init__(self, chunk_index: _Optional[int] = ..., samples: _Optional[_Iterable[int]] = ..., is_last: _Optional[bool] = ...) -> None: ...

class ResultPoint(_message.Message):
    __slots__ = ()
    POINT_INDEX_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    IS_LAST_FIELD_NUMBER: _ClassVar[int]
    SEND_TIMESTAMP_US_FIELD_NUMBER: _ClassVar[int]
    point_index: int
    time: float
    x: float
    y: float
    is_last: bool
    send_timestamp_us: int
    def __init__(self, point_index: _Optional[int] = ..., time: _Optional[float] = ..., x: _Optional[float] = ..., y: _Optional[float] = ..., is_last: _Optional[bool] = ..., send_timestamp_us: _Optional[int] = ...) -> None: ...

class ResultPointNak(_message.Message):
    __slots__ = ()
    POINT_INDEX_FIELD_NUMBER: _ClassVar[int]
    point_index: int
    def __init__(self, point_index: _Optional[int] = ...) -> None: ...

class ResultPointRetransmit(_message.Message):
    __slots__ = ()
    POINT_INDEX_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    point_index: int
    available: bool
    time: float
    x: float
    y: float
    def __init__(self, point_index: _Optional[int] = ..., available: _Optional[bool] = ..., time: _Optional[float] = ..., x: _Optional[float] = ..., y: _Optional[float] = ...) -> None: ...

class ResultsChunkNak(_message.Message):
    __slots__ = ()
    CHUNK_INDEX_FIELD_NUMBER: _ClassVar[int]
    chunk_index: int
    def __init__(self, chunk_index: _Optional[int] = ...) -> None: ...

class ResultsChunkRetransmit(_message.Message):
    __slots__ = ()
    CHUNK_INDEX_FIELD_NUMBER: _ClassVar[int]
    TIMES_FIELD_NUMBER: _ClassVar[int]
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    IS_LAST_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_FIELD_NUMBER: _ClassVar[int]
    chunk_index: int
    times: _containers.RepeatedScalarFieldContainer[float]
    x: _containers.RepeatedScalarFieldContainer[float]
    y: _containers.RepeatedScalarFieldContainer[float]
    is_last: bool
    available: bool
    def __init__(self, chunk_index: _Optional[int] = ..., times: _Optional[_Iterable[float]] = ..., x: _Optional[_Iterable[float]] = ..., y: _Optional[_Iterable[float]] = ..., is_last: _Optional[bool] = ..., available: _Optional[bool] = ...) -> None: ...

class FwUpdateStartRequest(_message.Message):
    __slots__ = ()
    FIRMWARE_SIZE_FIELD_NUMBER: _ClassVar[int]
    FIRMWARE_CRC_FIELD_NUMBER: _ClassVar[int]
    CHUNK_SIZE_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    firmware_size: int
    firmware_crc: int
    chunk_size: int
    version: str
    def __init__(self, firmware_size: _Optional[int] = ..., firmware_crc: _Optional[int] = ..., chunk_size: _Optional[int] = ..., version: _Optional[str] = ...) -> None: ...

class FwUpdateStartResponse(_message.Message):
    __slots__ = ()
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    error: str
    def __init__(self, accepted: _Optional[bool] = ..., error: _Optional[str] = ...) -> None: ...

class FwUpdateChunk(_message.Message):
    __slots__ = ()
    CHUNK_INDEX_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    CHUNK_CRC_FIELD_NUMBER: _ClassVar[int]
    chunk_index: int
    data: bytes
    chunk_crc: int
    def __init__(self, chunk_index: _Optional[int] = ..., data: _Optional[bytes] = ..., chunk_crc: _Optional[int] = ...) -> None: ...

class FwUpdateChunkAck(_message.Message):
    __slots__ = ()
    CHUNK_INDEX_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    chunk_index: int
    status: FwChunkStatus
    def __init__(self, chunk_index: _Optional[int] = ..., status: _Optional[_Union[FwChunkStatus, str]] = ...) -> None: ...

class FwUpdateFinishRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class FwUpdateFinishResponse(_message.Message):
    __slots__ = ()
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    status: FwUpdateStatus
    error: str
    def __init__(self, success: _Optional[bool] = ..., status: _Optional[_Union[FwUpdateStatus, str]] = ..., error: _Optional[str] = ...) -> None: ...

class FwUpdateStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class FwUpdateStatusResponse(_message.Message):
    __slots__ = ()
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CHUNKS_RECEIVED_FIELD_NUMBER: _ClassVar[int]
    TOTAL_CHUNKS_FIELD_NUMBER: _ClassVar[int]
    BYTES_RECEIVED_FIELD_NUMBER: _ClassVar[int]
    status: FwUpdateStatus
    chunks_received: int
    total_chunks: int
    bytes_received: int
    def __init__(self, status: _Optional[_Union[FwUpdateStatus, str]] = ..., chunks_received: _Optional[int] = ..., total_chunks: _Optional[int] = ..., bytes_received: _Optional[int] = ...) -> None: ...

class FwBootConfirmRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class FwBootConfirmResponse(_message.Message):
    __slots__ = ()
    CONFIRMED_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    confirmed: bool
    version: str
    def __init__(self, confirmed: _Optional[bool] = ..., version: _Optional[str] = ...) -> None: ...

class Envelope(_message.Message):
    __slots__ = ()
    SEQ_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    PING_FIELD_NUMBER: _ClassVar[int]
    PONG_FIELD_NUMBER: _ClassVar[int]
    SET_SETTINGS_REQUEST_FIELD_NUMBER: _ClassVar[int]
    SET_SETTINGS_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    SET_LIST_START_REQUEST_FIELD_NUMBER: _ClassVar[int]
    SET_LIST_START_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    LIST_CHUNK_FIELD_NUMBER: _ClassVar[int]
    SET_LIST_COMPLETE_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    START_SCAN_REQUEST_FIELD_NUMBER: _ClassVar[int]
    START_SCAN_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    GET_RESULTS_REQUEST_FIELD_NUMBER: _ClassVar[int]
    RESULTS_CHUNK_FIELD_NUMBER: _ClassVar[int]
    GET_STATUS_REQUEST_FIELD_NUMBER: _ClassVar[int]
    GET_STATUS_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    REBOOT_REQUEST_FIELD_NUMBER: _ClassVar[int]
    GET_TRANSFORMED_LIST_REQUEST_FIELD_NUMBER: _ClassVar[int]
    TRANSFORMED_LIST_CHUNK_FIELD_NUMBER: _ClassVar[int]
    GET_DEVICE_INFO_REQUEST_FIELD_NUMBER: _ClassVar[int]
    GET_DEVICE_INFO_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    RAW_CAPTURE_REQUEST_FIELD_NUMBER: _ClassVar[int]
    RAW_CAPTURE_CHUNK_FIELD_NUMBER: _ClassVar[int]
    RESULT_POINT_FIELD_NUMBER: _ClassVar[int]
    RESULT_POINT_NAK_FIELD_NUMBER: _ClassVar[int]
    RESULT_POINT_RETRANSMIT_FIELD_NUMBER: _ClassVar[int]
    FW_UPDATE_START_REQUEST_FIELD_NUMBER: _ClassVar[int]
    FW_UPDATE_START_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    FW_UPDATE_CHUNK_FIELD_NUMBER: _ClassVar[int]
    FW_UPDATE_CHUNK_ACK_FIELD_NUMBER: _ClassVar[int]
    FW_UPDATE_FINISH_REQUEST_FIELD_NUMBER: _ClassVar[int]
    FW_UPDATE_FINISH_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    FW_UPDATE_STATUS_REQUEST_FIELD_NUMBER: _ClassVar[int]
    FW_UPDATE_STATUS_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    FW_BOOT_CONFIRM_REQUEST_FIELD_NUMBER: _ClassVar[int]
    FW_BOOT_CONFIRM_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    RESULTS_CHUNK_NAK_FIELD_NUMBER: _ClassVar[int]
    RESULTS_CHUNK_RETRANSMIT_FIELD_NUMBER: _ClassVar[int]
    seq: int
    type: MsgType
    ping: Ping
    pong: Pong
    set_settings_request: SetSettingsRequest
    set_settings_response: SetSettingsResponse
    set_list_start_request: SetListStartRequest
    set_list_start_response: SetListStartResponse
    list_chunk: ListChunk
    set_list_complete_response: SetListCompleteResponse
    start_scan_request: StartScanRequest
    start_scan_response: StartScanResponse
    get_results_request: GetResultsRequest
    results_chunk: ResultsChunk
    get_status_request: GetStatusRequest
    get_status_response: GetStatusResponse
    reboot_request: RebootRequest
    get_transformed_list_request: GetTransformedListRequest
    transformed_list_chunk: TransformedListChunk
    get_device_info_request: GetDeviceInfoRequest
    get_device_info_response: GetDeviceInfoResponse
    raw_capture_request: RawCaptureRequest
    raw_capture_chunk: RawCaptureChunk
    result_point: ResultPoint
    result_point_nak: ResultPointNak
    result_point_retransmit: ResultPointRetransmit
    fw_update_start_request: FwUpdateStartRequest
    fw_update_start_response: FwUpdateStartResponse
    fw_update_chunk: FwUpdateChunk
    fw_update_chunk_ack: FwUpdateChunkAck
    fw_update_finish_request: FwUpdateFinishRequest
    fw_update_finish_response: FwUpdateFinishResponse
    fw_update_status_request: FwUpdateStatusRequest
    fw_update_status_response: FwUpdateStatusResponse
    fw_boot_confirm_request: FwBootConfirmRequest
    fw_boot_confirm_response: FwBootConfirmResponse
    results_chunk_nak: ResultsChunkNak
    results_chunk_retransmit: ResultsChunkRetransmit
    def __init__(self, seq: _Optional[int] = ..., type: _Optional[_Union[MsgType, str]] = ..., ping: _Optional[_Union[Ping, _Mapping]] = ..., pong: _Optional[_Union[Pong, _Mapping]] = ..., set_settings_request: _Optional[_Union[SetSettingsRequest, _Mapping]] = ..., set_settings_response: _Optional[_Union[SetSettingsResponse, _Mapping]] = ..., set_list_start_request: _Optional[_Union[SetListStartRequest, _Mapping]] = ..., set_list_start_response: _Optional[_Union[SetListStartResponse, _Mapping]] = ..., list_chunk: _Optional[_Union[ListChunk, _Mapping]] = ..., set_list_complete_response: _Optional[_Union[SetListCompleteResponse, _Mapping]] = ..., start_scan_request: _Optional[_Union[StartScanRequest, _Mapping]] = ..., start_scan_response: _Optional[_Union[StartScanResponse, _Mapping]] = ..., get_results_request: _Optional[_Union[GetResultsRequest, _Mapping]] = ..., results_chunk: _Optional[_Union[ResultsChunk, _Mapping]] = ..., get_status_request: _Optional[_Union[GetStatusRequest, _Mapping]] = ..., get_status_response: _Optional[_Union[GetStatusResponse, _Mapping]] = ..., reboot_request: _Optional[_Union[RebootRequest, _Mapping]] = ..., get_transformed_list_request: _Optional[_Union[GetTransformedListRequest, _Mapping]] = ..., transformed_list_chunk: _Optional[_Union[TransformedListChunk, _Mapping]] = ..., get_device_info_request: _Optional[_Union[GetDeviceInfoRequest, _Mapping]] = ..., get_device_info_response: _Optional[_Union[GetDeviceInfoResponse, _Mapping]] = ..., raw_capture_request: _Optional[_Union[RawCaptureRequest, _Mapping]] = ..., raw_capture_chunk: _Optional[_Union[RawCaptureChunk, _Mapping]] = ..., result_point: _Optional[_Union[ResultPoint, _Mapping]] = ..., result_point_nak: _Optional[_Union[ResultPointNak, _Mapping]] = ..., result_point_retransmit: _Optional[_Union[ResultPointRetransmit, _Mapping]] = ..., fw_update_start_request: _Optional[_Union[FwUpdateStartRequest, _Mapping]] = ..., fw_update_start_response: _Optional[_Union[FwUpdateStartResponse, _Mapping]] = ..., fw_update_chunk: _Optional[_Union[FwUpdateChunk, _Mapping]] = ..., fw_update_chunk_ack: _Optional[_Union[FwUpdateChunkAck, _Mapping]] = ..., fw_update_finish_request: _Optional[_Union[FwUpdateFinishRequest, _Mapping]] = ..., fw_update_finish_response: _Optional[_Union[FwUpdateFinishResponse, _Mapping]] = ..., fw_update_status_request: _Optional[_Union[FwUpdateStatusRequest, _Mapping]] = ..., fw_update_status_response: _Optional[_Union[FwUpdateStatusResponse, _Mapping]] = ..., fw_boot_confirm_request: _Optional[_Union[FwBootConfirmRequest, _Mapping]] = ..., fw_boot_confirm_response: _Optional[_Union[FwBootConfirmResponse, _Mapping]] = ..., results_chunk_nak: _Optional[_Union[ResultsChunkNak, _Mapping]] = ..., results_chunk_retransmit: _Optional[_Union[ResultsChunkRetransmit, _Mapping]] = ...) -> None: ...
