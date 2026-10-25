#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Validate the exact successful Arras release before registry publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from email.parser import Parser
from pathlib import Path
from typing import Any, NoReturn

if __package__:
    from . import _umf_admission_receipt as _umf_receipt
    from . import verify_public_release_assets as _public_assets
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _umf_admission_receipt as _umf_receipt
    import verify_public_release_assets as _public_assets

_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA64 = re.compile(r"[0-9a-f]{64}\Z")
_RUN_ID = re.compile(r"[1-9][0-9]{0,19}\Z")
_DIRECT_REQUIREMENT = re.compile(
    r"^\s*[A-Za-z0-9][A-Za-z0-9._-]*\s*(?:\[[^\]]*\]\s*)?@", re.ASCII
)
_REQUIRED_JOBS = {
    "check": {"check"},
    "truss": {"Truss adapter on PostgreSQL 18.6"},
    "build": {"build"},
    "installed-native": {"Installed native adapter on Linux x86_64"},
    "assemble-evidence": {"assemble-evidence"},
    "ui-qualification": {"UI and packed-theme release qualification"},
    "github-release": {"github-release"},
    "installed-downstream": {"installed-downstream"},
    "downloaded-release": {"Verify anonymous public release bundle"},
}


class RegistryPublicationError(ValueError):
    """An original release run or registry payload cannot be trusted."""


def _fail(message: str) -> NoReturn:
    raise RegistryPublicationError(message)


def _object(value: object, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{description} must be a JSON object")
    return value


def _read_json(path: Path, description: str) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            _fail(f"{description} is missing, non-regular or too large")
        value = _umf_receipt.strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        if isinstance(exc, RegistryPublicationError):
            raise
        _fail(f"{description} is invalid: {type(exc).__name__}")
    return _object(value, description)


def _version(tag: str) -> str:
    match = _TAG.fullmatch(tag)
    if match is None:
        _fail("release tag must be a numeric vX.Y.Z tag")
    return ".".join(match.groups())


def _validate_jobs(jobs: dict[str, Any], version: str) -> None:
    raw = jobs.get("jobs")
    if not isinstance(raw, list) or jobs.get("total_count") != len(raw) or len(raw) > 1000:
        _fail("release run jobs response is incomplete")
    by_name: dict[str, dict[str, Any]] = {}
    for job in raw:
        if not isinstance(job, dict) or not isinstance(job.get("name"), str):
            _fail("release run contains an invalid job record")
        if job["name"] in by_name:
            _fail("release run jobs response contains duplicate names")
        by_name[job["name"]] = job
    required = dict(_REQUIRED_JOBS)
    if _umf_receipt.required_for_version(version):
        required["umf-admission"] = {"Fresh installed UMF admission proof on exact wheel"}
    selected: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for job_id, names in required.items():
        found = names.intersection(by_name)
        if not found:
            missing.append(job_id)
        else:
            selected[job_id] = by_name[next(iter(found))]
    if missing:
        _fail("release run is missing mandatory gates: " + ", ".join(sorted(missing)))
    if any(job.get("conclusion") != "success" for job in selected.values()):
        _fail("a mandatory release gate did not succeed")
    release_steps = selected["github-release"].get("steps")
    if not isinstance(release_steps, list) or not any(
        isinstance(step, dict)
        and step.get("name") == "Create the release"
        and step.get("conclusion") == "success"
        for step in release_steps
    ):
        _fail("the original GitHub release publication step did not succeed")


def _validate_tag(
    tag: str,
    source_sha: str,
    tag_ref: dict[str, Any],
    tag_object: dict[str, Any] | None,
    expected_tag_object_sha: str,
) -> None:
    ref_name = f"refs/tags/{tag}"
    ref = tag_ref.get("ref")
    if ref != ref_name:
        _fail("remote tag ref does not match the requested release tag")
    value = _object(tag_ref.get("object"), "remote tag ref object")
    sha = value.get("sha")
    kind = value.get("type")
    if not isinstance(sha, str) or not _SHA40.fullmatch(sha) or sha != expected_tag_object_sha:
        _fail("remote tag object differs from the immutable release provenance")
    if kind == "commit":
        if tag_object is not None or sha != source_sha:
            _fail("lightweight tag does not identify the release source commit")
    elif kind == "tag":
        if tag_object is None or tag_object.get("sha") != sha or tag_object.get("tag") != tag:
            _fail("annotated tag object identity differs from the release provenance")
        target = _object(tag_object.get("object"), "annotated tag target")
        if target.get("type") != "commit" or target.get("sha") != source_sha:
            _fail("annotated tag no longer targets the recorded release source")
    else:
        _fail("remote tag ref has an unsupported object type")


def _validate_release_assets(release: dict[str, Any], expected_names: set[str], tag: str) -> None:
    if (
        release.get("tag_name") != tag
        or release.get("draft") is not False
        or release.get("prerelease") is not False
    ):
        _fail("GitHub release is absent, draft, prerelease or bound to another tag")
    raw = release.get("assets")
    if not isinstance(raw, list) or len(raw) > 100:
        _fail("GitHub release asset inventory is malformed")
    names: list[str] = []
    for asset in raw:
        if not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
            _fail("GitHub release contains an invalid asset")
        names.append(asset["name"])
    if len(names) != len(set(names)) or set(names) != expected_names:
        _fail("GitHub release asset inventory differs from the verified release bundle")


def _validate_run_identity(
    run: dict[str, Any],
    workflow: dict[str, Any],
    *,
    repository: str,
    default_branch: str,
    requested_run_id: str,
) -> str:
    if not _REPO.fullmatch(repository) or not default_branch:
        _fail("repository or default-branch identity is invalid")
    if not _RUN_ID.fullmatch(requested_run_id):
        _fail("publication run id is malformed")
    run_id = run.get("id")
    if run_id != int(requested_run_id) or str(run_id) != requested_run_id:
        _fail("workflow run response differs from the requested run id")
    repo = _object(run.get("repository"), "workflow run repository")
    if repo.get("full_name") != repository:
        _fail("workflow run belongs to another repository")
    if (
        run.get("path") != ".github/workflows/release.yml"
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("event") not in {"push", "workflow_dispatch"}
    ):
        _fail("workflow run is not a successful completed Arras Release")
    workflow_id = run.get("workflow_id")
    if not isinstance(workflow_id, int) or workflow.get("id") != workflow_id:
        _fail("workflow definition differs from the original run")
    if workflow.get("path") != ".github/workflows/release.yml" or workflow.get("state") != "active":
        _fail("original release workflow path or state is invalid")
    return str(run.get("event"))


def _validate_driver_provenance(
    run: dict[str, Any],
    provenance: dict[str, Any],
    *,
    event: str,
    repository: str,
    default_branch: str,
) -> tuple[str, str, str, str, str, str]:
    driver = _object(provenance.get("driver"), "release driver provenance")
    target = _object(provenance.get("target"), "release target provenance")
    tag = target.get("tag")
    source_sha = target.get("source_sha")
    tag_object_sha = target.get("tag_object_sha")
    version = _version(tag) if isinstance(tag, str) else ""
    driver_sha = driver.get("sha")
    run_attempt = run.get("run_attempt")
    if (
        provenance.get("schema") != "arras.release-driver-provenance.v1"
        or provenance.get("event") != event
        or driver.get("run_id") != str(run.get("id"))
        or str(driver.get("run_attempt")) != str(run_attempt)
        or driver.get("sha") != run.get("head_sha")
        or driver.get("workflow_sha") != driver_sha
        or not isinstance(driver_sha, str)
        or not _SHA40.fullmatch(driver_sha)
        or not isinstance(source_sha, str)
        or not _SHA40.fullmatch(source_sha)
        or not isinstance(tag_object_sha, str)
        or not _SHA40.fullmatch(tag_object_sha)
        or target.get("version") != version
    ):
        _fail("release driver provenance does not bind the original workflow run")
    if event == "push":
        if run.get("head_branch") != tag or driver.get("ref") != f"refs/tags/{tag}":
            _fail("tag-push release provenance refers to another tag")
    else:
        if (
            run.get("head_branch") != default_branch
            or driver.get("ref") != f"refs/heads/{default_branch}"
        ):
            _fail("manual release provenance was not dispatched from the default branch")
    expected_ref = f"{repository}/.github/workflows/release.yml@{driver.get('ref')}"
    if driver.get("workflow_ref") != expected_ref:
        _fail("driver workflow ref differs from the original release event")
    if event == "push" and run.get("head_sha") != source_sha:
        _fail("tag-push run source differs from target source")
    return tag, version, source_sha, tag_object_sha, driver_sha, str(run_attempt)


def _validate_manual_pins(
    *,
    requested_tag: str,
    expected_source_sha: str,
    expected_tag_object_sha: str,
    tag: str,
    source_sha: str,
    tag_object_sha: str,
) -> None:
    if requested_tag and requested_tag != tag:
        _fail("manual release tag does not match the original run")
    if expected_source_sha and expected_source_sha != source_sha:
        _fail("manual source pin differs from the original run")
    if expected_tag_object_sha and expected_tag_object_sha != tag_object_sha:
        _fail("manual tag-object pin differs from the original run")
    for label, value in (
        ("source", expected_source_sha),
        ("tag-object", expected_tag_object_sha),
    ):
        if value and not _SHA40.fullmatch(value):
            _fail(f"manual {label} pin is malformed")


def validate_publication_context(
    run: dict[str, Any],
    jobs: dict[str, Any],
    workflow: dict[str, Any],
    provenance: dict[str, Any],
    tag_ref: dict[str, Any],
    tag_object: dict[str, Any] | None,
    release: dict[str, Any],
    *,
    expected_asset_names: set[str],
    repository: str,
    default_branch: str,
    requested_run_id: str,
    requested_tag: str = "",
    expected_source_sha: str = "",
    expected_tag_object_sha: str = "",
) -> dict[str, str]:
    event = _validate_run_identity(
        run,
        workflow,
        repository=repository,
        default_branch=default_branch,
        requested_run_id=requested_run_id,
    )
    tag, version, source_sha, tag_object_sha, driver_sha, run_attempt = _validate_driver_provenance(
        run,
        provenance,
        event=event,
        repository=repository,
        default_branch=default_branch,
    )
    _validate_manual_pins(
        requested_tag=requested_tag,
        expected_source_sha=expected_source_sha,
        expected_tag_object_sha=expected_tag_object_sha,
        tag=tag,
        source_sha=source_sha,
        tag_object_sha=tag_object_sha,
    )

    _validate_tag(tag, source_sha, tag_ref, tag_object, tag_object_sha)
    _validate_jobs(jobs, version)
    _validate_release_assets(release, expected_asset_names, tag)
    return {
        "tag": tag,
        "version": version,
        "source_sha": source_sha,
        "tag_object_sha": tag_object_sha,
        "driver_sha": driver_sha,
        "run_id": requested_run_id,
        "run_attempt": run_attempt,
        "repository": repository,
    }


def validate_release_inputs(args: argparse.Namespace) -> dict[str, str]:
    run = _read_json(args.run, "original workflow run")
    jobs = _read_json(args.jobs, "original workflow jobs")
    workflow = _read_json(args.workflow, "release workflow definition")
    provenance = _read_json(args.provenance, "release-driver provenance")
    tag_ref = _read_json(args.tag_ref, "remote tag ref")
    tag_object = (
        _read_json(args.tag_object, "remote annotated tag object") if args.tag_object else None
    )
    release = _read_json(args.release, "GitHub release metadata")
    target = _object(provenance.get("target"), "release target provenance")
    tag = target.get("tag")
    version = _version(tag) if isinstance(tag, str) else ""
    wheel = f"arras-{version}-py3-none-any.whl"
    evidence = _read_json(args.assets / "release-evidence.json", "release evidence")
    artifacts = _object(evidence.get("release_artifacts"), "release artifacts")
    wheel_identity = _object(artifacts.get("wheel"), "release wheel identity")
    wheel_sha = wheel_identity.get("sha256")
    if (
        wheel_identity.get("filename") != wheel
        or not isinstance(wheel_sha, str)
        or not _SHA64.fullmatch(wheel_sha)
    ):
        _fail("release evidence has an invalid wheel identity")
    if args.expected_wheel_sha256 and args.expected_wheel_sha256 != wheel_sha:
        _fail("manual wheel digest differs from the verified release artifact")
    sums_path = args.assets / "SHA256SUMS"
    try:
        sums_raw = sums_path.read_bytes()
    except OSError as exc:
        _fail(f"trusted SHA256SUMS cannot be read: {exc.strerror or type(exc).__name__}")
    sums_sha = hashlib.sha256(sums_raw).hexdigest()
    if args.expected_sums_sha256 and args.expected_sums_sha256 != sums_sha:
        _fail("manual SHA256SUMS digest differs from the verified release artifact")
    _, entries = _public_assets._validate_trusted(args.assets, version, wheel, wheel_sha)
    identity = validate_publication_context(
        run,
        jobs,
        workflow,
        provenance,
        tag_ref,
        tag_object,
        release,
        expected_asset_names=set(entries) | {"SHA256SUMS"},
        repository=args.repository,
        default_branch=args.default_branch,
        requested_run_id=args.run_id,
        requested_tag=args.expected_tag,
        expected_source_sha=args.expected_source_sha,
        expected_tag_object_sha=args.expected_tag_object_sha,
    )
    identity.update({"wheel": wheel, "wheel_sha256": wheel_sha, "sums_sha256": sums_sha})
    return identity


def _metadata_files(wheel: Path, sdist: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(wheel) as archive:
            members = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
            if len(members) != 1:
                _fail("wheel must contain exactly one dist-info METADATA")
            if archive.getinfo(members[0]).file_size > 8 * 1024 * 1024:
                _fail("wheel METADATA exceeds its size limit")
            files[wheel.name] = archive.read(members[0])
        with tarfile.open(sdist, "r:gz") as archive:
            members = [
                m for m in archive.getmembers() if m.isfile() and m.name.endswith("/PKG-INFO")
            ]
            if len(members) != 1:
                _fail("sdist must contain exactly one PKG-INFO")
            if members[0].size > 8 * 1024 * 1024:
                _fail("sdist PKG-INFO exceeds its size limit")
            stream = archive.extractfile(members[0])
            if stream is None:
                _fail("sdist PKG-INFO cannot be read")
            files[sdist.name] = stream.read(8 * 1024 * 1024 + 1)
    except (OSError, zipfile.BadZipFile, tarfile.TarError) as exc:
        _fail(f"Python distribution metadata cannot be read: {type(exc).__name__}")
    if any(len(data) > 8 * 1024 * 1024 for data in files.values()):
        _fail("Python distribution metadata exceeds its size limit")
    return files


def pypi_incompatible_direct_requirements(wheel: Path, sdist: Path) -> dict[str, list[str]]:
    incompatible: dict[str, list[str]] = {}
    for filename, data in _metadata_files(wheel, sdist).items():
        try:
            message = Parser().parsestr(data.decode("utf-8"), headersonly=True)
        except UnicodeDecodeError:
            _fail("Python distribution metadata is not UTF-8")
        direct = [
            value
            for value in message.get_all("Requires-Dist", [])
            if _DIRECT_REQUIREMENT.search(value)
        ]
        if direct:
            incompatible[filename] = direct
    return incompatible


def _registry_json(url: str) -> dict[str, Any] | None:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "arras-registry-verifier/1"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                _fail("registry metadata request did not return HTTP 200")
            raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                _fail("registry metadata exceeds its size limit")
            value = _umf_receipt.strict_json_loads(raw.decode("utf-8"))
            return _object(value, "registry metadata")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        _fail(f"registry metadata request failed with HTTP {exc.code}")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        _fail(f"registry metadata request failed: {type(exc).__name__}")


def _download_public(url: str) -> bytes:
    parsed = urllib.parse.urlparse(url)
    allowed_hosts = {"registry.npmjs.org", "files.pythonhosted.org"}
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        _fail("registry returned a tarball URL outside the expected public host")
    request = urllib.request.Request(url, headers={"User-Agent": "arras-registry-verifier/1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status != 200:
                _fail("registry tarball request did not return HTTP 200")
            final_url = urllib.parse.urlparse(response.geturl())
            if final_url.scheme != "https" or final_url.hostname not in allowed_hosts:
                _fail("registry tarball redirected outside the expected public host")
            data = response.read(512 * 1024 * 1024 + 1)
    except (OSError, urllib.error.URLError) as exc:
        _fail(f"registry tarball request failed: {type(exc).__name__}")
    if len(data) > 512 * 1024 * 1024:
        _fail("registry tarball exceeds its size limit")
    return data


def check_npm_registry(package: str, version: str, expected_sha256: str) -> str:
    if package != "@documentdrivendx/arras-ui" or not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+", version
    ):
        _fail("npm package or version is not the reviewed Arras UI target")
    if not _SHA64.fullmatch(expected_sha256):
        _fail("npm expected digest is malformed")
    encoded_package = urllib.parse.quote(package, safe="")
    value = _registry_json(f"https://registry.npmjs.org/{encoded_package}/{version}")
    if value is None:
        return "absent"
    if value.get("name") != package or value.get("version") != version:
        _fail("npm registry response identifies a different package version")
    dist = _object(value.get("dist"), "npm dist metadata")
    tarball_url = dist.get("tarball")
    if not isinstance(tarball_url, str):
        _fail("npm registry metadata has no tarball URL")
    actual = hashlib.sha256(_download_public(tarball_url)).hexdigest()
    if actual != expected_sha256:
        _fail("npm version collision: registry bytes differ from the verified release tarball")
    return "matching"


def check_pypi_registry(package: str, version: str, expected_files: dict[str, str]) -> str:
    if package != "arras" or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        _fail("PyPI package or version is not the reviewed Arras target")
    if not expected_files or any(
        not _SHA64.fullmatch(digest) for digest in expected_files.values()
    ):
        _fail("PyPI expected file inventory is malformed")
    value = _registry_json(f"https://pypi.org/pypi/{package}/{version}/json")
    if value is None:
        return "absent"
    info = _object(value.get("info"), "PyPI package info")
    if info.get("name") != package or info.get("version") != version:
        _fail("PyPI registry response identifies a different package version")
    urls = value.get("urls")
    if not isinstance(urls, list):
        _fail("PyPI registry metadata has no release file inventory")
    actual: dict[str, str] = {}
    for item in urls:
        if not isinstance(item, dict) or not isinstance(item.get("filename"), str):
            _fail("PyPI registry metadata contains an invalid file record")
        if item["filename"] in actual:
            _fail("PyPI registry metadata contains a duplicate filename")
        digests = _object(item.get("digests"), "PyPI file digests")
        digest = digests.get("sha256")
        if not isinstance(digest, str) or not _SHA64.fullmatch(digest):
            _fail("PyPI registry metadata contains an invalid SHA-256")
        actual[item["filename"]] = digest
    if actual != expected_files:
        _fail(
            "PyPI version collision: registry file inventory or bytes differ from release artifacts"
        )
    for item in urls:
        filename = item["filename"]
        url = item.get("url")
        if (
            not isinstance(url, str)
            or hashlib.sha256(_download_public(url)).hexdigest() != expected_files[filename]
        ):
            _fail(
                "PyPI version collision: served registry file bytes differ from the verified release"
            )
    return "matching"


def wait_for_registry_match(check: Any, timeout_seconds: int = 180) -> str:
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 180:
        _fail("registry visibility timeout must be from 1 to 180 seconds")
    deadline = time.monotonic() + timeout_seconds
    while True:
        status = check()
        if status == "matching":
            return status
        if status != "absent":
            _fail("registry checker returned an unsupported visibility state")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _fail("registry did not expose the exact published bytes before the visibility timeout")
        time.sleep(min(5, remaining))


def _print_state(value: str, output: Path | None) -> None:
    print(json.dumps({"status": value}, sort_keys=True))
    if output is not None:
        if output.exists() or output.is_symlink():
            _fail("registry result path must be new")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"status": value}, indent=2) + "\n", encoding="utf-8")
    github_output = __import__("os").environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as stream:
            stream.write(f"status={value}\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-release")
    for name in (
        "run",
        "jobs",
        "workflow",
        "provenance",
        "tag-ref",
        "release",
        "assets",
        "output",
    ):
        validate.add_argument(f"--{name}", type=Path, required=True)
    validate.add_argument("--tag-object", type=Path)
    validate.add_argument("--repository", required=True)
    validate.add_argument("--default-branch", required=True)
    validate.add_argument("--run-id", required=True)
    validate.add_argument("--expected-tag", default="")
    validate.add_argument("--expected-source-sha", default="")
    validate.add_argument("--expected-tag-object-sha", default="")
    validate.add_argument("--expected-sums-sha256", default="")
    validate.add_argument("--expected-wheel-sha256", default="")
    metadata = commands.add_parser("pypi-metadata")
    metadata.add_argument("--wheel", type=Path, required=True)
    metadata.add_argument("--sdist", type=Path, required=True)
    npm = commands.add_parser("check-npm")
    npm.add_argument("--version", required=True)
    npm.add_argument("--sha256", required=True)
    npm.add_argument("--output", type=Path)
    npm.add_argument("--wait-for-present", action="store_true")
    npm.add_argument("--visibility-timeout", type=int, default=180)
    pypi = commands.add_parser("check-pypi")
    pypi.add_argument("--version", required=True)
    pypi.add_argument("--expected-files", type=Path, required=True)
    pypi.add_argument("--output", type=Path)
    pypi.add_argument("--wait-for-present", action="store_true")
    pypi.add_argument("--visibility-timeout", type=int, default=180)
    return parser


def _execute(args: argparse.Namespace) -> int:
    try:
        if args.command == "validate-release":
            identity = validate_release_inputs(args)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if args.output.exists() or args.output.is_symlink():
                _fail("release identity output path must be new")
            args.output.write_text(
                json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(json.dumps(identity, sort_keys=True))
        elif args.command == "pypi-metadata":
            incompatible = pypi_incompatible_direct_requirements(args.wheel, args.sdist)
            if incompatible:
                names = ", ".join(sorted(incompatible))
                _fail(f"PyPI rejects direct-URL Requires-Dist metadata in: {names}")
            print(json.dumps({"status": "compatible"}, sort_keys=True))
        elif args.command == "check-npm":
            def check_npm() -> str:
                return check_npm_registry(
                    "@documentdrivendx/arras-ui", args.version, args.sha256
                )

            status = (
                wait_for_registry_match(check_npm, args.visibility_timeout)
                if args.wait_for_present
                else check_npm()
            )
            _print_state(
                status, args.output
            )
        else:
            expected = _read_json(args.expected_files, "expected PyPI file manifest")
            files = expected.get("files")
            if not isinstance(files, dict) or any(
                not isinstance(k, str) or not isinstance(v, str) for k, v in files.items()
            ):
                _fail("expected PyPI file manifest is malformed")
            def check_pypi() -> str:
                return check_pypi_registry("arras", args.version, files)

            status = (
                wait_for_registry_match(check_pypi, args.visibility_timeout)
                if args.wait_for_present
                else check_pypi()
            )
            _print_state(status, args.output)
    except (RegistryPublicationError, OSError) as exc:
        print(f"registry publication validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    return _execute(_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
