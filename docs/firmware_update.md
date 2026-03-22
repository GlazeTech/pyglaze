# Firmware Updates

`pyglaze` supports firmware updates over MimLink via `FirmwareUpdater`.

If you need to decide which release artifact to flash, use the firmware catalog
helpers first. See [Firmware Catalogs](firmware_catalog.md).

## Prerequisites

- Device running MimLink firmware update handlers.
- Serial port access to the device.
- A pre-signed MCUboot image (`*.signed.bin`).

`pyglaze` does not sign firmware images. Signing should happen in your build/release pipeline.

## Basic Usage

```py
from pyglaze.device import FirmwareUpdater


def on_progress(stage: str) -> None:
    print(f"stage: {stage}")


updater = FirmwareUpdater.from_port("/dev/cu.usbserial-XXXX")
result = updater.update(
    "build/current/MimOS-nucleo.signed.bin",
    version="v1.2.3",
    on_progress=on_progress,
)

print(result.confirmed_version, result.final_status.name.lower())
```

Progress stages emitted by `on_progress`:

- `uploading`
- `reconnecting`
- `confirming`
- `done`

## Query Current Boot State

```py
from pyglaze.device import FirmwareUpdater

updater = FirmwareUpdater.from_port("/dev/cu.usbserial-XXXX")
info = updater.get_boot_info()
print(info.firmware_version, info.update_status.name.lower())
```

## Error Handling

`FirmwareUpdater.update(...)` raises `FirmwareUpdateError` when:

- the image is not MCUboot-signed (header magic check fails),
- the transfer is rejected or aborted by device responses,
- reconnect/confirm/status reads time out.

`FirmwareUpdater` retries reconnect-sensitive operations across fresh client connections before timing out.

## Confirm / Rollback Semantics

- After upload, the device reboots into the test image.
- Unconfirmed test images can roll back depending on MCUboot/device policy.
- `FirmwareUpdater.update(...)` waits for reconnect and then confirms boot for you.

If you need manual control (for rollback testing), use lower-level `FirmwareClient` methods directly.

`FirmwareClient.get_firmware_update_status()` returns a `FirmwareUpdateStatus`
model with:

- `status`: `FirmwareUpdateState`
- `chunks_received`: `int`
- `total_chunks`: `int`
- `bytes_received`: `int`
