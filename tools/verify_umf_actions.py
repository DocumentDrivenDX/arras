#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Verify generated UMF actions from an exact Arras wheel in a fresh environment."""

from __future__ import annotations

import argparse
import base64
import csv
import dataclasses
import email.parser
import hashlib
import json
import os
import platform as host_platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, cast

from _umf_sdk_cohorts import SDKCohort, select_sdk_cohort

SCHEMA = "arras.umf-actions-installed/1"
MAX_WHEEL_BYTES = 64 * 1024 * 1024
MAX_FIXTURE_BYTES = 16 * 1024 * 1024
MAX_RUN_SECONDS = 30 * 60
PUBLIC_INDEX = "https://pypi.org/simple"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_GENERATED_DIST_INFO = {"INSTALLER", "REQUESTED", "direct_url.json", "RECORD"}
_FIXTURE_HASHES = {
    "source.json": "5b79b3dba5ebc52ac9452f85a75411dab5edaa34154adda76f872a53c21d0818",
    "vectors.json": "c811eefac81c4f5ff3a7aa60cbe7f7657f7599040cd0869b2616c450931a950e",
    "current-conformance.json": "bb008a98b8448050748e65f867e7863475ccad9501a5b9229ae9e6d336691544",
}


class VerificationError(RuntimeError):
    """A bounded proof failure that does not include package, path, or SDK prose."""

    def __init__(self, stage: str, code: str) -> None:
        self.stage = stage
        self.code = code
        self.cleanup_status = "not_started"
        super().__init__(f"{stage}: {code}")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _regular(path: Path, stage: str) -> Path:
    try:
        info = path.lstat()
    except OSError as error:
        raise VerificationError(stage, "input-unavailable") from error
    if path.is_symlink() or not path.is_file() or info.st_size > MAX_WHEEL_BYTES:
        raise VerificationError(stage, "input-not-regular-or-over-limit")
    return path.resolve(strict=True)


def _member(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or "\x00" in name
        or "\\" in name
        or path.is_absolute()
        or any(p in ("", ".", "..") for p in path.parts)
        or any(part == "" for part in name.split("/"))
    ):
        raise VerificationError("wheel", "unsafe-member-path")


def _wheel_members(path: Path) -> dict[str, bytes]:
    if path.stat().st_size > MAX_WHEEL_BYTES:
        raise VerificationError("wheel", "wheel-over-limit")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = [item for item in archive.infolist() if not item.is_dir()]
            if len(infos) > 100_000 or sum(item.file_size for item in infos) > MAX_WHEEL_BYTES:
                raise VerificationError("wheel", "wheel-payload-over-limit")
            members: dict[str, bytes] = {}
            for item in infos:
                _member(item.filename)
                if item.external_attr >> 16 & 0o170000 == 0o120000:
                    raise VerificationError("wheel", "symlink-wheel-member")
                if item.filename in members:
                    raise VerificationError("wheel", "duplicate-wheel-member")
                members[item.filename] = archive.read(item)
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise VerificationError("wheel", "invalid-wheel-archive") from error
    return members


def _verify_record(members: dict[str, bytes]) -> None:
    record_paths = [name for name in members if name.endswith(".dist-info/RECORD")]
    if len(record_paths) != 1:
        raise VerificationError("wheel", "wheel-metadata-inventory-invalid")
    try:
        rows = list(csv.reader(members[record_paths[0]].decode("utf-8").splitlines()))
    except (UnicodeDecodeError, csv.Error) as error:
        raise VerificationError("wheel", "invalid-wheel-metadata-or-record") from error
    seen: set[str] = set()
    for row in rows:
        if len(row) != 3:
            raise VerificationError("wheel", "invalid-record-row")
        name, digest, size = row
        _member(name)
        if name in seen or name not in members:
            raise VerificationError("wheel", "record-inventory-invalid")
        seen.add(name)
        if name.endswith(".dist-info/RECORD"):
            if digest or size:
                raise VerificationError("wheel", "record-self-hash-present")
            continue
        encoded = base64.urlsafe_b64encode(hashlib.sha256(members[name]).digest())
        if (
            not digest.startswith("sha256=")
            or digest.removeprefix("sha256=") != encoded.rstrip(b"=").decode("ascii")
            or not size.isdigit()
            or int(size) != len(members[name])
        ):
            raise VerificationError("wheel", "record-content-mismatch")
    if seen != set(members):
        raise VerificationError("wheel", "record-inventory-mismatch")
    return


def _metadata(path: Path, expected_name: str) -> tuple[email.message.Message, dict[str, bytes]]:
    members = _wheel_members(path)
    metadata_paths = [name for name in members if name.endswith(".dist-info/METADATA")]
    if len(metadata_paths) != 1:
        raise VerificationError("wheel", "wheel-metadata-inventory-invalid")
    _verify_record(members)
    try:
        metadata = email.parser.Parser().parsestr(members[metadata_paths[0]].decode("utf-8"))
    except UnicodeDecodeError as error:
        raise VerificationError("wheel", "invalid-wheel-metadata-or-record") from error
    normalized = metadata.get("Name", "").lower().replace("_", "-")
    if normalized != expected_name:
        raise VerificationError("wheel", "unexpected-distribution")
    version = metadata.get("Version", "")
    if not _VERSION.fullmatch(version):
        raise VerificationError("wheel", "invalid-version")
    if expected_name == "arras" and path.name != f"arras-{version}-py3-none-any.whl":
        raise VerificationError("wheel", "unexpected-arras-wheel-identity")
    if expected_name == "umf-core" and not path.name.startswith(f"umf_core-{version}-"):
        raise VerificationError("wheel", "unexpected-umf-wheel-identity")
    return metadata, members


def _public_cohort(metadata: email.message.Message) -> SDKCohort:
    try:
        return select_sdk_cohort(
            metadata,
            platform=sys.platform,
            machine=host_platform.machine(),
        )
    except ValueError as error:
        raise VerificationError("arras-wheel", "umf-extra-cohort-invalid") from error


def _fixture(repository: Path, name: str) -> bytes:
    paths = {
        "source.json": repository / "tests/fixtures/umf-actions-binding/source.json",
        "vectors.json": repository / "tests/fixtures/umf-actions-binding/vectors.json",
        "current-conformance.json": repository
        / "tests/fixtures/umf-core-reference/current-conformance.json",
    }
    path = paths[name]
    try:
        info = path.lstat()
        if path.is_symlink() or not path.is_file() or info.st_size > MAX_FIXTURE_BYTES:
            raise VerificationError("fixtures", "fixture-not-regular-or-over-limit")
        data = path.read_bytes()
    except OSError as error:
        raise VerificationError("fixtures", "fixture-unavailable") from error
    if _sha_bytes(data) != _FIXTURE_HASHES[name]:
        raise VerificationError("fixtures", "fixture-digest-mismatch")
    return data


def _run(
    command: list[str], *, cwd: Path, env: dict[str, str], stage: str
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command, cwd=cwd, env=env, capture_output=True, text=True, timeout=MAX_RUN_SECONDS
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise VerificationError(stage, "command-unavailable-or-timed-out") from error
    if (
        len(result.stdout.encode("utf-8")) > 1024 * 1024
        or len(result.stderr.encode("utf-8")) > 1024 * 1024
    ):
        raise VerificationError(stage, "command-output-over-limit")
    if result.returncode:
        raise VerificationError(stage, "command-failed")
    return result


def _install_report(path: Path, *, url: str, digest: str) -> None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        installed = value["install"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise VerificationError("install", "pip-report-invalid") from error
    matches = []
    for item in installed:
        if not isinstance(item, dict) or not isinstance(item.get("metadata"), dict):
            continue
        if str(item["metadata"].get("name", "")).lower().replace("_", "-") != "umf-core":
            continue
        info = item.get("download_info")
        archive = info.get("archive_info") if isinstance(info, dict) else None
        hashes = archive.get("hashes") if isinstance(archive, dict) else None
        if isinstance(info, dict) and isinstance(hashes, dict):
            matches.append((info.get("url"), hashes.get("sha256")))
    if matches != [(url, digest)]:
        raise VerificationError("install", "umf-extra-resolution-mismatch")


def _download(url: str, digest: str, destination: Path) -> None:
    try:
        with urllib.request.urlopen(url, timeout=60) as response, destination.open("xb") as out:
            total = 0
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > MAX_WHEEL_BYTES:
                    raise VerificationError("umf-download", "wheel-over-limit")
                out.write(block)
    except VerificationError:
        raise
    except OSError as error:
        raise VerificationError("umf-download", "artifact-unavailable") from error
    if _sha_file(destination) != digest:
        raise VerificationError("umf-download", "artifact-digest-mismatch")


def _venv(python: Path, target: Path, cwd: Path, env: dict[str, str]) -> Path:
    _run([str(python), "-I", "-m", "venv", str(target)], cwd=cwd, env=env, stage="venv")
    result = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not result.is_file():
        raise VerificationError("venv", "python-missing")
    return result


def _install_public(
    python: Path, wheel: Path, temp: Path, env: dict[str, str], report: Path
) -> None:
    requirement = f"arras[umf] @ {wheel.as_uri()}"
    _run(
        [
            str(python),
            "-I",
            "-m",
            "pip",
            "install",
            "--isolated",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            "--index-url",
            PUBLIC_INDEX,
            "--report",
            str(report),
            requirement,
        ],
        cwd=temp,
        env=env,
        stage="public-extra-install",
    )


def _install_candidate(
    python: Path,
    arras_wheel: Path,
    sdk_wheel: Path,
    metadata: email.message.Message,
    temp: Path,
    env: dict[str, str],
) -> None:
    requirements = [line.strip() for line in metadata.get_all("Requires-Dist", [])]
    base: list[str] = []
    for line in requirements:
        if re.match(r"^umf-core\s*@", line, re.IGNORECASE) or ";" in line:
            continue
        if ";" in line or not line.lower().startswith("graphql-core"):
            raise VerificationError("candidate-install", "unsupported-base-requirement")
        base.append(line)
    if not base:
        raise VerificationError("candidate-install", "base-requirement-missing")
    _run(
        [str(python), "-I", "-m", "pip", "install", "--isolated", "--no-deps", str(arras_wheel)],
        cwd=temp,
        env=env,
        stage="candidate-arras-install",
    )
    _run(
        [
            str(python),
            "-I",
            "-m",
            "pip",
            "install",
            "--isolated",
            "--only-binary=:all:",
            "--index-url",
            PUBLIC_INDEX,
            *base,
        ],
        cwd=temp,
        env=env,
        stage="candidate-base-dependencies",
    )
    _run(
        [
            str(python),
            "-I",
            "-m",
            "pip",
            "install",
            "--isolated",
            "--only-binary=:all:",
            "--index-url",
            PUBLIC_INDEX,
            str(sdk_wheel),
        ],
        cwd=temp,
        env=env,
        stage="candidate-sdk-install",
    )


def _json_result(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise VerificationError("probe", "probe-json-invalid") from error
    if not isinstance(value, dict):
        raise VerificationError("probe", "probe-result-not-object")
    return cast(dict[str, Any], value)


def _validate_probe(
    value: dict[str, Any], *, arras_sha: str, arras_version: str, sdk_sha: str, sdk_version: str
) -> dict[str, Any]:
    controls = {
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
    expected_keys = {
        "status",
        "skipped",
        "arras_wheel_sha256",
        "umf_wheel_sha256",
        "source_sha256",
        "vectors_sha256",
        "runtime",
        "origins",
        "installed",
        "generated_client_sha256",
        "controls",
        "corpus",
    }
    if set(value) != expected_keys:
        raise VerificationError("probe", "probe-result-shape-invalid")
    runtime = value.get("runtime")
    origins = value.get("origins")
    installed = value.get("installed")
    corpus = value.get("corpus")
    if (
        not isinstance(runtime, dict)
        or set(runtime) != {"python", "platform"}
        or not all(
            type(runtime.get(key)) is str and _VERSION.fullmatch(runtime[key]) for key in runtime
        )
        or not isinstance(origins, dict)
        or set(origins) != {"arras", "umf", "umf.action_runtime", "umf.rust_codegen"}
        or not all(_safe_origin(item, module) for module, item in origins.items())
        or not isinstance(installed, dict)
        or set(installed) != {"arras", "umf_core"}
        or not isinstance(corpus, dict)
        or set(corpus) != {"cases", "reference_matches", "empty_registry_matches"}
    ):
        raise VerificationError("probe", "probe-result-shape-invalid")
    for distribution in installed.values():
        if (
            not isinstance(distribution, dict)
            or set(distribution)
            != {
                "name",
                "version",
                "payload_files",
                "payload_sha256",
                "record_matches",
                "resource_files",
                "resource_manifest_sha256",
                "native_files",
                "native_manifest_sha256",
            }
            or type(distribution["name"]) is not str
            or not _VERSION.fullmatch(distribution["name"])
            or type(distribution["version"]) is not str
            or not _VERSION.fullmatch(distribution["version"])
            or type(distribution["payload_files"]) is not int
            or distribution["payload_files"] <= 0
            or type(distribution["record_matches"]) is not int
            or distribution["record_matches"] != distribution["payload_files"]
            or type(distribution["payload_sha256"]) is not str
            or not _SHA.fullmatch(distribution["payload_sha256"])
            or type(distribution["resource_files"]) is not int
            or distribution["resource_files"] < 0
            or type(distribution["resource_manifest_sha256"]) is not str
            or not _SHA.fullmatch(distribution["resource_manifest_sha256"])
            or type(distribution["native_files"]) is not int
            or distribution["native_files"] < 0
            or type(distribution["native_manifest_sha256"]) is not str
            or not _SHA.fullmatch(distribution["native_manifest_sha256"])
        ):
            raise VerificationError("probe", "installed-payload-result-invalid")
    if (
        value.get("status") != "passed"
        or set(value.get("controls", {})) != controls
        or any(item is not True for item in value["controls"].values())
        or type(value.get("skipped")) is not int
        or value["skipped"] != 0
        or corpus != {"cases": 139, "reference_matches": 139, "empty_registry_matches": 139}
        or value.get("arras_wheel_sha256") != arras_sha
        or value.get("umf_wheel_sha256") != sdk_sha
        or value.get("source_sha256") != _FIXTURE_HASHES["source.json"]
        or value.get("vectors_sha256") != _FIXTURE_HASHES["vectors.json"]
        or type(value.get("generated_client_sha256")) is not str
        or not _SHA.fullmatch(value["generated_client_sha256"])
        or installed["arras"]["name"] != "arras"
        or installed["umf_core"]["name"] != "umf-core"
        or installed["arras"]["version"] != arras_version
        or installed["umf_core"]["version"] != sdk_version
    ):
        raise VerificationError("probe", "control-inventory-or-corpus-incomplete")
    return {
        "runtime": dict(runtime),
        "origins": dict(origins),
        "installed": {key: dict(item) for key, item in installed.items()},
        "generated_client_sha256": value["generated_client_sha256"],
        "controls": {key: True for key in sorted(controls)},
        "corpus": dict(corpus),
    }


def _safe_origin(value: object, module: str) -> bool:
    prefixes = {
        "arras": "arras/",
        "umf": "umf/",
        "umf.action_runtime": "umf/action_runtime",
        "umf.rust_codegen": "umf/rust_codegen",
    }
    return (
        type(value) is str
        and len(value) <= 256
        and value.startswith(prefixes[module])
        and re.fullmatch(r"[A-Za-z0-9_./-]+", value) is not None
        and ".." not in PurePosixPath(value).parts
        and not PurePosixPath(value).is_absolute()
    )


def _gate_fields(candidate: Path | None, candidate_sha: str | None) -> dict[str, Any]:
    if candidate is None:
        return {"public_gate": True, "mode": "public-extra", "candidate_override": None}
    if candidate_sha is None or not _SHA.fullmatch(candidate_sha):
        raise VerificationError("umf-wheel", "candidate-digest-missing")
    return {
        "public_gate": False,
        "mode": "local-candidate",
        "candidate_override": {"sha256": candidate_sha, "public_gate": False},
    }


def verify(
    wheel_path: Path,
    output_path: Path,
    *,
    python_path: Path | None = None,
    umf_wheel_path: Path | None = None,
    umf_sha256: str | None = None,
) -> dict[str, Any]:
    tool_path = Path(__file__).resolve()
    probe_path = tool_path.with_name("_umf_actions_probe.py")
    selector_path = tool_path.with_name("_umf_sdk_cohorts.py")
    source_hashes = (_sha_file(tool_path), _sha_file(probe_path), _sha_file(selector_path))
    prepared = _prepare_inputs(
        wheel_path, output_path, python_path, umf_wheel_path, umf_sha256, source_hashes
    )
    if tuple(_sha_file(path) for path in (tool_path, probe_path, selector_path)) != source_hashes:
        raise VerificationError("tool", "source-changed-during-validation")
    temp = _new_workspace()
    try:
        receipt = _run_proof(prepared, temp)
        shutil.rmtree(temp)
        if temp.exists():
            raise VerificationError("cleanup", "temporary-workspace-remains")
        receipt["cleanup"] = {"completed": True, "fresh_venvs": 1, "shared_site_packages": False}
        return receipt
    except VerificationError as error:
        if temp.exists():
            try:
                shutil.rmtree(temp)
            except OSError:
                error.cleanup_status = "failed"
            else:
                error.cleanup_status = "completed"
        else:
            error.cleanup_status = "completed"
        raise
    except Exception as error:
        cleanup_status = "completed"
        if temp.exists():
            try:
                shutil.rmtree(temp)
            except OSError:
                cleanup_status = "failed"
        failure = VerificationError("internal", "unexpected-verifier-error")
        failure.cleanup_status = cleanup_status
        raise failure from error


@dataclasses.dataclass(frozen=True)
class _Prepared:
    wheel: Path
    wheel_sha: str
    metadata: email.message.Message
    public_url: str
    public_sha: str
    public_cohort: SDKCohort
    sdk_version: str
    candidate: Path | None
    candidate_sha: str | None
    python: Path
    fixtures: dict[str, bytes]
    source_hashes: tuple[str, str, str]


def _prepare_inputs(
    wheel: Path,
    output: Path,
    python: Path | None,
    candidate: Path | None,
    candidate_sha: str | None,
    source_hashes: tuple[str, str, str],
) -> _Prepared:
    repository = Path(__file__).resolve().parents[1]
    wheel = _regular(wheel, "arras-wheel")
    wheel_sha = _sha_file(wheel)
    if (candidate is None) != (candidate_sha is None):
        raise VerificationError("arguments", "candidate-wheel-requires-sha256")
    metadata, _members = _metadata(wheel, "arras")
    if _sha_file(wheel) != wheel_sha:
        raise VerificationError("arras-wheel", "wheel-changed-during-validation")
    public_cohort = _public_cohort(metadata)
    public_url, public_sha = public_cohort.url, public_cohort.sha256
    sdk_version = public_cohort.distribution_version
    if candidate is not None:
        candidate = _regular(candidate, "umf-wheel")
        if (
            candidate_sha is None
            or not _SHA.fullmatch(candidate_sha)
            or _sha_file(candidate) != candidate_sha
        ):
            raise VerificationError("umf-wheel", "candidate-digest-mismatch")
        candidate_metadata, _candidate_members = _metadata(candidate, "umf-core")
        sdk_version = candidate_metadata.get("Version", "")
    output = output.resolve(strict=False)
    for source in (wheel, *((candidate,) if candidate else ())):
        if output == source or (output.exists() and os.path.samefile(output, source)):
            raise VerificationError("arguments", "output-aliases-input")
    fixtures = {name: _fixture(repository, name) for name in _FIXTURE_HASHES}
    return _Prepared(
        wheel,
        wheel_sha,
        metadata,
        public_url,
        public_sha,
        public_cohort,
        sdk_version,
        candidate,
        candidate_sha,
        (python or Path(sys.executable)).resolve(strict=True),
        fixtures,
        source_hashes,
    )


def _new_workspace() -> Path:
    repository = Path(__file__).resolve().parents[1]
    temp = Path(tempfile.mkdtemp(prefix="arras-umf-actions-", dir=Path(tempfile.gettempdir())))
    if temp.resolve().is_relative_to(repository):
        shutil.rmtree(temp, ignore_errors=True)
        raise VerificationError("workspace", "temporary-workspace-inside-checkout")
    return temp


def _run_proof(prepared: _Prepared, temp: Path) -> dict[str, Any]:
    staged_arras = temp / prepared.wheel.name
    shutil.copyfile(prepared.wheel, staged_arras)
    if (
        _sha_file(staged_arras) != prepared.wheel_sha
        or _sha_file(prepared.wheel) != prepared.wheel_sha
    ):
        raise VerificationError("arras-wheel", "wheel-changed-while-staging")
    staged_candidate = _stage_candidate(prepared, temp)
    env = {key: value for key, value in os.environ.items() if not key.startswith(("PIP_", "UV_"))}
    env.update({"PIP_CONFIG_FILE": os.devnull, "PIP_INDEX_URL": PUBLIC_INDEX, "PYTHONPATH": ""})
    venv_python = _venv(prepared.python, temp / "venv", temp, env)
    sdk_path = _install_selected(prepared, staged_arras, staged_candidate, venv_python, temp, env)
    staged_sdk = _stage_sdk(sdk_path, temp, prepared.candidate_sha or prepared.public_sha)
    fixture_paths = _stage_fixtures(prepared.fixtures, temp)
    tool_path = Path(__file__).resolve()
    probe_path = tool_path.with_name("_umf_actions_probe.py")
    selector_path = tool_path.with_name("_umf_sdk_cohorts.py")
    tool_sha, probe_sha, selector_sha = prepared.source_hashes
    result = _execute_probe(
        venv_python, probe_path, staged_arras, staged_sdk, fixture_paths, temp, env
    )
    safe_probe = _validate_probe(
        result,
        arras_sha=prepared.wheel_sha,
        arras_version=prepared.metadata.get("Version", ""),
        sdk_sha=prepared.candidate_sha or prepared.public_sha,
        sdk_version=prepared.sdk_version,
    )
    _check_post_run_identity(
        prepared,
        staged_arras,
        staged_sdk,
        tool_path,
        probe_path,
        selector_path,
        tool_sha,
        probe_sha,
        selector_sha,
    )
    gate = _gate_fields(prepared.candidate, prepared.candidate_sha)
    return {
        "schema": SCHEMA,
        "status": "passed",
        **gate,
        "arras_wheel": {
            "filename": prepared.wheel.name,
            "version": prepared.metadata.get("Version"),
            "sha256": prepared.wheel_sha,
        },
        "umf": {
            "public_extra": dataclasses.asdict(prepared.public_cohort),
            "installed": {"filename": staged_sdk.name, "sha256": _sha_file(staged_sdk)},
            "candidate_override": gate["candidate_override"],
        },
        "fixtures": dict(_FIXTURE_HASHES),
        "tool_sha256": tool_sha,
        "probe_sha256": probe_sha,
        "selector_sha256": selector_sha,
        **safe_probe,
    }


def _stage_candidate(prepared: _Prepared, temp: Path) -> Path | None:
    if prepared.candidate is None:
        return None
    staged = temp / prepared.candidate.name
    shutil.copyfile(prepared.candidate, staged)
    if (
        _sha_file(staged) != prepared.candidate_sha
        or _sha_file(prepared.candidate) != prepared.candidate_sha
    ):
        raise VerificationError("umf-wheel", "wheel-changed-while-staging")
    return staged


def _install_selected(
    prepared: _Prepared,
    arras_wheel: Path,
    candidate_wheel: Path | None,
    python: Path,
    temp: Path,
    env: dict[str, str],
) -> Path:
    if candidate_wheel is not None:
        _install_candidate(python, arras_wheel, candidate_wheel, prepared.metadata, temp, env)
        return candidate_wheel
    report = temp / "pip-install-report.json"
    _install_public(python, arras_wheel, temp, env, report)
    _install_report(report, url=prepared.public_url, digest=prepared.public_sha)
    from urllib.parse import urlsplit

    filename = Path(urlsplit(prepared.public_url).path).name
    if not filename.endswith(".whl") or "/" in filename or "\\" in filename:
        raise VerificationError("umf-download", "wheel-filename-invalid")
    path = temp / filename
    _download(prepared.public_url, prepared.public_sha, path)
    return path


def _stage_sdk(path: Path, temp: Path, expected: str) -> Path:
    staged = temp / path.name
    if staged != path:
        shutil.copyfile(path, staged)
    if _sha_file(staged) != expected:
        raise VerificationError("umf-wheel", "staged-sdk-digest-mismatch")
    return staged


def _stage_fixtures(fixtures: dict[str, bytes], temp: Path) -> list[Path]:
    paths: list[Path] = []
    for name, data in fixtures.items():
        destination = temp / name
        destination.write_bytes(data)
        paths.append(destination)
    return paths


def _execute_probe(
    python: Path,
    probe: Path,
    arras_wheel: Path,
    sdk_wheel: Path,
    fixtures: list[Path],
    temp: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    command = [str(python), "-I", str(probe), "--probe", str(arras_wheel), str(sdk_wheel)]
    command.extend(str(path) for path in fixtures)
    return _json_result(_run(command, cwd=temp, env=env, stage="installed-action-probe"))


def _check_post_run_identity(
    prepared: _Prepared,
    staged_arras: Path,
    staged_sdk: Path,
    tool: Path,
    probe: Path,
    selector: Path,
    tool_sha: str,
    probe_sha: str,
    selector_sha: str,
) -> None:
    if (
        _sha_file(prepared.wheel) != prepared.wheel_sha
        or _sha_file(staged_arras) != prepared.wheel_sha
    ):
        raise VerificationError("arras-wheel", "wheel-changed-during-proof")
    expected_sdk = prepared.candidate_sha or prepared.public_sha
    if _sha_file(staged_sdk) != expected_sdk:
        raise VerificationError("umf-wheel", "wheel-changed-during-proof")
    if prepared.candidate is not None and _sha_file(prepared.candidate) != expected_sdk:
        raise VerificationError("umf-wheel", "wheel-changed-during-proof")
    if (
        _sha_file(tool) != tool_sha
        or _sha_file(probe) != probe_sha
        or _sha_file(selector) != selector_sha
    ):
        raise VerificationError("tool", "source-changed-during-proof")


def _write_receipt(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--python", type=Path)
    parser.add_argument("--umf-wheel", type=Path)
    parser.add_argument("--umf-sha256")
    args = parser.parse_args(argv)
    try:
        receipt = verify(
            args.wheel,
            args.output_json,
            python_path=args.python,
            umf_wheel_path=args.umf_wheel,
            umf_sha256=args.umf_sha256,
        )
    except VerificationError as error:
        safe = {
            "schema": SCHEMA,
            "status": "failed",
            "public_gate": False,
            "attempted_mode": "local-candidate" if args.umf_wheel is not None else "public-extra",
            "failure": {"stage": error.stage, "code": error.code},
            "cleanup": {"status": error.cleanup_status},
            "limitations": ["A failed proof is not qualification."],
        }
        try:
            _write_receipt(args.output_json, safe)
        except OSError:
            pass
        print(f"UMF actions proof failed: {error.stage}:{error.code}", file=sys.stderr)
        return 1
    _write_receipt(args.output_json, receipt)
    print(
        json.dumps({"status": receipt["status"], "receipt": str(args.output_json)}, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
