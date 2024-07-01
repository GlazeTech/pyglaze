# LeDeviceConfiguration

**`pyglaze.device.LeDeviceConfiguration`**

::: pyglaze.device.LeDeviceConfiguration

## Examples


#### Make a device configuration
Depending on which device is used, a matching device configuration must be used.

=== "Make a device configuration"

    ```py
    from pyglaze.device import LeDeviceConfiguration

    config = LeDeviceConfiguration(
        amp_port="mock_device", delayunit="mock_delay", use_ema=True
    )
    ```

Be sure to use the correct port and delayunit! The `mock_device` and `mock_delay` are only for testing purposes