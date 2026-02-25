# Scanner

**`pyglaze.scanning.Scanner`**


::: pyglaze.scanning.Scanner

## Examples

#### Initialize a Scanner and perform a scan
The connection specifies how to reach the device. The config holds scan parameters. Be sure to replace `mock_mimlink_device` with a suitable value.


=== "ScannerConfiguration"

    ```py
    from pyglaze.device import ConnectionInfo, ScannerConfiguration
    from pyglaze.scanning import Scanner

    connection = ConnectionInfo(port="mock_mimlink_device")
    config = ScannerConfiguration()
    scanner = Scanner(connection=connection, config=config)
    scan_result = scanner.scan()
    ```
