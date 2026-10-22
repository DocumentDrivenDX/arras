# SPDX-License-Identifier: MIT OR Apache-2.0
"""The internal dependency rules hold (US-056), and the checker fails a forbidden edge.

This is the project's boundary check for the library's own modules (architecture.md, Module
Boundaries). `arras.boundary` is the other one, for hosts.
"""

from __future__ import annotations

from pathlib import Path

from modules_check import cycles, group_of, sources, too_long, violations

SRC = Path(__file__).resolve().parent.parent / "src"


def test_the_library_keeps_its_module_rules() -> None:
    assert violations(sources(SRC)) == []


def test_every_module_is_in_a_group() -> None:
    assert [m for m in sources(SRC) if group_of(m) is None] == []


def test_core_does_not_reach_a_transport() -> None:
    mods = {"arras.core": "from arras.console import create_app\n", "arras.console": ""}
    assert violations(mods) == ["arras.core:1: core must not import arras.console (console)"]


def test_mcp_does_not_reach_the_dev_host() -> None:
    mods = {"arras.mcp": "from arras.devhost import build\n", "arras.devhost": ""}
    assert violations(mods) == ["arras.mcp:1: mcp must not import arras.devhost (devhost)"]


def test_a_lazy_import_is_still_an_edge() -> None:
    mods = {
        "arras.core": "def f():\n    from arras.mcp import serve\n",
        "arras.mcp": "",
    }
    assert violations(mods) == ["arras.core:2: core must not import arras.mcp (mcp)"]


def test_a_type_checking_import_is_not_an_edge() -> None:
    mods = {
        "arras.gqlschema": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from arras.core import Ontology\n",
        "arras.core": "",
    }
    assert violations(mods) == []


def test_a_cycle_between_modules_is_found() -> None:
    mods = {
        "arras.model": "from arras.actions import A\n",
        "arras.actions": "from arras.model import M\n",
    }
    assert any(v.startswith("cycle: ") for v in violations(mods))
    assert cycles({"a": {"b"}, "b": {"a"}}) == [["a", "b", "a"]]
    assert cycles({"a": {"b"}, "b": set()}) == []


def test_a_module_in_no_group_is_reported() -> None:
    assert violations({"other.thing": ""}) == ["other.thing: belongs to no group"]


# A ceiling at the longest module today (`fakes.py`), never raised: lower it as modules are split.
MAX_MODULE_LINES = 926


def test_no_module_grows_past_the_ceiling() -> None:
    assert too_long(sources(SRC), MAX_MODULE_LINES) == {}


def test_a_module_over_the_ceiling_is_found() -> None:
    assert too_long(
        {"arras.core": "x\n" * (MAX_MODULE_LINES + 1), "arras.names": "x\n"}, MAX_MODULE_LINES
    ) == {"arras.core": MAX_MODULE_LINES + 1}


def test_operate_may_not_reach_another_transport() -> None:
    for other in ("console", "mcp", "devhost"):
        mods = {
            "arras.operate": f"from arras.{other} import x\n",
            f"arras.{other}": "",
        }
        assert violations(mods) == [
            f"arras.operate:1: operate must not import arras.{other} ({other})"
        ]


def test_only_the_dev_host_composes_the_transports() -> None:
    mods = {
        "arras.devhost": "from arras.console import create_app\nfrom arras.operate import create_app as c\n",
        "arras.console": "",
        "arras.operate": "",
    }
    assert violations(mods) == []


def test_the_wheel_carries_the_built_ui_but_not_its_source() -> None:
    """ADR-027: the build output (gitignored, so named as artifacts) rides in both the sdist and the
    wheel, which `uv build` makes from the sdist; the `ui/` source tree does not. The exclusions are
    anchored so they do not also match the `arras.ui` package."""
    import tomllib

    cfg = tomllib.loads((SRC.parent / "pyproject.toml").read_text())
    build = cfg["tool"]["hatch"]["build"]["targets"]
    built = ["src/arras/ui/static/**", "src/arras/ui/npm/*.tgz"]
    assert build["wheel"]["packages"] == ["src/arras"]
    assert build["wheel"]["artifacts"] == built and build["sdist"]["artifacts"] == built
    assert "/ui" in build["sdist"]["exclude"] and "ui" not in build["sdist"]["exclude"]


def test_an_import_in_the_else_of_type_checking_is_an_edge() -> None:
    mods = {
        "arras.core": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    pass\nelse:\n    from arras.console import x\n",
        "arras.console": "",
    }
    assert violations(mods) == ["arras.core:5: core must not import arras.console (console)"]


def test_a_relative_import_is_an_edge() -> None:
    mods = {
        "arras.core": "from .console import create_app\n",
        "arras.console": "",
        "arras.mcp": "from ..core import Arras\n",
        "arras.mcp.config": "from . import identity\n",
        "arras.mcp.identity": "from ..console import x\n",
    }
    assert violations(mods) == [
        "arras.core:1: core must not import arras.console (console)",
        "arras.mcp.identity:1: mcp must not import arras.console (console)",
    ]


def test_only_telemetry_loads_opentelemetry() -> None:
    loaders = [m for m, text in sources(SRC).items() if "opentelemetry" in text]
    assert loaders == ["arras.telemetry"]


def test_arras_defines_no_query_language() -> None:
    """Weft owns the language (CONTRACT-001): no dialect or resolver module, and no library module
    but the memory adapter's own stand-in reads a statement."""
    mods = sources(SRC)
    assert "arras.dialect" not in mods and "arras.queries" not in mods
    readers = {m for m, text in mods.items() if "fakes_weft" in text}
    assert readers <= {"arras.fakes", "arras.fakes_weft"}


# -- the adapters group (ADR-006, ADR-010)
def test_adapters_import_only_the_contract_and_below() -> None:
    fine = {
        "arras.adapters.truss": "from arras.backend import Provider\n",
        "arras.backend": "",
    }
    assert violations(fine) == []
    for target, group in (
        ("arras.core", "core"),
        ("arras.fakes", "doubles"),
        ("arras.conformance", "doubles"),
        ("arras.mcp", "mcp"),
    ):
        mods = {"arras.adapters.truss": f"import {target}\n", target: ""}
        assert violations(mods) == [
            f"arras.adapters.truss:1: adapters must not import {target} ({group})"
        ]


def test_only_a_binding_or_the_dev_host_may_import_an_adapter() -> None:
    for importer, group in (
        ("arras.core", "core"),
        ("arras.fakes", "doubles"),
        ("arras.operate", "operate"),
        ("arras.console", "console"),
        ("arras.ui", "ui"),
        ("arras", "root"),
    ):
        mods = {importer: "from arras.adapters.truss import TrussBackend\n"}
        mods["arras.adapters.truss"] = ""
        assert violations(mods) == [
            f"{importer}:1: {group} must not import arras.adapters.truss (adapters)"
        ]
    for importer in ("arras.mcp", "arras.devhost"):
        mods = {importer: "from arras.adapters.truss import TrussBackend\n"}
        mods["arras.adapters.truss"] = ""
        assert violations(mods) == []


_ENGINE_LIBRARIES = ("truss", "psycopg", "weft")


def _loads_engine_library(text: str) -> bool:
    import ast

    from modules_check import _runtime_imports  # pyright: ignore[reportPrivateUsage]

    return any(
        module.split(".")[0] in _ENGINE_LIBRARIES
        for module, _, _ in _runtime_imports(ast.parse(text), "arras")
    )


def test_only_the_adapters_load_the_engine_libraries() -> None:
    loaders = [m for m, text in sources(SRC).items() if _loads_engine_library(text)]
    assert [m for m in loaders if not m.startswith("arras.adapters")] == []
    assert _loads_engine_library("def f():\n    import psycopg\n")
    assert _loads_engine_library("from truss import Ok\n")
    assert not _loads_engine_library(
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import truss\n"
    )


def test_the_base_import_loads_no_engine_library() -> None:
    import subprocess
    import sys

    code = (
        "import sys, arras, arras.adapters, arras.adapters.truss;"
        " assert not {'truss', 'psycopg', 'weft'} & set(sys.modules), sorted(sys.modules)"
    )
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
