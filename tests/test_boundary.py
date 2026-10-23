# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
from pathlib import Path

import pytest

import arras
from arras.boundary import PUBLIC_MODULE_NAMES, check_host, check_library, main


def write(tmp: Path, name: str, text: str) -> Path:
    p = tmp / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_a_host_using_only_public_names_passes(tmp_path: Path) -> None:
    write(
        tmp_path,
        "host/app.py",
        "from arras import Arras, Principal, Refused\nfrom arras.console import create_app\nimport arras\n",
    )
    assert check_host(tmp_path) == []


def test_a_host_importing_a_name_outside_all_fails(tmp_path: Path) -> None:
    write(tmp_path, "app.py", "from arras import Arras, routing, _private\n")
    found = check_host(tmp_path)
    assert {v.message.split()[0] for v in found} == {"routing", "_private"}
    assert all(v.line == 1 for v in found)


def test_a_host_importing_an_internal_module_fails(tmp_path: Path) -> None:
    write(tmp_path, "a.py", "import arras.fakes\n")
    write(tmp_path, "b.py", "from arras.core import Arras\n")
    write(tmp_path, "c.py", "from arras.console.schema import build_module_schema\n")
    msgs = [v.message for v in check_host(tmp_path)]
    assert len(msgs) == 3 and all("not a public module" in m for m in msgs)


def test_a_host_cannot_import_the_private_catalog_helper(tmp_path: Path) -> None:
    write(tmp_path, "app.py", "from arras._catalogs import collect_catalogs\n")
    assert [v.message for v in check_host(tmp_path)] == [
        "arras._catalogs is not a public module of arras"
    ]


def test_a_star_import_fails_and_other_packages_are_ignored(tmp_path: Path) -> None:
    write(tmp_path, "a.py", "from arras import *\nimport os, json\nfrom sample_host import x\n")
    assert [v.message for v in check_host(tmp_path)] == ["import * from arras hides what is used"]


def test_arras_importing_its_host_fails(tmp_path: Path) -> None:
    write(tmp_path, "lib/mod.py", "import sample_host.workflows\nfrom os import path\n")
    found = check_library(tmp_path, ["sample_host"])
    assert [v.message for v in found] == ["Arras imports the host package sample_host.workflows"]


def test_the_library_does_not_import_any_host() -> None:
    root = Path(arras.__file__).parent
    assert check_library(root, ["sample_host"]) == []


def test_the_exit_status_and_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, "ok.py", "from arras import Arras\n")
    assert main(["--host", str(tmp_path)]) == 0
    write(tmp_path, "bad.py", "from arras.fakes import MemoryStore\n")
    assert main(["--host", str(tmp_path)]) == 1
    assert "bad.py:1" in capsys.readouterr().err


def test_public_names_are_all_real() -> None:
    for module, names in PUBLIC_MODULE_NAMES.items():
        mod = __import__(module, fromlist=["x"])
        for n in names:
            assert hasattr(mod, n), (module, n)


def test_attribute_access_through_an_imported_module_is_checked(tmp_path: Path) -> None:
    write(
        tmp_path,
        "a.py",
        "import arras\narras.core.Ontology\narras.routing.Router\narras.Arras\n",
    )
    write(tmp_path, "b.py", "import arras as h\nh.fakes.MemoryStore\nh.Principal\n")
    write(
        tmp_path,
        "c.py",
        "import arras.console\narras.console.schema.build_module_schema\narras.console.create_app\n",
    )
    write(tmp_path, "d.py", "from arras import console\nconsole.create_app\nconsole.schema\n")
    msgs = sorted(f"{Path(v.path).name}:{v.message}" for v in check_host(tmp_path))
    assert msgs == [
        "a.py:arras.core is not public",
        "a.py:arras.routing is not public",
        "b.py:arras.fakes is not public",
        "c.py:arras.console.schema is not public",
        "d.py:arras.console.schema is not public",
    ]


def test_launcher_subset_accepts_only_the_selected_mcp_symbol(tmp_path: Path) -> None:
    write(tmp_path, "direct.py", "from arras.mcp import launch\n")
    write(tmp_path, "module.py", "import arras.mcp as mcp\nmcp.launch\n")
    write(tmp_path, "root.py", "from arras import mcp\nmcp.launch\n")
    assert check_host(tmp_path) == []

    write(
        tmp_path,
        "exports.py",
        "from arras.mcp import McpServer, TokenSource, principal_from_token, serve\n",
    )
    write(tmp_path, "attribute.py", "import arras.mcp as mcp\nmcp.serve\n")
    write(tmp_path, "server.py", "import arras.mcp.server\n")
    write(tmp_path, "process.py", "import arras.mcp.process\n")
    write(tmp_path, "identity.py", "import arras.mcp.identity\n")
    found = {(Path(v.path).name, v.message) for v in check_host(tmp_path)}
    assert found == {
        ("exports.py", "McpServer is not in arras.mcp's public names"),
        ("exports.py", "TokenSource is not in arras.mcp's public names"),
        ("exports.py", "principal_from_token is not in arras.mcp's public names"),
        ("exports.py", "serve is not in arras.mcp's public names"),
        ("attribute.py", "arras.mcp.serve is not public"),
        ("server.py", "arras.mcp.server is not a public module of arras"),
        ("process.py", "arras.mcp.process is not a public module of arras"),
        ("identity.py", "arras.mcp.identity is not a public module of arras"),
    }


def test_asset_host_surface_excludes_helpers_and_constants(tmp_path: Path) -> None:
    write(
        tmp_path,
        "public.py",
        "from arras.ui.assets import AssetManifest, load_manifest\n",
    )
    assert check_host(tmp_path) == []
    write(tmp_path, "private.py", "from arras.ui.assets import _relpath, MAX_FILES\n")
    assert {v.message for v in check_host(tmp_path)} == {
        "_relpath is not in arras.ui.assets's public names",
        "MAX_FILES is not in arras.ui.assets's public names",
    }


def test_truss_harness_is_public_but_its_implementation_stays_private(tmp_path: Path) -> None:
    write(
        tmp_path,
        "public.py",
        "from arras.conformance.truss import TrussHarness\n",
    )
    assert check_host(tmp_path) == []
    write(tmp_path, "private.py", "import arras.conformance._checks\n")
    write(tmp_path, "private_types.py", "import arras._doctor_types\n")
    write(tmp_path, "adapter_helper.py", "import arras.adapters.truss._conformance\n")
    found = {Path(v.path).name: v.message for v in check_host(tmp_path)}
    assert found == {
        "private.py": "arras.conformance._checks is not a public module of arras",
        "private_types.py": "arras._doctor_types is not a public module of arras",
        "adapter_helper.py": "arras.adapters.truss._conformance is not a public module of arras",
    }
    write(tmp_path, "private_member.py", "from arras.conformance.truss import _open\n")
    assert any(
        "_open is not in arras.conformance.truss's public names" == v.message
        for v in check_host(tmp_path)
    )


def test_a_public_submodule_can_be_imported_as_a_name(tmp_path: Path) -> None:
    write(
        tmp_path,
        "a.py",
        "from arras import console\nfrom arras.console import create_app, Request\n",
    )
    assert check_host(tmp_path) == []
    write(tmp_path, "b.py", "from arras import mcp\nmcp.launch\n")  # launcher-only import
    assert check_host(tmp_path) == []


def test_dynamic_imports_of_internals_are_found(tmp_path: Path) -> None:
    write(
        tmp_path,
        "a.py",
        "import importlib\nimportlib.import_module('arras.fakes')\n__import__('arras.core')\nimportlib.import_module('arras.console')\nimportlib.import_module(name)\n",
    )
    assert sorted(v.message for v in check_host(tmp_path)) == [
        "arras.core is not a public module of arras",
        "arras.fakes is not a public module of arras",
    ]


def test_conditional_and_typing_imports_count(tmp_path: Path) -> None:
    write(
        tmp_path,
        "a.py",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from arras.model import ModuleInfo\ntry:\n    import arras.fakes\nexcept ImportError:\n    pass\n",
    )
    assert len(check_host(tmp_path)) == 2


def test_a_check_of_nothing_is_not_a_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for argv in ([], ["--host", str(tmp_path / "missing")], ["--host", str(tmp_path)]):
        with pytest.raises(SystemExit) as e:
            main(argv)
        assert e.value.code == 2
    write(tmp_path, "ok.py", "x = 1\n")
    assert main(["--host", str(tmp_path)]) == 0
    assert main(["--host-package", "sample_host"]) == 0
    assert (
        main(["--host-package", "arras"]) == 1
    )  # the library imports itself: a host named so fails
    capsys.readouterr()


def test_a_host_under_a_directory_named_like_a_skipped_one_is_still_checked(tmp_path: Path) -> None:
    deep = tmp_path / ".venv" / "proj"
    write(deep, "bad.py", "import arras.fakes\n")
    assert len(check_host(deep)) == 1
