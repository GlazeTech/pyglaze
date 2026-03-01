from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pyglaze.device.configuration import Interval, LeDeviceConfiguration
from pyglaze.device.mimlink_client import DeviceComError, MimLinkClient
from pyglaze.devtools.mock_device import (
    TRANSFER_MODE_PER_POINT,
    LeMockDevice,
    MockDeviceConfig,
    ScriptedTransport,
    list_mock_devices,
)
from pyglaze.mimlink import msg_types as mt
from pyglaze.mimlink.codec import EnvelopeCodec
from pyglaze.scanning.scanner import _compute_scanning_list

if TYPE_CHECKING:
    from pyglaze.mimlink.proto.envelope_pb2 import Envelope


def _build(
    n_points: int = 100,
    *,
    config: MockDeviceConfig | None = None,
    integration_periods: int = 1,
) -> tuple[LeDeviceConfiguration, MimLinkClient]:
    dev_config = LeDeviceConfiguration(
        amp_port="mock_device",
        use_ema=False,
        n_points=n_points,
        scan_intervals=[Interval(0.0, 1.0)],
        integration_periods=integration_periods,
    )
    backend = LeMockDevice(config)
    backend.reset_input_buffer()
    client = MimLinkClient(conn=backend, timeout=5.0)
    return dev_config, client


def test_set_settings_and_upload_list() -> None:
    config, client = _build()
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    client.close()


def test_full_scan_bulk() -> None:
    config, client = _build()
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    times, Xs, Ys = client.start_scan(config.n_points, config._sweep_length_ms)
    assert len(times) == config.n_points
    assert len(Xs) == config.n_points
    assert len(Ys) == config.n_points
    client.close()


def test_full_scan_per_point() -> None:
    config, client = _build(
        config=MockDeviceConfig(transfer_mode=TRANSFER_MODE_PER_POINT)
    )
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    times, Xs, Ys = client.start_scan(config.n_points, config._sweep_length_ms)
    assert len(times) == config.n_points
    assert len(Xs) == config.n_points
    assert len(Ys) == config.n_points
    client.close()


def test_get_device_info() -> None:
    config, client = _build()
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    info = client.get_device_info()
    assert info.serial_number == "M-9999"
    assert info.firmware_version == "v0.1.0"
    client.close()


def test_get_status() -> None:
    config, client = _build()
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    status = client.get_status()
    assert status.scan_ongoing is False
    assert status.list_length == config.n_points
    client.close()


def test_retransmit_missing_chunks() -> None:
    config, client = _build(config=MockDeviceConfig(drop_retransmit_once=True))
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    times, _Xs, _Ys = client.start_scan(config.n_points, config._sweep_length_ms)
    assert len(times) == config.n_points
    client.close()


def test_retransmit_missing_points() -> None:
    config, client = _build(
        config=MockDeviceConfig(
            transfer_mode=TRANSFER_MODE_PER_POINT, drop_retransmit_once=True
        ),
    )
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    times, _Xs, _Ys = client.start_scan(config.n_points, config._sweep_length_ms)
    assert len(times) == config.n_points
    client.close()


def test_scan_failure() -> None:
    config, client = _build(config=MockDeviceConfig(fail_after=0))
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    with pytest.raises(DeviceComError):
        client.start_scan(config.n_points, config._sweep_length_ms)
    client.close()


def test_set_settings_rejected() -> None:
    config, client = _build(config=MockDeviceConfig(reject_settings=True))
    with pytest.raises(DeviceComError, match="Failed to set settings"):
        client.set_settings(
            config.n_points, config.integration_periods, use_ema=config.use_ema
        )
    client.close()


def test_upload_list_start_rejected() -> None:
    config, client = _build(config=MockDeviceConfig(reject_list_start=True))
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    with pytest.raises(DeviceComError, match="Failed to start list upload"):
        client.upload_list(scanning_list)
    client.close()


def test_upload_list_complete_rejected() -> None:
    config, client = _build(config=MockDeviceConfig(reject_list_complete=True))
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    with pytest.raises(DeviceComError, match="Failed to upload list"):
        client.upload_list(scanning_list)
    client.close()


def test_start_scan_rejected() -> None:
    config, client = _build(config=MockDeviceConfig(reject_scan_start=True))
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    with pytest.raises(DeviceComError, match="Failed to start scan"):
        client.start_scan(config.n_points, config._sweep_length_ms)
    client.close()


def test_send_expect_timeout_then_retry() -> None:
    # The mock responds to set_settings (1 response) but then times out.
    # upload_list calls _send_expect for set_list_start which will timeout,
    # retry, and timeout again → exhaustion.
    config, client = _build(config=MockDeviceConfig(timeout_after_n_responses=1))
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client._timeout = 0.1  # Short timeout to speed up test
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    with pytest.raises(DeviceComError, match="Timeout"):
        client.upload_list(scanning_list)
    client.close()


def test_send_expect_wrong_type() -> None:
    config, client = _build()
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    # Inject a wrong-type response: send a start_scan request but have the
    # mock respond. The mock will respond with START_SCAN_RESPONSE. We then
    # call _send_expect expecting a different type.
    env = client._codec.build_envelope(mt.START_SCAN_REQUEST)
    env.start_scan_request.SetInParent()
    with pytest.raises(DeviceComError, match="Unexpected response"):
        client._send_expect(env, mt.SET_SETTINGS_RESPONSE)
    client.close()


def test_drain_corrupt_frame() -> None:
    config, client = _build()
    assert isinstance(client._conn, LeMockDevice)
    client._conn._tx_buffer.extend(b"\x01\x02\x03\x00")  # invalid frame
    # Now send a valid command — the corrupt frame should be skipped.
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.close()


def test_retransmit_chunk_exhaustion() -> None:
    config, client = _build(
        config=MockDeviceConfig(drop_retransmit_once=True, retransmit_unavailable=True),
    )
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    with pytest.raises(DeviceComError, match="unavailable after"):
        client.start_scan(config.n_points, config._sweep_length_ms)
    client.close()


def test_retransmit_point_exhaustion() -> None:
    config, client = _build(
        config=MockDeviceConfig(
            transfer_mode=TRANSFER_MODE_PER_POINT,
            drop_retransmit_once=True,
            retransmit_unavailable=True,
        ),
    )
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    with pytest.raises(DeviceComError, match="unavailable after"):
        client.start_scan(config.n_points, config._sweep_length_ms)
    client.close()


def test_start_scan_without_list() -> None:
    config, client = _build()
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    # Don't upload a list → mock returns started=False
    with pytest.raises(DeviceComError, match="Failed to start scan"):
        client.start_scan(config.n_points, config._sweep_length_ms)
    client.close()


def test_list_mock_devices() -> None:
    devices = list_mock_devices()
    assert "mock_device" in devices
    assert len(devices) >= 3


def test_scan_failure_per_point() -> None:
    config, client = _build(
        config=MockDeviceConfig(fail_after=0, transfer_mode=TRANSFER_MODE_PER_POINT)
    )
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    with pytest.raises(DeviceComError):
        client.start_scan(config.n_points, config._sweep_length_ms)
    client.close()


def test_await_scan_complete_timeout() -> None:
    # Use high integration_periods so mock scan takes very long.
    config = LeDeviceConfiguration(
        amp_port="mock_device",
        use_ema=False,
        n_points=10,
        scan_intervals=[Interval(0.0, 1.0)],
        integration_periods=10000,
    )
    backend = LeMockDevice()
    client = MimLinkClient(conn=backend, timeout=2.0)
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    # Pass a very short sweep_length_ms so the polling window expires
    # before the mock scan finishes (mock scan takes ~10s).
    with pytest.raises(DeviceComError, match="Timeout waiting for scan"):
        client.start_scan(config.n_points, sweep_length_ms=1.0)
    client.close()


def _build_scripted_envelopes(codec: EnvelopeCodec, envelopes: list[Envelope]) -> bytes:
    return b"".join(codec.encode(env) for env in envelopes)


def test_inline_retransmit_per_point() -> None:
    codec = EnvelopeCodec()

    env0 = codec.build_envelope(mt.RESULT_POINT)
    p0 = env0.result_point
    p0.point_index = 0
    p0.time, p0.x, p0.y, p0.is_last = 1.0, 2.0, 3.0, False

    env_rt = codec.build_envelope(mt.RESULT_POINT_RETRANSMIT)
    rt = env_rt.result_point_retransmit
    rt.point_index = 1
    rt.available = True
    rt.time, rt.x, rt.y = 4.0, 5.0, 6.0

    env2 = codec.build_envelope(mt.RESULT_POINT)
    p2 = env2.result_point
    p2.point_index = 2
    p2.time, p2.x, p2.y, p2.is_last = 7.0, 8.0, 9.0, True

    data = _build_scripted_envelopes(codec, [env0, env_rt, env2])
    conn = ScriptedTransport(data)
    client = MimLinkClient(conn=conn, timeout=5.0)
    times, _Xs, _Ys = client._collect_per_point(3, 100.0)
    assert len(times) == 3
    client.close()


def test_inline_retransmit_bulk() -> None:
    """L239-243: RESULTS_CHUNK_RETRANSMIT arrives during bulk chunk stream."""
    codec = EnvelopeCodec()

    # GET_STATUS_RESPONSE for _await_scan_complete
    status_env = codec.build_envelope(mt.GET_STATUS_RESPONSE)
    status_env.get_status_response.scan_ongoing = False

    chunk0 = codec.build_envelope(mt.RESULTS_CHUNK)
    c0 = chunk0.results_chunk
    c0.chunk_index = 0
    c0.times.extend([1.0])
    c0.x.extend([2.0])
    c0.y.extend([3.0])
    c0.is_last = False

    rt_chunk = codec.build_envelope(mt.RESULTS_CHUNK_RETRANSMIT)
    rt = rt_chunk.results_chunk_retransmit
    rt.chunk_index = 1
    rt.available = True
    rt.times.extend([4.0])
    rt.x.extend([5.0])
    rt.y.extend([6.0])
    rt.is_last = False

    chunk2 = codec.build_envelope(mt.RESULTS_CHUNK)
    c2 = chunk2.results_chunk
    c2.chunk_index = 2
    c2.times.extend([7.0])
    c2.x.extend([8.0])
    c2.y.extend([9.0])
    c2.is_last = True

    data = _build_scripted_envelopes(codec, [status_env, chunk0, rt_chunk, chunk2])
    conn = ScriptedTransport(data)
    client = MimLinkClient(conn=conn, timeout=5.0)
    times, _Xs, _Ys = client._collect_bulk(3, 1.0)
    assert len(times) == 3
    client.close()


# --- MimOS boundary constraint tests ---


def test_list_length_zero_rejected() -> None:
    """list_length=0 is below the minimum (1)."""
    config, client = _build(n_points=0)
    with pytest.raises(DeviceComError, match="Failed to set settings"):
        client.set_settings(0, config.integration_periods, use_ema=config.use_ema)
    client.close()


def test_list_length_max_accepted() -> None:
    """list_length=6000 is the maximum allowed."""
    config, client = _build(n_points=6000)
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    client.close()


def test_list_length_over_max_rejected() -> None:
    """list_length=6001 exceeds the maximum."""
    config, client = _build(n_points=6001)
    with pytest.raises(DeviceComError, match="Failed to set settings"):
        client.set_settings(
            config.n_points, config.integration_periods, use_ema=config.use_ema
        )
    client.close()


def test_integration_periods_zero_rejected() -> None:
    """integration_periods=0 is below the minimum (1)."""
    config, client = _build(integration_periods=0)
    with pytest.raises(DeviceComError, match="Failed to set settings"):
        client.set_settings(config.n_points, 0, use_ema=config.use_ema)
    client.close()


def test_integration_periods_max_accepted() -> None:
    """integration_periods=10000 is the maximum allowed."""
    config, client = _build(integration_periods=10000)
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.upload_list(scanning_list)
    client.close()


def test_integration_periods_over_max_rejected() -> None:
    """integration_periods=10001 exceeds the maximum."""
    config, client = _build(integration_periods=10001)
    with pytest.raises(DeviceComError, match="Failed to set settings"):
        client.set_settings(
            config.n_points, config.integration_periods, use_ema=config.use_ema
        )
    client.close()
