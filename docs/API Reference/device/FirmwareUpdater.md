# FirmwareUpdater

**`pyglaze.device.FirmwareUpdater`**

::: pyglaze.device.FirmwareUpdater

## Examples

```py
from pyglaze.device import FirmwareUpdater

updater = FirmwareUpdater.from_port("/dev/cu.usbserial-XXXX")
result = updater.update("build/current/MimOS-nucleo.signed.bin")
print(result.confirmed_version)
```
