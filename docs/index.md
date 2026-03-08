# Welcome to Pyglaze

---

**Source Code**: <a href="https://github.com/GlazeTech/pyglaze" target="_blank">https://github.com/GlazeTech/pyglaze</a>

**Documentation Version**: 0.6.0

---

This is the Pyglaze API documentation. Pyglaze is a python library used to operate the devices of [Glaze Technologies](https://www.glazetech.dk/). If you have a feature request or discover a bug, please create an issue [here](https://github.com/GlazeTech/pyglaze/issues) and we will look at it ASAP!

> Breaking change in `0.6.0`: `Pulse` is no longer part of `pyglaze`. `pyglaze`
> returns `UnprocessedWaveform` objects.

## Usage

Pyglaze provides two main interfaces for operating Glaze devices: The [`Scanner`](API%20Reference/scanning/Scanner.md) and the The [`GlazeClient`](API%20Reference/scanning/GlazeClient.md), where `Scanner`is a synchronous scanner, only scanning when requested, and `GlazeClient` is an asynchronous scanner, continuously scanning in the background.

### GlazeClient
Using the `GlazeClient`is the preferred way to acquire scans. Before starting the scanner, a device configuration must be created. Depending on the type of device, different configurations are required, see e.g. a definition [here](API%20Reference/device/LeDeviceConfiguration.md). Be sure to replace `mock_device` and `mock_delay` with suitable values. Here, we will use a [`LeDeviceConfiguration`](API%20Reference/device/LeDeviceConfiguration.md).

```py
import json
from pathlib import Path

from pyglaze.device import Interval, LeDeviceConfiguration
from pyglaze.scanning import GlazeClient

device_config = LeDeviceConfiguration(
    amp_port="mock_device",
    integration_periods=10,
    scan_intervals=[
        Interval(0.5, 1.0),
        Interval(1.0, 0.0),
        Interval(0.0, 0.5),
    ],
)

```
When defining the configuration, a list of `scan_intervals` is set, determining which parts of the available timewindow should be scanned. Here, we scan a triangular waveform. Next, let's perform a scan.

```py
with GlazeClient(config=device_config) as client:
    scans = client.read(n_pulses=1)
    reconstructed_waveforms = [
        pulse.from_triangular_waveform(ramp="down")
        .reconstruct(method="cubic_spline")
        for pulse in scans
    ]

```

The client returns a list of [`UnprocessedWaveform`](API%20Reference/datamodels/UnprocessedWaveform.md), which can have many shapes and forms depending on the `scan_intervals`. Here, we extract the part of the waveforms corresponding to the down-ramp of the triangular waveform, then we perform a reconstruction to ensure we have uniformly sampled data. Finally, we'll save the reconstructed waveforms to disk.

```py
with Path("scan_result.json").open("w") as f:
    json.dump(
        [
            {"time": list(waveform.time), "signal": list(waveform.signal)}
            for waveform in reconstructed_waveforms
        ],
        f,
        indent=4,
    )
```

### Scanner
Much like the `GlazeClient`, a `Scanner`is instantiated by first defining a configuration. Once instantiated, scans can be acquired by calling the `scanner.scan()` method.

```py
import json
from pathlib import Path

from pyglaze.device import Interval, LeDeviceConfiguration
from pyglaze.scanning import Scanner

device_config = LeDeviceConfiguration(
    amp_port="mock_device",
    integration_periods=10,
    n_points=100,
    scan_intervals=[
        Interval(0.5, 1.0),
        Interval(1.0, 0.0),
        Interval(0.0, 0.5),
    ],
)

scanner = Scanner(config=device_config)
device_config = LeDeviceConfiguration(
    amp_port="mock_device",
    integration_periods=10,
    scan_intervals=[
        Interval(0.5, 1.0),
        Interval(1.0, 0.0),
        Interval(0.0, 0.5),
    ],
)
waveform = scanner.scan()
reconstructed = waveform.from_triangular_waveform(ramp="down").reconstruct(
    method="cubic_spline"
)
```
Like before, the reconstructed waveform is now ready for further analysis or saving.

```py
with Path("scan_result_scanner.json").open("w") as f:
    json.dump(
        {"time": list(reconstructed.time), "signal": list(reconstructed.signal)},
        f,
        indent=4,
    )
```
