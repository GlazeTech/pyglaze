from __future__ import annotations

from pathlib import Path

import pytest

from pyglaze.devtools.mock_device import mock_transport

from .doctest_deps import DOCTEST_DEPS_REGISTRY, DoctestDep
from .markdownparser import check_md_file


@pytest.mark.parametrize("path", Path("docs").glob("**/*.md"), ids=str)
def test_valid_python(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    print(f"Checking {path}")
    try:
        DOCTEST_DEPS_REGISTRY.setup(path=path, monkeypatch=monkeypatch)
        check_md_file(path=path)
    except Exception:
        DOCTEST_DEPS_REGISTRY.teardown(path=path)
        raise
    else:
        DOCTEST_DEPS_REGISTRY.teardown(path=path)


@DOCTEST_DEPS_REGISTRY.register
class PulseExampleDeps(DoctestDep):
    PULSE_PATH = Path("my_pulse_data.json")

    def path(self: PulseExampleDeps) -> Path:
        return Path("docs/API Reference/datamodels/Pulse.md")

    def setup(self: PulseExampleDeps, monkeypatch: pytest.MonkeyPatch) -> None:
        pass

    def teardown(self: PulseExampleDeps) -> None:
        self.PULSE_PATH.unlink(missing_ok=True)


@DOCTEST_DEPS_REGISTRY.register
class IndexDeps(DoctestDep):
    def path(self: IndexDeps) -> Path:
        return Path("docs/index.md")

    def setup(self: IndexDeps, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_factory = lambda port: mock_transport()  # noqa: E731
        monkeypatch.setattr("pyglaze.device.discover_one", lambda: "/dev/mock")
        monkeypatch.setattr("pyglaze.device.serial_transport", mock_factory)
        monkeypatch.setattr(
            "pyglaze.device.discovery.discover_one", lambda: "/dev/mock"
        )
        monkeypatch.setattr(
            "pyglaze.device.serial_backend.serial_transport", mock_factory
        )

    def teardown(self: IndexDeps) -> None:
        for p in [
            Path("scan_result_scanner.json"),
            Path("scan_result.json"),
        ]:
            p.unlink(missing_ok=True)
