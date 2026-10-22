# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
import inspect
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

from arras.conformance import load_corpus
from arras.conformance.truss import TrussHarness
from arras.errors import Refused
from arras.types import Principal


def test_native_harness_is_lazy_and_has_no_persistent_configuration() -> None:
    harness = TrussHarness()
    assert harness.roles == ("reader", "provider")
    assert harness.corpus_version == 13
    assert harness._owned == []
    assert "url" not in inspect.signature(TrussHarness).parameters
    assert "credential_source" not in inspect.signature(TrussHarness).parameters
    assert "directory" not in inspect.signature(TrussHarness).parameters
    harness.close()
    harness.close()
    assert harness._owned == []


def test_importing_helper_does_not_import_native_runtime() -> None:
    # A subprocess gives this check an uncontaminated import table even when the full suite has
    # already exercised PostgreSQL.
    import subprocess

    code = """
import sys
class BlockNative:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'psycopg' or fullname == 'truss' or fullname.startswith('truss.'):
            raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, BlockNative())
import arras.conformance.truss
from arras.conformance.truss import TrussHarness
h = TrussHarness()
assert h._owned == []
h.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_admin_flag_does_not_create_schema_membership(monkeypatch: Any) -> None:
    harness = TrussHarness()
    memberships: list[tuple[str, str, bool]] = []

    class Local:
        def person(self, user: str) -> Principal:
            return Principal(user, "token")

        @staticmethod
        def reader_role(module: str) -> str:
            return f"{module}_reader"

        @staticmethod
        def writer_role(module: str) -> str:
            return f"{module}_writer"

        @staticmethod
        def auditor_role(module: str) -> str:
            return f"{module}_auditor"

        registrar_role = "registrar"

        def membership(self, user: str, role: str, *, grant: bool) -> None:
            memberships.append((user, role, grant))

    local = Local()
    harness._local = local
    harness._module = cast(Any, SimpleNamespace(name="catalog"))
    monkeypatch.setattr(harness, "_open", lambda: local)
    harness.grant("admin_without_schema", {"catalog": ["write"]}, admin=True)

    assert memberships == [("admin_without_schema", "catalog_writer", True)]
    assert harness.principal("admin_without_schema").admin is True


def test_partial_local_open_is_still_owned_and_closed(monkeypatch: Any) -> None:
    closed: list[bool] = []

    class PartialLocal:
        def __init__(self, _: str) -> None:
            pass

        def open(self) -> None:
            raise ModuleNotFoundError("native dependency unavailable")

        def close(self) -> None:
            closed.append(True)

    module = ModuleType("arras.adapters.truss.local")
    cast(Any, module).LocalTruss = PartialLocal
    monkeypatch.setitem(sys.modules, module.__name__, module)
    harness = TrussHarness()
    with pytest.raises(ModuleNotFoundError):
        harness._open()
    assert len(harness._owned) == 1
    harness.close()
    assert closed == [True]


def test_native_harness_backend_name_is_accepted_by_real_factory() -> None:
    from arras.adapters.truss import create_backend

    backend = create_backend("truss_conformance", None)
    assert backend.name == "truss_conformance"


def test_install_marker_simulation_refuses_persistent_resources_before_psycopg_import(
    monkeypatch: Any,
) -> None:
    import builtins

    from arras.adapters.truss._conformance import tamper_install_marker

    original_import = builtins.__import__

    def import_without_psycopg(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "psycopg":
            raise AssertionError("persistent marker refusal must precede driver import")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_psycopg)
    persistent = cast(Any, SimpleNamespace(persistent=True))
    with pytest.raises(RuntimeError, match="owned throwaway database"):
        tamper_install_marker(persistent, None, restore=False)


@pytest.mark.truss
def test_owned_harness_registers_and_issues_a_real_foreign_receipt() -> None:
    from arras.umf import parse_module
    from test_truss_harness import _require

    _require()
    corpus = load_corpus()
    document = corpus["_module_text"].encode()
    module = parse_module(document)
    harness = TrussHarness()
    try:
        harness.install(module, document)
        token = harness.foreign_token()
        assert token
        harness.grant("no_schema_admin", {module.name: ["write"]}, admin=True)
        with pytest.raises(Refused):
            harness.backend().register(
                harness.principal("no_schema_admin"),
                document,
                module,
                unknown_endpoint="reject",
            )
    finally:
        harness.close()
