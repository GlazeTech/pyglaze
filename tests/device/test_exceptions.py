from __future__ import annotations

import pickle

from pyglaze.device import (
    DeviceState,
    DeviceStateError,
)


def test_device_state_error_roundtrips_through_pickle() -> None:
    err = DeviceStateError(
        DeviceState(
            operational_state="commissioning_idle",
            config_status_reason="invalid_config",
        ),
        action="start a normal scan",
    )

    restored = pickle.loads(pickle.dumps(err))

    assert isinstance(restored, DeviceStateError)
    assert restored.state.operational_state == "commissioning_idle"
    assert restored.state.config_status_reason == "invalid_config"
    assert restored.action == "start a normal scan"
    assert "commissioning/recovery idle" in str(restored)
