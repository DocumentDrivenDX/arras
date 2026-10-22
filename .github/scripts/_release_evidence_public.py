#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Allowlisted public projections for local release qualification receipts."""

from __future__ import annotations

import re
from typing import Any, cast

if __package__:
    from . import _release_evidence_inputs as _inputs
else:
    import _release_evidence_inputs as _inputs

_fail = _inputs.fail
_object = _inputs.object_value
_keys = _inputs.exact_object
_string = _inputs.string

_DOCTOR_LIMITS = [
    "Public projection omits host paths; the original receipt is retained privately and linked by SHA-256.",
    "SDK/doctor fixture proof applies only to the named wheel and runtime; native and server startup were mocked or not imported.",
    "This component proof does not establish official UMF runtime semantics, managed production behavior, or public-download qualification.",
]
_LAUNCHER_VALUES = {
    "alias_conflict_refused": "passed",
    "custom_devhost_help": "passed",
    "custom_devhost_startup_forwarding": "passed",
    "custom_devhost_unsupported_args": "passed",
    "custom_mcp_help": "passed",
    "custom_mcp_unsupported_args": "passed",
    "effective_telemetry_names": "observed through public launch factory",
    "native_and_server_work": "mocked or not imported",
}
_TELEMETRY_VALUES = {
    "concurrent_and_nested_contexts": "passed",
    "default_deny_and_failure_isolation": "passed",
    "public_direct_library": "passed",
    "public_mcp_frame": "passed",
    "public_worker_backed_asgi": "passed",
}
_PHASE_KEYS = {
    "direct",
    "mcp_frame",
    "worker_backed_asgi_console",
    "worker_backed_asgi_operate",
    "concurrent_nested",
    "nested_ambient_restoration",
    "finish_time_snapshot",
    "provider_fault_isolation",
}
_PHASE_SERVICES = {
    "direct": "extension-alpha+extension-beta",
    "mcp_frame": "extension-beta",
    "worker_backed_asgi_console": "extension-alpha",
    "worker_backed_asgi_operate": "extension-alpha",
    "concurrent_nested": "extension-alpha+extension-beta",
    "nested_ambient_restoration": "extension-alpha",
    "finish_time_snapshot": "extension-alpha",
    "provider_fault_isolation": "extension-alpha",
}
_FALSE_PASS_CONTROLS = [
    "MCP successful empty result",
    "ASGI successful HTTP 200 empty body",
    "finish-time ambient-context misrouting",
]
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+!-]*\Z")
_CASE_CODE = re.compile(r"[a-z][a-z0-9_]*\Z")
_DIST_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_VERSION_TOKEN = re.compile(r"[0-9][A-Za-z0-9.+!-]{0,99}\Z")
_TRIPWIRE_EXPECTED = {
    "positive": (True, True),
    "invalid_config": (False, True),
    "unsupported": (False, False),
}


def _text(value: object, label: str) -> str:
    return _string(value, label)


def _boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        _fail(f"{label} must be a boolean")
    return cast(bool, value)


def _positive_count(value: object, label: str) -> int:
    if type(value) is not int or value < 1:
        _fail(f"{label} must be a positive integer")
    return cast(int, value)


def _safe_token(value: object, label: str) -> str:
    result = _text(value, label)
    if _SAFE_TOKEN.fullmatch(result) is None:
        _fail(f"{label} is not a safe public token")
    return result


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        _fail(f"{label} must be an array")
    return [_text(item, f"{label}[{index}]") for index, item in enumerate(value)]


def binding_projection(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "bound",
        "wheel": {key: value["wheel"][key] for key in ("name", "version", "sha256")},
        "find_links": {"sha256": value["find_links"]["sha256"]},
        "bound_manifest": {"sha256": value["bound_manifest"]["sha256"]},
    }


def doctor_projection(value: dict[str, Any], source_sha256: str) -> dict[str, Any]:
    """Project validated doctor evidence without copying local diagnostics."""
    platform = _keys(
        value.get("platform"), "doctor.platform", {"os", "architecture", "release"}
    )
    wheel = _keys(
        value.get("wheel"), "doctor.wheel", {"filename", "version", "sha256"}
    )
    cases_raw = value.get("cases")
    if not isinstance(cases_raw, list):
        _fail("doctor.cases must be an array")
    cases: list[dict[str, Any]] = []
    expected_cases = _inputs.DOCTOR_CASE_STATUSES
    if len(cases_raw) != len(expected_cases):
        _fail("doctor case projection is incomplete")
    for index, raw in enumerate(cases_raw):
        row = _keys(raw, f"doctor.cases[{index}]", {"name", "status", "codes"})
        status = row.get("status")
        if type(status) is not int or status < 0:
            _fail(f"doctor.cases[{index}].status must be a nonnegative integer")
        case_name = _text(row.get("name"), f"doctor.cases[{index}].name")
        if (case_name, status) != expected_cases[index]:
            _fail(f"doctor.cases[{index}] differs from the reviewed case")
        codes = _string_list(row.get("codes"), f"doctor.cases[{index}].codes")
        if any(_CASE_CODE.fullmatch(code) is None for code in codes):
            _fail(f"doctor.cases[{index}].codes contains an unsafe diagnostic code")
        cases.append(
            {
                "name": case_name,
                "status": status,
                "codes": codes,
            }
        )

    tripwire_raw = _keys(
        value.get("tripwire_report"),
        "doctor.tripwire_report",
        {"tripwires", "positive", "invalid_config", "unsupported"},
    )
    tripwires = _text(tripwire_raw.get("tripwires"), "doctor.tripwire_report.tripwires")
    if tripwires != "passed":
        _fail("doctor tripwire summary is not passed")
    tripwires_public: dict[str, Any] = {"tripwires": tripwires}
    for name in ("positive", "invalid_config", "unsupported"):
        row = _object(tripwire_raw.get(name), f"doctor.tripwire_report.{name}")
        ok = _boolean(row.get("ok"), f"doctor.tripwire_report.{name}.ok")
        complete = _boolean(row.get("complete"), f"doctor.tripwire_report.{name}.complete")
        if (ok, complete) != _TRIPWIRE_EXPECTED[name]:
            _fail(f"doctor tripwire {name} differs from the reviewed outcome")
        tripwires_public[name] = {"ok": ok, "complete": complete}

    launcher_raw = _object(value.get("launcher_probes"), "doctor.launcher_probes")
    if set(launcher_raw) != set(_LAUNCHER_VALUES):
        _fail("doctor launcher probes have an unsupported shape")
    launcher = {
        name: _text(launcher_raw[name], f"doctor.launcher_probes.{name}")
        for name in _LAUNCHER_VALUES
    }
    if launcher != _LAUNCHER_VALUES:
        _fail("doctor launcher probe outcomes differ from the reviewed controls")

    telemetry_raw = _object(value.get("telemetry_probes"), "doctor.telemetry_probes")
    telemetry: dict[str, Any] = {}
    for name, expected in _TELEMETRY_VALUES.items():
        observed = _text(telemetry_raw.get(name), f"doctor.telemetry_probes.{name}")
        if observed != expected:
            _fail(f"doctor telemetry probe {name} is not passed")
        telemetry[name] = observed
    if telemetry_raw.get("status") != "passed":
        _fail("doctor telemetry status is not passed")
    telemetry["status"] = "passed"
    telemetry["generated_probe_sha256"] = _inputs.digest(
        telemetry_raw.get("generated_probe_sha256"),
        "doctor.telemetry_probes.generated_probe_sha256",
    )
    telemetry["global_provider_unchanged"] = _boolean(
        telemetry_raw.get("global_provider_unchanged"),
        "doctor.telemetry_probes.global_provider_unchanged",
    )
    if telemetry["global_provider_unchanged"] is not True:
        _fail("doctor telemetry global provider changed")
    expected_resources = ["extension-alpha", "extension-beta"]
    resources = _string_list(
        telemetry_raw.get("sdk_resource_names"), "doctor.telemetry_probes.sdk_resource_names"
    )
    if resources != expected_resources:
        _fail("doctor SDK resource names differ from the reviewed pair")
    telemetry["sdk_resource_names"] = resources
    names_raw = _keys(
        telemetry_raw.get("launcher_effective_names"),
        "doctor.telemetry_probes.launcher_effective_names",
        {"attribute_namespace", "log_prefix", "event_prefix"},
    )
    names = {key: _text(names_raw[key], f"doctor.launcher_effective_names.{key}") for key in names_raw}
    if names != {key: "extension_host" for key in names}:
        _fail("doctor effective telemetry names differ from the reviewed namespace")
    telemetry["launcher_effective_names"] = names
    versions_raw = _keys(
        telemetry_raw.get("versions"),
        "doctor.telemetry_probes.versions",
        {"opentelemetry-api", "opentelemetry-sdk"},
    )
    telemetry["versions"] = {
        key: _safe_token(versions_raw[key], f"doctor.telemetry_probes.versions.{key}")
        for key in sorted(versions_raw)
    }
    versions_raw = _object(value.get("versions"), "doctor.versions")
    distributions_raw = _keys(
        versions_raw.get("python_distributions"),
        "doctor.versions.python_distributions",
        {"arras", "example-extension-host", "graphql-core", "opentelemetry-api", "opentelemetry-sdk"},
    )
    distributions: dict[str, str] = {}
    for name, raw_version in distributions_raw.items():
        if _DIST_NAME.fullmatch(name) is None:
            _fail("doctor Python distribution name is unsafe")
        version = _text(raw_version, f"doctor.versions.python_distributions.{name}")
        if _VERSION_TOKEN.fullmatch(version) is None:
            _fail(f"doctor Python distribution version for {name} is unsafe")
        distributions[name] = version
    if distributions["arras"] != wheel["version"] or any(
        distributions[name] != telemetry["versions"][name]
        for name in ("opentelemetry-api", "opentelemetry-sdk")
    ):
        _fail("doctor installed distribution versions disagree with wheel or telemetry identity")
    extension_wheel_raw = _keys(
        versions_raw.get("extension_host_wheel"),
        "doctor.versions.extension_host_wheel",
        {"filename", "sha256"},
    )
    extension_filename = _safe_token(
        extension_wheel_raw["filename"], "doctor.versions.extension_host_wheel.filename"
    )
    expected_extension_filename = (
        f"example_extension_host-{distributions['example-extension-host']}-py3-none-any.whl"
    )
    if extension_filename != expected_extension_filename:
        _fail("doctor extension-host wheel filename differs from its installed version")
    extension_wheel = {
        "filename": extension_filename,
        "sha256": _inputs.digest(
            extension_wheel_raw["sha256"], "doctor.versions.extension_host_wheel.sha256"
        ),
    }
    phases_raw = _keys(
        telemetry_raw.get("phases"), "doctor.telemetry_probes.phases", _PHASE_KEYS
    )
    phases: dict[str, Any] = {}
    for name, service in _PHASE_SERVICES.items():
        row = _keys(
            phases_raw[name],
            f"doctor.telemetry_probes.phases.{name}",
            {"spans", "events", "logs", "service_name"},
        )
        observed_service = _text(
            row.get("service_name"), f"doctor.telemetry_probes.phases.{name}.service_name"
        )
        if observed_service != service:
            _fail(f"doctor telemetry phase {name} is misrouted")
        phases[name] = {
            key: _positive_count(row.get(key), f"doctor.telemetry_probes.phases.{name}.{key}")
            for key in ("spans", "events", "logs")
        }
        phases[name]["service_name"] = observed_service
    telemetry["phases"] = phases
    controls = _string_list(
        telemetry_raw.get("false_pass_controls"),
        "doctor.telemetry_probes.false_pass_controls",
    )
    if controls != _FALSE_PASS_CONTROLS:
        _fail("doctor false-pass controls differ from reviewed controls")
    telemetry["false_pass_controls"] = controls

    return {
        "schema": "arras.ui.doctor-public-qualification.v1",
        "status": "passed",
        "source_receipt_sha256": _inputs.digest(source_sha256, "doctor source receipt SHA-256"),
        "verifier_source_sha256": _inputs.digest(
            value.get("verifier_source_sha256"), "doctor.verifier_source_sha256"
        ),
        "generated_probe_sha256": _inputs.digest(
            value.get("generated_probe_sha256"), "doctor.generated_probe_sha256"
        ),
        "platform": {
            key: _safe_token(platform[key], f"doctor.platform.{key}")
            for key in ("os", "architecture", "release")
        },
        "python": _safe_token(value.get("python"), "doctor.python"),
        "wheel": {
            key: _safe_token(wheel[key], f"doctor.wheel.{key}")
            for key in ("filename", "version")
        }
        | {"sha256": _inputs.digest(wheel.get("sha256"), "doctor.wheel.sha256")},
        "npm_sha256": _inputs.digest(value.get("npm_sha256"), "doctor.npm_sha256"),
        "cases": cases,
        "tripwire_report": tripwires_public,
        "launcher_probes": launcher,
        "telemetry_probes": telemetry,
        "versions": {
            "python_distributions": distributions,
            "extension_host_wheel": extension_wheel,
        },
        "qualification_limits": list(_DOCTOR_LIMITS),
    }


def distribution_projection(value: dict[str, Any], source_sha256: str) -> dict[str, Any]:
    """Project distribution evidence while excluding machine-local package paths."""
    projected: dict[str, Any] = {
        "schema": "arras.distribution-public-qualification.v1",
        "source_receipt_sha256": _inputs.digest(
            source_sha256, "distribution source receipt SHA-256"
        ),
    }
    for name in ("source_wheel", "sdist", "sdist_rebuilt_wheel"):
        row = _keys(value.get(name), f"distribution.{name}", {"file", "sha256"})
        projected[name] = {
            "file": _safe_token(row["file"], f"distribution.{name}.file"),
            "sha256": _inputs.digest(row["sha256"], f"distribution.{name}.sha256"),
        }
    npm = _keys(value.get("npm"), "distribution.npm", {"file", "sha256", "exact_between_wheels"})
    exact = _boolean(npm["exact_between_wheels"], "distribution.npm.exact_between_wheels")
    if not exact:
        _fail("distribution npm bytes are not exact between wheels")
    projected["npm"] = {
        "file": _safe_token(npm["file"], "distribution.npm.file"),
        "sha256": _inputs.digest(npm["sha256"], "distribution.npm.sha256"),
        "exact_between_wheels": exact,
    }
    for name in ("platform", "python_interpreter", "qualified_python"):
        projected[name] = _safe_token(value.get(name), f"distribution.{name}")
    cohort = _text(value.get("javascript_consumer_cohort"), "distribution.javascript_consumer_cohort")
    if cohort != "workspace-linked UI dependencies; package itself extracted from each verified wheel":
        _fail("distribution JavaScript consumer cohort is unrecognized")
    projected["javascript_consumer_cohort"] = cohort
    for name in ("declared_python", "qualification", "not_qualified_without_observation"):
        projected[name] = _string_list(value.get(name), f"distribution.{name}")
    if any(_SAFE_TOKEN.fullmatch(item) is None for item in projected["declared_python"]):
        _fail("distribution declared Python versions contain an unsafe token")
    if projected["qualification"] != ["artifact-inspected", "installed-consumer-tested"]:
        _fail("distribution qualification outcomes differ from reviewed controls")
    if projected["not_qualified_without_observation"] != [
        "Linux",
        "Python 3.12",
        "Python 3.13",
        "registry installation",
        "managed Arras host",
        "official UMF runtime",
    ]:
        _fail("distribution limitations differ from reviewed controls")
    consumers_raw = _keys(
        value.get("consumers"),
        "distribution.consumers",
        {"source_wheel", "sdist_rebuilt_wheel"},
    )
    consumers: dict[str, Any] = {}
    fields = {
        "environment",
        "python",
        "platform",
        "graphql_core",
        "graphql_core_inventory_sha256",
        "in_memory_operation",
        "packed_npm_consumer",
        "schema_callback",
    }
    for consumer_name in ("source_wheel", "sdist_rebuilt_wheel"):
        raw = _object(consumers_raw[consumer_name], f"distribution.consumers.{consumer_name}")
        if not fields <= set(raw):
            _fail(f"distribution.consumers.{consumer_name} is incomplete")
        expected_environment = "source-wheel" if consumer_name == "source_wheel" else "sdist-rebuilt-wheel"
        environment = _text(raw["environment"], f"distribution.consumers.{consumer_name}.environment")
        if environment != expected_environment:
            _fail(f"distribution.consumers.{consumer_name} environment is unrecognized")
        packed_consumer = _text(
            raw["packed_npm_consumer"],
            f"distribution.consumers.{consumer_name}.packed_npm_consumer",
        )
        if packed_consumer != "Packed consumer passed through package exports":
            _fail(f"distribution.consumers.{consumer_name} npm check is unrecognized")
        consumer: dict[str, Any] = {
            "environment": environment,
            "python": _safe_token(raw["python"], f"distribution.consumers.{consumer_name}.python"),
            "platform": _safe_token(raw["platform"], f"distribution.consumers.{consumer_name}.platform"),
            "graphql_core": _safe_token(
                raw["graphql_core"], f"distribution.consumers.{consumer_name}.graphql_core"
            ),
            "packed_npm_consumer": packed_consumer,
        }
        consumer["graphql_core_inventory_sha256"] = _inputs.digest(
            raw["graphql_core_inventory_sha256"],
            f"distribution.consumers.{consumer_name}.graphql_core_inventory_sha256",
        )
        consumer["in_memory_operation"] = _boolean(
            raw["in_memory_operation"], f"distribution.consumers.{consumer_name}.in_memory_operation"
        )
        consumer["schema_callback"] = _boolean(
            raw["schema_callback"], f"distribution.consumers.{consumer_name}.schema_callback"
        )
        if not consumer["in_memory_operation"] or not consumer["schema_callback"]:
            _fail(f"distribution.consumers.{consumer_name} checks are incomplete")
        consumers[consumer_name] = consumer
    projected["consumers"] = consumers
    return projected


def release_evidence_projection(
    *,
    version: str,
    wheel_name: str,
    wheel_sha: str,
    npm_name: str,
    npm_sha: str,
    source_hashes: dict[str, str],
    native: dict[str, Any],
    ui: dict[str, Any],
    consumer: dict[str, Any],
    component_hashes: dict[str, str],
    sdist_name: str,
    sdist_sha: str,
    doctor_runtime: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "passed",
        "version": version,
        "release_artifacts": {
            "wheel": {"filename": wheel_name, "sha256": wheel_sha},
            "sdist": {"filename": sdist_name, "sha256": sdist_sha},
            "npm": {"filename": npm_name, "sha256": npm_sha},
        },
        "published_components": dict(sorted(component_hashes.items())),
        "source_evidence_sha256": dict(sorted(source_hashes.items())),
        "qualification_scope": {
            "statement": "Linked component proofs apply only to their named artifacts, runtime cohorts, and reviewed limits; this bundle is not one production-host end-to-end qualification.",
            "native_runtime": native["runtime"],
            "doctor_runtime": doctor_runtime,
            "native_corpus_version": native["corpus"]["version"],
            "native_limits": native["corpus"]["limits"],
            "consumer_backend": "memory-store",
            "ui_suite": "full portable acceptance suite",
        },
        "gates": {
            "distribution": "passed",
            "doctor": "passed",
            "native": "passed",
            "ui": "passed",
            "consumer": "passed",
            "public_download": {
                "status": "not_run_at_assembly",
                "purpose": "A separate post-download receipt must record the later public-download consumer check.",
            },
        },
    }
