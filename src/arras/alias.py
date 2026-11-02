# SPDX-License-Identifier: MIT OR Apache-2.0
"""Serve `arras` under another import name (CONTRACT-005).

A downstream distribution that kept an older import name ships a thin package that calls
`alias_package(__name__)` from its `__init__.py`. Every module imported below the alias is then
the `arras` module object itself (`alias.model is arras.model`), loaded once, with its own
`__spec__`, so `importlib.resources`, `pickle` and `python -m` behave as they do for `arras`.

Three details are easy to get wrong and are handled here:

- The finder is inserted at the front of `sys.meta_path`. A finder appended after the path finder
  is never asked, because the path finder fails the alias name first or loads a second copy.
- The import system overwrites `__spec__` of the module a loader returns; the loader puts the
  original back, or `importlib.resources` fails with an orphan-path error.
- A module the alias package really contains (`alias/__main__.py`, a renamed launcher) wins over
  the aliased one, and an aliased module has a loader with `get_code`, so `python -m alias.x` runs.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
from collections.abc import Iterable, Sequence
from types import ModuleType
from typing import Any

__all__ = ["alias_package"]


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, real: str) -> None:
        self.real = real
        self._spec: importlib.machinery.ModuleSpec | None = None

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType:
        module = importlib.import_module(self.real)
        self._spec = module.__spec__
        return module

    def exec_module(self, module: ModuleType) -> None:
        module.__spec__ = self._spec  # the import system has just replaced it with the alias's

    def get_code(self, fullname: str) -> Any:
        """The code of the real module, for `python -m alias.x` (runpy asks the loader)."""
        spec = importlib.util.find_spec(self.real)
        loader = getattr(spec, "loader", None)
        if loader is None or not hasattr(loader, "get_code"):
            raise ImportError(f"no code object available for {fullname}", name=fullname)
        return loader.get_code(self.real)


class _AliasFinder(importlib.abc.MetaPathFinder):
    def __init__(self, alias: str, target: str, modules: Iterable[str] | None) -> None:
        self.alias = alias
        self.target = target
        self.closed = None if modules is None else frozenset(modules)

    def _allowed(self, relative: str) -> bool:
        """With a closed list, a listed module and the packages that lead to it."""
        if self.closed is None:
            return True
        return any(m == relative or m.startswith(relative + ".") for m in self.closed)

    def _own(self, fullname: str) -> importlib.machinery.ModuleSpec | None:
        """The alias package's own file for `fullname`, if it really contains one."""
        alias_module = sys.modules.get(self.alias)
        shared = set(getattr(sys.modules.get(self.target), "__path__", ()))
        roots: Sequence[str] = [
            r for r in getattr(alias_module, "__path__", ()) if r not in shared
        ]  # a `__path__` borrowed from the target is not a shim
        *parents, _ = fullname.removeprefix(self.alias + ".").split(".")
        folders = [os.path.join(root, *parents) for root in roots]
        folders = [f for f in folders if os.path.isdir(f)]
        return importlib.machinery.PathFinder.find_spec(fullname, folders) if folders else None

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if not fullname.startswith(self.alias + "."):
            return None
        own = self._own(fullname)
        if own is not None:
            return own
        relative = fullname.removeprefix(self.alias + ".")
        real = f"{self.target}.{relative}"
        # A name that is not served is refused here, not passed on: the path finder would search
        # the aliased parent's own directory and load a second copy under the alias's name.
        if not self._allowed(relative):
            raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)
        try:
            real_spec = importlib.util.find_spec(real)
        except ModuleNotFoundError:
            real_spec = None
        if real_spec is None:
            raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)
        spec = importlib.machinery.ModuleSpec(
            fullname,
            _AliasLoader(real),
            origin=real_spec.origin,  # runpy sets `sys.argv[0]` from it
            is_package=real_spec.submodule_search_locations is not None,
        )
        if real_spec.submodule_search_locations is not None:
            spec.submodule_search_locations = list(real_spec.submodule_search_locations)
        return spec


def alias_package(
    name: str, *, target: str = "arras", modules: Iterable[str] | None = None
) -> None:
    """Make every module below `target` importable as `name.<module>`, as the same object.

    Call it from the alias package's `__init__.py` as `alias_package(__name__)`. It installs the
    finder at the front of `sys.meta_path` (a repeated call replaces the earlier finder for the
    same name) and gives the alias package attribute access to the names of `target`, so
    `alias.Arras is arras.Arras`.

    `modules` closes the set: when given, only the listed submodules (dotted names below the
    package, such as `"model"` or `"ui.assets"`) and the packages that lead to them can be
    imported, and every other `name.<module>` is `ModuleNotFoundError`. A module the alias package
    contains itself is never replaced, whatever `modules` says."""
    real = importlib.import_module(target)
    closed = None if modules is None else tuple(modules)
    finder = _AliasFinder(name, target, closed)
    sys.meta_path[:] = [
        f for f in sys.meta_path if not (isinstance(f, _AliasFinder) and f.alias == name)
    ]
    sys.meta_path.insert(0, finder)
    package = sys.modules.get(name)
    if package is None:
        return

    def getattr_(attribute: str) -> Any:
        value = getattr(real, attribute)
        if isinstance(value, ModuleType) and value.__name__.startswith(target + "."):
            relative = value.__name__.removeprefix(target + ".")
            if not finder._allowed(relative):  # pyright: ignore[reportPrivateUsage]
                raise AttributeError(f"module {name!r} has no attribute {attribute!r}")
        return value

    package.__getattr__ = getattr_  # type: ignore[attr-defined]
    package.__dir__ = lambda: sorted({*vars(package), *dir(real)})  # type: ignore[method-assign]
