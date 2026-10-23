#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Qualify the installed Truss harness against one exact, hash-pinned public cohort."""

from __future__ import annotations

import argparse
import email
import hashlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, NoReturn, cast

if __package__:
    from ._native_artifacts import ArtifactError, https_url
    from ._native_artifacts import verify_find_links as _verify_find_links
    from ._native_install import command as install_command
    from ._native_payload import PayloadError, classify_native, verify_payload_parity
    from ._native_process import ProcessTimeout, owned_postmaster_files, run_owned, temp_parent
else:
    from _native_artifacts import ArtifactError, https_url
    from _native_artifacts import verify_find_links as _verify_find_links
    from _native_install import command as install_command
    from _native_payload import PayloadError, classify_native, verify_payload_parity
    from _native_process import ProcessTimeout, owned_postmaster_files, run_owned, temp_parent

PUBLIC_INDEX = "https://pypi.org/simple"
REQUIRED_NATIVE = {"truss-toolkit", "weft-sql", "pgserver-pg18"}
STATUS_NAMES = ("passed", "failed", "harness_error", "limit", "host_specific")
DEFAULT_CONFORMANCE_TIMEOUT_SECONDS = 35 * 60
MIN_CONFORMANCE_TIMEOUT_SECONDS = 1
MAX_CONFORMANCE_TIMEOUT_SECONDS = 2 * 60 * 60
_SHA = re.compile(r"^[0-9a-f]{64}$")


class VerificationError(ValueError):
    """A cohort or installed-artifact check failed."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


def _fail(message: str) -> NoReturn:
    raise VerificationError(message)


def validate_conformance_timeout(value: object) -> int:
    """Validate the caller-selected deadline without accepting bools or coercions."""
    if type(value) is not int:
        _fail("conformance timeout must be an integer number of seconds")
    if not MIN_CONFORMANCE_TIMEOUT_SECONDS <= value <= MAX_CONFORMANCE_TIMEOUT_SECONDS:
        _fail(
            "conformance timeout must be between "
            f"{MIN_CONFORMANCE_TIMEOUT_SECONDS} and {MAX_CONFORMANCE_TIMEOUT_SECONDS} seconds"
        )
    return value


def _conformance_timeout_argument(value: str) -> int:
    if re.fullmatch(r"-?[0-9]+", value) is None:
        raise argparse.ArgumentTypeError("must be an integer number of seconds")
    try:
        return validate_conformance_timeout(int(value))
    except VerificationError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _receipt_default(value: object) -> str:
    """Retain validated filesystem observations on the failure path, too."""
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"unsupported receipt value: {type(value).__name__}")


def _canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _mapping(value: object, label: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} must contain exactly {sorted(keys)}")
    mapping = cast(dict[str, Any], value)
    if set(mapping) != keys:
        _fail(f"{label} must contain exactly {sorted(keys)}")
    return mapping


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{label} must be a nonempty string")
    return value


def _digest(value: object, label: str) -> str:
    result = _string(value, label)
    if _SHA.fullmatch(result) is None:
        _fail(f"{label} must be a lowercase SHA-256 hex digest")
    return result


def validate_cohort(value: object) -> dict[str, Any]:
    cohort = _mapping(
        value,
        "cohort",
        {"schema_version", "arras", "runtime", "find_links", "native_wheels", "corpus"},
    )
    if type(cohort["schema_version"]) is not int or cohort["schema_version"] != 1:
        _fail("unsupported cohort schema_version")
    arras = _mapping(cohort["arras"], "arras", {"version", "sha256"})
    _string(arras["version"], "arras.version")
    _digest(arras["sha256"], "arras.sha256")
    runtime = _mapping(cohort["runtime"], "runtime", {"python", "sys_platform", "machine"})
    if runtime["python"] != "3.11":
        _fail("cohort runtime.python must be '3.11'")
    _string(runtime["sys_platform"], "runtime.sys_platform")
    _string(runtime["machine"], "runtime.machine")
    find_links = _mapping(cohort["find_links"], "find_links", {"sha256"})
    _digest(find_links["sha256"], "find_links.sha256")

    _validate_native_wheels(cohort["native_wheels"])
    _validate_corpus(cohort["corpus"])
    return cohort


def _validate_native_wheels(value: object) -> None:
    if not isinstance(value, list) or not value:
        _fail("native_wheels must be a nonempty list")
    wheels = cast(list[Any], value)
    names: set[str] = set()
    filenames: set[str] = set()
    for index, raw in enumerate(wheels):
        label = f"native_wheels[{index}]"
        wheel = _mapping(raw, label, {"distribution", "version", "filename", "url", "sha256"})
        name = _canonical_name(_string(wheel["distribution"], f"{label}.distribution"))
        if name in names:
            _fail(f"duplicate native distribution {name}")
        names.add(name)
        _string(wheel["version"], f"{label}.version")
        filename = _string(wheel["filename"], f"{label}.filename")
        if Path(filename).name != filename or not filename.endswith(".whl"):
            _fail(f"{label}.filename must be a flat .whl filename")
        if filename in filenames:
            _fail(f"duplicate native wheel filename {filename}")
        filenames.add(filename)
        url = _string(wheel["url"], f"{label}.url")
        _https_url(url)
        if Path(urllib.parse.urlsplit(url).path).name != filename:
            _fail(f"{label}.url basename must equal its filename")
        _digest(wheel["sha256"], f"{label}.sha256")
    if not REQUIRED_NATIVE <= names:
        _fail(f"native_wheels must include {sorted(REQUIRED_NATIVE)}")


def _validate_corpus(value: object) -> None:
    corpus = _mapping(value, "corpus", {"version", "roles", "limits"})
    if (
        not isinstance(corpus["version"], int)
        or isinstance(corpus["version"], bool)
        or corpus["version"] <= 0
    ):
        _fail("corpus.version must be a positive integer")
    roles = corpus["roles"]
    if (
        not isinstance(roles, list)
        or roles != ["reader", "provider"]
        or not all(isinstance(role, str) and role for role in cast(list[Any], roles))
    ):
        _fail("corpus.roles must be exactly ['reader', 'provider']")
    limits = corpus["limits"]
    if not isinstance(limits, dict):
        _fail("corpus.limits must be an object (empty means strict all-pass)")
    limits = cast(dict[str, Any], limits)
    for case_id, raw_limit in limits.items():
        _string(case_id, "corpus.limits case id")
        limit = _mapping(raw_limit, f"corpus.limits.{case_id}", {"step", "error", "detail"})
        _string(limit["step"], f"corpus.limits.{case_id}.step")
        _string(limit["error"], f"corpus.limits.{case_id}.error")
        if limit["detail"] is not None and not isinstance(limit["detail"], str):
            _fail(f"corpus.limits.{case_id}.detail must be string or null")


def _https_url(value: str) -> urllib.parse.SplitResult:
    try:
        return https_url(value)
    except ArtifactError as exc:
        _fail(str(exc))


def verify_find_links(path: Path, expected_sha256: str, wheels: list[dict[str, Any]]) -> bytes:
    try:
        return _verify_find_links(path, expected_sha256, wheels)
    except ArtifactError as exc:
        _fail(str(exc))


class _HttpsRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> Any:
        if urllib.parse.urlsplit(newurl).scheme != "https":
            _fail("native wheel download attempted a non-HTTPS redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_verified(wheel: dict[str, Any], output: Path, *, opener: Any = None) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    path = output / wheel["filename"]
    if path.exists():
        _fail(f"duplicate downloaded wheel path {path.name}")
    request = urllib.request.Request(wheel["url"], headers={"User-Agent": "Arras native verifier"})
    client = opener or urllib.request.build_opener(_HttpsRedirect())
    digest = hashlib.sha256()
    size = 0
    try:
        with client.open(request, timeout=60) as response, path.open("xb") as target:
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > 1024 * 1024 * 1024:
                    _fail("native wheel exceeds the 1 GiB download bound")
                digest.update(block)
                target.write(block)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    if digest.hexdigest() != wheel["sha256"]:
        path.unlink(missing_ok=True)
        _fail(f"downloaded wheel digest mismatch for {wheel['filename']}")
    return path


def wheel_metadata(path: Path) -> tuple[str, str, list[str]]:
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                _fail(f"wheel is corrupt: {path.name}")
            names = archive.namelist()
            if len(names) != len(set(names)):
                _fail(f"wheel has duplicate members: {path.name}")
            metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
            if len(metadata) != 1:
                _fail(f"wheel needs one METADATA file: {path.name}")
            message = email.message_from_bytes(archive.read(metadata[0]))
            name, version = message.get("Name"), message.get("Version")
            if not name or not version:
                _fail(f"wheel METADATA omits name/version: {path.name}")
            return name, version, names
    except (OSError, zipfile.BadZipFile) as exc:
        _fail(f"cannot inspect wheel {path}: {exc}")


def verify_wheel_metadata(path: Path, *, distribution: str, version: str) -> None:
    actual_name, actual_version, _ = wheel_metadata(path)
    if _canonical_name(actual_name) != _canonical_name(distribution) or actual_version != version:
        _fail(
            f"wheel metadata mismatch for {path.name}: {actual_name} {actual_version}, "
            f"expected {distribution} {version}"
        )


def _sanitize_environment(base: dict[str, str], cache: Path) -> dict[str, str]:
    env = {
        key: value
        for key, value in base.items()
        if not key.startswith(("PIP_", "UV_", "PYTHON", "LD_", "DYLD_", "PG", "TRUSS_", "WEFT_"))
        and key not in {"VIRTUAL_ENV", "PYTHONUSERBASE", "CONDA_PREFIX", "CONDA_DEFAULT_ENV"}
    }
    env.update(
        {
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_INDEX_URL": PUBLIC_INDEX,
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PYTHONPATH": "",
            "PYTHONNOUSERSITE": "1",
            "ARRAS_REQUIRE_TRUSS": "1",
            "TMPDIR": str(cache.parent / "pg"),
            "TEMP": str(cache.parent / "pg"),
            "TMP": str(cache.parent / "pg"),
            "UV_NO_CONFIG": "1",
            "UV_CACHE_DIR": str(cache),
        }
    )
    return env


def _run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int = DEFAULT_CONFORMANCE_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    try:
        return run_owned(args, cwd=cwd, env=env, timeout=timeout)
    except ProcessTimeout as exc:
        cleanup = (
            f"; owned PostgreSQL state remains under private TMPDIR: {exc.leftovers}"
            if exc.leftovers
            else ""
        )
        raise VerificationError(
            f"owned verifier command timed out after {timeout} seconds and cleanup signal; "
            f"stdout={exc.stdout!r}; stderr={exc.stderr!r}{cleanup}",
            details={
                "process": {
                    "command": args,
                    "timed_out": True,
                    "timeout_seconds": timeout,
                    "stdout": exc.stdout,
                    "stderr": exc.stderr,
                    "remaining_postmaster_pid_files": [str(path) for path in exc.leftovers],
                }
            },
        ) from None


def _interpreter_runtime(python: Path, cwd: Path, env: dict[str, str]) -> dict[str, str]:
    script = "import platform,sys; print(f'{sys.version_info.major}.{sys.version_info.minor}|{sys.platform}|{platform.machine()}')"
    run = _run([str(python), "-I", "-c", script], cwd=cwd, env=env)
    if run.returncode:
        _fail(f"selected Python could not be inspected: {run.stderr[-2000:]}")
    try:
        version, sys_platform, machine = run.stdout.strip().split("|", 2)
    except ValueError:
        _fail("selected Python emitted malformed runtime identity")
    return {"python": version, "sys_platform": sys_platform, "machine": machine}


def _installed_probe(python: Path, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    script = r"""
import hashlib, importlib.metadata as md, json, platform, sys, sysconfig
import arras
from arras.conformance import load_corpus, tags
from arras.conformance.truss import TrussHarness
corpus = load_corpus()
roles = list(TrussHarness.roles)
selected = [case['id'] for case in corpus['cases'] if tags(tuple(roles)) & set(case['tags'])]
skipped = [case['id'] for case in corpus['cases'] if case['id'] not in set(selected)]
limits = {case: {'step': value.step, 'error': value.error, 'detail': value.detail}
          for case, value in TrussHarness.LIMITS.items()}
distributions = {d.metadata['Name']: d.version for d in md.distributions() if d.metadata.get('Name')}
native_files = {}
for dist in md.distributions():
    name = dist.metadata.get('Name')
    if not name:
        continue
    found = []
    for relative in dist.files or ():
        path = dist.locate_file(relative)
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        head = path.open('rb').read(4)
        classification = classify_native(head, suffix, sys.platform)
        if classification is None:
            continue
        binary_format, runtime_native = classification
        found.append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'format': binary_format, 'runtime_native': runtime_native})
    if found:
        native_files[name] = found
print(json.dumps({'python': f'{sys.version_info.major}.{sys.version_info.minor}',
                  'sys_platform': sys.platform, 'machine': platform.machine(),
                  'arras_import': str(arras.__file__),
                  'purelib': sysconfig.get_paths()['purelib'],
                  'platlib': sysconfig.get_paths()['platlib'],
                  'scripts': sysconfig.get_paths()['scripts'],
                  'data': sysconfig.get_paths()['data'],
                  'include': sysconfig.get_paths()['include'],
                  'base': sys.prefix,
                  'executable': sys.executable,
                  'corpus_version': corpus['version'], 'roles': roles,
                  'applicable_case_ids': selected, 'skipped_case_ids': skipped,
                  'limits': limits, 'distributions': distributions,
                  'native_files': native_files}, sort_keys=True))
"""
    script = inspect.getsource(classify_native) + "\n" + script
    run = _run([str(python), "-I", "-c", script], cwd=cwd, env=env)
    if run.returncode:
        _fail(f"installed native probe failed: {run.stderr[-4000:]}")
    try:
        value = json.loads(run.stdout)
    except json.JSONDecodeError as exc:
        _fail(f"installed native probe emitted invalid JSON: {exc}")
    if not isinstance(value, dict):
        _fail("installed native probe did not emit an object")
    return cast(dict[str, Any], value)


def _verify_payload_parity(wheel: Path, roots: dict[str, Path]) -> dict[str, str]:
    try:
        return verify_payload_parity(wheel, roots)
    except PayloadError as exc:
        _fail(str(exc))


def _verify_report(
    report: dict[str, Any], probe: dict[str, Any], corpus: dict[str, Any], cli_status: int
) -> dict[str, int]:
    roles = corpus["roles"]
    expected_ids = probe["applicable_case_ids"]
    expected_skipped = probe["skipped_case_ids"]
    if report.get("backend") != "truss" or report.get("roles") != roles:
        _fail("native CLI report backend or role set differs from the selected cohort")
    if report.get("corpus_version") != corpus["version"] or report.get("newer_corpus") is not False:
        _fail("native CLI report corpus version is incompatible with the selected cohort")
    _validate_case_id_lists(expected_ids, expected_skipped)
    results = _validate_case_results(report, expected_ids, expected_skipped, corpus)
    counts = _validate_report_counts(report, results, corpus)
    if cli_status != 0:
        _fail(f"native CLI exited with status {cli_status}")
    return counts


def _validate_case_results(
    report: dict[str, Any],
    expected_ids: list[str],
    expected_skipped: list[str],
    corpus: dict[str, Any],
) -> list[dict[str, Any]]:
    if report.get("skipped") != expected_skipped:
        _fail("native CLI skipped IDs differ from independently derived IDs")
    results = report.get("results")
    if not isinstance(results, list) or not results:
        _fail("native CLI emitted an empty or malformed case result list")
    result_items = cast(list[Any], results)
    ids: list[Any] = [
        cast(dict[str, Any], item).get("case") if isinstance(item, dict) else None
        for item in result_items
    ]
    if any(not isinstance(case_id, str) or not case_id for case_id in ids):
        _fail("native CLI result case IDs must be nonempty strings")
    if ids != expected_ids or len(ids) != len(set(ids)):
        _fail("native CLI result IDs differ from the independently derived applicable corpus")
    return cast(list[dict[str, Any]], results)


def _validate_case_id_lists(selected: Any, skipped: Any) -> None:
    if not isinstance(selected, list) or not isinstance(skipped, list):
        _fail("independently derived corpus case IDs are malformed")
    labeled_values: list[tuple[str, list[Any]]] = [
        ("applicable", cast(list[Any], selected)),
        ("skipped", cast(list[Any], skipped)),
    ]
    for label, values in labeled_values:
        if any(not isinstance(value, str) or not value for value in values):
            _fail(f"independently derived {label} case IDs must be nonempty strings")
        if len(values) != len(set(values)):
            _fail(f"independently derived {label} case IDs are duplicated")
    if set(cast(list[str], selected)) & set(cast(list[str], skipped)):
        _fail("applicable and skipped corpus case IDs overlap")


def _validate_report_counts(
    report: dict[str, Any], results: list[dict[str, Any]], corpus: dict[str, Any]
) -> dict[str, int]:
    counts = {name: 0 for name in STATUS_NAMES}
    for item in results:
        status = item.get("status")
        if not isinstance(status, str) or status not in counts:
            _fail(f"native CLI returned unknown status {status!r}")
        case_id = item.get("case")
        if status == "host_specific":
            _fail("host_specific cases are not allowed by this native cohort schema")
        if status == "limit" and case_id not in corpus["limits"]:
            _fail(f"unlisted documented limit for {case_id!r}")
        counts[status] += 1
    raw_declared = report.get("counts")
    if not isinstance(raw_declared, dict):
        _fail("native CLI status counts have an invalid shape")
    declared = cast(dict[str, Any], raw_declared)
    if set(declared) != set(STATUS_NAMES):
        _fail("native CLI status counts have an invalid shape")
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in declared.values()):
        _fail("native CLI status counts must be nonnegative integers")
    if declared != counts:
        _fail(f"native CLI status counts disagree with results: {declared!r} != {counts!r}")
    if counts["failed"] or counts["harness_error"]:
        _fail("native CLI reported failed or harness_error cases")
    limits = corpus["limits"]
    actual_limits = {item["case"] for item in results if item.get("status") == "limit"}
    if counts["limit"] != len(limits) or actual_limits != set(limits):
        _fail("native CLI limit outcomes differ from the reviewed cohort allowlist")
    return counts


def _verify_native_inventory(
    native_inventory: object, cohort: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(native_inventory, dict):
        _fail("installed native-file inventory is malformed")
    entries = cast(dict[str, Any], native_inventory)
    native_names = {
        _canonical_name(name) for name, files in entries.items() if _has_runtime_native_file(files)
    }
    selected_names = {_canonical_name(record["distribution"]) for record in cohort["native_wheels"]}
    selected_names.add("arras")
    unselected = native_names - selected_names
    if unselected:
        _fail(
            f"native-bearing installed distributions are absent from the selected cohort: {sorted(unselected)}"
        )
    return cast(dict[str, list[dict[str, Any]]], native_inventory)


def _has_runtime_native_file(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return any(
        isinstance(entry, dict) and cast(dict[str, Any], entry).get("runtime_native") is True
        for entry in cast(list[Any], value)
    )


def _verify_install_report(
    report_path: Path,
    cohort: dict[str, Any],
    wheel_paths: dict[str, Path],
    arras_wheel: Path,
) -> list[dict[str, str]]:
    try:
        payload = json.loads(report_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"pip did not produce an installation report: {exc}")
    if not isinstance(payload, dict):
        _fail("pip installation report is not an object")
    installs = cast(dict[str, Any], payload).get("install")
    if not isinstance(installs, list) or not installs:
        _fail("pip installation report has no installed distributions")
    selected: dict[str, tuple[Path, str]] = {
        _canonical_name(wheel["distribution"]): (wheel_paths[wheel["filename"]], wheel["sha256"])
        for wheel in cohort["native_wheels"]
    }
    selected["arras"] = (arras_wheel, cohort["arras"]["sha256"])
    observed, seen = _inspect_install_records(cast(list[Any], installs), selected)
    if not set(selected) <= seen:
        _fail(f"pip report omitted selected distributions {sorted(set(selected) - seen)}")
    return sorted(observed, key=lambda record: _canonical_name(record["distribution"]))


def _inspect_install_records(
    installs: list[Any], selected: dict[str, tuple[Path, str]]
) -> tuple[list[dict[str, str]], set[str]]:
    observed: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in installs:
        record = _inspect_install_item(item, selected)
        canonical = _canonical_name(record["distribution"])
        if canonical in seen:
            _fail(f"pip report duplicates distribution {record['distribution']}")
        seen.add(canonical)
        observed.append(record)
    return observed, seen


def _inspect_install_item(item: Any, selected: dict[str, tuple[Path, str]]) -> dict[str, str]:
    if not isinstance(item, dict):
        _fail("pip installation report contains a malformed distribution record")
    item = cast(dict[str, Any], item)
    raw_metadata = item.get("metadata")
    if not isinstance(raw_metadata, dict):
        _fail("pip installation report contains a malformed distribution record")
    metadata = cast(dict[str, Any], raw_metadata)
    name, version = metadata.get("name"), metadata.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        _fail("pip installation report omits package identity")
    url, digest = _artifact_identity(item, name)
    selection = selected.get(_canonical_name(name))
    if selection is None:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {
            "pypi.org",
            "files.pythonhosted.org",
        }:
            _fail(f"unselected dependency {name} came from a non-public PyPI artifact URL")
    else:
        selected_path, expected_digest = selection
        actual_path = Path(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).resolve()
        if actual_path != selected_path.resolve():
            _fail(f"pip did not install {name} from the explicitly verified wheel")
        if digest != expected_digest:
            _fail(f"pip report SHA-256 differs for explicitly selected {name}")
    return {"distribution": name, "version": version, "url": url, "sha256": digest}


def _artifact_identity(item: dict[str, Any], name: str) -> tuple[str, str]:
    info = item.get("download_info")
    if not isinstance(info, dict):
        _fail(f"pip report omits artifact origin for {name}")
    info = cast(dict[str, Any], info)
    if not isinstance(info.get("url"), str):
        _fail(f"pip report omits artifact origin for {name}")
    archive = info.get("archive_info")
    if not isinstance(archive, dict):
        _fail(f"pip report omits SHA-256 for {name}")
    hashes = cast(dict[str, Any], archive).get("hashes")
    if not isinstance(hashes, dict):
        _fail(f"pip report omits SHA-256 for {name}")
    hashes = cast(dict[str, Any], hashes)
    digest = hashes.get("sha256")
    if not isinstance(digest, str) or _SHA.fullmatch(digest) is None:
        _fail(f"pip report omits SHA-256 for {name}")
    return cast(str, info["url"]), digest


def verify(
    wheel: Path,
    cohort_path: Path,
    find_links: Path,
    output: Path,
    *,
    python: Path | None = None,
    conformance_timeout_seconds: int = DEFAULT_CONFORMANCE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    selected_timeout = validate_conformance_timeout(conformance_timeout_seconds)
    cohort, wheel, find_links, selected_python, output, receipt = _prepare_inputs(
        wheel, cohort_path, find_links, output, python
    )
    receipt["conformance_timeout_seconds"] = selected_timeout
    temp = Path(tempfile.mkdtemp(prefix="arras-native-", dir=temp_parent()))
    context: dict[str, Any] | None = None
    try:
        context = _provision_and_probe(temp, selected_python, wheel, cohort, find_links)
        context["parity"] = _validate_installed(
            context["probe"], context["venv_python"], wheel, cohort, context["wheel_paths"]
        )
        receipt.update(
            _run_and_record(
                temp,
                context,
                cohort,
                conformance_timeout_seconds=selected_timeout,
            )
        )
        output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        return receipt
    except Exception as exc:
        failure_details = {
            "inputs": receipt["inputs"],
            "conformance_timeout_seconds": selected_timeout,
        }
        if context is not None:
            failure_details["runtime"] = context.get("runtime")
            failure_details["native_wheels"] = context.get("downloaded")
            failure_details["pip_artifacts"] = context.get("install_inventory")
            failure_details["installed_probe"] = context.get("probe")
            failure_details["installed_checks"] = context.get("parity")
        if isinstance(exc, VerificationError):
            failure = exc
            failure.details = {**failure_details, **failure.details}
        else:
            failure = VerificationError(str(exc), details=failure_details)
        leftovers = owned_postmaster_files(temp)
        if leftovers:
            cleanup = {
                "status": "retained_owned_postgresql_state",
                "private_temp_root": str(temp),
                "postmaster_pid_files": [str(path) for path in leftovers],
            }
            failure.details["cleanup"] = cleanup
        if failure is exc:
            raise
        raise failure from exc
    finally:
        if not owned_postmaster_files(temp):
            shutil.rmtree(temp)


def _prepare_inputs(
    wheel: Path, cohort_path: Path, find_links: Path, output: Path, python: Path | None
) -> tuple[dict[str, Any], Path, Path, Path, Path, dict[str, Any]]:
    cohort = validate_cohort(_load_json_unique(cohort_path))
    wheel = wheel.resolve(strict=True)
    if _sha(wheel.read_bytes()) != cohort["arras"]["sha256"]:
        _fail("Arras wheel SHA-256 differs from cohort")
    verify_wheel_metadata(wheel, distribution="arras", version=cohort["arras"]["version"])
    find_links = find_links.resolve(strict=True)
    verify_find_links(find_links, cohort["find_links"]["sha256"], cohort["native_wheels"])
    selected_python = (python or Path(sys.executable)).resolve(strict=True)
    if getattr(os, "geteuid", lambda: 1)() == 0:
        _fail("native qualification refuses to run as root")
    output = output.resolve()
    if _output_aliases_input(output, (wheel, cohort_path.resolve(), find_links, selected_python)):
        _fail("receipt output must not overwrite any selected input")
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema_version": 1,
        "status": "pending",
        "inputs": {
            "arras_wheel": {"path": str(wheel), "sha256": _sha(wheel.read_bytes())},
            "cohort": {
                "path": str(cohort_path.resolve()),
                "sha256": _sha(cohort_path.read_bytes()),
            },
            "find_links": {"path": str(find_links), "sha256": _sha(find_links.read_bytes())},
        },
    }
    return cohort, wheel, find_links, selected_python, output, receipt


def _load_json_unique(path: Path) -> Any:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                _fail(f"duplicate JSON object key {key!r} in {path.name}")
            value[key] = item
        return value

    return json.loads(path.read_text(), object_pairs_hook=unique_pairs)


def _output_aliases_input(output: Path, inputs: tuple[Path, ...]) -> bool:
    resolved = output.resolve()
    for path in inputs:
        if resolved == path.resolve():
            return True
        if output.exists() and path.exists() and os.path.samefile(output, path):
            return True
    return False


def _provision_and_probe(
    temp: Path, selected_python: Path, wheel: Path, cohort: dict[str, Any], find_links: Path
) -> dict[str, Any]:
    cache = temp / "cache"
    cache.mkdir()
    (temp / "pg").mkdir()
    env = _sanitize_environment(dict(os.environ), cache)
    runtime = _interpreter_runtime(selected_python, temp, env)
    if runtime != cohort["runtime"]:
        _fail(f"selected Python runtime {runtime!r} differs from cohort {cohort['runtime']!r}")
    wheel_paths, downloaded = _download_cohort(temp, cohort)
    venv_python = _create_environment(selected_python, temp, env)
    pip_report = temp / "pip-install-report.json"
    install = install_command(
        venv_python,
        wheel,
        cohort,
        wheel_paths,
        pip_report,
        public_index=PUBLIC_INDEX,
        canonical_name=_canonical_name,
    )
    installed = _run(install, cwd=temp, env=env)
    if installed.returncode:
        _fail(
            f"native cohort installation failed:\n{installed.stdout[-4000:]}\n{installed.stderr[-4000:]}"
        )
    install_inventory = _verify_install_report(pip_report, cohort, wheel_paths, wheel)
    probe = _installed_probe(venv_python, temp, env)
    return {
        "env": env,
        "runtime": runtime,
        "wheel_paths": wheel_paths,
        "downloaded": downloaded,
        "venv_python": venv_python,
        "install_inventory": install_inventory,
        "probe": probe,
        "find_links": find_links,
    }


def _download_cohort(
    temp: Path, cohort: dict[str, Any]
) -> tuple[dict[str, Path], list[dict[str, Any]]]:
    wheel_dir = temp / "verified-wheels"
    wheel_paths: dict[str, Path] = {}
    downloaded: list[dict[str, Any]] = []
    for record in cohort["native_wheels"]:
        path = download_verified(record, wheel_dir)
        verify_wheel_metadata(path, distribution=record["distribution"], version=record["version"])
        wheel_paths[record["filename"]] = path
        downloaded.append({**record, "verified_sha256": _sha(path.read_bytes())})
    return wheel_paths, downloaded


def _create_environment(selected_python: Path, temp: Path, env: dict[str, str]) -> Path:
    venv_dir = temp / "venv"
    created = _run([str(selected_python), "-I", "-m", "venv", str(venv_dir)], cwd=temp, env=env)
    if created.returncode:
        _fail(f"could not create the selected Python venv:\n{created.stderr[-3000:]}")
    python = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return python


def _validate_installed(
    probe: dict[str, Any],
    venv_python: Path,
    wheel: Path,
    cohort: dict[str, Any],
    wheel_paths: dict[str, Path],
) -> dict[str, Any]:
    runtime_keys = ("python", "sys_platform", "machine")
    if {key: probe.get(key) for key in runtime_keys} != cohort["runtime"]:
        _fail("installed interpreter runtime differs from cohort")
    corpus = cohort["corpus"]
    if probe.get("corpus_version") != corpus["version"] or probe.get("roles") != corpus["roles"]:
        _fail("installed native harness corpus version or roles differ from cohort")
    if probe.get("limits") != corpus["limits"]:
        _fail("installed TrussHarness.LIMITS differs from the reviewed cohort mapping")
    roots = {
        key: Path(probe[key])
        for key in ("purelib", "platlib", "scripts", "data", "include", "base", "executable")
    }
    imports = Path(str(probe.get("arras_import", ""))).resolve()
    if not any(imports.is_relative_to(roots[key].resolve()) for key in ("purelib", "platlib")):
        _fail("installed Arras import came from outside the fresh environment")
    raw_distributions = probe.get("distributions")
    if not isinstance(raw_distributions, dict):
        _fail("installed distribution inventory is malformed")
    distributions = cast(dict[str, Any], raw_distributions)
    actual_arras = _find_version(distributions, "arras")
    if actual_arras != cohort["arras"]["version"]:
        _fail("installed Arras distribution version differs from the selected wheel")
    actual_versions = _validate_selected_versions(distributions, cohort["native_wheels"])
    native_inventory = _verify_native_inventory(probe.get("native_files"), cohort)
    payloads = {"arras": _verify_payload_parity(wheel, roots)}
    for record in cohort["native_wheels"]:
        payloads[record["distribution"]] = _verify_payload_parity(
            wheel_paths[record["filename"]], roots
        )
    return {
        "roots": roots,
        "native_inventory": native_inventory,
        "payloads": payloads,
        "actual_versions": actual_versions,
    }


def _find_version(distributions: dict[str, Any], target: str) -> Any:
    return next(
        (version for name, version in distributions.items() if _canonical_name(name) == target),
        None,
    )


def _validate_selected_versions(
    distributions: dict[str, Any], wheels: list[dict[str, Any]]
) -> dict[str, str]:
    versions: dict[str, str] = {}
    for record in wheels:
        actual = _find_version(distributions, _canonical_name(record["distribution"]))
        if actual != record["version"]:
            _fail(f"installed {record['distribution']} version {actual!r} differs from cohort")
        versions[record["distribution"]] = cast(str, actual)
    return versions


def _run_and_record(
    temp: Path,
    context: dict[str, Any],
    cohort: dict[str, Any],
    *,
    conformance_timeout_seconds: int = DEFAULT_CONFORMANCE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    selected_timeout = validate_conformance_timeout(conformance_timeout_seconds)
    python, env = context["venv_python"], context["env"]
    cli = _run(
        [str(python), "-I", "-m", "arras.conformance", "--backend", "truss"],
        cwd=temp,
        env=env,
        timeout=selected_timeout,
    )
    cli_evidence: dict[str, Any] = {
        "command": "python -I -m arras.conformance --backend truss",
        "timeout_seconds": selected_timeout,
        "exit_code": cli.returncode,
        "stdout": cli.stdout,
        "stderr": cli.stderr,
    }
    leftovers = owned_postmaster_files(temp)
    if leftovers:
        raise VerificationError(
            f"native harness left PostgreSQL state under private TMPDIR: {leftovers}",
            details={"cli": cli_evidence},
        )
    try:
        report = json.loads(cli.stdout)
    except json.JSONDecodeError as exc:
        raise VerificationError(
            f"native CLI emitted invalid JSON (exit {cli.returncode}): {exc}; {cli.stderr[-2000:]}",
            details={"cli": cli_evidence},
        ) from exc
    if not isinstance(report, dict):
        raise VerificationError(
            "native CLI report is not a JSON object", details={"cli": cli_evidence}
        )
    probe = context["probe"]
    cli_evidence["report"] = report
    try:
        counts = _verify_report(
            cast(dict[str, Any], report), probe, cohort["corpus"], cli.returncode
        )
    except VerificationError as exc:
        raise VerificationError(str(exc), details={"cli": cli_evidence}) from exc
    return {
        "status": "passed",
        "conformance_timeout_seconds": selected_timeout,
        "runtime": context["runtime"],
        "native_wheels": context["downloaded"],
        "installed_distributions": context["parity"]["actual_versions"],
        "all_installed_distributions": dict(sorted(probe["distributions"].items())),
        "native_files": context["parity"]["native_inventory"],
        "pip_artifacts": context["install_inventory"],
        "payload_parity": context["parity"]["payloads"],
        "corpus": {
            "version": probe["corpus_version"],
            "roles": probe["roles"],
            "applicable_case_ids": probe["applicable_case_ids"],
            "skipped_case_ids": probe["skipped_case_ids"],
            "limits": probe["limits"],
            "counts": counts,
            "results": report["results"],
        },
        "cli": {
            "command": cli_evidence["command"],
            "exit_code": cli.returncode,
            "timeout_seconds": selected_timeout,
        },
        "native_binary_scope": {
            "observed": "native files declared by installed Python distributions",
            "system_dynamic_link_audit": "not performed",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--find-links", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument(
        "--python", type=Path, help="Python 3.11 interpreter (defaults to this process)"
    )
    parser.add_argument(
        "--conformance-timeout-seconds",
        type=_conformance_timeout_argument,
        default=DEFAULT_CONFORMANCE_TIMEOUT_SECONDS,
        help=(
            "deadline for the conformance command only "
            f"({MIN_CONFORMANCE_TIMEOUT_SECONDS}..{MAX_CONFORMANCE_TIMEOUT_SECONDS}; "
            f"default {DEFAULT_CONFORMANCE_TIMEOUT_SECONDS})"
        ),
    )
    args = parser.parse_args(argv)
    if _output_aliases_input(
        args.output_json,
        tuple(
            path.resolve()
            for path in (
                args.wheel,
                args.cohort,
                args.find_links,
                args.python or Path(sys.executable),
            )
        ),
    ):
        message = "receipt output must not overwrite any selected input"
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": message,
                    "conformance_timeout_seconds": args.conformance_timeout_seconds,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    try:
        receipt = verify(
            args.wheel,
            args.cohort,
            args.find_links,
            args.output_json,
            python=args.python,
            conformance_timeout_seconds=args.conformance_timeout_seconds,
        )
    except Exception as exc:
        receipt = {
            "schema_version": 1,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "conformance_timeout_seconds": args.conformance_timeout_seconds,
        }
        if isinstance(exc, VerificationError) and exc.details:
            receipt.update(exc.details)
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(receipt, indent=2, sort_keys=True, default=_receipt_default) + "\n"
        )
        print(json.dumps(receipt, sort_keys=True, default=_receipt_default), file=sys.stderr)
        return 1
    print(
        json.dumps({"status": receipt["status"], "receipt": str(args.output_json)}, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
