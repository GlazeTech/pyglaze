from typing import get_args
from uuid import UUID

import pytest

from pyglaze.device import get_device_id
from pyglaze.device.identifiers import DeviceName


def test_get_device_id_contains_all() -> None:
    names = get_args(DeviceName)
    for name in names:
        assert isinstance(get_device_id(name), UUID)


def test_get_device_id_fails_on_nonexisting() -> None:
    with pytest.raises(
        ValueError,
        match="Device nonexisting device does not exist. Possible values are *",
    ):
        get_device_id("nonexisting device")  # type: ignore[arg-type]
