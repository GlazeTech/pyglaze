from __future__ import annotations

import pytest

from pyglaze.device.configuration import Interval, LeDeviceConfiguration
from pyglaze.device.exceptions import DeviceComError
from pyglaze.device.scan_client import ScanClient
from pyglaze.device.transport import MimLinkTransport
from pyglaze.devtools.mock_device import LeMockDevice, MockDeviceConfig
from pyglaze.mimlink import msg_types as mt
from pyglaze.scanning.scanner import _compute_scanning_list


def _build(
    n_points: int = 100,
    *,
    config: MockDeviceConfig | None = None,
    integration_periods: int = 1,
) -> tuple[LeDeviceConfiguration, ScanClient]:
    dev_config = LeDeviceConfiguration(
        amp_port="mock_device",
        use_ema=False,
        n_points=n_points,
        scan_intervals=[Interval(0.0, 1.0)],
        integration_periods=integration_periods,
    )
    backend = LeMockDevice(config)
    backend.reset_input_buffer()
    transport = MimLinkTransport(conn=backend)
    client = ScanClient(
        transport=transport,
        n_points=dev_config.n_points,
        sweep_length_ms=dev_config._sweep_length_ms,
    )
    return dev_config, client


def test_send_expect_timeout_then_retry() -> None:
    # The mock responds to set_settings (1 response) but then times out.
    # upload_list calls _send_expect for set_list_start which will timeout,
    # retry, and timeout again → exhaustion.
    config, client = _build(config=MockDeviceConfig(timeout_after_n_responses=1))
    scanning_list = _compute_scanning_list(config.n_points, config.scan_intervals)
    client._transport.default_timeout_s = 0.1  # Short timeout to speed up test
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    with pytest.raises(DeviceComError, match="Timeout"):
        client.upload_list(scanning_list)
    client.close()


def test_receive_backs_off_on_empty_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    _config, client = _build(config=MockDeviceConfig(empty_responses=True))
    sleep_calls: list[float] = []

    def _fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    monkeypatch.setattr("pyglaze.device.transport.time.sleep", _fake_sleep)

    with pytest.raises(DeviceComError, match="Timeout"):
        client._transport.receive(timeout=0.01)

    assert sleep_calls
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
    env = client._transport.build_envelope(mt.START_SCAN_REQUEST)
    env.start_scan_request.SetInParent()
    with pytest.raises(DeviceComError, match="Unexpected response"):
        client._transport.send_expect(env, mt.SET_SETTINGS_RESPONSE)
    client.close()


def test_drain_corrupt_frame() -> None:
    config, client = _build()
    assert isinstance(client._transport._conn, LeMockDevice)
    client._transport._conn._tx_buffer.extend(b"\x01\x02\x03\x00")
    # Now send a valid command — the corrupt frame should be skipped.
    client.set_settings(
        config.n_points, config.integration_periods, use_ema=config.use_ema
    )
    client.close()
