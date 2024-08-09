# Scanner

**`pyglaze.scanning.Scanner`**


::: pyglaze.scanning.Scanner

## Examples

#### Initialize a Scanner and perform a scan
The config file should be valid JSON conforming to the specific `DeviceConfiguration` type. See e.g. a definition [here](../device/ForceDeviceConfiguration.md). Be sure to replace `mock_device` and `mock_delay` with suitable values.

=== "ForceDeviceConfiguration"

    ```py
    from pyglaze.device import ForceDeviceConfiguration
    from pyglaze.scanning import Scanner

    device_config = ForceDeviceConfiguration(
        amp_port="mock_device", sweep_length_ms=10
    )
    scanner = Scanner(config=device_config)
    scan_result = scanner.scan()
    ```

=== "LeDeviceConfiguration"

    ```py
    from pyglaze.device import LeDeviceConfiguration
    from pyglaze.scanning import Scanner

    device_config = LeDeviceConfiguration(amp_port="mock_device")
    scanner = Scanner(config=device_config)
    scan_result = scanner.scan()
    ```
