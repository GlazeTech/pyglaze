from __future__ import annotations

import pickle

from pyglaze.device import (
    ConfigStatusReason,
    DeviceState,
    DeviceStateError,
    OperationalState,
)


def test_device_state_error_roundtrips_through_pickle() -> None:
    err = DeviceStateError(
        DeviceState(
            operational_state=OperationalState.COMMISSIONING_IDLE,
            config_status_reason=ConfigStatusReason.INVALID_CONFIG,
        ),
        action="start a normal scan",
    )

    restored = pickle.loads(pickle.dumps(err))

    assert isinstance(restored, DeviceStateError)
    assert restored.state.operational_state is OperationalState.COMMISSIONING_IDLE
    assert restored.state.config_status_reason is ConfigStatusReason.INVALID_CONFIG
    assert restored.action == "start a normal scan"
    assert "commissioning/recovery idle" in str(restored)
