#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Validate and project the installed generated-action qualification receipt."""

from __future__ import annotations

import email.parser
import hashlib
import importlib.util
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, NoReturn

SCHEMA = "arras.umf-actions-installed/1"
PUBLIC_SCHEMA = "arras.umf-actions-public-qualification/1"
SCOPE = (
    "exact installed Arras wheel, official UMF core 0.10.0 single-SET admission and generated "
    "Apply/Validate over the arras-umf-set/1 in-memory profile; 139 reference and 139 "
    "fresh-empty-registry cases; no Truss, replica, durable replay, or wider action/constraint claim"
)
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_PYTHON = re.compile(r"3\.11\.[0-9]+\Z")
_CONTROLS = {
    "arras_payload_record_parity",
    "umf_payload_record_parity",
    "imports_from_fresh_environment",
    "generated_client_apply_validate_vectors",
    "public_registration_and_import",
    "validate_has_no_public_state_change",
    "apply_and_read_at_least",
    "allowed_value_rejected_without_effect",
    "no_op_and_replay_stable",
    "current_access_denial_without_effect",
    "uncertain_response_not_retried",
    "corpus_reference_and_empty_registry_139",
}
_FIXTURES = {
    "source.json": "5b79b3dba5ebc52ac9452f85a75411dab5edaa34154adda76f872a53c21d0818",
    "vectors.json": "c811eefac81c4f5ff3a7aa60cbe7f7657f7599040cd0869b2616c450931a950e",
    "current-conformance.json": "bb008a98b8448050748e65f867e7863475ccad9501a5b9229ae9e6d336691544",
}
_RUNTIME = {
    "platforms": {"darwin": "arm64", "linux": "x86_64"},
    "machines": {"arm64", "x86_64", "aarch64", "AMD64"},
}


class ActionReceiptError(ValueError):
    """An action receipt failed a closed release-evidence check."""


def _fail(message: str) -> NoReturn:
    raise ActionReceiptError(message)


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    return value


def _exact(value: object, keys: set[str], label: str) -> dict[str, Any]:
    result = _object(value, label)
    if set(result) != keys:
        _fail(f"{label} has an unexpected shape")
    return result


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        _fail(f"{label} is not a lowercase SHA-256")
    return value


def _cohorts(repository: Path) -> Any:
    name = "arras_release_umf_sdk_cohorts"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = repository / "tools/_umf_sdk_cohorts.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        _fail("verified UMF cohort selector is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _wheel_metadata(path: Path, *, name: str, sha256: str) -> tuple[dict[str, Any], str]:
    if (
        not path.is_file()
        or path.is_symlink()
        or hashlib.sha256(path.read_bytes()).hexdigest() != sha256
    ):
        _fail("selected Arras wheel identity differs")
    try:
        with zipfile.ZipFile(path) as archive:
            metadata_files = [
                item for item in archive.infolist() if item.filename.endswith(".dist-info/METADATA")
            ]
            if len(metadata_files) != 1:
                _fail("selected wheel metadata inventory is invalid")
            metadata = email.parser.Parser().parsestr(
                archive.read(metadata_files[0]).decode("utf-8")
            )
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, RuntimeError) as error:
        raise ActionReceiptError("selected wheel metadata is invalid") from error
    if metadata.get("Name", "").lower().replace("_", "-") != name:
        _fail("selected wheel distribution differs")
    version = metadata.get("Version", "")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        _fail("selected wheel version is invalid")
    return metadata, version


def required_for_wheel(path: Path, *, wheel_sha256: str) -> bool:
    """Derive the release gate from every verified SDK declaration in the built wheel."""
    metadata, version = _wheel_metadata(path, name="arras", sha256=wheel_sha256)
    declarations = metadata.get_all("Requires-Dist", [])
    has_umf_declaration = any(_is_umf_declaration(item) for item in declarations)
    if not has_umf_declaration:
        admission = _admission_receipt_module()
        if not admission.required_for_version(version):
            return False
        _fail("release wheel omits its required UMF SDK declaration")
    try:
        return _cohorts(Path(__file__).resolve().parents[2]).single_set_capability(metadata)
    except ValueError as error:
        raise ActionReceiptError(
            "Arras wheel SDK capability declarations are not verified"
        ) from error


def _is_umf_declaration(value: str) -> bool:
    match = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", value)
    return match is not None and re.sub(r"[-_.]+", "-", match.group(1)).lower() == "umf-core"


def _admission_receipt_module() -> Any:
    name = "arras_release_umf_admission_receipt"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = Path(__file__).with_name("_umf_admission_receipt.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        _fail("UMF admission compatibility rule is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _selected_cohort(metadata: Any, runtime: dict[str, Any], repository: Path) -> Any:
    platform_name = runtime["platform"]
    machine = runtime["machine"]
    normalized_machine = {"aarch64": "arm64", "AMD64": "x86_64"}.get(machine, machine)
    if _RUNTIME["platforms"].get(platform_name) != normalized_machine:
        _fail("action receipt runtime platform is unsupported")
    selector = _cohorts(repository)
    try:
        action_capable = selector.single_set_capability(metadata)
        cohort = selector.select_sdk_cohort(
            metadata, platform=platform_name, machine=normalized_machine
        )
    except ValueError as error:
        raise ActionReceiptError("Arras wheel SDK cohort is not verified") from error
    if action_capable is not True or cohort.supports_single_set is not True:
        _fail("selected UMF cohort lacks the generated single-SET capability")
    if (cohort.platform, cohort.machine) != (platform_name, normalized_machine) and (
        cohort.platform,
        cohort.machine,
    ) != ("any", "any"):
        _fail("selected UMF cohort differs from the observed action runtime")
    return cohort


def _validate_runtime(value: object) -> dict[str, Any]:
    runtime = _exact(value, {"python", "platform", "machine", "implementation"}, "runtime")
    if (
        type(runtime["python"]) is not str
        or _PYTHON.fullmatch(runtime["python"]) is None
        or type(runtime["platform"]) is not str
        or runtime["implementation"] != "CPython"
        or runtime["platform"] not in _RUNTIME["platforms"]
        or type(runtime["machine"]) is not str
        or runtime["machine"] not in _RUNTIME["machines"]
    ):
        _fail("action receipt runtime identity is unsupported")
    return runtime


def _validate_distribution(
    value: object, *, name: str, version: str, require_resource_native: bool = False
) -> dict[str, Any]:
    row = _exact(
        value,
        {
            "name",
            "version",
            "payload_files",
            "payload_sha256",
            "record_matches",
            "resource_files",
            "resource_manifest_sha256",
            "native_files",
            "native_manifest_sha256",
        },
        f"{name} installed payload",
    )
    if (
        row["name"] != name
        or row["version"] != version
        or type(row["payload_files"]) is not int
        or row["payload_files"] <= 0
        or type(row["record_matches"]) is not int
        or row["record_matches"] != row["payload_files"]
        or type(row["resource_files"]) is not int
        or row["resource_files"] < 0
        or type(row["native_files"]) is not int
        or row["native_files"] < 0
        or (require_resource_native and row["resource_files"] == 0)
        or (require_resource_native and row["native_files"] == 0)
    ):
        _fail(f"{name} installed payload inventory differs")
    for key in ("payload_sha256", "resource_manifest_sha256", "native_manifest_sha256"):
        _digest(row[key], f"{name} {key}")
    return row


def _validate_sources(root: dict[str, Any], repository: Path) -> dict[str, Any]:
    source_paths = {
        "tool_sha256": repository / "tools/verify_umf_actions.py",
        "probe_sha256": repository / "tools/_umf_actions_probe.py",
        "selector_sha256": repository / "tools/_umf_sdk_cohorts.py",
    }
    for key, path in source_paths.items():
        _digest(root[key], key)
        if hashlib.sha256(path.read_bytes()).hexdigest() != root[key]:
            _fail(f"action receipt {key} differs from reviewed source")
    fixtures = _exact(root["fixtures"], set(_FIXTURES), "action fixtures")
    if fixtures != _FIXTURES:
        _fail("action fixture digests differ from the reviewed source")
    for filename, digest in _FIXTURES.items():
        fixture_path = (
            repository / "tests/fixtures/umf-actions-binding" / filename
            if filename != "current-conformance.json"
            else repository / "tests/fixtures/umf-core-reference" / filename
        )
        if hashlib.sha256(fixture_path.read_bytes()).hexdigest() != digest:
            _fail("action fixture bytes differ from the reviewed source")
    return fixtures


def _validate_installed(
    root: dict[str, Any], *, version: str, cohort: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    origins = _exact(
        root["origins"], {"arras", "umf", "umf.action_runtime", "umf.rust_codegen"}, "origins"
    )
    if origins != {
        "arras": "arras/__init__.py",
        "umf": "umf/__init__.py",
        "umf.action_runtime": "umf/action_runtime.py",
        "umf.rust_codegen": "umf/rust_codegen.py",
    }:
        _fail("action receipt import origins differ from the installed packages")
    installed = _exact(root["installed"], {"arras", "umf_core"}, "installed distributions")
    return (
        _validate_distribution(installed["arras"], name="arras", version=version),
        _validate_distribution(
            installed["umf_core"],
            name="umf-core",
            version=cohort.distribution_version,
            require_resource_native=True,
        ),
    )


def _validate_results(root: dict[str, Any]) -> None:
    if (
        type(root["generated_client_sha256"]) is not str
        or _SHA.fullmatch(root["generated_client_sha256"]) is None
    ):
        _fail("generated client digest is invalid")
    controls = _exact(root["controls"], _CONTROLS, "action controls")
    if any(item is not True for item in controls.values()):
        _fail("action control inventory is incomplete")
    corpus = _exact(
        root["corpus"], {"cases", "reference_matches", "empty_registry_matches"}, "corpus"
    )
    if any(type(corpus[key]) is not int or corpus[key] != 139 for key in corpus):
        _fail("action receipt does not prove exact 139-case parity")
    cleanup = _exact(
        root["cleanup"], {"completed", "fresh_venvs", "shared_site_packages"}, "cleanup"
    )
    if (
        cleanup["completed"] is not True
        or type(cleanup["fresh_venvs"]) is not int
        or cleanup["fresh_venvs"] != 1
        or cleanup["shared_site_packages"] is not False
    ):
        _fail("action proof did not complete owned-environment cleanup")


def _validate_common(
    value: object,
    *,
    version: str,
    wheel_name: str,
    wheel_sha256: str,
    wheel_path: Path,
    phase: str,
    repository: Path,
) -> tuple[dict[str, Any], Any, dict[str, Any], dict[str, Any]]:
    root = _exact(
        value,
        {
            "schema",
            "status",
            "public_gate",
            "mode",
            "candidate_override",
            "arras_wheel",
            "umf",
            "fixtures",
            "tool_sha256",
            "probe_sha256",
            "selector_sha256",
            "runtime",
            "origins",
            "installed",
            "generated_client_sha256",
            "controls",
            "corpus",
            "cleanup",
            "qualification_phase",
        },
        "action receipt",
    )
    if (
        root["schema"] != SCHEMA
        or root["status"] != "passed"
        or root["public_gate"] is not True
        or root["mode"] != "public-extra"
        or root["candidate_override"] is not None
        or root["qualification_phase"] != phase
    ):
        _fail("action receipt is not a successful public-extra proof for this phase")
    arras = _exact(root["arras_wheel"], {"filename", "version", "sha256"}, "Arras wheel")
    if (arras["filename"], arras["version"], arras["sha256"]) != (
        wheel_name,
        version,
        wheel_sha256,
    ):
        _fail("action receipt identifies a different Arras wheel")
    _digest(arras["sha256"], "Arras wheel SHA-256")
    metadata, observed_version = _wheel_metadata(wheel_path, name="arras", sha256=wheel_sha256)
    if observed_version != version:
        _fail("selected Arras wheel version differs")
    runtime = _validate_runtime(root["runtime"])
    _validate_sources(root, repository)
    cohort = _selected_cohort(metadata, runtime, repository)
    umf = _exact(root["umf"], {"public_extra", "installed", "candidate_override"}, "UMF")
    selected = _exact(
        umf["public_extra"],
        {
            "cohort_id",
            "distribution_version",
            "document_version",
            "platform",
            "machine",
            "filename",
            "url",
            "sha256",
            "supports_single_set",
        },
        "selected public UMF cohort",
    )
    wanted = {
        "cohort_id": cohort.cohort_id,
        "distribution_version": cohort.distribution_version,
        "document_version": cohort.document_version,
        "platform": cohort.platform,
        "machine": cohort.machine,
        "filename": cohort.filename,
        "url": cohort.url,
        "sha256": cohort.sha256,
        "supports_single_set": True,
    }
    if (
        type(selected["supports_single_set"]) is not bool
        or selected["supports_single_set"] is not True
        or selected != wanted
    ):
        _fail("action receipt selected UMF cohort differs from the verified Arras wheel")
    if umf["candidate_override"] is not None:
        _fail("candidate SDK evidence cannot qualify a public release")
    installed_identity = _exact(umf["installed"], {"filename", "sha256"}, "installed UMF wheel")
    if (
        installed_identity["filename"] != cohort.filename
        or installed_identity["sha256"] != cohort.sha256
    ):
        _fail("installed UMF wheel differs from the verified public cohort")
    _digest(installed_identity["sha256"], "installed UMF wheel SHA-256")
    _validate_results(root)
    arras_installed, umf_installed = _validate_installed(root, version=version, cohort=cohort)
    return root, cohort, arras_installed, umf_installed


def validate_receipt(
    value: object,
    *,
    version: str,
    wheel_name: str,
    wheel_sha256: str,
    wheel_path: Path,
    phase: str,
    repository: Path,
) -> dict[str, Any]:
    """Validate raw receipt and return a safe public projection."""
    if phase not in {"release-build", "public-download"}:
        _fail("action receipt phase is unsupported for release evidence")
    root, cohort, arras, umf = _validate_common(
        value,
        version=version,
        wheel_name=wheel_name,
        wheel_sha256=wheel_sha256,
        wheel_path=wheel_path,
        phase=phase,
        repository=repository,
    )
    projection = {
        "schema": PUBLIC_SCHEMA,
        "status": "passed",
        "qualification_scope": SCOPE,
        "qualification_phase": phase,
        "arras_wheel": dict(root["arras_wheel"]),
        "umf_wheel": {
            "cohort_id": cohort.cohort_id,
            "filename": cohort.filename,
            "version": cohort.distribution_version,
            "document_version": cohort.document_version,
            "url": cohort.url,
            "sha256": cohort.sha256,
        },
        "tool_sha256": root["tool_sha256"],
        "probe_sha256": root["probe_sha256"],
        "selector_sha256": root["selector_sha256"],
        "fixtures": dict(_FIXTURES),
        "runtime": dict(root["runtime"]),
        "installed": {"arras": dict(arras), "umf_core": dict(umf)},
        "generated_client_sha256": root["generated_client_sha256"],
        "controls": {key: True for key in sorted(_CONTROLS)},
        "corpus": {"cases": 139, "reference_matches": 139, "empty_registry_matches": 139},
        "cleanup": {"completed": True, "fresh_venvs": 1, "shared_site_packages": False},
    }
    return projection


def validate_public_projection(
    value: object,
    *,
    version: str,
    wheel_name: str,
    wheel_sha256: str,
    phase: str,
    wheel_path: Path,
    repository: Path,
) -> dict[str, Any]:
    """Check the public action component's closed shape and exact release binding."""
    root = _exact(
        value,
        {
            "schema",
            "status",
            "qualification_scope",
            "qualification_phase",
            "arras_wheel",
            "umf_wheel",
            "tool_sha256",
            "probe_sha256",
            "selector_sha256",
            "fixtures",
            "runtime",
            "installed",
            "generated_client_sha256",
            "controls",
            "corpus",
            "cleanup",
        },
        "public action receipt",
    )
    if (
        root["schema"] != PUBLIC_SCHEMA
        or root["status"] != "passed"
        or root["qualification_scope"] != SCOPE
        or root["qualification_phase"] != phase
    ):
        _fail("public action receipt scope or status differs")
    arras = _exact(root["arras_wheel"], {"filename", "version", "sha256"}, "Arras wheel")
    if (arras["filename"], arras["version"], arras["sha256"]) != (
        wheel_name,
        version,
        wheel_sha256,
    ):
        _fail("public action receipt identifies a different Arras wheel")
    for key in ("tool_sha256", "probe_sha256", "selector_sha256", "generated_client_sha256"):
        _digest(root[key], key)
    runtime = _validate_runtime(root["runtime"])
    metadata, observed_version = _wheel_metadata(wheel_path, name="arras", sha256=wheel_sha256)
    if observed_version != version:
        _fail("selected Arras wheel version differs")
    cohort = _selected_cohort(metadata, runtime, repository)
    umf = _exact(
        root["umf_wheel"],
        {"cohort_id", "filename", "version", "document_version", "url", "sha256"},
        "public UMF wheel",
    )
    _digest(umf["sha256"], "public UMF wheel SHA-256")
    if umf != {
        "cohort_id": cohort.cohort_id,
        "filename": cohort.filename,
        "version": cohort.distribution_version,
        "document_version": cohort.document_version,
        "url": cohort.url,
        "sha256": cohort.sha256,
    }:
        _fail("public action receipt UMF identity differs from the selected cohort")
    installed = _exact(root["installed"], {"arras", "umf_core"}, "installed distributions")
    _validate_distribution(installed["arras"], name="arras", version=version)
    _validate_distribution(
        installed["umf_core"],
        name="umf-core",
        version=umf["version"],
        require_resource_native=True,
    )
    fixtures = _exact(root["fixtures"], set(_FIXTURES), "action fixtures")
    if fixtures != _FIXTURES:
        _fail("public action fixture digests differ")
    controls = _exact(root["controls"], _CONTROLS, "action controls")
    if any(item is not True for item in controls.values()):
        _fail("public action controls differ")
    corpus = _exact(
        root["corpus"], {"cases", "reference_matches", "empty_registry_matches"}, "corpus"
    )
    if any(type(corpus[key]) is not int or corpus[key] != 139 for key in corpus):
        _fail("public action corpus counts differ")
    cleanup = _exact(
        root["cleanup"], {"completed", "fresh_venvs", "shared_site_packages"}, "cleanup"
    )
    if (
        cleanup["completed"] is not True
        or type(cleanup["fresh_venvs"]) is not int
        or cleanup["fresh_venvs"] != 1
        or cleanup["shared_site_packages"] is not False
    ):
        _fail("public action cleanup does not pass")
    return root
