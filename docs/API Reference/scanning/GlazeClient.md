# GlazeClient

**`pyglaze.scanning.GlazeClient`**

!!! warning

    Ensure that you are properly connected to the lock-in amp, have it selected,
    and a configuration is chosen.

::: pyglaze.scanning.GlazeClient

## Examples

```py title="Initialize a Scanner and perform two scans"
from pyglaze.device import LeDeviceConfiguration
from pyglaze.scanning import GlazeClient


def main() -> None:
    n_pulses = 2
    device_config = LeDeviceConfiguration(
        amp_port="mock_device", delayunit="mock_delay"
    )
    with GlazeClient(device_config) as client:
        unprocessed_waveforms = client.read(n_pulses=n_pulses)


if __name__ == "__main__":
    main()

```

1. The config file should be valid JSON of the `DeviceConfiguration` type. See a list of configuration options under "API Reference > Device".
