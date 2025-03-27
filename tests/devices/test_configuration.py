from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.conftest import DEVICE_CONFIGS

if TYPE_CHECKING:
    from pyglaze.device.configuration import DeviceConfiguration


@pytest.mark.parametrize("config_name", DEVICE_CONFIGS)
def test_save_load_device_config(
    config_name: str, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    device_config: DeviceConfiguration = request.getfixturevalue(config_name)
    save_path = tmp_path / "test_save_config.json"

    device_config.save(save_path)
    loaded_conf = device_config.load(save_path)
    assert loaded_conf == device_config
