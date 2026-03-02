# /// script
# requires-python = ">=3.12"
# dependencies = ["pyglaze"]
# ///
from pyglaze.device import Interval, LeDeviceConfiguration
from pyglaze.scanning import Scanner

config = LeDeviceConfiguration(
    amp_port="auto",
    integration_periods=10,
    scan_intervals=[
        Interval(0.5, 1.0),
        Interval(1.0, 0.0),
        Interval(0.0, 0.5),
    ],
)

scanner = Scanner(config=config)
waveform = scanner.scan()
scanner.disconnect()

pulse = (
    waveform.from_triangular_waveform(ramp="down")
    .reconstruct(method="cubic_spline")
    .as_pulse()
)

print(f"Pulse acquired: {len(pulse.time)} points")
print(f"Time range: {pulse.time[0]:.4f} - {pulse.time[-1]:.4f}")
