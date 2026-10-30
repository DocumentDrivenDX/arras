# SPDX-License-Identifier: MIT OR Apache-2.0
"""`arras.alias.alias_package`: a thin package under another import name serves `arras` itself.

Each case runs in a fresh interpreter, because the helper installs a `sys.meta_path` finder and
fills `sys.modules`."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

ALIAS = "legacyname"


def _package(
    root: Path, init: str = "from arras.alias import alias_package\nalias_package(__name__)\n"
) -> Path:
    package = root / ALIAS
    package.mkdir()
    (package / "__init__.py").write_text(init)
    return package


def _python(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(root), *sys.path[:0]])}
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, env=env, check=False, timeout=120
    )


def _run(root: Path, code: str) -> subprocess.CompletedProcess[str]:
    return _python(root, "-c", textwrap.dedent(code))


def test_an_aliased_module_is_the_arras_module_and_loaded_once(tmp_path: Path) -> None:
    _package(tmp_path)
    done = _run(
        tmp_path,
        f"""
        import sys
        import {ALIAS}
        import {ALIAS}.model, {ALIAS}.ui.assets, {ALIAS}.conformance.truss
        import arras, arras.model, arras.ui.assets
        assert {ALIAS}.model is arras.model
        assert {ALIAS}.ui.assets is arras.ui.assets
        assert {ALIAS}.Arras is arras.Arras and {ALIAS}.ui is arras.ui
        from {ALIAS}.model import ModuleInfo
        assert ModuleInfo is arras.model.ModuleInfo
        copies = {{}}
        for name, module in list(sys.modules.items()):
            if name.startswith("{ALIAS}."):
                assert module is sys.modules["arras." + name.split(".", 1)[1]], name
            elif name.startswith("arras") and module is not None:
                copies.setdefault(id(module), []).append(name)
        assert all(len(names) == 1 for names in copies.values()), copies
        print("ok")
        """,
    )
    assert done.stdout.strip() == "ok", done.stderr


def test_importlib_resources_works_through_the_alias(tmp_path: Path) -> None:
    _package(tmp_path)
    done = _run(
        tmp_path,
        f"""
        import importlib.resources as r
        import {ALIAS}.conformance
        import arras.conformance
        text = r.files("{ALIAS}.conformance").joinpath("corpus.json").read_text()
        assert text == r.files("arras.conformance").joinpath("corpus.json").read_text()
        assert {ALIAS}.conformance.__spec__.name == "arras.conformance"
        print("ok")
        """,
    )
    assert done.stdout.strip() == "ok", done.stderr


def test_python_m_runs_an_aliased_entry_point(tmp_path: Path) -> None:
    _package(tmp_path)
    done = _python(tmp_path, "-m", f"{ALIAS}.conformance", "--help")
    assert done.returncode == 0 and "conformance corpus" in done.stdout, done.stderr


def test_a_module_the_alias_contains_wins_for_import_and_python_m(tmp_path: Path) -> None:
    package = _package(tmp_path)
    (package / "__main__.py").write_text("print('shim main')\n")
    (package / "ui").mkdir()
    (package / "ui" / "__init__.py").write_text("OWN = True\n")
    done = _python(tmp_path, "-m", ALIAS)
    assert done.stdout.strip() == "shim main", done.stderr
    done = _run(
        tmp_path,
        f"""
        import {ALIAS}.ui, {ALIAS}.model, arras.ui
        assert {ALIAS}.ui.OWN and {ALIAS}.ui is not arras.ui
        assert {ALIAS}.model is __import__("arras.model", fromlist=["x"])
        print("ok")
        """,
    )
    assert done.stdout.strip() == "ok", done.stderr


def test_a_closed_list_serves_only_the_listed_modules(tmp_path: Path) -> None:
    _package(
        tmp_path,
        'from arras.alias import alias_package\nalias_package(__name__, modules=["errors", "ui.assets"])\n',
    )
    done = _run(
        tmp_path,
        f"""
        import {ALIAS}.errors, {ALIAS}.ui.assets, arras.errors, arras.ui.assets
        assert {ALIAS}.errors is arras.errors and {ALIAS}.ui.assets is arras.ui.assets
        for refused in ("model", "ui.__main__", "conformance"):
            try:
                __import__("{ALIAS}." + refused)
            except ModuleNotFoundError:
                continue
            raise SystemExit("imported " + refused)
        assert {ALIAS}.Arras is arras.Arras
        try:
            {ALIAS}.conformance
        except AttributeError:
            print("ok")
        """,
    )
    assert done.stdout.strip() == "ok", done.stderr


def test_a_missing_module_is_not_found_and_a_repeated_call_installs_one_finder(
    tmp_path: Path,
) -> None:
    _package(tmp_path)
    done = _run(
        tmp_path,
        f"""
        import sys
        import {ALIAS}
        from arras.alias import alias_package
        alias_package("{ALIAS}")
        assert sum(type(f).__name__ == "_AliasFinder" for f in sys.meta_path) == 1
        assert type(sys.meta_path[0]).__name__ == "_AliasFinder"
        try:
            import {ALIAS}.no_such_module
        except ModuleNotFoundError as error:
            assert error.name == "{ALIAS}.no_such_module", error.name
            print("ok")
        """,
    )
    assert done.stdout.strip() == "ok", done.stderr


def test_a_borrowed_path_is_not_a_shim_and_nothing_is_loaded_twice(tmp_path: Path) -> None:
    """An alias whose `__path__` is arras's own directory would let the path finder load a
    second copy of each module under the alias's name; the front-of-the-list finder prevents it."""
    _package(
        tmp_path,
        "import arras\nfrom arras.alias import alias_package\n__path__ = list(arras.__path__)\n"
        "alias_package(__name__)\n",
    )
    done = _run(
        tmp_path,
        f"""
        import sys
        import {ALIAS}.model, {ALIAS}.ui.assets, arras.model, arras.ui.assets
        assert {ALIAS}.model is arras.model and {ALIAS}.ui.assets is arras.ui.assets
        assert sys.meta_path.index(next(f for f in sys.meta_path if hasattr(f, "alias"))) == 0
        print("ok")
        """,
    )
    assert done.stdout.strip() == "ok", done.stderr
