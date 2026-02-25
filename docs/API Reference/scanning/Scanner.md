# Scanner

**`pyglaze.scanning.Scanner`**


::: pyglaze.scanning.Scanner

## Examples

#### Initialize a Scanner and perform a scan
The config holds scan parameters. Use `discover_one()` to find a connected device, or replace `mock_mimlink_device` with your serial port path.


=== "ScannerConfiguration"

    ```py
    from pyglaze.device import ScannerConfiguration
    from pyglaze.scanning import Scanner

    config = ScannerConfiguration()
    scanner = Scanner(port="mock_mimlink_device", config=config)
    scan_result = scanner.scan()
    ```
