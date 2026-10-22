# SPDX-License-Identifier: MIT OR Apache-2.0
"""The reviewed distribution catalog stays aligned with deliberate declarations."""

from __future__ import annotations

import importlib
import inspect
import json
import re
import subprocess
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from importlib import resources
from io import StringIO
from pathlib import Path
from typing import Any, cast, get_args
from unittest.mock import patch

import pytest

import arras
from arras import boundary, conformance, operate, policy, telemetry, ui
from arras.branding import Brand as LeafBrand
from arras.distribution import DistributionConfig
from arras.errors import PolicyRefused
from arras.mcp import launch


def catalog() -> Any:
    return json.loads(resources.files("arras").joinpath("public-api.json").read_text())


def exact(actual: object, expected: object, label: str) -> None:
    assert actual == expected, f"{label}: {actual!r} != {expected!r}"


def resolve_dotted(name: str) -> object:
    parts = name.split(".")
    for end in range(len(parts), 0, -1):
        try:
            obj: object = importlib.import_module(".".join(parts[:end]))
        except ImportError:
            continue
        for part in parts[end:]:
            obj = getattr(obj, part)
        return obj
    raise AssertionError(f"cannot resolve {name}")


def test_manifest_versions_and_public_imports_are_exact() -> None:
    manifest = catalog()
    assert manifest["schema_version"] == 1
    import tomllib

    with (Path(__file__).parents[1] / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    distribution = manifest["distribution"]
    exact(distribution["python_requires"], project["requires-python"], "Python requirement")
    declared_classifiers = sorted(
        classifier.rsplit(" :: ", 1)[-1]
        for classifier in project["classifiers"]
        if classifier.startswith("Programming Language :: Python :: 3.")
    )
    exact(distribution["declared_python"], declared_classifiers, "declared Python classifiers")
    py = manifest["python"]
    exact(py["root_all"], arras.__all__, "root __all__")
    assert py["root_all"] == sorted(arras.__all__, key=lambda n: (not n.isupper(), n))
    declared: dict[str, frozenset[str]] = {}
    for name, spec in cast(dict[str, Any], py["modules"]).items():
        if name not in set(py["host_modules"]) | set(py["launcher_modules"]) | {"arras"}:
            continue
        if name not in set(py["host_modules"]) and name != "arras":
            declared[name] = frozenset()
        else:
            names: object = spec["names"]
            declared[name] = frozenset(
                arras.__all__ if names == "root_all" else cast(list[str], names)
            )
    for module, selected_names in py["launcher_modules"].items():
        declared[module] = declared.get(module, frozenset()) | frozenset(selected_names)
    exact(boundary.PUBLIC_MODULE_NAMES, declared, "boundary modules")
    for module, names in declared.items():
        imported = importlib.import_module(module)
        exact({name for name in names if hasattr(imported, name)}, set(names), f"{module} exports")
    exact(
        set(py["development_modules"]),
        {"arras.devhost", "arras.devtruss", "arras.devcredentials"},
        "development modules",
    )
    exact(set(py["mcp_modules"]), {"arras.mcp"}, "MCP module classification")
    exact(
        set(py["private_modules"]),
        {
            "arras.conformance.__main__",
            "arras._doctor_types",
            "arras.adapters.truss._conformance",
            "arras.conformance._checks",
        },
        "private implementation modules",
    )
    exact(set(py["modules"]["arras.branding"]["names"]), {"Brand", "BRAND_CAPS"}, "brand leaf")
    exact(
        set(py["modules"]["arras.distribution"]["names"]),
        {"DistributionConfig", "TelemetryNames"},
        "distribution config",
    )
    exact(
        set(py["modules"]["arras.mcp"]["names"]),
        {"McpServer", "TokenSource", "principal_from_token", "serve", "launch"},
        "MCP public names",
    )
    exact(
        set(py["modules"]["arras.policy"]["names"]),
        {
            "PolicyBackend",
            "PolicyRequest",
            "PolicyDecision",
            "PolicyOperation",
            "WritePolicy",
            "PolicyAnnotationCapabilities",
            "PolicyAnnotationProvider",
            "PolicyRefused",
        },
        "generic policy public names",
    )
    assert policy.PolicyRefused is PolicyRefused
    brand_export = "Brand"
    assert getattr(ui, brand_export) is LeafBrand and callable(launch)
    assert DistributionConfig().env_prefix == "ARRAS"
    assert LeafBrand().csp() == ui.PAGE_CSP
    assert set(py["modules"]["arras.conformance"]["names"]) == {
        "Harness",
        "Limit",
        "Result",
        "Report",
        "run_corpus",
    }
    assert all(hasattr(conformance, name) for name in py["modules"]["arras.conformance"]["names"])
    assert set(py["modules"]["arras.ui"]["names"]) == {"Brand", "create_app", "npm_package"}
    assert set(py["modules"]["arras.operate"]["names"]) == {
        "create_app",
        "create_schema_app",
        "Request",
        "operators_in_groups",
    }
    assert set(py["modules"]["arras.telemetry"]["names"]) == {"dropped", "TelemetryContext"}
    assert getattr(ui, brand_export) and operate.operators_in_groups and callable(telemetry.dropped)


def test_native_launcher_and_asset_exports_match_the_selected_catalog() -> None:
    py = catalog()["python"]
    truss_conformance = importlib.import_module("arras.conformance.truss")
    exact(
        set(py["modules"]["arras.conformance.truss"]["names"]),
        {"TrussHarness"},
        "native conformance public surface",
    )
    exact(
        py["launcher_modules"],
        {"arras.mcp": ["launch"]},
        "launcher-only MCP imports",
    )
    exact(
        set(py["modules"]["arras.ui.assets"]["names"]),
        {"load_manifest", "AssetManifest"},
        "asset validation public surface",
    )
    exact(
        list(inspect.signature(truss_conformance.TrussHarness).parameters),
        [],
        "TrussHarness constructor parameters",
    )
    lazy_check = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; from arras.conformance.truss import TrussHarness; TrussHarness(); "
            "assert not {'truss', 'psycopg', 'weft'} & set(sys.modules)",
        ],
        capture_output=True,
        text=True,
    )
    assert lazy_check.returncode == 0, lazy_check.stderr


def test_catalog_records_the_packed_ui_acceptance_inventory() -> None:
    manifest = catalog()
    acceptance = manifest["resources"]["ui_acceptance"]
    exact(
        manifest["distribution"]["npm"]["exports"]["./testkit"],
        {"runtime": "dist/testkit.js", "types": "dist/types/testkit/index.d.ts"},
        "testkit package export",
    )
    exact(
        manifest["distribution"]["npm"]["exports"]["./testkit/host"],
        {"runtime": "dist/testkit/host.js", "types": "dist/types/testkit/host.d.ts"},
        "testkit host package export",
    )
    exact(
        manifest["ui"]["npm_runtime_exports"]["./testkit"],
        ["createAcceptanceConfig"],
        "testkit runtime exports",
    )
    exact(
        manifest["ui"]["npm_type_exports"]["./testkit"],
        ["AcceptanceConfigOptions"],
        "testkit type exports",
    )
    exact(
        manifest["ui"]["npm_runtime_exports"]["./testkit/host"],
        ["AcceptanceHost"],
        "testkit host runtime exports",
    )
    exact(
        manifest["ui"]["npm_type_exports"]["./testkit/host"],
        [],
        "testkit host type exports",
    )
    source = (Path(__file__).parents[1] / "ui/src/testkit/inventory.ts").read_text()
    spec_match = re.search(r"CANONICAL_SPECS\s*=\s*\[(.*?)\]\s*as const", source, re.DOTALL)
    assert spec_match is not None
    exact(
        acceptance["specs"],
        re.findall(r'"([^"\n]+)"', spec_match.group(1)),
        "packed acceptance specs",
    )
    count_match = re.search(r"CANONICAL_TEST_COUNTS\s*=\s*\{(.*?)\}\s*as const", source, re.DOTALL)
    assert count_match is not None
    normalized_counts = {
        (quoted or bare): int(count)
        for quoted, bare, count in re.findall(
            r'(?:"([^"]+)"|(\w+))\s*:\s*(\d+)', count_match.group(1)
        )
    }
    exact(acceptance["expected_counts"], normalized_counts, "packed acceptance counts")
    assert acceptance["manifest_path"] == "support/acceptance/resources.json"
    assert acceptance["version"] == 1
    assert re.fullmatch(r"[0-9a-f]{64}", acceptance["manifest_sha256"])
    assert acceptance["file_count"] == 83


def _assert_selected_consumer_imports(tmp_path: Path) -> None:
    source = """from arras import mcp as root_mcp
import arras.mcp as module_mcp
from arras.mcp import launch
from arras.branding import Brand
from arras.distribution import DistributionConfig, TelemetryNames
from arras.devhost import DevHost, main as devhost_main
from arras.doctor import Diagnostic, DoctorReport, DoctorRequest, check
from arras.policy import (
    PolicyAnnotationCapabilities,
    PolicyAnnotationProvider,
    PolicyBackend,
    PolicyDecision,
    PolicyOperation,
    PolicyRefused,
    PolicyRequest,
    WritePolicy,
)
from arras.testing import InMemory
from arras.ui.assets import AssetManifest, load_manifest
from arras.conformance import run_corpus
from arras.conformance.truss import TrussHarness
from arras.telemetry import TelemetryContext
from arras.distribution import TelemetryNames
"""
    (tmp_path / "consumer.py").write_text(source, encoding="utf-8")
    assert boundary.check_host(tmp_path) == []


def _write_synthetic_theme(tmp_path: Path) -> Path:
    import hashlib

    css = b".arras-root { color: rebeccapurple; }"
    (tmp_path / "theme.css").write_bytes(css)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "format": "arras.ui.assets",
                "version": 1,
                "kind": "theme",
                "package": {"name": "test-theme", "version": "1.0.0"},
                "contracts": {"console": 2},
                "entry": {"stylesheet": "theme.css"},
                "files": {
                    "theme.css": {
                        "sha256": hashlib.sha256(css).hexdigest(),
                        "size": len(css),
                        "mime": "text/css",
                    }
                },
                "ui_versions": ["0.5.0"],
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def _exercise_selected_public_calls(tmp_path: Path) -> None:
    from arras import mcp as root_mcp
    from arras.branding import Brand
    from arras.conformance import run_corpus
    from arras.conformance.truss import TrussHarness
    from arras.distribution import DistributionConfig, TelemetryNames
    from arras.doctor import Diagnostic, DoctorReport, DoctorRequest, check
    from arras.mcp import launch
    from arras.policy import (
        PolicyAnnotationCapabilities,
        PolicyAnnotationProvider,
        PolicyOperation,
        WritePolicy,
    )
    from arras.telemetry import TelemetryContext
    from arras.testing import InMemory
    from arras.ui.assets import AssetManifest, load_manifest

    assert callable(launch) and root_mcp.launch is launch
    distribution = DistributionConfig(
        brand=Brand(name="Example"),
        mcp_server_name="example",
        mcp_tool_prefix="ex",
        env_prefix="EXAMPLE",
        telemetry=TelemetryNames(log_prefix="example"),
    )
    telemetry_context = TelemetryContext(distribution.telemetry)
    with telemetry_context.activate():
        assert telemetry_context.names == distribution.telemetry

    import asyncio

    calls: list[bool] = []

    async def inert_asgi(_scope: Any, _receive: Any, _send: Any) -> None:
        calls.append(telemetry_context.names == distribution.telemetry)

    async def exercise_asgi() -> None:
        async def empty(_scope: Any) -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def discard(_message: Any) -> None:
            return None

        await telemetry_context.wrap_asgi(inert_asgi)({"type": "http"}, empty, discard)

    asyncio.run(exercise_asgi())
    assert calls == [True]
    assert isinstance(check(DoctorRequest(distribution=distribution)), DoctorReport)
    world = InMemory()
    diagnostic = Diagnostic("selected", "info", "distribution", "brand", "Example selected")
    assert diagnostic.code == "selected"
    capabilities = PolicyAnnotationCapabilities(operations=frozenset({"import_records"}))
    assert capabilities.version == 1 and capabilities.operations == frozenset({"import_records"})
    assert "import_records" in get_args(PolicyOperation)
    assert callable(WritePolicy) and callable(PolicyAnnotationProvider)

    _assert_denied_policy_import(world)
    _assert_custom_launcher_help(distribution)
    asset = load_manifest(_write_synthetic_theme(tmp_path), kind="theme")
    assert isinstance(asset, AssetManifest) and asset.entry["stylesheet"] == "theme.css"
    assert isinstance(TrussHarness(), TrussHarness)
    report = run_corpus(TrussHarness, only=[])
    assert report.results == [] and report.skipped


def _assert_denied_policy_import(world: Any) -> None:
    from arras.errors import PolicyRefused
    from arras.policy import PolicyBackend, PolicyDecision, PolicyRequest

    seen: list[PolicyRequest] = []

    def deny(request: PolicyRequest) -> PolicyDecision:
        seen.append(request)
        return PolicyDecision(False, code="example_policy")

    backend = world.backends["memory"]
    guarded = PolicyBackend(backend, deny)
    with patch.object(backend, "import_records", wraps=backend.import_records) as provider_import:
        with pytest.raises(PolicyRefused) as refusal:
            guarded.import_records(
                world.admin,
                "catalog",
                [],
                load_id="selected-consumer-smoke",
                initiated_by="selected-consumer-smoke",
            )
        provider_import.assert_not_called()
    assert len(seen) == 1 and isinstance(seen[0], PolicyRequest)
    assert seen[0].operation == "import_records" and seen[0].modules == ("catalog",)
    assert refusal.value.reason == "no_access"
    assert refusal.value.policy_code == "example_policy"


def _assert_custom_launcher_help(distribution: Any) -> None:
    from arras.devhost import main as devhost_main
    from arras.mcp import launch

    for invoke in (
        lambda: launch(["--help"], distribution=distribution),
        lambda: devhost_main(["--help"], distribution=distribution),
    ):
        output = StringIO()
        with redirect_stdout(output), pytest.raises(SystemExit) as help_exit:
            invoke()
        assert help_exit.value.code == 0
        assert "Example" in output.getvalue()


def test_selected_host_seams_import_and_make_inert_public_calls(tmp_path: Path) -> None:
    _assert_selected_consumer_imports(tmp_path)
    _exercise_selected_public_calls(tmp_path)


def test_private_telemetry_emitters_and_logger_are_not_host_api(tmp_path: Path) -> None:
    from arras import boundary

    source = tmp_path / "private_telemetry.py"
    source.write_text(
        "from arras.telemetry import operation, _logger, _make_context, Operation\n",
        encoding="utf-8",
    )
    rejected = [row.message for row in boundary.check_host(tmp_path)]
    assert len(rejected) == 4
    assert {message.split(" ")[0] for message in rejected} == {
        "operation",
        "_logger",
        "_make_context",
        "Operation",
    }
    assert all("arras.telemetry" in message for message in rejected)


def test_contract_map_is_explicit_and_matches_runtime_keys() -> None:
    manifest = catalog()
    contracts = manifest["contracts"]
    expected = {
        "CONTRACT-001": ("interface", 2),
        "CONTRACT-002": (None, 1),
        "CONTRACT-003": ("actions", 1),
        "CONTRACT-004": ("backend", 5),
        "CONTRACT-005": ("lifecycle", 2),
        "CONTRACT-006": ("console", 2),
        "CONTRACT-007": ("mcp", 2),
        "CONTRACT-008": (None, 1),
        "CONTRACT-009": ("operate", 2),
        "CONTRACT-010": ("browser", 1),
        "CONTRACT-011": ("schema", 1),
    }
    exact(
        {key: (item["runtime_key"], item["version"]) for key, item in contracts.items()},
        expected,
        "contract map",
    )
    exact(
        {v["runtime_key"]: v["version"] for v in contracts.values() if v["runtime_key"]},
        arras.CONTRACT_VERSIONS,
        "runtime contract keys",
    )
    for contract_id, item in contracts.items():
        path = Path(__file__).parents[1] / "docs/helix/02-design/contracts" / f"{contract_id}-*.md"
        matches = list(path.parent.glob(path.name))
        assert len(matches) == 1
        text = matches[0].read_text()
        version = re.search(r"\*\*Version\*\*: v(\d+)", text)
        assert version and int(version.group(1)) == item["version"], contract_id


def test_callable_parameters_and_published_ui_contracts_stay_in_sync() -> None:
    manifest = catalog()
    for dotted, expected in manifest["python"]["callables"].items():
        sig = inspect.signature(cast(Any, resolve_dotted(dotted)))
        rows = expected["parameters"]
        assert [p.name for p in sig.parameters.values()] == [p["name"] for p in rows]
        assert [p.kind.name for p in sig.parameters.values()] == [p["kind"] for p in rows]
        for p, declared in zip(sig.parameters.values(), rows, strict=True):
            if "default" not in declared:
                assert p.default is inspect.Parameter.empty
            elif declared["default"] == "default Brand":
                assert p.default is not inspect.Parameter.empty
            elif declared["default"] == "package static directory":
                assert p.default == ui.STATIC
            elif declared["default"] == "empty tuple":
                assert p.default == ()
            elif declared["default"] == "TelemetryNames()":
                from arras.distribution import TelemetryNames

                assert p.default == TelemetryNames()
            elif declared["default"] == "default UI directory":
                from arras.devhost import DEFAULT_UI

                assert p.default == DEFAULT_UI
            elif declared["default"] in {
                "configured wait bound",
                "default sleeper",
                "monotonic clock",
            }:
                assert p.default is not inspect.Parameter.empty
            else:
                assert p.default == declared["default"]
    telemetry_module = __import__("arras.telemetry", fromlist=["EVENTS"])
    exact(set(manifest["telemetry"]["events"]), set(telemetry_module.EVENTS), "telemetry events")
    exact(
        set(manifest["telemetry"]["attributes"]),
        set(telemetry_module.ATTRIBUTES),
        "telemetry attributes",
    )
    expected_exported = {
        "error.type" if n == "error.type" else "arras." + n for n in telemetry_module.ATTRIBUTES
    }
    exact(
        set(manifest["telemetry"]["attribute_export_names"]),
        expected_exported,
        "exported telemetry attribute names",
    )
    exact(
        manifest["telemetry"]["identities"],
        {"logger": "arras.telemetry", "tracer": "arras"},
        "telemetry identities",
    )
    ts = Path(__file__).parents[1] / "ui/src/ds/contract.ts"
    source_tokens = __import__("re").findall(r'"(--arras-[a-z-]+)"', ts.read_text())
    assert manifest["ui"]["role_tokens"] == source_tokens


def test_configuration_cli_and_resource_inventory_are_declared_separately() -> None:
    manifest = catalog()
    telemetry_module = importlib.import_module("arras.telemetry")
    cfg = __import__("arras.mcp.config", fromlist=["KEYS"])
    exact(
        manifest["host_configuration"]["environment"]["keys"],
        [key.name for key in cfg.KEYS],
        "MCP env keys",
    )
    exact(set(manifest["host_configuration"]["files"]["keys"]), cfg.FILE_KEYS, "TOML keys")
    exact(
        manifest["host_configuration"]["environment"]["pattern"],
        {"key": "ARRAS_BACKEND_<NAME>_ENDPOINT", "regex": cfg.ENDPOINT_KEY.pattern, "owner": "ops"},
        "endpoint environment pattern",
    )
    exact(
        set(manifest["host_configuration"]["files"]["placement_keys"]),
        cfg.PLACEMENT_FILE_KEYS,
        "placement keys",
    )
    exact(set(manifest["host_configuration"]["files"]["ops_keys"]), cfg.OPS_FILE_KEYS, "ops keys")
    exact(
        manifest["host_configuration"]["environment"]["ignored_prefixes"],
        list(cfg.IGNORED_PREFIXES),
        "ignored environment prefixes",
    )
    owners = {
        key.owner: sorted(k.name for k in cfg.KEYS if k.owner == key.owner) for key in cfg.KEYS
    }
    declared_owners = manifest["host_configuration"]["ownership"]
    exact(
        set(declared_owners["ops"]),
        set(owners["ops"]) | {"ARRAS_BACKEND_<NAME>_ENDPOINT"},
        "ops environment ownership",
    )
    exact(set(declared_owners["dev"]), set(owners["dev"]), "developer environment ownership")
    devhost = importlib.import_module("arras.devhost")
    exact(
        manifest["host_configuration"]["development_environment"]["keys"],
        [devhost.TRUSS_URL_VARIABLE, devhost.TRUSS_CREDENTIALS_VARIABLE],
        "development host environment keys",
    )
    exact(manifest["ui"]["root_class"], ".arras-root", "CSS root class")
    assert ".arras-root" in (Path(__file__).parents[1] / "ui/src/styles.css").read_text()
    exact(
        manifest["telemetry"]["privacy"]["value_limit_characters"],
        telemetry_module.MAX_VALUE_LENGTH,
        "telemetry value cap",
    )
    exact(
        set(manifest["host_configuration"]["files"]["ownership"]["dev"]),
        set(cfg.FILE_KEYS),
        "developer file ownership",
    )
    exact(
        set(manifest["host_configuration"]["files"]["ownership"]["ops"]),
        {"backends.<name>.endpoint"},
        "ops file ownership",
    )
    assert (
        manifest["resources"]["conformance_corpus_version"] == conformance.load_corpus()["version"]
    )
    assert manifest["resources"]["vocabularies"] == [
        {"name": "arras.view", "version": __import__("arras.view", fromlist=["VERSION"]).VERSION}
    ]
    exact(
        manifest["commands"]["python -m arras.devhost"],
        [
            option
            for action in devhost._parser()._actions
            for option in action.option_strings
            if option != "-h" and option != "--help"
        ],
        "devhost CLI options",
    )
    command_controls: tuple[tuple[str, set[str]], ...] = (
        ("python -m arras.ui", {"npm-package", "--copy"}),
        ("python -m arras.boundary", {"--host", "--library", "--host-package"}),
        ("python -m arras.mcp", {"-h", "--help"}),
        ("python -m arras.conformance", {"--backend"}),
    )
    for command, expected_options in command_controls:
        if command == "python -m arras.ui":
            output = subprocess.run(
                [sys.executable, "-m", "arras.ui", "npm-package", "--help"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            found = {"npm-package"} | (set(re.findall(r"--[a-z-]+", output)) - {"--help"})
        elif command == "python -m arras.boundary":
            output = subprocess.run(
                [sys.executable, "-m", "arras.boundary", "--help"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            found = set(re.findall(r"--[a-z-]+", output)) - {"--help"}
        elif command == "python -m arras.mcp":
            output = subprocess.run(
                [sys.executable, "-m", "arras.mcp", "--help"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            found = set(re.findall(r"(?:-h|--help)", output))
        else:
            output = subprocess.run(
                [sys.executable, "-m", "arras.conformance", "--help"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            found = set(re.findall(r"--[a-z-]+", output)) - {"--help"}
            assert "memory-store" in output and "memory-replica" in output and "truss" in output
        exact(set(manifest["commands"][command]), expected_options, f"{command} declaration")
        exact(found, expected_options, f"{command} parser")
    assert Path(arras.__file__).with_name("py.typed").is_file()


def test_catalog_mutations_are_rejected_by_the_wired_parity_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import copy

    original_catalog = catalog
    controls: list[tuple[Callable[[], None], Callable[[Any], Any]]] = [
        (
            test_manifest_versions_and_public_imports_are_exact,
            lambda m: m["python"]["root_all"].pop(),
        ),
        (
            test_manifest_versions_and_public_imports_are_exact,
            lambda m: m["python"]["modules"]["arras.conformance.truss"]["names"].append(
                "load_corpus"
            ),
        ),
        (
            test_manifest_versions_and_public_imports_are_exact,
            lambda m: m["python"]["private_modules"].remove("arras.conformance._checks"),
        ),
        (
            test_manifest_versions_and_public_imports_are_exact,
            lambda m: m["python"]["launcher_modules"]["arras.mcp"].append("serve"),
        ),
        (
            test_manifest_versions_and_public_imports_are_exact,
            lambda m: m["python"]["launcher_modules"]["arras.mcp"].clear(),
        ),
        (
            test_manifest_versions_and_public_imports_are_exact,
            lambda m: m["python"]["modules"]["arras.ui.assets"]["names"].append("_relpath"),
        ),
        (
            test_configuration_cli_and_resource_inventory_are_declared_separately,
            lambda m: m["commands"]["python -m arras.devhost"].append("--invented"),
        ),
        (
            test_configuration_cli_and_resource_inventory_are_declared_separately,
            lambda m: m["host_configuration"]["environment"]["keys"].pop(),
        ),
        (
            test_callable_parameters_and_published_ui_contracts_stay_in_sync,
            lambda m: m["ui"]["role_tokens"].pop(),
        ),
        (
            test_callable_parameters_and_published_ui_contracts_stay_in_sync,
            lambda m: m["telemetry"]["events"].pop(),
        ),
        (
            test_contract_map_is_explicit_and_matches_runtime_keys,
            lambda m: m["contracts"]["CONTRACT-001"].update(version=1),
        ),
    ]
    for parity_check, mutate in controls:
        candidate: Any = copy.deepcopy(original_catalog())
        mutate(candidate)
        monkeypatch.setattr(sys.modules[__name__], "catalog", lambda candidate=candidate: candidate)
        with pytest.raises((AssertionError, KeyError, TypeError)):
            parity_check()
        monkeypatch.setattr(sys.modules[__name__], "catalog", original_catalog)
