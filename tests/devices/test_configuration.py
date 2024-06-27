from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from pyglaze.device import ForceDeviceConfiguration, Interval, LeDeviceConfiguration
from pyglaze.device.delayunit import list_delayunits
from tests.conftest import DEVICE_CONFIGS

if TYPE_CHECKING:
    from pyglaze.device.configuration import DeviceConfiguration


def test_wrong_delayunit_force() -> None:
    with pytest.raises(
        ValueError,
        match=f"Unknown delayunit 'Nonexisting_unit'. Valid options are: {', '.join(list_delayunits())}.",
    ):
        ForceDeviceConfiguration(
            amp_port="mock_device", sweep_length_ms=6000, delayunit="Nonexisting_unit"
        )


def test_wrong_delayunit_le() -> None:
    with pytest.raises(
        ValueError,
        match=f"Unknown delayunit 'Nonexisting_unit'. Valid options are: {', '.join(list_delayunits())}.",
    ):
        LeDeviceConfiguration(amp_port="mock_device", delayunit="Nonexisting_unit")


@pytest.mark.parametrize(
    "test_pars",
    [
        {"sweep_length_ms": 500, "delayunit": "mock_delay"},
        {
            "sweep_length_ms": 500,
            "scan_intervals": [Interval(0.0, 0.5), Interval(0.6, 1.0)],
            "delayunit": "mock_delay",
        },
    ],
)
def test_create_simple_scan_config(test_pars: dict[str, Any]) -> None:
    _ = ForceDeviceConfiguration(amp_port="mock_device", **test_pars)


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_save_load_device_config(
    config_name: str, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    save_path = tmp_path / "test_save_config.json"

    device_config.save(save_path)
    loaded_conf = device_config.load(save_path)
    assert loaded_conf == device_config
