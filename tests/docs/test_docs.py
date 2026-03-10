from __future__ import annotations

from pathlib import Path

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


_HARDWARE_ONLY_DOCS = [
    Path("docs/firmware_update.md"),
    Path("docs/API Reference/device/FirmwareUpdater.md"),
]


@DOCTEST_DEPS_REGISTRY.register
class FirmwareUpdateDeps(DoctestDep):
    def path(self: FirmwareUpdateDeps) -> Path:
        return _HARDWARE_ONLY_DOCS[0]

    def setup(self: FirmwareUpdateDeps, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ARG002
        pytest.skip("firmware update examples require hardware")

    def teardown(self: FirmwareUpdateDeps) -> None:
        pass


@DOCTEST_DEPS_REGISTRY.register
class FirmwareUpdaterApiDeps(DoctestDep):
    def path(self: FirmwareUpdaterApiDeps) -> Path:
        return _HARDWARE_ONLY_DOCS[1]

    def setup(self: FirmwareUpdaterApiDeps, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ARG002
        pytest.skip("firmware update examples require hardware")

    def teardown(self: FirmwareUpdaterApiDeps) -> None:
        pass


@DOCTEST_DEPS_REGISTRY.register
class IndexDeps(DoctestDep):
    def path(self: IndexDeps) -> Path:
        return Path("docs/index.md")

    def setup(self: IndexDeps, monkeypatch: pytest.MonkeyPatch) -> None:
        pass

    def teardown(self: IndexDeps) -> None:
        for p in [
            Path("scan_result_scanner.json"),
            Path("scan_result.json"),
        ]:
            p.unlink(missing_ok=True)
