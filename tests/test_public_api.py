# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic, reportArgumentType=false
import inspect
import json
from dataclasses import replace
from pathlib import Path

import pytest

import arras
from arras import Arras, Invalid, Placement
from arras.compat import check
from arras.sandbox import Sandbox, catalog_document
from arras.umf import parse_module


def test_all_names_exist_and_are_public() -> None:
    for name in arras.__all__:
        assert hasattr(arras, name), name
        assert name == "CONTRACT_VERSIONS" or not name.startswith("_")
    assert len(arras.__all__) == len(set(arras.__all__))
    assert arras.__all__ == sorted(arras.__all__, key=lambda n: (not n.isupper(), n))


def test_a_host_can_catch_and_type_every_outcome() -> None:
    needed = {
        "Refused",
        "Unavailable",
        "Invalid",
        "Unsupported",
        "NotYetCurrent",
        "Conflict",
        "PreconditionFailed",
        "Receipt",
        "BatchReceipt",
        "Validation",
        "ImportResult",
        "RegistryResult",
        "Registry",
        "Status",
        "BackendStatus",
        "ModuleInfo",
        "Capabilities",
        "Principal",
        "Rows",
        "Freshness",
        "Consistency",
        "Arras",
        "Ontology",
    }
    assert needed <= set(arras.__all__)


def test_contract_versions_name_every_contract() -> None:
    assert set(arras.CONTRACT_VERSIONS) == {
        "interface",
        "actions",
        "backend",
        "lifecycle",
        "console",
        "operate",
        "schema",
        "mcp",
        "browser",
    }
    assert all(isinstance(v, int) and v >= 1 for v in arras.CONTRACT_VERSIONS.values())
    assert arras.CONTRACT_VERSIONS["interface"] == 2
    assert arras.CONTRACT_VERSIONS["actions"] == 2
    assert arras.CONTRACT_VERSIONS["backend"] == 6
    assert arras.CONTRACT_VERSIONS["lifecycle"] == 3


def test_the_lifecycle_surface_is_migrate_with_a_timeout_and_the_role_names() -> None:
    """CONTRACT-005 v3: `migrate(*, timeout)` reports the install's owner and registrar roles."""
    import dataclasses
    import inspect

    assert arras.CONTRACT_VERSIONS["lifecycle"] == 3
    timeout = inspect.signature(arras.Arras.migrate).parameters["timeout"]
    assert timeout.kind is inspect.Parameter.KEYWORD_ONLY and timeout.default is None
    assert [f.name for f in dataclasses.fields(arras.MigrationResult)] == [
        "ran",
        "revision",
        "owner_role",
        "registrar_role",
    ]
    assert arras.MigrationResult(False, "r").owner_role is None


def test_the_backend_port_carries_a_weft_statement() -> None:
    """CONTRACT-004 v6: `query` takes the module and a `Statement`, Arras reads neither, and
    `describe` names the Weft version and profiles a backend hosts."""
    from arras.backend import Backend

    assert arras.CONTRACT_VERSIONS["backend"] == 6  # + declared metadata-profile support
    assert arras.CONTRACT_VERSIONS["operate"] == 2  # POST /query names its module, no cursor
    assert arras.CONTRACT_VERSIONS["interface"] == 2  # query names its module, returns no cursor
    assert arras.CONTRACT_VERSIONS["mcp"] == 2  # the query tool requires module, takes no after
    assert arras.CONTRACT_VERSIONS["console"] == 2  # lists take no after, pages no nextCursor
    import inspect

    from arras.core import Ontology

    params = list(inspect.signature(Ontology.query).parameters)
    assert params[:4] == ["self", "module", "sql", "params"] and "after" not in params
    assert "next_cursor" not in {f.name for f in __import__("dataclasses").fields(arras.Rows)}
    s = arras.Statement(
        "SELECT u.code FROM catalog.UseCase u WHERE u.code = :k ORDER BY u.code LIMIT 100",
        {"k": "a"},
    )
    assert (s.sql, dict(s.params)) == (s.sql, {"k": "a"})
    assert (
        dict(
            arras.Statement("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100").params
        )
        == {}
    )
    w = arras.WeftSupport("weft-sql/0.2.0", ("count-summary",))
    assert (w.version, w.profiles) == ("weft-sql/0.2.0", ("count-summary",))
    from arras.results import BackendInfo

    assert BackendInfo("b", ("reader",)).audit is True  # a journal is the default claim
    assert BackendInfo("b", ("reader",)).weft is None  # a backend that hosts no Weft names none
    assert "query" in dir(Backend) and "reads" not in dir(Backend)  # Arras never reads it


def test_the_package_is_typed() -> None:
    assert (Path(arras.__file__).parent / "py.typed").exists()


def test_metadata_profiles_are_final_defaulted_host_metadata_fields() -> None:
    import dataclasses
    import inspect

    module_fields = dataclasses.fields(arras.ModuleInfo)
    assert module_fields[-1].name == "metadata_profile"
    assert module_fields[-1].default == "legacy-arras/1"
    assert arras.ModuleInfo(
        "m", arras.Placement("store"), arras.Revision(), ()
    ).metadata_profile == ("legacy-arras/1")

    from arras.results import BackendInfo

    backend_fields = dataclasses.fields(BackendInfo)
    assert backend_fields[-2].name == "metadata_profiles"
    assert backend_fields[-2].default == ("legacy-arras/1",)
    assert backend_fields[-1].name == "action_profiles"
    assert backend_fields[-1].default == ()
    assert BackendInfo("store", ("reader",)).metadata_profiles == ("legacy-arras/1",)
    assert BackendInfo("store", ("reader",)).action_profiles == ()
    for method in (arras.Arras.__init__, arras.Arras.start):
        parameter = inspect.signature(method).parameters["metadata_profile"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default == "legacy-arras/1"


def test_the_bindings_use_only_the_public_surface_for_the_host_facing_types() -> None:
    from arras.console import create_app
    from arras.mcp import McpServer

    for fn in (create_app, McpServer.__init__):
        for p in inspect.signature(fn).parameters.values():
            assert "_private" not in str(p.annotation)


def test_an_expected_backend_that_was_not_supplied_is_not_configured() -> None:
    h = Arras.start({}, expected=("primary", "mirror"))
    s = h.status()
    assert {n: (x.available, x.reason) for n, x in s.items()} == {
        "primary": (False, "not_configured"),
        "mirror": (False, "not_configured"),
    }
    box = Sandbox()
    h = Arras.start({"primary": box.store}, expected=("primary", "mirror"))
    s = h.status()
    assert s["primary"].available and s["mirror"].reason == "not_configured"


def test_an_import_is_always_its_callers_own() -> None:
    assert "initiated_by" not in inspect.signature(arras.Ontology.import_records).parameters


def test_removing_a_type_an_action_names_is_refused() -> None:
    old = parse_module(catalog_document())
    new = replace(
        old,
        entity_types=tuple(t for t in old.entity_types if t.local_name != "UseCase"),
        relationships=(),
        actions=(),
    )

    class Stats:
        def count(self, t: str) -> int:
            return 0

        def missing(self, t: str, p: str) -> list[str]:
            return []

    with pytest.raises(Invalid) as e:
        check(old, new, Stats())
    assert any("action" in v.message for v in e.value.violations)
    only_actions = replace(new, actions=old.actions)
    with pytest.raises(Invalid):  # the actions still name it
        check(old, only_actions, Stats())


def test_attach_checks_the_module_can_be_served() -> None:
    import arras.gqlschema as schema

    box = Sandbox()
    h = Arras.start(
        box.backends, admin=box.people["root"], placement={"catalog": Placement("memory_replica")}
    )
    o = h.session(box.people["root"])
    d = json.loads(catalog_document())
    d["modules"][0]["actions"] = []
    original = schema.build_module_schema
    seen: list[str] = []
    schema.build_module_schema = lambda mod: seen.append(mod.name) or original(mod)
    try:
        o.registry().attach(json.dumps(d))
    finally:
        schema.build_module_schema = original
    assert seen == ["catalog"]


def test_only_the_mcp_binding_and_the_dev_hosts_entry_point_read_the_environment() -> None:
    """The library takes parameters. `mcp/config.py` is the one binding that reads the environment
    for a deployed process; the development entry point reads `ARRAS_TRUSS_DEV_URL` and
    `ARRAS_TRUSS_DEV_CREDENTIALS` only while composing persistent Truss in `python -m arras.devhost`,
    a tool no host imports (`devhost.truss_url` takes the mapping as a parameter)."""
    import ast

    root = Path(arras.__file__).parent
    names = {"environ", "environb", "getenv", "putenv", "unsetenv"}
    readers: set[str] = set()
    for p in root.rglob("*.py"):
        tree = ast.parse(p.read_text())
        os_aliases = {
            a.asname or a.name
            for n in ast.walk(tree)
            if isinstance(n, ast.Import)
            for a in n.names
            if a.name == "os"
        }
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.ImportFrom)
                and n.module == "os"
                and any(a.name in names for a in n.names)
            ):
                readers.add(p.relative_to(root).as_posix())
            elif (
                isinstance(n, ast.Attribute)
                and n.attr in names
                and isinstance(n.value, ast.Name)
                and n.value.id in os_aliases
            ):
                readers.add(p.relative_to(root).as_posix())
            elif (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "getattr"
                and len(n.args) > 1
                and isinstance(n.args[1], ast.Constant)
                and n.args[1].value in names
            ):
                readers.add(p.relative_to(root).as_posix())
    assert readers == {"mcp/config.py", "devhost.py"}, readers


def test_only_the_mcp_binding_reads_configuration_files() -> None:
    """The library takes parameters (CONTRACT-005): of the package, only the config schema parses a
    TOML file, so layer files and the environment have one reader between them."""
    import ast

    root = Path(arras.__file__).parent
    readers: set[str] = set()
    for p in root.rglob("*.py"):
        for n in ast.walk(ast.parse(p.read_text())):
            if (isinstance(n, ast.Import) and any(a.name == "tomllib" for a in n.names)) or (
                isinstance(n, ast.ImportFrom) and n.module == "tomllib"
            ):
                readers.add(p.relative_to(root).as_posix())
    assert readers == {"mcp/config.py"}, readers
