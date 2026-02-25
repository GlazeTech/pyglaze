from pathlib import Path

from pyglaze.device.configuration import Interval, ScannerConfiguration


def test_save_load_scanner_config(tmp_path: Path) -> None:
    config = ScannerConfiguration(
        use_ema=True,
        n_points=100,
        scan_intervals=[Interval(0.0, 1.0)],
        integration_periods=1,
    )
    save_path = tmp_path / "test_save_config.json"

    config.save(save_path)
    loaded_conf = ScannerConfiguration.load(save_path)
    assert loaded_conf == config
