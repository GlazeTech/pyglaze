# Welcome to Pyglaze

---

**Source Code**: <a href="https://github.com/GlazeTech/pyglaze" target="_blank">https://github.com/GlazeTech/pyglaze</a>

**Documentation Version**: 0.2.2

---

This is the Pyglaze API documentation. Pyglaze is a python library used to operate the devices of [Glaze Technologies](https://www.glazetech.dk/). If you have a feature request or discover a bug, please create an issue [here](https://github.com/GlazeTech/pyglaze/issues) and we will look at it ASAP!

## Usage

Pyglaze provides two main interfaces for operating Glaze devices: The [`Scanner`](API%20Reference/scanning/Scanner.md) and the The [`GlazeClient`](API%20Reference/scanning/GlazeClient.md), where `Scanner`is a synchronous scanner, only scanning when requested, and `GlazeClient` is an asynchronous scanner, continuously scanning in the background.

### GlazeClient
Using the `GlazeClient`is the prefered way to acquire scans. Before starting the scanner, a device configuration must be created. Depending on the type of device, different configurations are required, see e.g. a definition [here](API%20Reference/device/ForceDeviceConfiguration.md) or [here](API%20Reference/device/LeDeviceConfiguration.md). Be sure to replace `mock_device` and `mock_delay` with suitable values. Here, we will use a [`LeDeviceConfiguration`](API%20Reference/device/LeDeviceConfiguration.md).


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
    pulses = [
        pulse.from_triangular_waveform(ramp="down")
        .reconstruct(method="cubic_spline")
        .as_pulse()
        for pulse in scans
    ]

```

The client returns a list of [`UnprocessedWaveform`](API%20Reference/datamodels/UnprocessedWaveform.md), which can have many shapes and forms depending on the `scan_intervals`. Here, we extract the part of the waveforms corresponding to the down-ramp of the triangular waveform, then we perform a reconstruction to ensure we have pulses with equidistant times. Finally, having preprocessed the waveforms, we convert it to a list of[`Pulse`](API%20Reference/datamodels/UnprocessedWaveform.md). The pulse has attributes such as `pulse.time`, `pulse.signal`, `pulse.frequency` and `pulse.fft` in addition to many different convenience methods such as `pulse.filter()` for applying low- and highpass fitlers, `pulse.spectrum_dB()` for calculating the spectrum on a dB-scale and `pulse.to_native_dict()` for e.g. saving the pulse. Finally, we'll use the latter to save the results to disk

```py
with Path("scan_result.json").open("w") as f:
    json.dump([pulse.to_native_dict() for pulse in pulses], f, indent=4)
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
pulse = (
    waveform.from_triangular_waveform(ramp="down")
    .reconstruct(method="cubic_spline")
    .as_pulse()
)
```
Like before, the pulse is now ready for further analysis or for saving to disk.

```py
with Path("scan_result_scanner.json").open("w") as f:
    json.dump(pulse.to_native_dict(), f, indent=4)
```