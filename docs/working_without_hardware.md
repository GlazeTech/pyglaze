# Working without Hardware (Mock Device)

Pyglaze ships with a built-in *mock device* that produces synthetic data identical in shape and units to what you would receive from a physical Glaze device. This makes it possible to develop, unit-test, or demonstrate software even when no hardware is connected.

**Quick-start**
To mock the asynchronous scanner, use
```python
from pyglaze.device import ConnectionInfo, ScannerConfiguration
from pyglaze.scanning import GlazeClient

connection = ConnectionInfo(port="mock_mimlink_device")
config = ScannerConfiguration()
with GlazeClient(connection, config) as client:
    pulses = client.read(n_pulses=1)
```

To use the synchronous scanner, use
```python
from pyglaze.device import ConnectionInfo, ScannerConfiguration
from pyglaze.scanning import Scanner

connection = ConnectionInfo(port="mock_mimlink_device")
config = ScannerConfiguration()
scanner = Scanner(connection=connection, config=config)
waveform = scanner.scan()
```


---

## 1  When to use the mock device

| Scenario                   | Benefit                                                                     |
| -------------------------- | --------------------------------------------------------------------------- |
| **Algorithm development**  | Iterate on processing pipelines without reserving lab time.                 |
| **Continuous integration** | Run the full test-suite on CI servers that have no USB access.              |
| **Workshops & demos**      | Teach new users the API anywhere, even on a plane.                          |
| **Bug reports**            | Supply a minimal, reproducible script that others can run without hardware. |

---

## 2  How it works

* The sentinel string `"mock_mimlink_device"` instructs Pyglaze to replace the serial driver with a software stub.
* All higher-level classes (`Scanner`, `GlazeClient`, `Pulse`, `UnprocessedWaveform`, ...) operate unchanged.


---

## 3  Common pitfalls

1. **Misspelling the sentinel** - the string is case-sensitive. Use exactly `"mock_mimlink_device"`.
2. **Mistaking it for a placeholder** - it *is* the implementation, not an example to replace.

---


## 4  Search keywords

* simulate / simulation
* virtual device
* offline mode
* no hardware
* CI pipeline
* test without device
