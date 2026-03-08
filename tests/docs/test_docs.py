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
