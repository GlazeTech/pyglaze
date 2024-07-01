# ForceDeviceConfiguration

**`pyglaze.device.ForceDeviceConfiguration`**

::: pyglaze.device.ForceDeviceConfiguration

**`pyglaze.device.LeDeviceConfiguration`**

::: pyglaze.device.LeDeviceConfiguration

## Examples


#### Make a device configuration
Depending on which device is used, a matching device configuration must be used.
=== "ForceDeviceConfiguration"
```py
from pyglaze.device import ForceDeviceConfiguration

config = ForceDeviceConfiguration(
    amp_port="mock_device", sweep_length_ms=6000, delayunit="mock_delay"
)
```
=== "LeDeviceConfiguration"
```py
from pyglaze.device import LeDeviceConfiguration

config = LeDeviceConfiguration(
    amp_port="mock_device", delayunit="mock_delay", use_ema=True
)
```

Be sure to use the correct port and delayunit! The `mock_device` and `mock_delay` are only for testing purposes