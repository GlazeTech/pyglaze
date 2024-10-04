# ForceDeviceConfiguration

**`pyglaze.device.ForceDeviceConfiguration`**

::: pyglaze.device.ForceDeviceConfiguration

## Examples


#### Make a device configuration
Depending on which device is used, a matching device configuration must be used.

```py
from pyglaze.device import ForceDeviceConfiguration

config = ForceDeviceConfiguration(
    amp_port="mock_device", sweep_length_ms=6000
)
```

Be sure to use the correct port and delayunit! The `mock_device` and `mock_delay` are only for testing purposes