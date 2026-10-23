#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Verify the optional UMF admission feature from a freshly installed Arras wheel.

The verifier intentionally runs its fixed probes in two new virtual environments. A
successful receipt is an installed-artifact result for the named wheel and runtime;
it is not evidence of a public Arras release, Truss support, or browser behavior.
"""

from __future__ import annotations

import argparse
import base64
import csv
import email.parser
import hashlib
import importlib.util
import json
import os
import platform as host_platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, cast

_PROCESS_HELPER_SHA256 = "07aba19a8d454dd4be6d5fc701340a33daec6dee35812aadad3939352708dd86"


def _load_cohort_selector() -> Any:
    name = "arras_umf_admission_cohorts"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = Path(__file__).resolve().with_name("_umf_sdk_cohorts.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("UMF cohort selector is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_process_helpers() -> Any:
    name = "arras_umf_admission_process"
    path = Path(__file__).resolve().with_name("_umf_admission_process.py")
    if hashlib.sha256(path.read_bytes()).hexdigest() != _PROCESS_HELPER_SHA256:
        raise RuntimeError("UMF verifier process helper failed its source pin")
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("UMF verifier process helpers are unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_COHORTS = _load_cohort_selector()
_PROCESS = _load_process_helpers()
KNOWN_COHORTS = _COHORTS.KNOWN_COHORTS
SDKCohort = _COHORTS.SDKCohort
select_sdk_cohort = _COHORTS.select_sdk_cohort
CORPUS_SHA256 = "bb008a98b8448050748e65f867e7863475ccad9501a5b9229ae9e6d336691544"
METADATA_SHA256 = "da883657baefe7b7a4ab8654f78e7d84ef1e281eea7bc7cee48f8662007cd687"
SCHEMA = "arras.umf-admission-installed/1"
MAX_WHEEL_BYTES = 64 * 1024 * 1024
MAX_CORPUS_BYTES = 16 * 1024 * 1024
MAX_RUN_SECONDS = 30 * 60
PUBLIC_INDEX = "https://pypi.org/simple"
_NAME_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_GENERATED_DIST_INFO = {"INSTALLER", "REQUESTED", "direct_url.json", "RECORD"}


class VerificationError(RuntimeError):
    """A bounded proof failure with a stable stage and no source-derived detail."""

    def __init__(self, stage: str, code: str, *, details: dict[str, Any] | None = None) -> None:
        self.stage = stage
        self.code = code
        self.details = details or {}
        super().__init__(f"{stage}: {code}")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_fixed_fixture(path: Path, *, limit: int, digest: str, stage: str) -> bytes:
    try:
        metadata = path.lstat()
        if path.is_symlink() or not path.is_file() or metadata.st_size > limit:
            raise VerificationError(stage, "fixture-not-regular-or-over-limit")
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
    except OSError as error:
        raise VerificationError(stage, "fixture-unavailable") from error
    if len(raw) > limit or _sha256_bytes(raw) != digest:
        raise VerificationError(stage, "fixture-digest-mismatch")
    return raw


def _require_regular_file(path: Path, stage: str) -> Path:
    try:
        stat = path.lstat()
    except OSError as error:
        raise VerificationError(stage, "input-unavailable") from error
    if path.is_symlink() or not path.is_file() or stat.st_size > MAX_WHEEL_BYTES:
        raise VerificationError(stage, "input-not-regular-or-over-limit")
    return path.resolve(strict=True)


def _ensure_output_distinct(output: Path, inputs: tuple[Path, ...]) -> None:
    resolved = output.resolve(strict=False)
    for item in inputs:
        candidate = item.resolve(strict=False)
        if resolved == candidate:
            raise VerificationError("arguments", "output-aliases-input")
        if output.exists() and candidate.exists():
            try:
                if os.path.samefile(output, candidate):
                    raise VerificationError("arguments", "output-aliases-input")
            except OSError as error:
                raise VerificationError("arguments", "cannot-check-output-alias") from error


def _safe_member(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise VerificationError("wheel", "unsafe-member-path")


def _verify_record(members: dict[str, bytes], record: bytes) -> int:
    try:
        rows = list(csv.reader(record.decode("utf-8").splitlines()))
    except (UnicodeDecodeError, csv.Error) as error:
        raise VerificationError("wheel", "invalid-record") from error
    seen: set[str] = set()
    for row in rows:
        if len(row) != 3:
            raise VerificationError("wheel", "invalid-record-row")
        name, digest, size = row
        _safe_member(name)
        if name in seen:
            raise VerificationError("wheel", "duplicate-record-path")
        seen.add(name)
        if name not in members:
            raise VerificationError("wheel", "record-path-missing")
        if name.endswith(".dist-info/RECORD"):
            if digest or size:
                raise VerificationError("wheel", "record-self-hash-present")
            continue
        if not digest.startswith("sha256=") or not size.isdigit():
            raise VerificationError("wheel", "unsupported-record-digest")
        actual_digest = base64.urlsafe_b64encode(hashlib.sha256(members[name]).digest())
        actual_digest = actual_digest.rstrip(b"=").decode("ascii")
        if digest.removeprefix("sha256=") != actual_digest or int(size) != len(members[name]):
            raise VerificationError("wheel", "record-content-mismatch")
    if seen != set(members):
        raise VerificationError("wheel", "record-inventory-mismatch")
    return len(seen)


def _host_cohort(metadata: Any) -> SDKCohort:
    machine = host_platform.machine().lower()
    machine = {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    try:
        return select_sdk_cohort(
            metadata, platform=sys.platform, machine=machine, registry=KNOWN_COHORTS
        )
    except ValueError as error:
        raise VerificationError("arras-wheel", "optional-extra-not-pinned") from error


def _wheel_members(path: Path) -> tuple[dict[str, bytes], Any, Any, bytes]:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            files = [info for info in infos if not info.is_dir()]
            if len(files) > 100_000 or sum(info.file_size for info in files) > MAX_WHEEL_BYTES:
                raise VerificationError("wheel", "wheel-payload-over-limit")
            members: dict[str, bytes] = {}
            for info in files:
                _safe_member(info.filename)
                if info.filename in members:
                    raise VerificationError("wheel", "duplicate-wheel-member")
                members[info.filename] = archive.read(info)
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise VerificationError("wheel", "invalid-wheel-archive") from error
    metadata_paths = [name for name in members if name.endswith(".dist-info/METADATA")]
    wheel_paths = [name for name in members if name.endswith(".dist-info/WHEEL")]
    record_paths = [name for name in members if name.endswith(".dist-info/RECORD")]
    if len(metadata_paths) != 1 or len(wheel_paths) != 1 or len(record_paths) != 1:
        raise VerificationError("wheel", "wheel-metadata-inventory-invalid")
    metadata = email.parser.Parser().parsestr(members[metadata_paths[0]].decode("utf-8"))
    wheel_metadata = email.parser.Parser().parsestr(members[wheel_paths[0]].decode("utf-8"))
    return members, metadata, wheel_metadata, members[record_paths[0]]


def _wheel_cohort(
    path: Path,
    *,
    expected: str,
    normalized: str,
    version: str,
    digest: str,
    metadata: Any,
    cohort: SDKCohort | None,
) -> SDKCohort | None:
    if expected == "arras":
        if normalized != "arras" or path.name != f"arras-{version}-py3-none-any.whl":
            raise VerificationError("arras-wheel", "unexpected-distribution-identity")
        return _host_cohort(metadata)
    if normalized != "umf-core":
        raise VerificationError("umf-wheel", "unexpected-distribution-identity")
    if cohort is None:
        matches = [row for row in KNOWN_COHORTS if row.filename == path.name]
        cohort = matches[0] if len(matches) == 1 else None
    if (
        cohort is None
        or path.name != cohort.filename
        or version != cohort.distribution_version
        or digest != cohort.sha256
    ):
        raise VerificationError("umf-wheel", "unexpected-official-artifact")
    return cohort


def _wheel_details(path: Path, *, expected: str, cohort: SDKCohort | None = None) -> dict[str, Any]:
    if path.stat().st_size > MAX_WHEEL_BYTES:
        raise VerificationError("wheel", "wheel-over-limit")
    digest = _sha256_file(path)
    if expected == "umf" and cohort is None:
        named = [row for row in KNOWN_COHORTS if row.filename == path.name]
        if len(named) == 1 and digest != named[0].sha256:
            raise VerificationError("umf-wheel", "unexpected-official-artifact")
    members, metadata, wheel_metadata, record = _wheel_members(path)
    name = metadata.get("Name", "")
    version = metadata.get("Version", "")
    normalized = re.sub(r"[-_.]+", "-", name).lower()
    if not _NAME_VERSION.fullmatch(version):
        raise VerificationError("wheel", "invalid-version-metadata")
    cohort = _wheel_cohort(
        path,
        expected=expected,
        normalized=normalized,
        version=version,
        digest=digest,
        metadata=metadata,
        cohort=cohort,
    )
    is_pure = wheel_metadata.get("Root-Is-Purelib", "").lower() == "true"
    if expected == "umf" and cohort is not None:
        if is_pure != (cohort.platform == "any"):
            raise VerificationError("wheel", "wheel-purity-differs-from-cohort")
    elif not is_pure:
        raise VerificationError("wheel", "non-pure-wheel")
    records = _verify_record(members, record)
    return {
        "filename": path.name,
        "name": normalized,
        "version": version,
        "sha256": digest,
        "record_entries": records,
        "metadata": metadata,
        "member_names": tuple(members),
        "members": members,
        "sdk_cohort": cohort,
    }


def _validate_corpus(raw: bytes) -> tuple[dict[str, Any], tuple[str, ...]]:
    if _sha256_bytes(raw) != CORPUS_SHA256 or len(raw) > MAX_CORPUS_BYTES:
        raise VerificationError("corpus", "fixture-digest-mismatch")
    try:
        corpus = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError("corpus", "invalid-json") from error
    if not isinstance(corpus, dict) or corpus.get("profile") != "umf.current-conformance/1":
        raise VerificationError("corpus", "unexpected-corpus-profile")
    if corpus.get("currentVersion") != "0.10.0":
        raise VerificationError("corpus", "unexpected-corpus-version")
    cases = corpus.get("cases")
    if not isinstance(cases, list) or len(cases) != 139:
        raise VerificationError("corpus", "unexpected-case-count")
    ids: list[str] = []
    for case in cases:
        if not isinstance(case, dict):
            raise VerificationError("corpus", "invalid-case")
        case_id = case.get("id")
        if type(case_id) is not str or not case_id or not isinstance(case.get("document"), dict):
            raise VerificationError("corpus", "invalid-case-identity-or-document")
        if type(case.get("valid")) is not bool or type(case.get("complete")) is not bool:
            raise VerificationError("corpus", "invalid-case-expectation")
        if not isinstance(case.get("diagnostics"), list):
            raise VerificationError("corpus", "invalid-case-diagnostics")
        ids.append(case_id)
    if len(set(ids)) != len(ids):
        raise VerificationError("corpus", "duplicate-case-id")
    return cast(dict[str, Any], corpus), tuple(ids)


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    stage: str,
    timeout: int = MAX_RUN_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return _PROCESS.run(
        command,
        cwd=cwd,
        env=env,
        stage=stage,
        timeout=timeout,
        error_type=VerificationError,
    )


def _json_from(result: subprocess.CompletedProcess[str], stage: str) -> dict[str, Any]:
    return _PROCESS.json_from(result, stage, error_type=VerificationError)


def _install_requirement(
    python: Path,
    arras_wheel: Path,
    *,
    extra: bool,
    cwd: Path,
    env: dict[str, str],
    report: Path,
) -> None:
    requirement = f"arras{'[umf]' if extra else ''} @ {arras_wheel.as_uri()}"
    _run(
        [
            str(python),
            "-I",
            "-m",
            "pip",
            "install",
            "--isolated",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "--index-url",
            PUBLIC_INDEX,
            "--report",
            str(report),
            requirement,
        ],
        cwd=cwd,
        env=env,
        stage="install-arras-extra" if extra else "install-arras-base",
    )


def _check_install_report(path: Path, cohort: SDKCohort) -> None:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        installed = report["install"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise VerificationError("install-report", "invalid-pip-install-report") from error
    sdk_items = [
        item
        for item in installed
        if isinstance(item, dict)
        and isinstance(item.get("metadata"), dict)
        and str(item["metadata"].get("name", "")).lower() == "umf-core"
    ]
    if len(sdk_items) != 1:
        raise VerificationError("install-report", "optional-engine-not-selected")
    info = sdk_items[0].get("download_info")
    hashes = info.get("archive_info", {}).get("hashes", {}) if isinstance(info, dict) else {}
    if (
        not isinstance(info, dict)
        or info.get("url") != cohort.url
        or hashes.get("sha256") != cohort.sha256
    ):
        raise VerificationError("install-report", "optional-engine-source-mismatch")


def _probe(
    mode: str,
    python: Path,
    *,
    cwd: Path,
    env: dict[str, str],
    arguments: list[str],
) -> dict[str, Any]:
    probe_script = Path(__file__).resolve().with_name("_umf_admission_probe.py")
    result = _run(
        [str(python), "-I", str(probe_script), "--_probe", mode, *arguments],
        cwd=cwd,
        env=env,
        stage=f"{mode}-probe",
    )
    value = _json_from(result, f"{mode}-probe")
    (cwd / f"{mode}-probe-result.json").write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return value


def _validate_probe(
    result: dict[str, Any], mode: str, expected_ids: tuple[str, ...] | None = None
) -> None:
    if result.get("status") != "passed" or result.get("mode") != mode:
        raise VerificationError(f"{mode}-probe", "controls-did-not-pass")
    controls = result.get("controls")
    expected_controls = {
        "base": {
            "legacy_registration_document_and_empty_read",
            "base_has_no_umf_distribution",
            "base_imported_no_umf",
            "admission_refuses_missing_engine",
            "projection_refuses_missing_engine",
            "selected_host_refuses_without_fallback",
        },
        "extra": {
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
        },
    }[mode]
    if (
        not isinstance(controls, dict)
        or set(controls) != expected_controls
        or any(value is not True for value in controls.values())
    ):
        raise VerificationError(f"{mode}-probe", "control-inventory-incomplete")
    if mode == "extra":
        corpus = result.get("corpus")
        if not isinstance(corpus, dict):
            raise VerificationError("extra-probe", "corpus-result-missing")
        ids = corpus.get("ordered_case_ids")
        if (
            corpus.get("status") != "passed"
            or type(corpus.get("case_count")) is not int
            or corpus["case_count"] != 139
            or type(corpus.get("unique_id_count")) is not int
            or corpus["unique_id_count"] != 139
            or type(corpus.get("reference_matches")) is not int
            or corpus["reference_matches"] != 139
            or type(corpus.get("empty_registry_matches")) is not int
            or corpus["empty_registry_matches"] != 139
            or type(corpus.get("skipped")) is not int
            or corpus["skipped"] != 0
            or not isinstance(ids, list)
            or len(ids) != 139
            or any(type(item) is not str or not item for item in ids)
            or len(set(ids)) != 139
            or expected_ids is None
            or tuple(ids) != expected_ids
            or corpus.get("fixture_sha256") != CORPUS_SHA256
        ):
            raise VerificationError("extra-probe", "corpus-coverage-incomplete")
    payload = result.get("payload")
    if not isinstance(payload, dict):
        raise VerificationError(f"{mode}-probe", "payload-parity-missing")
    payload_key = "arras_exact_files"
    payload_count = payload.get(payload_key)
    if type(payload_count) is not int or payload_count <= 0:
        raise VerificationError(f"{mode}-probe", "payload-parity-incomplete")


def _source_sha256s() -> tuple[str, str, str]:
    helper_path = Path(__file__).resolve().with_name("_umf_admission_process.py")
    if _sha256_file(helper_path) != _PROCESS_HELPER_SHA256:
        raise VerificationError("tool", "process-helper-source-changed")
    here = Path(__file__).resolve().parent
    return _PROCESS.source_hashes(
        here / "verify_umf_admission.py",
        here / "_umf_admission_probe.py",
        here / "_umf_sdk_cohorts.py",
    )


def _remove_owned_temp(path: Path) -> None:
    _PROCESS.remove_owned_temp(path, error_type=VerificationError)


def _create_venv(python: Path, destination: Path, temp: Path, env: dict[str, str]) -> Path:
    _run(
        [str(python), "-I", "-m", "venv", str(destination)],
        cwd=temp,
        env=env,
        stage="create-venv",
        timeout=120,
    )
    executable = destination / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not executable.is_file():
        raise VerificationError("create-venv", "selected-interpreter-venv-missing")
    return executable


def _python_identity(python: Path, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    return _PROCESS.python_identity(
        python,
        cwd,
        env,
        error_type=VerificationError,
        run_timeout=MAX_RUN_SECONDS,
    )


def _download_umf(destination: Path, cohort: SDKCohort) -> Path:
    try:
        with (
            urllib.request.urlopen(cohort.url, timeout=60) as response,
            destination.open("wb") as out,
        ):
            total = 0
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > MAX_WHEEL_BYTES:
                    raise VerificationError("umf-download", "wheel-over-limit")
                out.write(block)
    except VerificationError:
        raise
    except OSError as error:
        raise VerificationError("umf-download", "public-artifact-unavailable") from error
    return destination


def _make_receipt(
    arras: dict[str, Any],
    umf: dict[str, Any],
    corpus_ids: tuple[str, ...],
    metadata_digest: str,
    base: dict[str, Any],
    extra: dict[str, Any],
    runtime: dict[str, str],
    cleanup: dict[str, Any],
    qualification_phase: str,
    source_sha256s: tuple[str, str, str],
) -> dict[str, Any]:
    tool_sha, probe_sha, selector_sha = source_sha256s
    receipt = {
        "schema": SCHEMA,
        "status": "passed",
        "qualification_scope": "installed-wheel-umf-admission/1",
        "qualification_phase": qualification_phase,
        "arras_wheel": {
            "filename": arras["filename"],
            "version": arras["version"],
            "sha256": arras["sha256"],
            "record_entries": arras["record_entries"],
        },
        "umf_wheel": {
            "filename": umf["filename"],
            "version": umf["version"],
            "sha256": umf["sha256"],
            "url": umf["sdk_cohort"].url,
            "source_mode": umf["source_mode"],
            "record_entries": umf["record_entries"],
        },
        "tool_sha256": tool_sha,
        "fixed_probe_sha256": probe_sha,
        "fixtures": {
            "official_corpus_sha256": CORPUS_SHA256,
            "official_corpus_case_count": 139,
            "ordered_case_ids": list(corpus_ids),
            "metadata_fixture_sha256": metadata_digest,
        },
        "runtime": runtime,
        "environments": {"base": base, "extra": extra},
        "corpus": {
            "status": "passed",
            "fixture_sha256": CORPUS_SHA256,
            "case_count": 139,
            "unique_id_count": 139,
            "ordered_case_ids": list(corpus_ids),
            "reference_matches": 139,
            "empty_registry_matches": 139,
            "skipped": 0,
        },
        "controls": {
            "base": base["controls"],
            "extra": extra["controls"],
        },
        "cleanup": cleanup,
        "limitations": [
            "This proves only the named installed wheel and runtime.",
            "This does not qualify native Truss, browser, UI, or production behavior.",
        ],
    }
    receipt["selector_sha256"] = selector_sha
    return receipt


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _failed_receipt(stage: str, code: str, *, wheel: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "failed",
        "failure": {"stage": stage, "code": code},
        "arras_wheel": None
        if wheel is None
        else {
            "filename": wheel["filename"],
            "version": wheel["version"],
            "sha256": wheel["sha256"],
        },
        "qualification_scope": "installed-wheel-umf-admission/1",
        "limitations": ["A failed proof is not qualification."],
    }


def _probe_installed_mode(
    mode: str,
    *,
    selected_python: Path,
    staged_arras: Path,
    sdk_path: Path,
    repository: Path,
    corpus_path: Path,
    metadata_path: Path,
    ordered_ids: tuple[str, ...],
    temp: Path,
    env: dict[str, str],
    arras_version: str,
    cohort: SDKCohort,
) -> dict[str, Any]:
    root = temp / mode
    python = _create_venv(selected_python, root, temp, env)
    report = temp / f"{mode}-install-report.json"
    _install_requirement(
        python,
        staged_arras,
        extra=mode == "extra",
        cwd=temp,
        env=env,
        report=report,
    )
    if mode == "extra":
        _check_install_report(report, cohort)
        arguments = [
            str(repository),
            str(corpus_path),
            str(metadata_path),
            str(staged_arras),
            str(sdk_path),
            cohort.filename,
            cohort.distribution_version,
            cohort.url,
            cohort.sha256,
        ]
    else:
        arguments = [str(repository), str(metadata_path), str(staged_arras)]
    probe = _probe(mode, python, cwd=temp, env=env, arguments=arguments)
    _validate_probe(probe, mode, ordered_ids if mode == "extra" else None)
    if probe.get("arras_version") != arras_version:
        raise VerificationError(f"{mode}-probe", "installed-arras-version-mismatch")
    if mode == "extra" and (
        probe.get("umf_version") != cohort.distribution_version
        or probe.get("umf_sha256") != cohort.sha256
    ):
        raise VerificationError("extra-probe", "installed-wheel-identity-mismatch")
    return probe


def _check_staged_identity(path: Path, expected: str, stage: str) -> None:
    if _sha256_file(path) != expected:
        raise VerificationError(stage, "staged-artifact-changed")


def _run_fresh_proof(
    *,
    arras_path: Path,
    arras: dict[str, Any],
    corpus_raw: bytes,
    ordered_ids: tuple[str, ...],
    metadata_raw: bytes,
    metadata_digest: str,
    repository: Path,
    selected_python: Path,
    umf_path: Path | None,
    temp: Path,
    env: dict[str, str],
    qualification_phase: str,
    source_sha256s: tuple[str, str, str],
) -> dict[str, Any]:
    env["ARRAS_PRIVATE_DIAGNOSTICS"] = str(temp / "private-diagnostics")
    runtime = _python_identity(selected_python, temp, env)
    if runtime["implementation"] != "CPython" or tuple(
        int(part) for part in runtime["version"].split(".")[:2]
    ) < (3, 11):
        raise VerificationError("python", "requires-cpython-3.11-or-newer")
    cohort = arras["sdk_cohort"]
    runtime_machine = runtime["machine"].lower()
    runtime_machine = {"amd64": "x86_64", "aarch64": "arm64"}.get(runtime_machine, runtime_machine)
    if cohort.platform != "any" and (
        runtime["platform"] != cohort.platform or runtime_machine != cohort.machine
    ):
        raise VerificationError("python", "runtime-differs-from-selected-sdk-cohort")
    sdk_path = temp / cohort.filename
    if umf_path is None:
        _download_umf(sdk_path, cohort)
        source_mode = "pinned-public-url"
    else:
        shutil.copyfile(umf_path, sdk_path)
        source_mode = "provided-local-pinned-artifact"
    umf = _wheel_details(sdk_path, expected="umf", cohort=cohort)
    umf["source_mode"] = source_mode

    staged_arras = temp / arras_path.name
    shutil.copyfile(arras_path, staged_arras)
    staged_details = _wheel_details(staged_arras, expected="arras")
    if staged_details["sha256"] != arras["sha256"]:
        raise VerificationError("arras-wheel", "staged-wheel-digest-mismatch")
    corpus_path = temp / "current-conformance.json"
    metadata_path = temp / "primary-string-record.json"
    corpus_path.write_bytes(corpus_raw)
    metadata_path.write_bytes(metadata_raw)

    base = _probe_installed_mode(
        "base",
        selected_python=selected_python,
        staged_arras=staged_arras,
        sdk_path=sdk_path,
        repository=repository,
        corpus_path=corpus_path,
        metadata_path=metadata_path,
        ordered_ids=ordered_ids,
        temp=temp,
        env=env,
        arras_version=arras["version"],
        cohort=cohort,
    )
    extra = _probe_installed_mode(
        "extra",
        selected_python=selected_python,
        staged_arras=staged_arras,
        sdk_path=sdk_path,
        repository=repository,
        corpus_path=corpus_path,
        metadata_path=metadata_path,
        ordered_ids=ordered_ids,
        temp=temp,
        env=env,
        arras_version=arras["version"],
        cohort=cohort,
    )
    _check_staged_identity(staged_arras, arras["sha256"], "arras-wheel")
    _check_staged_identity(sdk_path, cohort.sha256, "umf-wheel")
    if _source_sha256s() != source_sha256s:
        raise VerificationError("tool", "source-changed-during-proof")
    return _make_receipt(
        arras,
        umf,
        ordered_ids,
        metadata_digest,
        base,
        extra,
        runtime,
        {"completed": True, "fresh_environments": 2, "shared_site_packages": False},
        qualification_phase,
        source_sha256s,
    )


def verify(
    arras_path: Path,
    *,
    umf_path: Path | None = None,
    python_path: Path | None = None,
    qualification_phase: str = "local-installed",
) -> dict[str, Any]:
    source_sha256s = _source_sha256s()
    if qualification_phase not in {"local-installed", "release-build", "public-download"}:
        raise VerificationError("arguments", "unsupported-qualification-phase")
    repository = Path(__file__).resolve().parents[1]
    arras_path = _require_regular_file(arras_path, "arras-wheel")
    if umf_path is not None:
        umf_path = _require_regular_file(umf_path, "umf-wheel")
    selected_python = (python_path or Path(sys.executable)).resolve(strict=True)
    if not selected_python.is_file():
        raise VerificationError("python", "selected-interpreter-not-file")
    corpus_path, metadata_path = _PROCESS.fixture_paths(repository)
    arras = _wheel_details(arras_path, expected="arras")
    if _source_sha256s() != source_sha256s:
        raise VerificationError("tool", "source-changed-during-selection")
    corpus_raw = _read_fixed_fixture(
        corpus_path,
        limit=MAX_CORPUS_BYTES,
        digest=CORPUS_SHA256,
        stage="corpus",
    )
    corpus, ordered_ids = _validate_corpus(corpus_raw)
    metadata_raw = _read_fixed_fixture(
        metadata_path,
        limit=MAX_CORPUS_BYTES,
        digest=METADATA_SHA256,
        stage="metadata-fixture",
    )
    metadata_digest = _sha256_bytes(metadata_raw)
    temp_parent = Path(tempfile.gettempdir()).resolve()
    temp = Path(tempfile.mkdtemp(prefix="arras-umf-admission-", dir=temp_parent))
    if _PROCESS.inside(temp, repository):
        shutil.rmtree(temp, ignore_errors=True)
        raise VerificationError("workspace", "temporary-environment-inside-checkout")
    preserve_temp = False
    try:
        env = _PROCESS.environment(dict(os.environ), temp, public_index=PUBLIC_INDEX)
        return _run_fresh_proof(
            arras_path=arras_path,
            arras=arras,
            corpus_raw=corpus_raw,
            ordered_ids=ordered_ids,
            metadata_raw=metadata_raw,
            metadata_digest=metadata_digest,
            repository=repository,
            selected_python=selected_python,
            umf_path=umf_path,
            temp=temp,
            env=env,
            qualification_phase=qualification_phase,
            source_sha256s=source_sha256s,
        )
    except VerificationError as error:
        preserve_temp = True
        error.details["private_diagnostics_directory"] = str(temp / "private-diagnostics")
        raise
    except Exception as error:
        preserve_temp = True
        wrapped = VerificationError("verification", type(error).__name__)
        wrapped.details["private_workspace"] = str(temp)
        raise wrapped from error
    finally:
        if not preserve_temp:
            _remove_owned_temp(temp)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--umf-wheel", type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--python", type=Path, help="selected CPython >=3.11")
    parser.add_argument(
        "--qualification-phase",
        choices=("local-installed", "release-build", "public-download"),
        default="local-installed",
    )
    args = parser.parse_args(arguments)
    input_paths = [
        args.wheel,
        Path(__file__).resolve(),
        Path(__file__).with_name("_umf_admission_probe.py"),
    ]
    if args.umf_wheel is not None:
        input_paths.append(args.umf_wheel)
    input_paths.append(args.python or Path(sys.executable))
    repository = Path(__file__).resolve().parents[1]
    input_paths.extend(_PROCESS.fixture_paths(repository))
    try:
        _ensure_output_distinct(args.output_json, tuple(input_paths))
    except VerificationError as error:
        print(f"UMF installed proof refused output: {type(error).__name__}", file=sys.stderr)
        return 1
    try:
        receipt = verify(
            args.wheel,
            umf_path=args.umf_wheel,
            python_path=args.python,
            qualification_phase=args.qualification_phase,
        )
    except VerificationError as error:
        _atomic_json(args.output_json, _failed_receipt(error.stage, error.code, wheel=None))
        print(f"UMF installed proof failed at {error.stage}: {error.code}", file=sys.stderr)
        private_path = error.details.get("private_workspace") or error.details.get(
            "private_diagnostics_directory"
        )
        if private_path:
            print(f"Private failure evidence retained at {private_path}", file=sys.stderr)
        return 1
    _atomic_json(args.output_json, receipt)
    print(
        json.dumps({"status": receipt["status"], "receipt": str(args.output_json)}, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
