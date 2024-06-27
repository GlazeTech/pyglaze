# Pulse

**`pyglaze.datamodels.Pulse`**

::: pyglaze.datamodels.Pulse

## Notes

The lock-in amp outputs $\left( r, \theta \right)$ values. To get useful readings, one
must convert these readings by

$$ r \operatorname{sgn} (\theta - 180). $$

$\operatorname{sgn}$, the so-called
[signum function](https://en.wikipedia.org/wiki/Sign_function) outputs the signs of a
vector in a piecewise fashion, implemented in NumPy using

$$ \operatorname{sgn} = \frac{x}{\sqrt{x^2}}. $$

This is handled by the `ScanData` class, and is done transparently when using
`pyglaze.scanning.scanner.Scanner`.
If you have a previous reading that has been converted, `ScanData` allows you to
create an object from this data in dictionary form; see examples below.

## Examples

=== "From JSON file"

``` py
import json
from pathlib import Path

import numpy as np

from pyglaze.datamodels import Pulse

# Generate a pulse - would typically be done with an actual THz device
new_pulse = Pulse(
    time=np.linspace(0, 1, 100), signal=np.random.default_rng().normal(size=100)
)

# Save the pulse as a JSON file
with Path("my_pulse_data.json").open("w") as f:
    json.dump(new_pulse.to_native_dict(), f)

# Load the pulse from the JSON file again
with Path("my_pulse_data.json").open() as f:
    run_data = json.load(f)

pulse = Pulse.from_dict(d=run_data)
```
