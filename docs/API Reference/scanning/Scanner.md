# Scanner

**`pyglaze.scanning.Scanner`**


::: pyglaze.scanning.Scanner

## Examples

#### Initialize a Scanner and perform a scan
The config holds scan parameters. Use `serial_transport(discover_one())` to connect to a device, or use `mock_transport()` to run without hardware.


=== "ScannerConfiguration"

    ```py
    from pyglaze.device import ScannerConfiguration
    from pyglaze.devtools.mock_device import mock_transport
    from pyglaze.scanning import Scanner

    config = ScannerConfiguration()
    scanner = Scanner(transport=mock_transport(), config=config)
    scan_result = scanner.scan()
    ```
