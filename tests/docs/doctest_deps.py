from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class DoctestDep(ABC):
    @abstractmethod
    def path(self: DoctestDep) -> Path: ...

    @abstractmethod
    def setup(self: DoctestDep, monkeypatch: pytest.MonkeyPatch) -> None: ...

    @abstractmethod
    def teardown(self: DoctestDep) -> None: ...


class DoctestDepRegistry:
    def __init__(self: DoctestDepRegistry) -> None:
        self._registry: dict[Path, type[DoctestDep]] = {}

    def register(self: DoctestDepRegistry, dep: type[DoctestDep]) -> None:
        self._registry[dep().path()] = dep

    def setup(
        self: DoctestDepRegistry, path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dep = self._registry.get(path, None)
        if dep is not None:
            dep().setup(monkeypatch)

    def teardown(self: DoctestDepRegistry, path: Path) -> None:
        dep = self._registry.get(path, None)
        if dep is not None:
            dep().teardown()


DOCTEST_DEPS_REGISTRY = DoctestDepRegistry()
