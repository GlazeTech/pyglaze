from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

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
        self.PULSE_PATH.unlink()


@DOCTEST_DEPS_REGISTRY.register
class IndexDeps(DoctestDep):
    SAVED_PULSE_PATHS: ClassVar[list[Path]] = [
        Path("scan_result_scanner.json"),
        Path("scan_result.json"),
    ]

    def path(self: PulseExampleDeps) -> Path:
        return Path("docs/index.md")

    def setup(self: PulseExampleDeps, monkeypatch: pytest.MonkeyPatch) -> None:
        pass

    def teardown(self: PulseExampleDeps) -> None:
        for p in self.SAVED_PULSE_PATHS:
            p.unlink()
