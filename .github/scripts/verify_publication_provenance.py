#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Fail-closed checks for re-verifying an already published Arras release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, NoReturn

if __package__:
    from . import _umf_admission_receipt as _umf_receipt
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _umf_admission_receipt as _umf_receipt

_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA64 = re.compile(r"[0-9a-f]{64}\Z")
_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
_REQUIRED_JOBS = {
    "check": {"check"},
    "truss": {"Truss adapter on PostgreSQL 18.6"},
    "build": {"build"},
    "installed-native": {"Installed native adapter on Linux x86_64"},
    "assemble-evidence": {"assemble-evidence"},
    "ui-qualification": {"UI and packed-theme release qualification"},
    "github-release": {"github-release"},
}
_MAX_JSON = 8 * 1024 * 1024
_MAX_SUMS = 64 * 1024
_MAX_TOTAL = 1024 * 1024 * 1024


class ProvenanceError(ValueError):
    """The supplied publication identity or its trusted artifact is invalid."""


def _fail(message: str) -> NoReturn:
    raise ProvenanceError(message)


def _json(path: Path, description: str) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_JSON:
            _fail(f"{description} is missing, non-regular, or too large")
        value = _umf_receipt.strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        _fail(f"{description} is invalid: {type(exc).__name__}")
    if not isinstance(value, dict):
        _fail(f"{description} must be a JSON object")
    return value


def validate_inputs(args: argparse.Namespace) -> None:
    if not _TAG.fullmatch(args.release_tag):
        _fail("release tag must be an existing vX.Y.Z tag")
    for name in ("expected_source_sha", "expected_publication_driver_sha"):
        value = getattr(args, name)
        if not isinstance(value, str) or not _SHA40.fullmatch(value):
            _fail(f"{name} must be a full lowercase 40-hex SHA")
    for name in ("expected_sums_sha256", "expected_evidence_sha256", "expected_wheel_sha256"):
        value = getattr(args, name)
        if not isinstance(value, str) or not _SHA64.fullmatch(value):
            _fail(f"{name} must be a full lowercase 64-hex digest")
    if not isinstance(args.expected_tag_object_sha, str) or not _SHA40.fullmatch(
        args.expected_tag_object_sha
    ):
        _fail("expected_tag_object_sha must be a full lowercase 40-hex SHA")
    if not isinstance(args.publication_run_id, str) or not re.fullmatch(
        r"[1-9][0-9]{0,19}", args.publication_run_id
    ):
        _fail("publication run id must be a positive numeric GitHub run id")


def _validate_run_identity(
    run: dict[str, Any],
    workflow: dict[str, Any],
    *,
    repository: str,
    run_id: str,
    tag: str,
    source_sha: str,
    driver_sha: str,
    default_branch: str,
) -> None:
    if not _TAG.fullmatch(tag):
        _fail("release tag is malformed")
    if run.get("id") != int(run_id) or str(run.get("id")) != run_id:
        _fail("publication run response does not match the requested run id")
    run_repository = run.get("repository")
    if not isinstance(run_repository, dict) or run_repository.get("full_name") != repository:
        _fail("publication run belongs to a different repository")
    if run.get("path") != ".github/workflows/release.yml":
        _fail("publication run was not created by the reviewed release workflow")
    if run.get("event") != "workflow_dispatch":
        _fail("publication run is not the expected manual release run")
    if run.get("head_branch") != default_branch:
        _fail("publication run was not dispatched from the repository default branch")
    if run.get("head_sha") != driver_sha or run.get("conclusion") != "failure":
        _fail("publication run driver or expected post-publication conclusion differs")
    if run.get("status") != "completed":
        _fail("publication run has not completed")
    workflow_id = run.get("workflow_id")
    if not isinstance(workflow_id, int) or workflow.get("id") != workflow_id:
        _fail("publication workflow identity differs from the run")
    if workflow.get("path") != ".github/workflows/release.yml" or workflow.get("state") != "active":
        _fail("publication workflow path or state is invalid")
    if not _SHA40.fullmatch(source_sha):
        _fail("source commit identity is malformed")


def _validate_required_jobs(jobs: dict[str, Any], version: str) -> None:
    raw_jobs = jobs.get("jobs")
    if not isinstance(raw_jobs, list) or len(raw_jobs) > 1000:
        _fail("publication jobs response is malformed or incomplete")
    if jobs.get("total_count") != len(raw_jobs):
        _fail("publication jobs response is not complete")
    by_name: dict[str, dict[str, Any]] = {}
    for item in raw_jobs:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            _fail("publication jobs response contains an invalid job")
        name = item["name"]
        if name in by_name:
            _fail("publication jobs response contains duplicate job names")
        by_name[name] = item
    required_jobs = dict(_REQUIRED_JOBS)
    if _umf_receipt.required_for_version(version):
        required_jobs["umf-admission"] = {"Fresh installed UMF admission proof on exact wheel"}
    missing = [
        job_id
        for job_id, possible_names in required_jobs.items()
        if not possible_names.intersection(by_name)
    ]
    if missing:
        _fail("publication run is missing required pre-publication jobs")
    selected_jobs = {
        job_id: by_name[next(iter(possible_names.intersection(by_name)))]
        for job_id, possible_names in required_jobs.items()
    }
    if any(item.get("conclusion") != "success" for item in selected_jobs.values()):
        _fail("a required pre-publication qualification job did not succeed")
    if not any(
        step.get("name") == "Create the release" and step.get("conclusion") == "success"
        for step in selected_jobs["github-release"].get("steps", [])
        if isinstance(step, dict)
    ):
        _fail("the GitHub release publication step did not succeed")


def _required_job_ids(version: str) -> list[str]:
    required_jobs = set(_REQUIRED_JOBS)
    if _umf_receipt.required_for_version(version):
        required_jobs.add("umf-admission")
    return sorted(required_jobs)


def validate_run(
    run: dict[str, Any],
    jobs: dict[str, Any],
    workflow: dict[str, Any],
    *,
    repository: str,
    run_id: str,
    tag: str,
    source_sha: str,
    driver_sha: str,
    default_branch: str,
) -> None:
    _validate_run_identity(
        run,
        workflow,
        repository=repository,
        run_id=run_id,
        tag=tag,
        source_sha=source_sha,
        driver_sha=driver_sha,
        default_branch=default_branch,
    )
    _validate_required_jobs(jobs, ".".join(_TAG.fullmatch(tag).groups()))


def validate_publication_receipt(
    value: dict[str, Any],
    *,
    tag: str,
    source_sha: str,
    driver_sha: str,
    run_id: str,
    repository: str,
    default_branch: str,
    expected_tag_object_sha: str,
    expected_run_attempt: int,
) -> None:
    driver = value.get("driver")
    target = value.get("target")
    match = _TAG.fullmatch(tag)
    if match is None:
        _fail("release tag is malformed")
    if (
        value.get("schema") != "arras.release-driver-provenance.v1"
        or not isinstance(driver, dict)
        or not isinstance(target, dict)
        or driver.get("sha") != driver_sha
        or driver.get("workflow_sha") != driver_sha
        or driver.get("ref") != f"refs/heads/{default_branch}"
        or driver.get("workflow_ref")
        != f"{repository}/.github/workflows/release.yml@refs/heads/{default_branch}"
        or str(driver.get("run_id")) != run_id
        or str(driver.get("run_attempt")) != str(expected_run_attempt)
        or target.get("tag") != tag
        or target.get("source_sha") != source_sha
        or target.get("version") != ".".join(match.groups())
        or target.get("tag_object_sha") != expected_tag_object_sha
    ):
        _fail("original release-driver provenance does not bind this tag, source, driver and run")


def _read_sums_entries(path: Path, *, expected_count: int) -> dict[str, str]:
    entries: dict[str, str] = {}
    try:
        text = path.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError):
        _fail("trusted SHA256SUMS is not readable ASCII")
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]{0,199})", line)
        if match is None or match.group(2) in entries:
            _fail("trusted SHA256SUMS has malformed or duplicate entries")
        entries[match.group(2)] = match.group(1)
    if len(entries) != expected_count:
        _fail("trusted SHA256SUMS does not contain the versioned exact release inventory")
    return entries


def _verify_bundle_assets(directory: Path, entries: dict[str, str]) -> None:
    total = 0
    for name, digest in entries.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 512 * 1024 * 1024:
            _fail("trusted release artifact contains a missing, non-regular, or oversized file")
        total += path.stat().st_size
        if total > _MAX_TOTAL:
            _fail("trusted release asset bundle exceeds its total size limit")
        hasher = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    hasher.update(block)
        except OSError as exc:
            _fail(f"cannot read trusted release asset: {exc.strerror or type(exc).__name__}")
        if hasher.hexdigest() != digest:
            _fail(f"trusted release asset checksum failed: {name}")
    if set(item.name for item in directory.iterdir()) != set(entries) | {"SHA256SUMS"}:
        _fail("trusted release artifact inventory has unexpected or missing files")


def validate_bundle(
    directory: Path,
    *,
    version: str,
    expected_sums_sha256: str,
    expected_evidence_sha256: str,
    expected_wheel_sha256: str,
) -> str:
    wheel_name = f"arras-{version}-py3-none-any.whl"
    if directory.is_symlink() or not directory.is_dir():
        _fail("downloaded trusted release artifact must be a real directory")
    sums = directory / "SHA256SUMS"
    evidence = directory / "release-evidence.json"
    for path, expected, label, cap in (
        (sums, expected_sums_sha256, "SHA256SUMS", _MAX_SUMS),
        (evidence, expected_evidence_sha256, "release evidence", _MAX_JSON),
    ):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > cap:
            _fail(f"trusted {label} is missing, non-regular, or too large")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            _fail(f"trusted {label} does not match its dispatch digest")
    has_umf_admission = _umf_receipt.required_for_version(version)
    entries = _read_sums_entries(sums, expected_count=16 if has_umf_admission else 15)
    expected_entries = {
        f"arras-{version}-py3-none-any.whl",
        f"arras-{version}.tar.gz",
        f"documentdrivendx-arras-ui-{version}.tgz",
        "distribution-verification.json",
        "doctor-installed.json",
        "native-qualification.json",
        "native-cohort-binding.json",
        "native-cohort.json",
        "ui-qualification.json",
        "consumer-qualification.json",
        "release-evidence.json",
        "acceptance-inventory-neutral-theme.json",
        "acceptance-resources-neutral-theme.json",
        "playwright-summary-neutral-theme.json",
        "native-find-links.html",
    }
    if has_umf_admission:
        expected_entries.add("umf-admission-installed.json")
    if set(entries) != expected_entries:
        _fail("trusted SHA256SUMS differs from the exact versioned asset inventory")
    wheel_sha = entries.get(wheel_name)
    if wheel_sha != expected_wheel_sha256:
        _fail("trusted wheel digest differs from the dispatch digest")
    aggregate = _json(evidence, "trusted release aggregate")
    expected_schema = 2 if has_umf_admission else 1
    if (
        type(aggregate.get("schema_version")) is not int
        or aggregate.get("schema_version") != expected_schema
    ):
        _fail("trusted release aggregate schema does not match the expected release version")
    artifacts = aggregate.get("release_artifacts")
    if not isinstance(artifacts, dict):
        _fail("trusted release aggregate has no release-artifact map")
    wheel_artifact = artifacts.get("wheel")
    if not isinstance(wheel_artifact, dict):
        _fail("trusted release aggregate has no wheel identity")
    if (
        aggregate.get("status") != "passed"
        or aggregate.get("version") != version
        or wheel_artifact.get("filename") != wheel_name
        or wheel_artifact.get("sha256") != wheel_sha
    ):
        _fail("trusted release aggregate does not bind the expected wheel and version")
    if has_umf_admission:
        component = aggregate.get("umf_admission")
        proof_path = directory / "umf-admission-installed.json"
        try:
            proof = _umf_receipt.strict_json_loads(proof_path.read_text(encoding="utf-8"))
            _umf_receipt.validate_public_projection(
                proof, version=version, wheel_name=wheel_name, wheel_sha256=wheel_sha
            )
        except (
            OSError,
            UnicodeDecodeError,
            ValueError,
            _umf_receipt.AdmissionReceiptError,
        ) as exc:
            _fail(f"trusted UMF admission receipt is invalid: {type(exc).__name__}")
        if not isinstance(component, dict) or component != {
            "filename": "umf-admission-installed.json",
            "sha256": entries["umf-admission-installed.json"],
            "qualification_phase": "release-build",
            "status": "passed",
        }:
            _fail("trusted release aggregate does not bind the UMF admission receipt")
    _verify_bundle_assets(directory, entries)
    return wheel_name


def _load_inputs(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        _json(args.run_json, "publication run metadata"),
        _json(args.jobs_json, "publication job metadata"),
        _json(args.workflow_json, "publication workflow metadata"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--publication-run-id", required=True)
    parser.add_argument("--expected-publication-driver-sha", required=True)
    parser.add_argument("--expected-sums-sha256", required=True)
    parser.add_argument("--expected-evidence-sha256", required=True)
    parser.add_argument("--expected-wheel-sha256", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--default-branch", required=True)
    parser.add_argument("--expected-tag-object-sha", required=True)
    parser.add_argument("--validate-inputs-only", action="store_true")
    parser.add_argument("--run-json", type=Path)
    parser.add_argument("--jobs-json", type=Path)
    parser.add_argument("--workflow-json", type=Path)
    parser.add_argument("--publication-provenance-json", type=Path)
    parser.add_argument("--trusted-dir", type=Path)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        validate_inputs(args)
        if args.validate_inputs_only:
            print(json.dumps({"status": "inputs-valid"}, sort_keys=True))
            return 0
        if any(
            value is None
            for value in (
                args.run_json,
                args.jobs_json,
                args.workflow_json,
                args.publication_provenance_json,
                args.trusted_dir,
                args.output_json,
            )
        ):
            _fail("complete provenance and bundle inputs are required")
        run, jobs, workflow = _load_inputs(args)
        validate_run(
            run,
            jobs,
            workflow,
            repository=args.repository,
            run_id=args.publication_run_id,
            tag=args.release_tag,
            source_sha=args.expected_source_sha,
            driver_sha=args.expected_publication_driver_sha,
            default_branch=args.default_branch,
        )
        match = _TAG.fullmatch(args.release_tag)
        assert match is not None
        version = ".".join(match.groups())
        publication_receipt = _json(
            args.publication_provenance_json, "original release-driver provenance"
        )
        validate_publication_receipt(
            publication_receipt,
            tag=args.release_tag,
            source_sha=args.expected_source_sha,
            driver_sha=args.expected_publication_driver_sha,
            run_id=args.publication_run_id,
            repository=args.repository,
            default_branch=args.default_branch,
            expected_tag_object_sha=args.expected_tag_object_sha,
            expected_run_attempt=run.get("run_attempt"),
        )
        wheel_name = validate_bundle(
            args.trusted_dir,
            version=version,
            expected_sums_sha256=args.expected_sums_sha256,
            expected_evidence_sha256=args.expected_evidence_sha256,
            expected_wheel_sha256=args.expected_wheel_sha256,
        )
        outputs = {
            "release_tag": args.release_tag,
            "source_sha": args.expected_source_sha,
            "version": version,
            "wheel_name": wheel_name,
            "wheel_sha256": args.expected_wheel_sha256,
            "publication_run_id": args.publication_run_id,
            "publication_driver_sha": args.expected_publication_driver_sha,
            "tag_object_sha": args.expected_tag_object_sha,
            "sums_sha256": args.expected_sums_sha256,
            "evidence_sha256": args.expected_evidence_sha256,
            "publication_workflow_ref": publication_receipt["driver"]["workflow_ref"],
            "publication_run_attempt": publication_receipt["driver"]["run_attempt"],
            "umf_admission_required": str(_umf_receipt.required_for_version(version)).lower(),
        }
        target = os.environ.get("GITHUB_OUTPUT")
        if target:
            with open(target, "a", encoding="utf-8") as stream:
                for key, value in outputs.items():
                    stream.write(f"{key}={value}\n")
        receipt = {
            "schema_version": 1,
            "status": "passed",
            **outputs,
            "publication_event": run.get("event"),
            "publication_run_status": run.get("status"),
            "publication_run_conclusion": run.get("conclusion"),
            "publication_workflow_id": run.get("workflow_id"),
            "required_successful_jobs": _required_job_ids(version),
        }
        args.output_json.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(receipt, sort_keys=True))
    except (ProvenanceError, OSError) as exc:
        print(f"published release provenance verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
