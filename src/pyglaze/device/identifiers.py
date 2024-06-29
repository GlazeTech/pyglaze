from typing import Literal, get_args
from uuid import UUID

from typing_extensions import TypeAlias

DeviceName: TypeAlias = Literal["glaze1", "glaze2", "carmen"]


def _device_ids() -> dict[DeviceName, UUID]:
    return {
        "glaze1": UUID("5042dbda-e9bc-4216-a614-ac56d0a32023"),
        "glaze2": UUID("66fa482a-1ef4-4076-a883-72d7bf43e151"),
        "carmen": UUID("6a54db26-fa88-4146-b04f-b84b945bfea8"),
    }


def list_devices() -> list[DeviceName]:
    """List all available devices.

    Returns:
        A list of all available devices.
    """
    return list(_device_ids().keys())


def get_device_id(name: DeviceName) -> UUID:
    """Get the UUID of a device by its name.

    Args:
        name: The name of the device.

    Returns:
        Unique identifier of a device.
    """
    try:
        return _device_ids()[name]
    except KeyError as e:
        msg = (
            f"Device {name} does not exist. Possible values are {get_args(DeviceName)}"
        )
        raise ValueError(msg) from e
