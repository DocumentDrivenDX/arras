#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Strict versioned validation and safe projection for the UMF admission receipt."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, NoReturn

_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_PYTHON_VERSION = re.compile(r"3\.11\.[0-9]+\Z")
_RUNTIME_PLATFORMS = {"darwin", "linux", "win32"}
_RUNTIME_MACHINES = {"AMD64", "arm64", "aarch64", "i386", "i686", "x86_64"}
_EXPECTED_LIMITATIONS = [
    "This proves only the named installed wheel and runtime.",
    "This does not qualify native Truss, browser, UI, or production behavior.",
]
_UMF_URL = (
    "https://github.com/DocumentDrivenDX/umf/releases/download/umf-v0.5.4/"
    "umf_core-0.10.0-py3-none-any.whl"
)
_UMF_SHA = "49633924b45a3c8499d4fcc1a24c30d5a8fcb34d974ab019bbda987cb47da0f9"
_HISTORICAL_COHORT_ID = "umf-core-0.10.0-py3-none-any"
_CORPUS_SHA = "bb008a98b8448050748e65f867e7863475ccad9501a5b9229ae9e6d336691544"
_METADATA_SHA = "da883657baefe7b7a4ab8654f78e7d84ef1e281eea7bc7cee48f8662007cd687"
_BASE = [
    "legacy_registration_document_and_empty_read",
    "base_has_no_umf_distribution",
    "base_imported_no_umf",
    "admission_refuses_missing_engine",
    "projection_refuses_missing_engine",
    "selected_host_refuses_without_fallback",
]
_EXTRA = [
    "public_admission_and_projection",
    "metadata_registration_readback_original_bytes",
    "metadata_description_immutable_and_empty_read",
    "metadata_direct_write_refused_without_effects",
    "valid_but_unsupported_profile_control",
    "valid_incomplete_unknown_source_control",
    "source_only_repr_privacy",
    "default_profile_does_not_auto_detect",
    "unqualified_provider_does_not_accept",
    "metadata_profile_transition_refused",
]


class AdmissionReceiptError(ValueError):
    """Receipt failed an exact release-bound admission check."""


def _fail(message: str) -> NoReturn:
    raise AdmissionReceiptError(message)


def _cohort_module() -> Any:
    name = "arras_release_umf_sdk_cohorts"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = Path(__file__).resolve().parents[2] / "tools/_umf_sdk_cohorts.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        _fail("verified UMF cohort selector is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _cohort_for_identity(filename: object, version: object, digest: object, url: object) -> Any:
    cohorts = _cohort_module().KNOWN_COHORTS
    matches = [
        item
        for item in cohorts
        if (item.filename, item.distribution_version, item.sha256, item.url)
        == (filename, version, digest, url)
    ]
    if len(matches) != 1:
        _fail("UMF receipt identifies an unverified SDK cohort")
    return matches[0]


def _validate_cohort_runtime(cohort: Any, runtime: dict[str, Any]) -> None:
    if cohort.platform == "any":
        return
    platform_name = runtime.get("platform")
    machine = runtime.get("machine")
    normalized_machine = {
        "AMD64": "x86_64",
        "aarch64": "arm64",
        "x86_64": "x86_64",
        "arm64": "arm64",
    }.get(machine)
    if (platform_name, normalized_machine) != (cohort.platform, cohort.machine):
        _fail("UMF native cohort differs from the observed receipt runtime")


def strict_json_loads(value: str) -> Any:
    """Parse JSON while refusing duplicate object keys and non-finite numbers."""

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                _fail("JSON contains a duplicate object key")
            result[key] = item
        return result

    def reject_constant(_value: str) -> NoReturn:
        _fail("JSON contains a non-finite number")

    return json.loads(value, object_pairs_hook=unique_object, parse_constant=reject_constant)


def required_for_version(version: str) -> bool:
    match = _VERSION.fullmatch(version)
    if match is None:
        _fail("release version is malformed")
    major, minor, _patch = map(int, match.groups())
    return (major, minor) >= (0, 6)


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


def _fixture_ids(fixture: Path) -> list[str]:
    try:
        corpus = strict_json_loads(fixture.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        _fail("official corpus fixture is unavailable")
    cases = corpus.get("cases") if isinstance(corpus, dict) else None
    if not isinstance(cases, list) or len(cases) != 139:
        _fail("official corpus does not contain the exact 139 cases")
    expected = [row.get("id") for row in cases if isinstance(row, dict)]
    if len(expected) != 139 or any(not isinstance(item, str) or not item for item in expected):
        _fail("official corpus case identities are malformed")
    if len(set(expected)) != 139:
        _fail("receipt case IDs differ from the exact ordered official corpus")
    return expected


def _ids(value: object, fixture: Path) -> list[str]:
    expected = _fixture_ids(fixture)
    if value != expected:
        _fail("receipt case IDs differ from the exact ordered official corpus")
    return expected


def _validate_root(value: object, phase: str) -> dict[str, Any]:
    root = _object(value, "UMF receipt")
    historical_keys = {
        "schema",
        "status",
        "qualification_scope",
        "qualification_phase",
        "arras_wheel",
        "umf_wheel",
        "tool_sha256",
        "fixed_probe_sha256",
        "fixtures",
        "runtime",
        "environments",
        "corpus",
        "controls",
        "cleanup",
        "limitations",
    }
    if set(root) not in (historical_keys, historical_keys | {"selector_sha256"}):
        _fail("UMF receipt has an unexpected shape")
    if (
        root["schema"] != "arras.umf-admission-installed/1"
        or root["status"] != "passed"
        or root["qualification_scope"] != "installed-wheel-umf-admission/1"
        or root["qualification_phase"] != phase
    ):
        _fail("UMF receipt schema, status, scope or phase differs")
    return root


def _validate_wheels(
    root: dict[str, Any], version: str, wheel_name: str, wheel_sha: str
) -> tuple[dict[str, Any], dict[str, Any], Any]:
    arras = _exact(
        root["arras_wheel"], {"filename", "version", "sha256", "record_entries"}, "Arras wheel"
    )
    if (arras["filename"], arras["version"], arras["sha256"]) != (wheel_name, version, wheel_sha):
        _fail("UMF receipt identifies a different Arras wheel")
    if type(arras["record_entries"]) is not int or arras["record_entries"] < 1:
        _fail("Arras wheel RECORD count is invalid")
    umf = _exact(
        root["umf_wheel"],
        {"filename", "version", "sha256", "url", "source_mode", "record_entries"},
        "UMF wheel",
    )
    cohort = _cohort_for_identity(umf["filename"], umf["version"], umf["sha256"], umf["url"])
    selector_required = cohort.cohort_id != _HISTORICAL_COHORT_ID
    if selector_required:
        _digest(root.get("selector_sha256"), "selector SHA-256")
    elif "selector_sha256" in root:
        _digest(root["selector_sha256"], "selector SHA-256")
    if (
        umf["source_mode"] != "pinned-public-url"
        or type(umf["record_entries"]) is not int
        or umf["record_entries"] < 1
    ):
        _fail("UMF receipt does not bind the official SDK source")
    return arras, umf, cohort


def _validate_source_digests(
    root: dict[str, Any], repository: Path, cohort: Any
) -> tuple[str, str, str | None]:
    script = repository / "tools/verify_umf_admission.py"
    probe = repository / "tools/_umf_admission_probe.py"
    tool_sha, probe_sha = (
        hashlib.sha256(script.read_bytes()).hexdigest(),
        hashlib.sha256(probe.read_bytes()).hexdigest(),
    )
    if root["tool_sha256"] != tool_sha or root["fixed_probe_sha256"] != probe_sha:
        _fail("UMF receipt tool or probe digest differs from the checked source")
    selector_sha: str | None = None
    if cohort.cohort_id != _HISTORICAL_COHORT_ID or "selector_sha256" in root:
        selector = repository / "tools/_umf_sdk_cohorts.py"
        selector_sha = hashlib.sha256(selector.read_bytes()).hexdigest()
        if root.get("selector_sha256") != selector_sha:
            _fail("UMF receipt cohort selector digest differs from checked source")
    return tool_sha, probe_sha, selector_sha


def _validate_fixtures(root: dict[str, Any], repository: Path) -> list[str]:
    fixtures = _exact(
        root["fixtures"],
        {
            "official_corpus_sha256",
            "official_corpus_case_count",
            "ordered_case_ids",
            "metadata_fixture_sha256",
        },
        "fixtures",
    )
    corpus_path = repository / "tests/fixtures/umf-core-reference/current-conformance.json"
    metadata_path = repository / "tests/fixtures/umf-core-metadata/primary-string-record.json"
    if (
        fixtures["official_corpus_sha256"] != _CORPUS_SHA
        or fixtures["official_corpus_sha256"]
        != hashlib.sha256(corpus_path.read_bytes()).hexdigest()
        or type(fixtures["official_corpus_case_count"]) is not int
        or fixtures["official_corpus_case_count"] != 139
        or fixtures["metadata_fixture_sha256"] != _METADATA_SHA
        or fixtures["metadata_fixture_sha256"]
        != hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    ):
        _fail("UMF receipt fixture digest or count differs from the pinned source")
    return _ids(fixtures["ordered_case_ids"], corpus_path)


def _validate_environment(
    row: dict[str, Any], expected: list[str], label: str, version: str, cohort: Any
) -> dict[str, Any]:
    expected_keys = {
        "status",
        "mode",
        "arras_version",
        "controls",
        "installed_distributions",
        "payload",
        "import_origins",
        "pth_reuse",
        "source_aliases",
    }
    if label == "extra":
        expected_keys |= {"umf_version", "umf_sha256", "direct_url_verified", "corpus"}
    if set(row) != expected_keys:
        _fail(f"UMF {label} environment has an unexpected shape")
    if (
        row.get("status") != "passed"
        or row.get("mode") != label
        or row.get("arras_version") != version
    ):
        _fail(f"UMF {label} environment identity or status differs")
    controls = row.get("controls")
    if (
        not isinstance(controls, dict)
        or set(controls) != set(expected)
        or any(value is not True for value in controls.values())
    ):
        _fail(f"UMF {label} environment did not pass the exact controls")
    if row.get("pth_reuse") is not False or row.get("source_aliases") is not False:
        _fail(f"UMF {label} environment reused or aliased source paths")
    payload = _object(row.get("payload"), f"{label} payload")
    expected_payload_keys = {"arras_exact_files"}
    if label == "extra":
        expected_payload_keys.add("umf_exact_files")
    if set(payload) != expected_payload_keys:
        _fail(f"UMF {label} payload has an unexpected shape")
    if type(payload.get("arras_exact_files")) is not int or payload["arras_exact_files"] < 1:
        _fail(f"UMF {label} environment lacks Arras payload parity")
    if label == "extra" and (
        type(payload.get("umf_exact_files")) is not int or payload["umf_exact_files"] < 1
    ):
        _fail("UMF extra environment lacks SDK payload parity")
    if label == "extra" and (
        row.get("umf_version") != cohort.distribution_version
        or row.get("umf_sha256") != cohort.sha256
        or row.get("direct_url_verified") is not True
    ):
        _fail("UMF extra environment does not bind the official SDK install")
    expected_origins = {"arras": "arras/__init__.py"}
    if label == "extra":
        expected_origins["umf"] = "umf/__init__.py"
    if row.get("import_origins") != expected_origins:
        _fail(f"UMF {label} environment import origins differ from installed packages")
    distributions = _object(row.get("installed_distributions"), f"{label} distributions")
    arras_versions = [
        value
        for name, value in distributions.items()
        if isinstance(name, str) and re.sub(r"[-_.]+", "-", name).lower() == "arras"
    ]
    sdk_versions = [
        value
        for name, value in distributions.items()
        if isinstance(name, str) and re.sub(r"[-_.]+", "-", name).lower() == "umf-core"
    ]
    if (
        arras_versions != [version]
        or (label == "base" and sdk_versions)
        or (label == "extra" and sdk_versions != [cohort.distribution_version])
    ):
        _fail(f"UMF {label} distribution inventory contradicts the optional SDK controls")
    return payload


def _validate_environments(
    root: dict[str, Any], version: str, expected_ids: list[str], cohort: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    environments = _exact(root["environments"], {"base", "extra"}, "environments")
    base = _object(environments["base"], "base environment")
    extra = _object(environments["extra"], "extra environment")
    controls = _exact(root["controls"], {"base", "extra"}, "controls")
    for label, expected in (("base", _BASE), ("extra", _EXTRA)):
        values = controls[label]
        if (
            not isinstance(values, dict)
            or set(values) != set(expected)
            or any(value is not True for value in values.values())
        ):
            _fail("UMF receipt control inventory differs from required controls")
    base_payload = _validate_environment(base, _BASE, "base", version, cohort)
    extra_payload = _validate_environment(extra, _EXTRA, "extra", version, cohort)
    _validate_corpus_result(extra["corpus"], expected_ids)
    if extra["corpus"] != root["corpus"]:
        _fail("UMF extra environment corpus differs from the top-level corpus result")
    if base_payload["arras_exact_files"] != extra_payload["arras_exact_files"]:
        _fail("UMF environments disagree on exact Arras payload parity")
    return base, extra


def _validate_corpus_result(value: object, expected_ids: list[str]) -> dict[str, Any]:
    corpus = _exact(
        value,
        {
            "status",
            "fixture_sha256",
            "case_count",
            "unique_id_count",
            "ordered_case_ids",
            "reference_matches",
            "empty_registry_matches",
            "skipped",
        },
        "corpus result",
    )
    if (
        corpus["status"] != "passed"
        or corpus["fixture_sha256"] != _CORPUS_SHA
        or type(corpus["case_count"]) is not int
        or corpus["case_count"] != 139
        or type(corpus["unique_id_count"]) is not int
        or corpus["unique_id_count"] != 139
        or corpus["ordered_case_ids"] != expected_ids
        or type(corpus["reference_matches"]) is not int
        or corpus["reference_matches"] != 139
        or type(corpus["empty_registry_matches"]) is not int
        or corpus["empty_registry_matches"] != 139
        or type(corpus["skipped"]) is not int
        or corpus["skipped"] != 0
    ):
        _fail("UMF receipt does not prove exact zero-skip 139-case parity")
    return corpus


def _validate_corpus(root: dict[str, Any], expected_ids: list[str]) -> None:
    _validate_corpus_result(root["corpus"], expected_ids)


def _validate_cleanup(root: dict[str, Any]) -> None:
    cleanup = _exact(
        root["cleanup"], {"completed", "fresh_environments", "shared_site_packages"}, "cleanup"
    )
    if (
        cleanup["completed"] is not True
        or type(cleanup["fresh_environments"]) is not int
        or cleanup["fresh_environments"] != 2
        or cleanup["shared_site_packages"] is not False
    ):
        _fail("UMF proof did not complete owned-environment cleanup")


def validate_receipt(
    value: object,
    *,
    version: str,
    wheel_name: str,
    wheel_sha256: str,
    phase: str,
    repository: Path,
) -> dict[str, Any]:
    """Return an allowlisted public receipt projection after checking every fixed proof field."""
    if not required_for_version(version):
        _fail("UMF admission receipt is not part of this release version")
    root = _validate_root(value, phase)
    arras, umf, cohort = _validate_wheels(root, version, wheel_name, wheel_sha256)
    tool_sha, probe_sha, selector_sha = _validate_source_digests(root, repository, cohort)
    expected_ids = _validate_fixtures(root, repository)
    runtime = _object(root["runtime"], "runtime")
    if (
        set(runtime) != {"version", "implementation", "platform", "machine"}
        or not isinstance(runtime.get("version"), str)
        or _PYTHON_VERSION.fullmatch(runtime["version"]) is None
        or runtime.get("implementation") != "CPython"
        or not isinstance(runtime.get("platform"), str)
        or runtime.get("platform") not in _RUNTIME_PLATFORMS
        or not isinstance(runtime.get("machine"), str)
        or runtime.get("machine") not in _RUNTIME_MACHINES
    ):
        _fail("UMF receipt runtime identity is unsupported")
    _validate_cohort_runtime(cohort, runtime)
    base, extra = _validate_environments(root, version, expected_ids, cohort)
    _validate_corpus(root, expected_ids)
    _validate_cleanup(root)
    limitations = root["limitations"]
    if limitations != _EXPECTED_LIMITATIONS:
        _fail("UMF receipt limitations are malformed")
    base_payload, extra_payload = base["payload"], extra["payload"]
    historical_scope = "exact Arras wheel install, official UMF 0.10.0 admission parity (139 reference and 139 fresh-empty-registry cases), and fixed metadata-profile controls; no broader UMF execution claim"
    native_scope = (
        "exact Arras wheel install, official UMF core 0.10.0 admission parity using SDK distribution "
        f"{cohort.distribution_version} (139 reference and 139 fresh-empty-registry cases), and fixed "
        "metadata-profile controls; no broader UMF execution claim"
    )
    scope = historical_scope if cohort.cohort_id == _HISTORICAL_COHORT_ID else native_scope
    projection = {
        "schema": "arras.umf-admission-public-qualification/1",
        "status": "passed",
        "qualification_scope": scope,
        "qualification_phase": phase,
        "arras_wheel": {key: arras[key] for key in ("filename", "version", "sha256")},
        "umf_wheel": {key: umf[key] for key in ("filename", "version", "sha256", "url")},
        "tool_sha256": tool_sha,
        "fixed_probe_sha256": probe_sha,
        "fixtures": {
            "official_corpus_sha256": _CORPUS_SHA,
            "metadata_fixture_sha256": _METADATA_SHA,
        },
        "runtime": {
            key: runtime[key] for key in ("version", "implementation", "platform", "machine")
        },
        "corpus": {
            "status": "passed",
            "case_count": 139,
            "reference_matches": 139,
            "empty_registry_matches": 139,
            "skipped": 0,
            "ordered_case_ids_sha256": hashlib.sha256(
                json.dumps(expected_ids, separators=(",", ":")).encode()
            ).hexdigest(),
        },
        "payload_parity": {
            "arras_exact_files": base_payload["arras_exact_files"],
            "umf_exact_files": extra_payload["umf_exact_files"],
        },
        "controls": {"base": len(_BASE), "extra": len(_EXTRA), "cleanup": 2},
    }
    if selector_sha is not None:
        projection["selector_sha256"] = selector_sha
    return projection


def validate_public_projection(
    value: object, *, version: str, wheel_name: str, wheel_sha256: str
) -> dict[str, Any]:
    row = _object(value, "public UMF admission receipt")
    historical_keys = {
        "schema",
        "status",
        "qualification_scope",
        "qualification_phase",
        "arras_wheel",
        "umf_wheel",
        "tool_sha256",
        "fixed_probe_sha256",
        "fixtures",
        "runtime",
        "corpus",
        "payload_parity",
        "controls",
    }
    if set(row) not in (historical_keys, historical_keys | {"selector_sha256"}):
        _fail("public UMF admission receipt has an unexpected shape")
    umf = _exact(row["umf_wheel"], {"filename", "version", "sha256", "url"}, "public UMF wheel")
    cohort = _cohort_for_identity(umf["filename"], umf["version"], umf["sha256"], umf["url"])
    selector_required = cohort.cohort_id != _HISTORICAL_COHORT_ID
    if selector_required:
        selector_digest = _digest(row.get("selector_sha256"), "selector SHA-256")
        selector_path = Path(__file__).resolve().parents[2] / "tools/_umf_sdk_cohorts.py"
        if selector_digest != hashlib.sha256(selector_path.read_bytes()).hexdigest():
            _fail("public UMF cohort selector digest differs from checked source")
    elif "selector_sha256" in row:
        selector_digest = _digest(row["selector_sha256"], "selector SHA-256")
        selector_path = Path(__file__).resolve().parents[2] / "tools/_umf_sdk_cohorts.py"
        if selector_digest != hashlib.sha256(selector_path.read_bytes()).hexdigest():
            _fail("public UMF cohort selector digest differs from checked source")
    if (
        row["schema"] != "arras.umf-admission-public-qualification/1"
        or row["status"] != "passed"
        or row["qualification_phase"] != "release-build"
        or row["qualification_scope"]
        != (
            "exact Arras wheel install, official UMF 0.10.0 admission parity (139 reference and 139 fresh-empty-registry cases), and fixed metadata-profile controls; no broader UMF execution claim"
            if cohort.cohort_id == _HISTORICAL_COHORT_ID
            else (
                "exact Arras wheel install, official UMF core 0.10.0 admission parity using SDK distribution "
                f"{cohort.distribution_version} (139 reference and 139 fresh-empty-registry cases), and fixed "
                "metadata-profile controls; no broader UMF execution claim"
            )
        )
    ):
        _fail("public UMF admission receipt scope or status differs")
    arras = _exact(row["arras_wheel"], {"filename", "version", "sha256"}, "public Arras wheel")
    if (arras["filename"], arras["version"], arras["sha256"]) != (
        wheel_name,
        version,
        wheel_sha256,
    ):
        _fail("public UMF receipt identifies a different Arras wheel")
    runtime = _object(row["runtime"], "public UMF runtime")
    if set(runtime) != {"version", "implementation", "platform", "machine"}:
        _fail("public UMF runtime has an unexpected shape")
    _validate_cohort_runtime(cohort, runtime)
    fixtures = _exact(
        row["fixtures"],
        {"official_corpus_sha256", "metadata_fixture_sha256"},
        "public UMF fixtures",
    )
    if fixtures != {
        "official_corpus_sha256": _CORPUS_SHA,
        "metadata_fixture_sha256": _METADATA_SHA,
    }:
        _fail("public UMF receipt fixture digests differ")
    corpus = _exact(
        row["corpus"],
        {
            "status",
            "case_count",
            "reference_matches",
            "empty_registry_matches",
            "skipped",
            "ordered_case_ids_sha256",
        },
        "public UMF corpus",
    )
    if (
        corpus["status"] != "passed"
        or type(corpus["case_count"]) is not int
        or corpus["case_count"] != 139
        or type(corpus["reference_matches"]) is not int
        or corpus["reference_matches"] != 139
        or type(corpus["empty_registry_matches"]) is not int
        or corpus["empty_registry_matches"] != 139
        or type(corpus["skipped"]) is not int
        or corpus["skipped"] != 0
        or type(corpus["ordered_case_ids_sha256"]) is not str
        or corpus["ordered_case_ids_sha256"]
        != hashlib.sha256(
            json.dumps(
                _fixture_ids(
                    Path(__file__).resolve().parents[2]
                    / "tests/fixtures/umf-core-reference/current-conformance.json"
                ),
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    ):
        _fail("public UMF receipt does not prove exact 139-case parity")
    controls = _exact(row["controls"], {"base", "extra", "cleanup"}, "public UMF controls")
    if any(type(count) is not int for count in controls.values()) or controls != {
        "base": 6,
        "extra": 10,
        "cleanup": 2,
    }:
        _fail("public UMF receipt control counts differ")
    parity = _exact(
        row["payload_parity"], {"arras_exact_files", "umf_exact_files"}, "public UMF payload parity"
    )
    if any(type(count) is not int or count < 1 for count in parity.values()):
        _fail("public UMF receipt payload parity counts are invalid")
    _digest(row["tool_sha256"], "public UMF verifier digest")
    _digest(row["fixed_probe_sha256"], "public UMF probe digest")
    runtime = _exact(
        row["runtime"], {"version", "implementation", "platform", "machine"}, "public UMF runtime"
    )
    if (
        not isinstance(runtime["version"], str)
        or _PYTHON_VERSION.fullmatch(runtime["version"]) is None
        or runtime["implementation"] != "CPython"
        or not isinstance(runtime["platform"], str)
        or runtime["platform"] not in _RUNTIME_PLATFORMS
        or not isinstance(runtime["machine"], str)
        or runtime["machine"] not in _RUNTIME_MACHINES
    ):
        _fail("public UMF runtime identity is incomplete")
    return row
