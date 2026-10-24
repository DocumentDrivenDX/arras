#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Link exact, successful component receipts into a bounded release evidence bundle."""

from __future__ import annotations

import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any, cast

if __package__:
    from . import _release_evidence_inputs as _inputs
    from . import _release_evidence_public as _public
    from . import _release_evidence_ui as _ui
    from . import _umf_actions_receipt as _actions_receipt
    from . import _umf_admission_receipt as _umf_receipt
else:
    import _release_evidence_inputs as _inputs
    import _release_evidence_public as _public
    import _release_evidence_ui as _ui
    import _umf_actions_receipt as _actions_receipt
    import _umf_admission_receipt as _umf_receipt

MAX_INDEX = _inputs.MAX_INDEX
MAX_JSON = _inputs.MAX_JSON
MAX_SUMS = _inputs.MAX_SUMS
AssemblyError = _inputs.AssemblyError
_artifact = _inputs.artifact
_check_output_target = _inputs._check_output_target
_npm_identity = _inputs._npm_identity
_parse_sums = _inputs._parse_sums
_publish_bundle = _inputs._publish_bundle
_read_qualification_inputs = _inputs._read_qualification_inputs
_read_ui_sidecars = _inputs._read_ui_sidecars
_safe_https = _inputs._safe_https
_sdist_identity = _inputs._sdist_identity
_validate_index = _inputs._validate_index
_validate_native_scope = _inputs._validate_native_scope
_validate_cohort = _inputs._validate_cohort
_wheel_identity = _inputs._wheel_identity
_unique_ids = _inputs._unique_ids
_validate_limits = _inputs._validate_limits
_validate_ui_suite_cohort = _inputs.validate_ui_suite_cohort
_digest = _inputs.digest
_keys = _inputs.exact_object
_fail = _inputs.fail
_input_file = _inputs.input_file
_load_json = _inputs.load_json
_object = _inputs.object_value
_parse_json_object = _inputs.parse_json_object
_version = _inputs.release_version
_sha = _inputs.sha256
_string = _inputs.string

_load_json = _inputs.load_json

_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _read_umf_admission(
    version: str,
    path: Path | None,
    *,
    wheel_name: str,
    wheel_sha: str,
    selected_inputs: dict[str, tuple[Path, bytes, str]],
) -> tuple[dict[str, Any] | None, str | None]:
    required = _umf_receipt.required_for_version(version)
    if required != (path is not None):
        _fail("UMF admission receipt presence does not match the release version")
    if not required:
        return None, None
    raw = selected_inputs["UMF admission receipt"][1]
    digest = selected_inputs["UMF admission receipt"][2]
    projection = _umf_receipt.validate_receipt(
        _parse_json_object(raw, "UMF admission receipt"),
        version=version,
        wheel_name=wheel_name,
        wheel_sha256=wheel_sha,
        phase="release-build",
        repository=Path(__file__).resolve().parents[2],
    )
    return projection, digest


def _read_umf_actions(
    required: bool,
    path: Path | None,
    *,
    wheel_path: Path,
    wheel_name: str,
    wheel_sha: str,
    version: str,
    selected_inputs: dict[str, tuple[Path, bytes, str]],
) -> tuple[dict[str, Any] | None, str | None]:
    if required != (path is not None):
        _fail("UMF action receipt presence does not match the selected wheel capability")
    if not required:
        return None, None
    raw = selected_inputs["UMF actions receipt"][1]
    digest = selected_inputs["UMF actions receipt"][2]
    try:
        projection = _actions_receipt.validate_receipt(
            _parse_json_object(raw, "UMF actions receipt"),
            version=version,
            wheel_name=wheel_name,
            wheel_sha256=wheel_sha,
            wheel_path=wheel_path,
            phase="release-build",
            repository=Path(__file__).resolve().parents[2],
        )
    except _actions_receipt.ActionReceiptError as error:
        raise AssemblyError(f"UMF action receipt is invalid: {error}") from error
    return projection, digest


def _action_capability_required(wheel_path: Path, wheel_sha: str) -> bool:
    try:
        return _actions_receipt.required_for_wheel(wheel_path, wheel_sha256=wheel_sha)
    except _actions_receipt.ActionReceiptError as error:
        raise AssemblyError(f"release wheel action capability is not verified: {error}") from error


def _action_component_hashes(projection: dict[str, Any] | None) -> dict[str, str]:
    return (
        {}
        if projection is None
        else {"umf-actions-installed.json": _sha(_inputs.canonical_json(projection))}
    )


def _action_projection(projection: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {} if projection is None else {"umf-actions-installed.json": projection}


def _source_evidence_hashes(
    digests: dict[str, str],
    *,
    native_sha: str,
    binding_sha: str,
    cohort_sha: str,
    index_sha: str,
    ui_sha: str,
    consumer_sha: str,
    ui_sidecars: dict[str, bytes],
    umf_admission_sha: str | None,
    umf_actions_sha: str | None,
) -> dict[str, str]:
    source_hashes = {
        **digests,
        "native_receipt.json": native_sha,
        "native_binding.json": binding_sha,
        "native_cohort.json": cohort_sha,
        "native_index.html": index_sha,
        "ui_receipt.json": ui_sha,
        "consumer_receipt.json": consumer_sha,
        **{f"{name}.sha256": _sha(raw) for name, raw in ui_sidecars.items()},
        "distribution-verification.json": digests["distribution-verification.json"],
        "doctor-installed.json": digests["doctor-installed.json"],
    }
    if umf_admission_sha is not None:
        source_hashes["umf-admission-receipt.json"] = umf_admission_sha
    if umf_actions_sha is not None:
        source_hashes["umf-actions-receipt.json"] = umf_actions_sha
    return source_hashes


def _selected_receipt_bytes(
    values: dict[str, tuple[Path, bytes, str]], label: str
) -> tuple[Path, bytes, str]:
    return values[label]


def _verify_build(
    bundle: Path, expected_version: str, expected_wheel: str, expected_sha: str
) -> tuple[
    dict[str, Path], dict[str, str], dict[str, Any], dict[str, Any], str, bytes, dict[str, str]
]:
    if bundle.is_symlink() or not bundle.is_dir():
        _fail("build bundle must be an existing non-symlink directory")
    wheel_name = expected_wheel
    sdist_name = f"arras-{expected_version}.tar.gz"
    npm_name = f"documentdrivendx-arras-ui-{expected_version}.tgz"
    names = {
        wheel_name,
        sdist_name,
        npm_name,
        "distribution-verification.json",
        "doctor-installed.json",
    }
    selected: dict[str, Path] = {}
    raw: dict[str, bytes] = {}
    digests: dict[str, str] = {}
    for name in names:
        if Path(name).name != name:
            _fail("release asset names must be flat filenames")
        path = bundle / name
        resolved, data, digest = _artifact(path, name)
        selected[name], raw[name], digests[name] = resolved, data, digest
    if digests[wheel_name] != expected_sha:
        _fail("build wheel bytes differ from the trusted expected wheel SHA-256")
    sums_path = bundle / "SHA256SUMS"
    _, sums_raw = _input_file(sums_path, MAX_SUMS, "build SHA256SUMS")
    sums = _parse_sums(sums_raw, names)
    if any(sums[name] != digests[name] for name in names):
        _fail("build SHA256SUMS differs from selected release asset bytes")
    wheel_path = selected[wheel_name]
    npm_payload = _wheel_identity(wheel_path, expected_wheel, expected_version)
    npm_name, npm_resources = _npm_identity(npm_payload, expected_version)
    if npm_name != f"documentdrivendx-arras-ui-{expected_version}.tgz":
        _fail("wheel-carried npm archive name differs from expected release")
    if _sha(npm_payload) != digests[npm_name] or npm_payload != raw[npm_name]:
        _fail("wheel-carried npm bytes differ from the selected npm release artifact")
    _sdist_identity(selected[sdist_name], expected_version)
    distribution = _parse_json_object(raw["distribution-verification.json"], "distribution receipt")
    _validate_distribution(distribution, expected_version, wheel_name, digests)
    doctor = _parse_json_object(raw["doctor-installed.json"], "doctor receipt")
    doctor_runtime = _validate_doctor(
        doctor, expected_version, wheel_name, digests[wheel_name], digests[npm_name]
    )
    return selected, digests, distribution, doctor, npm_name, npm_resources, doctor_runtime


def _validate_distribution(
    value: dict[str, Any], version: str, wheel_name: str, digests: dict[str, str]
) -> None:
    if (
        value.get("schema") == "arras.distribution-public-qualification.v1"
        or "source_receipt_sha256" in value
    ):
        _fail("public distribution projection cannot be used as a raw qualification receipt")
    wheel = _object(value.get("source_wheel"), "distribution.source_wheel")
    sdist = _object(value.get("sdist"), "distribution.sdist")
    npm = _object(value.get("npm"), "distribution.npm")
    rebuilt = _object(value.get("sdist_rebuilt_wheel"), "distribution.sdist_rebuilt_wheel")
    if wheel.get("file") != wheel_name or wheel.get("sha256") != digests[wheel_name]:
        _fail("distribution receipt is not bound to the expected Arras wheel")
    sdist_name = f"arras-{version}.tar.gz"
    npm_name = f"documentdrivendx-arras-ui-{version}.tgz"
    if sdist.get("file") != sdist_name or sdist.get("sha256") != digests[sdist_name]:
        _fail("distribution receipt is not bound to the selected sdist")
    if npm.get("file") != npm_name or npm.get("sha256") != digests[npm_name]:
        _fail("distribution receipt is not bound to the selected npm archive")
    if npm.get("exact_between_wheels") is not True:
        _fail("distribution receipt did not prove exact npm bytes between wheels")
    if rebuilt.get("file") != wheel_name or not _SHA.fullmatch(str(rebuilt.get("sha256", ""))):
        _fail("distribution receipt omits its independently rebuilt wheel identity")
    qualification = value.get("qualification")
    if not isinstance(qualification, list) or not {
        "artifact-inspected",
        "installed-consumer-tested",
    } <= set(qualification):
        _fail("distribution receipt lacks required artifact and consumer checks")


def _validate_doctor(
    value: dict[str, Any], version: str, wheel_name: str, wheel_sha: str, npm_sha: str
) -> dict[str, str]:
    if value.get("schema") != "arras.ui.doctor-installed-qualification.v1":
        _fail("unsupported installed-doctor receipt schema")
    wheel = _object(value.get("wheel"), "doctor.wheel")
    if (wheel.get("filename"), wheel.get("version"), wheel.get("sha256")) != (
        wheel_name,
        version,
        wheel_sha,
    ):
        _fail("doctor receipt is not bound to the selected wheel")
    if value.get("status") != "passed":
        _fail("doctor receipt lacks the required overall passed status")
    doctor_runtime = _inputs.doctor_runtime(value)
    trusted_source = Path(__file__).resolve().parents[2] / "tools/verify_doctor.py"
    expected_source_sha, expected_probe_sha = _inputs.doctor_probe_hashes(trusted_source)
    if value.get("verifier_source_sha256") != expected_source_sha:
        _fail("doctor receipt verifier source digest differs from trusted checkout bytes")
    if value.get("generated_probe_sha256") != expected_probe_sha:
        _fail("doctor receipt probe digest differs from its trusted literal builder")
    if value.get("npm_sha256") != npm_sha:
        _fail("doctor receipt npm identity differs from the selected wheel")
    cases, tripwire, launcher, telemetry, phases = _inputs.doctor_evidence_sections(value)
    if cases != list(_inputs.DOCTOR_CASE_STATUSES):
        _fail("doctor receipt does not contain the complete reviewed 20-case result set")
    if tripwire.get("tripwires") != "passed":
        _fail("doctor side-effect tripwires did not pass")
    for name, expected in _inputs.DOCTOR_TRIPWIRE_STATES.items():
        result = _object(tripwire.get(name), f"doctor tripwire {name}")
        if (result.get("ok"), result.get("complete")) != expected:
            _fail(f"doctor tripwire {name} has an unexpected result")
    if any(launcher.get(name) != "passed" for name in _inputs.DOCTOR_LAUNCHER_PROBES):
        _fail("doctor installed launcher controls are incomplete")
    if (
        telemetry.get("status") != "passed"
        or telemetry.get("generated_probe_sha256") != expected_probe_sha
        or telemetry.get("global_provider_unchanged") is not True
        or telemetry.get("sdk_resource_names") != ["extension-alpha", "extension-beta"]
        or _object(telemetry.get("launcher_effective_names"), "doctor telemetry launcher names")
        != {
            "attribute_namespace": "extension_host",
            "log_prefix": "extension_host",
            "event_prefix": "extension_host",
        }
        or any(telemetry.get(name) != "passed" for name in _inputs.DOCTOR_TELEMETRY_PROBES)
    ):
        _fail("doctor public telemetry controls are incomplete")
    if set(phases) != set(_inputs.DOCTOR_PHASE_SERVICES):
        _fail("doctor telemetry phase coverage is incomplete")
    for name, service in _inputs.DOCTOR_PHASE_SERVICES.items():
        if phases[name].get("service_name") != service:
            _fail(f"doctor telemetry phase {name} is incomplete or misrouted")
    return doctor_runtime


def _validate_binding(
    binding: dict[str, Any],
    cohort_raw: bytes,
    wheel_name: str,
    version: str,
    wheel_sha: str,
    index_sha: str,
) -> None:
    if (
        type(binding.get("schema_version")) is not int
        or binding.get("schema_version") != 1
        or binding.get("status") != "bound"
    ):
        _fail("native binding receipt is not a successful schema-v1 binding")
    wheel = _object(binding.get("wheel"), "binding.wheel")
    if (wheel.get("name"), wheel.get("version"), wheel.get("sha256")) != (
        "arras",
        version,
        wheel_sha,
    ):
        _fail("native binding receipt identifies a different Arras wheel")
    if Path(_string(wheel.get("path"), "binding.wheel.path")).name != wheel_name:
        _fail("native binding receipt wheel path differs from selected release asset")
    links = _object(binding.get("find_links"), "binding.find_links")
    if links.get("sha256") != index_sha:
        _fail("native binding receipt identifies a different companion index")
    _digest(links.get("sha256"), "binding.find_links.sha256")
    manifest = _object(binding.get("bound_manifest"), "binding.bound_manifest")
    if manifest.get("sha256") != _sha(cohort_raw):
        _fail("native binding receipt does not identify the selected bound cohort bytes")


def _validate_native(
    receipt: dict[str, Any],
    cohort: dict[str, Any],
    cohort_sha: str,
    index_sha: str,
    wheel_sha: str,
    version: str,
) -> dict[str, Any]:
    if (
        type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != 1
        or receipt.get("status") != "passed"
    ):
        _fail("native receipt is not a successful schema-v1 qualification")
    _validate_native_sources(receipt, cohort, cohort_sha, index_sha, wheel_sha)
    corpus = _object(receipt.get("corpus"), "native.corpus")
    expected_corpus = cast(dict[str, Any], cohort["corpus"])
    corpus_projection = _native_corpus_projection(corpus, expected_corpus)
    selected = cast(list[dict[str, Any]], cohort["native_wheels"])
    return {
        "schema_version": 1,
        "status": "passed",
        "runtime": cohort["runtime"],
        "native_wheels": [
            {key: row[key] for key in ("distribution", "version", "filename", "url", "sha256")}
            for row in selected
        ],
        "corpus": corpus_projection,
        "cli": {"exit_code": 0},
        "native_binary_scope": _validate_native_scope(receipt.get("native_binary_scope")),
    }


def _validate_native_sources(
    receipt: dict[str, Any], cohort: dict[str, Any], cohort_sha: str, index_sha: str, wheel_sha: str
) -> None:
    cli = _object(receipt.get("cli"), "native.cli")
    if type(cli.get("exit_code")) is not int or cli["exit_code"] != 0:
        _fail("native corpus command did not exit successfully")
    inputs = _object(receipt.get("inputs"), "native.inputs")
    for key, digest in (
        ("arras_wheel", wheel_sha),
        ("cohort", cohort_sha),
        ("find_links", index_sha),
    ):
        item = _object(inputs.get(key), f"native.inputs.{key}")
        if item.get("sha256") != digest:
            _fail(f"native receipt input {key} differs from the selected release evidence")
    if receipt.get("runtime") != cohort["runtime"]:
        _fail("native runtime differs from the bound cohort")
    wheels = receipt.get("native_wheels")
    selected = cast(list[dict[str, Any]], cohort["native_wheels"])
    if not isinstance(wheels, list) or len(wheels) != len(selected):
        _fail("native receipt wheel inventory differs from the bound cohort")
    for observed, wanted in zip(wheels, selected, strict=True):
        row = _object(observed, "native wheel receipt")
        expected_fields = ("distribution", "version", "filename", "url")
        if any(row.get(key) != wanted[key] for key in expected_fields):
            _fail("native receipt selected a different native wheel")
        if row.get("verified_sha256") != wanted["sha256"]:
            _fail("native receipt did not verify selected native wheel bytes")


def _native_corpus_projection(
    corpus: dict[str, Any], expected_corpus: dict[str, Any]
) -> dict[str, Any]:
    if (
        corpus.get("version") != expected_corpus["version"]
        or corpus.get("roles") != expected_corpus["roles"]
    ):
        _fail("native receipt corpus version/roles differ from cohort")
    if _validate_limits(corpus.get("limits")) != _validate_limits(expected_corpus["limits"]):
        _fail("native receipt limits differ from the complete reviewed cohort map")
    applicable = _unique_ids(corpus.get("applicable_case_ids"), "native applicable IDs")
    skipped = _unique_ids(corpus.get("skipped_case_ids"), "native skipped IDs")
    if set(applicable) & set(skipped):
        _fail("native applicable and skipped case IDs overlap")
    results = corpus.get("results")
    if not isinstance(results, list) or not results:
        _fail("native receipt has no applicable corpus results")
    result_ids: list[str] = []
    counts = {"passed": 0, "limit": 0}
    safe_results: list[dict[str, str]] = []
    expected_limits = cast(dict[str, dict[str, str | None]], expected_corpus["limits"])
    for raw in results:
        row = _object(raw, "native result")
        case_id = _string(row.get("case"), "native result case ID")
        status = row.get("status")
        if status not in {"passed", "limit"}:
            _fail("native corpus contains a failed, host-specific, or unknown outcome")
        if status == "limit" and case_id not in expected_limits:
            _fail("native corpus contains an unreviewed limit")
        if status == "passed" and case_id in expected_limits:
            _fail("native corpus passed a case that the cohort deliberately limits")
        result_ids.append(case_id)
        counts[cast(str, status)] += 1
        safe_results.append({"case": case_id, "status": cast(str, status)})
    if len(result_ids) != len(set(result_ids)) or result_ids != applicable:
        _fail("native result IDs are duplicate or differ from applicable IDs")
    if not set(skipped).isdisjoint(result_ids):
        _fail("native skipped IDs overlap applicable results")
    observed_counts = _keys(
        corpus.get("counts"),
        "native corpus counts",
        {"passed", "failed", "harness_error", "limit", "host_specific"},
    )
    expected_counts = {
        "passed": counts["passed"],
        "failed": 0,
        "harness_error": 0,
        "limit": counts["limit"],
        "host_specific": 0,
    }
    if (
        any(
            type(observed_counts[key]) is not int or observed_counts[key] < 0
            for key in expected_counts
        )
        or observed_counts != expected_counts
    ):
        _fail("native corpus counts disagree with the individual result statuses")
    actual_limit_ids = {row["case"] for row in safe_results if row["status"] == "limit"}
    if actual_limit_ids != set(expected_limits):
        _fail("native limit outcomes do not exactly match the reviewed cohort map")
    return {
        "version": expected_corpus["version"],
        "roles": expected_corpus["roles"],
        "applicable_case_ids": applicable,
        "skipped_case_ids": skipped,
        "limits": expected_limits,
        "counts": observed_counts,
        "results": safe_results,
    }


def _validate_consumer(
    value: dict[str, Any], wheel_name: str, wheel_sha: str, version: str
) -> dict[str, Any]:
    if type(value.get("schema_version")) is not int or value.get("schema_version") != 1:
        _fail("consumer receipt has unsupported schema")
    wheel = _object(value.get("arras_wheel"), "consumer.arras_wheel")
    if wheel.get("sha256") != wheel_sha:
        _fail("consumer receipt identifies a different Arras wheel")
    env = _object(value.get("environment"), "consumer.environment")
    if (
        env.get("dependency_mode") != "fresh-public-index-resolution"
        or env.get("isolated_imports") is not True
    ):
        _fail(
            "consumer receipt did not use isolated imports and fresh public dependency resolution"
        )
    extension = _object(value.get("extension_host_wheel"), "consumer.extension_host_wheel")
    if not isinstance(extension.get("sha256"), str) or not _SHA.fullmatch(extension["sha256"]):
        _fail("consumer receipt omits the built downstream wheel digest")
    extension_name = _string(extension.get("filename"), "consumer extension-host wheel filename")
    if Path(extension_name).name != extension_name or not extension_name.endswith(".whl"):
        _fail("consumer extension-host wheel filename is unsafe")
    if extension.get("build_backend") != "hatchling via declared pyproject.toml and uv build":
        _fail("consumer package was not built through its declared backend")
    runs = _object(value.get("consumer_runs"), "consumer.consumer_runs")
    for key, resource, count in (("graph", "graph.json", 2), ("seed", "seed.json", 1)):
        run = _object(runs.get(key), f"consumer.{key}")
        if (
            run.get("selected_resource") != resource
            or run.get("module") != "notes"
            or type(run.get("imported")) is not int
            or run.get("imported") != count
        ):
            _fail(f"installed consumer did not load its own {resource}")
        if (
            run.get("imported_by") != "admin"
            or type(run.get("created_by_action")) is not int
            or run.get("created_by_action") != 1
        ):
            _fail(f"installed consumer {resource} attribution/action proof is incomplete")
    pytest = _object(value.get("installed_consumer_test"), "consumer.installed_consumer_test")
    test_counts = _object(pytest.get("counts"), "consumer installed pytest counts")
    if pytest.get("mode") != "isolated pytest against installed distributions":
        _fail("consumer receipt did not run its installed-only pytest")
    if (
        set(test_counts) != {"tests", "errors", "failures", "skipped"}
        or any(type(test_counts.get(key)) is not int for key in test_counts)
        or test_counts.get("tests", 0) <= 0
        or any(test_counts.get(key) != 0 for key in ("errors", "failures", "skipped"))
    ):
        _fail("installed consumer pytest did not pass completely")
    corpus = _object(value.get("memory_corpus"), "consumer.memory_corpus")
    corpus_projection = _consumer_corpus_projection(corpus)
    return {
        "schema_version": 1,
        "status": "passed",
        "version": version,
        "arras_wheel": {"filename": wheel_name, "sha256": wheel_sha},
        "extension_host_wheel": {"filename": extension_name, "sha256": extension["sha256"]},
        "dependency_mode": env["dependency_mode"],
        "installed_consumer_test": {"counts": test_counts},
        "consumer_runs": {
            name: {
                key: run[key]
                for key in (
                    "selected_resource",
                    "module",
                    "imported",
                    "imported_by",
                    "created_by_action",
                )
            }
            for name, run in (
                (name, _object(runs[name], f"consumer.{name}")) for name in ("graph", "seed")
            )
        },
        "memory_corpus": corpus_projection,
    }


def _consumer_corpus_projection(corpus: dict[str, Any]) -> dict[str, Any]:
    if corpus.get("backend") != "memory-store" or corpus.get("newer_corpus") is not False:
        _fail("consumer receipt did not run the supported installed memory corpus")
    if corpus.get("roles") != ["reader", "provider"]:
        _fail("consumer corpus did not select reader/provider roles")
    counts = _object(corpus.get("counts"), "consumer memory corpus counts")
    ids = _unique_ids(
        [_object(item, "consumer corpus result").get("case") for item in corpus.get("results", [])],
        "consumer result IDs",
    )
    results = cast(list[dict[str, Any]], corpus.get("results", []))
    if not ids or any(item.get("status") != "passed" for item in results):
        _fail("consumer memory corpus includes missing or non-passing outcomes")
    skipped = _unique_ids(corpus.get("skipped"), "consumer skipped IDs")
    if set(ids) & set(skipped):
        _fail("consumer memory corpus skipped IDs overlap applicable results")
    corpus_version = corpus.get("corpus_version")
    if type(corpus_version) is not int or corpus_version <= 0:
        _fail("consumer memory corpus version must be a positive integer")
    expected_counts = {
        "passed": len(ids),
        "failed": 0,
        "harness_error": 0,
        "host_specific": 0,
        "limit": 0,
    }
    if (
        set(counts) != set(expected_counts)
        or any(type(counts[key]) is not int or counts[key] < 0 for key in expected_counts)
        or counts != expected_counts
    ):
        _fail("consumer memory corpus counts disagree with its outcomes")
    return {
        "backend": "memory-store",
        "corpus_version": corpus_version,
        "roles": corpus["roles"],
        "counts": counts,
        "applicable_case_ids": ids,
        "skipped_case_ids": skipped,
        "results": [{"case": item["case"], "status": "passed"} for item in results],
    }


_validate_ui = _ui.validate_ui
_validate_ui_projects = _ui._validate_ui_projects
_prepare_ui_inventory = _ui._prepare_ui_inventory
_validate_ui_resources = _ui._validate_ui_resources


def assemble(
    *,
    build_bundle: Path,
    native_receipt_path: Path,
    binding_path: Path,
    cohort_path: Path,
    index_path: Path,
    ui_path: Path,
    consumer_path: Path,
    umf_admission_receipt_path: Path | None = None,
    umf_actions_receipt_path: Path | None = None,
    expected_version: str,
    expected_wheel: str,
    expected_wheel_sha256: str,
    output_dir: Path,
) -> dict[str, Any]:
    version = _version(expected_version)
    wheel_sha = _digest(expected_wheel_sha256, "expected wheel SHA-256")
    if expected_wheel != f"arras-{version}-py3-none-any.whl":
        _fail("expected wheel filename does not match the release version")
    selected, digests, distribution, doctor, npm_name, npm_resources, doctor_runtime = (
        _verify_build(build_bundle, version, expected_wheel, wheel_sha)
    )
    action_required = _action_capability_required(selected[expected_wheel], wheel_sha)
    qualification_rows = [
        ("native receipt", native_receipt_path, MAX_JSON),
        ("binding receipt", binding_path, MAX_JSON),
        ("bound cohort", cohort_path, MAX_JSON),
        ("native index", index_path, MAX_INDEX),
        ("full UI receipt", ui_path, MAX_JSON),
        ("fresh consumer receipt", consumer_path, MAX_JSON),
        *(
            (("UMF admission receipt", umf_admission_receipt_path, MAX_JSON),)
            if umf_admission_receipt_path is not None
            else ()
        ),
        *(
            (("UMF actions receipt", umf_actions_receipt_path, MAX_JSON),)
            if umf_actions_receipt_path is not None
            else ()
        ),
    ]
    selected_inputs = _read_qualification_inputs(tuple(qualification_rows))
    input_paths = [*selected.values(), (build_bundle / "SHA256SUMS").resolve(strict=True)] + [
        row[0] for row in selected_inputs.values()
    ]
    output_dir = _check_output_target(output_dir, build_bundle, input_paths)
    (
        (native_path, native_raw, native_sha),
        (binding_source, binding_raw, binding_sha),
        (cohort_source, cohort_raw, cohort_sha),
        (index_source, index_raw, index_sha),
        (ui_source, ui_raw, ui_sha),
        (consumer_source, consumer_raw, consumer_sha),
    ) = tuple(
        _selected_receipt_bytes(selected_inputs, label)
        for label in (
            "native receipt",
            "binding receipt",
            "bound cohort",
            "native index",
            "full UI receipt",
            "fresh consumer receipt",
        )
    )
    umf_admission, umf_admission_sha = _read_umf_admission(
        version,
        umf_admission_receipt_path,
        wheel_name=expected_wheel,
        wheel_sha=wheel_sha,
        selected_inputs=selected_inputs,
    )
    umf_actions, umf_actions_sha = _read_umf_actions(
        action_required,
        umf_actions_receipt_path,
        wheel_path=selected[expected_wheel],
        wheel_name=expected_wheel,
        wheel_sha=wheel_sha,
        version=version,
        selected_inputs=selected_inputs,
    )
    _ = native_path, binding_source, cohort_source, index_source, consumer_source
    cohort = _parse_json_object(cohort_raw, "bound native cohort")
    _validate_cohort(cohort, version, wheel_sha)
    if cohort["find_links"]["sha256"] != index_sha:
        _fail("native index SHA-256 differs from the bound cohort")
    _validate_index(index_raw, cohort)
    binding = _parse_json_object(binding_raw, "native binding receipt")
    _validate_binding(binding, cohort_raw, expected_wheel, version, wheel_sha, index_sha)
    native = _validate_native(
        _parse_json_object(native_raw, "native receipt"),
        cohort,
        cohort_sha,
        index_sha,
        wheel_sha,
        version,
    )
    ui, ui_sidecars = _validate_ui(
        _parse_json_object(ui_raw, "full UI receipt"),
        ui_source,
        expected_wheel,
        wheel_sha,
        digests[npm_name],
        version,
        npm_resources,
    )
    consumer = _validate_consumer(
        _parse_json_object(consumer_raw, "fresh consumer receipt"),
        expected_wheel,
        wheel_sha,
        version,
    )
    _validate_corpus_parity(native["corpus"], consumer["memory_corpus"])
    source_hashes = _source_evidence_hashes(
        digests,
        native_sha=native_sha,
        binding_sha=binding_sha,
        cohort_sha=cohort_sha,
        index_sha=index_sha,
        ui_sha=ui_sha,
        consumer_sha=consumer_sha,
        ui_sidecars=ui_sidecars,
        umf_admission_sha=umf_admission_sha,
        umf_actions_sha=umf_actions_sha,
    )
    projections = {
        "native-qualification.json": native,
        "native-cohort-binding.json": _public.binding_projection(binding),
        "distribution-verification.json": _public.distribution_projection(
            distribution, digests["distribution-verification.json"]
        ),
        "doctor-installed.json": _public.doctor_projection(
            doctor, digests["doctor-installed.json"]
        ),
        "ui-qualification.json": ui,
        "consumer-qualification.json": consumer,
    }
    component_hashes = {
        name: _sha(_inputs.canonical_json(value)) for name, value in projections.items()
    }
    component_hashes["native-cohort.json"] = cohort_sha
    component_hashes["native-find-links.html"] = index_sha
    if umf_admission is not None:
        component_hashes["umf-admission-installed.json"] = _sha(
            _inputs.canonical_json(umf_admission)
        )
    component_hashes.update(_action_component_hashes(umf_actions))
    component_hashes.update({name: _sha(raw) for name, raw in ui_sidecars.items()})
    aggregate = _public.release_evidence_projection(
        version=version,
        wheel_name=expected_wheel,
        wheel_sha=wheel_sha,
        npm_name=npm_name,
        npm_sha=digests[npm_name],
        source_hashes=source_hashes,
        native=native,
        ui=ui,
        consumer=consumer,
        component_hashes=component_hashes,
        sdist_name=f"arras-{version}.tar.gz",
        sdist_sha=digests[f"arras-{version}.tar.gz"],
        doctor_runtime=doctor_runtime,
        umf_admission=umf_admission,
        umf_actions=umf_actions,
        umf_actions_required=action_required,
    )
    projections["release-evidence.json"] = aggregate
    if umf_admission is not None:
        projections["umf-admission-installed.json"] = umf_admission
    projections.update(_action_projection(umf_actions))
    raw_files = {
        "native-cohort.json": cohort_raw,
        "native-find-links.html": index_raw,
        **ui_sidecars,
    }
    private_receipts = {"distribution-verification.json", "doctor-installed.json"}
    public_selected = {
        name: path for name, path in selected.items() if name not in private_receipts
    }
    _publish_bundle(output_dir, public_selected, projections, raw_files, digests)
    return aggregate


def _validate_corpus_parity(native: dict[str, Any], consumer: dict[str, Any]) -> None:
    for key in (
        "version",
        "roles",
        "applicable_case_ids",
        "skipped_case_ids",
    ):
        consumer_key = "corpus_version" if key == "version" else key
        if native.get(key) != consumer.get(consumer_key):
            _fail(f"native and memory corpus {key} do not describe the same source cohort")


def main(argv: list[str] | None = None) -> int:
    args = _inputs.parse_arguments(argv, __doc__ or "Release evidence assembler")
    try:
        result = assemble(
            build_bundle=args.build_bundle,
            native_receipt_path=args.native_receipt,
            binding_path=args.native_binding,
            cohort_path=args.native_cohort,
            index_path=args.native_index,
            ui_path=args.ui_receipt,
            consumer_path=args.consumer_receipt,
            expected_version=args.expected_version,
            expected_wheel=args.expected_wheel,
            expected_wheel_sha256=args.expected_wheel_sha256,
            umf_admission_receipt_path=args.umf_admission_receipt,
            umf_actions_receipt_path=args.umf_actions_receipt,
            output_dir=args.output_dir,
        )
    except (AssemblyError, OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        print(f"release evidence assembly failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": result["status"], "output_dir": str(args.output_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
