#!/usr/bin/env python3
"""Qualify the immutable 0.7.0 failed-publication/successful-readback chain."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import _release_evidence_inputs as inputs
import _release_evidence_ui as ui
import _umf_actions_receipt as actions
import _umf_admission_receipt as admission
import assemble_release_evidence as assembly
import local_registry_qualification as local
import verify_publication_provenance as provenance
import verify_registry_publication as registry

REPOSITORY = "DocumentDrivenDX/arras"
VERSION = "0.7.0"
TAG = "v0.7.0"
SOURCE = "f9f04c42ae0c989d34907e00a63ca95c3cb2fcdf"
TAG_OBJECT = "9f950b306eb3f86c057a118edba085e4fe81bbd4"
ORIGINAL_RUN = "41514683626"
ORIGINAL_DRIVER = "19c71f775e07a36ad23b3e80310e56aa61dae576"
WHEEL = "arras-0.7.0-py3-none-any.whl"
WHEEL_SHA = "b20f2b0c8a8f54b86abfca886dc555bb16faedd277c1e132c3c58dfc7aa17ad6"
NPM_SHA = "8f3c5ea2d98ffa8011e5acfe3d9a65cd773cd149481aeb6edcf2d671bb5af9de"
SDIST_SHA = "c790907c3bdb9600fe25942ceae10dae59307d0574e7cc6440a58261743ef00f"
SUMS_SHA = "7d02b79e1a0fc3fe388d86e9209559495f969d6724cc04075acb98804a827ab8"
EVIDENCE_SHA = "71ca10acf69b36c485588ddbcf838bc4fdb8dd380e862a79c663392ceb6d22d6"
RECOVERY_PATH = ".github/workflows/verify-published-release.yml"
RECEIPTS = {
    "public-input-verification.json",
    "public-distribution-verification.json",
    "public-doctor-installed.json",
    "public-extension-host-fresh-dependencies.json",
    "public-umf-admission-installed.json",
    "public-umf-actions-installed.json",
    "tests/downstream/evidence/linux/qualification-linux.json",
}
ROOT = Path(__file__).resolve().parents[2]


def fail(message: str) -> None:
    raise ValueError(message)


def read(path: Path) -> dict[str, Any]:
    return registry._read_json(path, "hosted recovery input")


def jobs_by_name(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = value.get("jobs")
    if not isinstance(raw, list) or value.get("total_count") != len(raw) or len(raw) > 1000:
        fail("recovery jobs response is incomplete")
    result: dict[str, dict[str, Any]] = {}
    for job in raw:
        if not isinstance(job, dict) or not isinstance(job.get("name"), str):
            fail("recovery job is malformed")
        if job["name"] in result or job.get("status") != "completed":
            fail("recovery job is duplicate or unfinished")
        result[job["name"]] = job
    return result


def validate_original_jobs(value: dict[str, Any]) -> None:
    provenance._validate_required_jobs(value, VERSION, actions_required=True)
    jobs = jobs_by_name(value)
    required = {
        **registry._REQUIRED_JOBS,
        "umf-admission": {"Fresh installed UMF admission proof on exact wheel"},
        "umf-actions": {"Fresh installed generated-action proof when the wheel requires it"},
    }
    selected: dict[str, dict[str, Any]] = {}
    for key, names in required.items():
        matched = names.intersection(jobs)
        if len(matched) != 1:
            fail("original publication mandatory job is absent or ambiguous")
        selected[key] = jobs[matched.pop()]
    if selected["downloaded-release"].get("conclusion") != "failure":
        fail("original public-download job must retain its failure")
    if any(
        job.get("conclusion") != "success"
        for key, job in selected.items()
        if key != "downloaded-release"
    ):
        fail("another original mandatory job did not succeed")
    if {name for name, job in jobs.items() if job.get("conclusion") != "success"} != {
        selected["downloaded-release"]["name"]
    }:
        fail("original failure was not isolated to public download")


def validate_recovery_run(
    run: dict[str, Any], workflow: dict[str, Any], jobs: dict[str, Any], run_id: str, driver: str
) -> None:
    if not re.fullmatch(r"[1-9][0-9]{0,19}", run_id) or not re.fullmatch(r"[0-9a-f]{40}", driver):
        fail("recovery run or driver pin is malformed")
    if (
        run.get("id") != int(run_id)
        or run.get("repository", {}).get("full_name") != REPOSITORY
        or run.get("path") != RECOVERY_PATH
        or run.get("event") != "workflow_dispatch"
        or run.get("head_branch") != "main"
        or run.get("head_sha") != driver
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or type(run.get("run_attempt")) is not int
        or run["run_attempt"] < 1
        or type(run.get("workflow_id")) is not int
        or workflow.get("id") != run.get("workflow_id")
        or workflow.get("path") != RECOVERY_PATH
        or workflow.get("state") != "active"
    ):
        fail("recovery run does not match its successful hosted driver")
    actual = jobs_by_name(jobs)
    expected = {
        "Verify the original publication provenance",
        "Re-test the published wheel in a fresh consumer / Install verified wheel and run explicit qualification stages",
        "Re-verify anonymous public assets and consumers",
    }
    if set(actual) != expected or any(
        job.get("conclusion") != "success" for job in actual.values()
    ):
        fail("recovery mandatory jobs did not all succeed")


def validate_summary(summary: dict[str, Any], run: dict[str, Any], driver: str) -> None:
    if (
        type(summary.get("schema_version")) is not int
        or summary.get("schema_version") != 1
        or summary.get("status") != "passed"
        or summary.get("purpose") != "verification-only; no release assets were created or changed"
        or summary.get("release") != {"tag": TAG, "source_sha": SOURCE}
        or summary.get("published_wheel") != {"filename": WHEEL, "sha256": WHEEL_SHA}
        or summary.get("umf_actions_required") is not True
        or summary.get("original_publication")
        != {
            "run_id": ORIGINAL_RUN,
            "run_attempt": "1",
            "driver_sha": ORIGINAL_DRIVER,
            "workflow_ref": f"{REPOSITORY}/.github/workflows/release.yml@refs/heads/main",
            "tag_object_sha": TAG_OBJECT,
            "sums_sha256": SUMS_SHA,
            "evidence_sha256": EVIDENCE_SHA,
        }
        or summary.get("verification")
        != {
            "run_id": str(run["id"]),
            "run_attempt": str(run["run_attempt"]),
            "driver_sha": driver,
            "workflow_ref": f"{REPOSITORY}/{RECOVERY_PATH}@refs/heads/main",
        }
    ):
        fail("recovery summary does not bind original and supplemental identities")


def validate_receipts(directory: Path, summary: dict[str, Any], assets: Path) -> dict[str, str]:
    records = summary.get("receipts")
    if not isinstance(records, list) or len(records) != len(RECEIPTS):
        fail("recovery receipt inventory is incomplete")
    selected: dict[str, Path] = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != {"filename", "sha256"}:
            fail("recovery receipt record is malformed")
        name = record["filename"]
        if not isinstance(name, str) or name not in RECEIPTS or name in selected:
            fail("recovery receipt is unknown or duplicated")
        path = directory / (name if name.startswith("tests/") else f"artifacts/{name}")
        if any(
            parent.is_symlink() for parent in [path, *path.parents] if parent != directory.parent
        ):
            fail("recovery receipt traverses a symlink")
        read(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            fail("recovery receipt checksum differs")
        selected[name] = path
    values = {name: read(path) for name, path in selected.items()}
    public = values["public-input-verification.json"]
    expected_entries = dict(
        line.split("  ", 1)[::-1] for line in (assets / "SHA256SUMS").read_text().splitlines()
    )
    if (
        type(public.get("schema_version")) is not int
        or public.get("schema_version") != 1
        or public.get("version") != VERSION
        or public.get("status") != "passed"
        or public.get("sums_sha256") != SUMS_SHA
        or public.get("wheel") != {"filename": WHEEL, "sha256": WHEEL_SHA}
        or public.get("npm_matches_wheel_payload") is not True
        or public.get("asset_count") != 17
        or public.get("assets")
        != [
            {"filename": name, "sha256": expected_entries[name]}
            for name in sorted(expected_entries)
        ]
    ):
        fail("recovery public asset comparison differs")
    assembly._validate_distribution(
        values["public-distribution-verification.json"],
        VERSION,
        WHEEL,
        {
            WHEEL: WHEEL_SHA,
            "arras-0.7.0.tar.gz": SDIST_SHA,
            "documentdrivendx-arras-ui-0.7.0.tgz": NPM_SHA,
        },
    )
    assembly._validate_doctor(
        values["public-doctor-installed.json"], VERSION, WHEEL, WHEEL_SHA, NPM_SHA
    )
    assembly._validate_consumer(
        values["public-extension-host-fresh-dependencies.json"], WHEEL, WHEEL_SHA, VERSION
    )
    for runtime in [
        values["public-doctor-installed.json"].get("python"),
        values["public-extension-host-fresh-dependencies.json"]
        .get("environment", {})
        .get("python"),
    ]:
        if not isinstance(runtime, str) or not re.fullmatch(r"3\.11\.[0-9]+", runtime):
            fail("normative public doctor and fresh consumer require Python 3.11")
    binding = dict(
        version=VERSION,
        wheel_name=WHEEL,
        wheel_sha256=WHEEL_SHA,
        phase="public-download",
        repository=ROOT,
        wheel_path=assets / WHEEL,
    )
    admission.validate_receipt(values["public-umf-admission-installed.json"], **binding)
    actions.validate_receipt(values["public-umf-actions-installed.json"], **binding)
    ui_name = "tests/downstream/evidence/linux/qualification-linux.json"
    ui_value = values[ui_name]
    _, resources = inputs._npm_identity(
        (assets / "documentdrivendx-arras-ui-0.7.0.tgz").read_bytes(), VERSION
    )
    _, sidecars = ui.validate_ui(
        ui_value, selected[ui_name], WHEEL, WHEEL_SHA, NPM_SHA, VERSION, resources
    )
    routes = ui_value.get("routes")
    if (
        not isinstance(routes, list)
        or len(routes) != 4
        or any(not isinstance(route, dict) for route in routes)
    ):
        fail("recovery UI route inventory differs")
    local.validate_ui_routes(routes)
    return {
        **{name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in selected.items()},
        **{
            f"tests/downstream/evidence/linux/{name}": hashlib.sha256(raw).hexdigest()
            for name, raw in sidecars.items()
        },
    }


def qualify(
    metadata: Path, original: Path, recovery: Path, run_id: str, driver: str
) -> dict[str, Any]:
    run, workflow, jobs = [
        read(metadata / f"original-{name}.json") for name in ["run", "workflow", "jobs"]
    ]
    original_proof = read(original / "provenance/release-driver-provenance.json")
    provenance._validate_run_identity(
        run,
        workflow,
        repository=REPOSITORY,
        run_id=ORIGINAL_RUN,
        tag=TAG,
        source_sha=SOURCE,
        driver_sha=ORIGINAL_DRIVER,
        default_branch="main",
    )
    validate_original_jobs(jobs)
    identity = registry._validate_driver_provenance(
        run, original_proof, event="workflow_dispatch", repository=REPOSITORY, default_branch="main"
    )
    if identity != (TAG, VERSION, SOURCE, TAG_OBJECT, ORIGINAL_DRIVER, "1"):
        fail("original immutable publication pins differ")
    assets = original / "release-assets"
    provenance.validate_bundle(
        assets,
        version=VERSION,
        expected_sums_sha256=SUMS_SHA,
        expected_evidence_sha256=EVIDENCE_SHA,
        expected_wheel_sha256=WHEEL_SHA,
    )
    if actions.required_for_wheel(assets / WHEEL, wheel_sha256=WHEEL_SHA) is not True:
        fail("original wheel does not require the reviewed action gate")
    registry._validate_tag(
        TAG, SOURCE, read(metadata / "tag-ref.json"), read(metadata / "tag-object.json"), TAG_OBJECT
    )
    expected_names = provenance._expected_bundle_entries(
        VERSION, has_umf_admission=True, actions_required=True
    ) | {"SHA256SUMS"}
    if {p.name for p in assets.iterdir()} != expected_names:
        fail("original release artifact directory has an unexpected inventory")
    release = read(metadata / "release.json")
    if release.get("immutable") is not True:
        fail("the closed 0.7.0 release must remain immutable")
    registry._validate_release_assets(release, expected_names, TAG)
    supplemental, definition, supplemental_jobs = [
        read(metadata / f"recovery-{name}.json") for name in ["run", "workflow", "jobs"]
    ]
    validate_recovery_run(supplemental, definition, supplemental_jobs, run_id, driver)
    anchor = read(recovery / "anchor/release-driver-provenance.json")
    if anchor != original_proof:
        fail("recovery anchor differs from original producer provenance")
    anchor_check = read(recovery / "anchor/original-publication-verification.json")
    expected_anchor = {
        "status": "passed",
        "publication_run_conclusion": "failure",
        "publication_run_status": "completed",
        "publication_event": "workflow_dispatch",
        "publication_run_id": ORIGINAL_RUN,
        "publication_driver_sha": ORIGINAL_DRIVER,
        "publication_run_attempt": "1",
        "publication_workflow_ref": f"{REPOSITORY}/.github/workflows/release.yml@refs/heads/main",
        "release_tag": TAG,
        "source_sha": SOURCE,
        "version": VERSION,
        "wheel_name": WHEEL,
        "wheel_sha256": WHEEL_SHA,
        "tag_object_sha": TAG_OBJECT,
        "sums_sha256": SUMS_SHA,
        "evidence_sha256": EVIDENCE_SHA,
        "umf_admission_required": "true",
        "umf_actions_required": "true",
        "required_successful_jobs": provenance._required_job_ids(VERSION, actions_required=True),
        "publication_workflow_id": run["workflow_id"],
        "schema_version": 1,
    }
    if type(anchor_check.get("schema_version")) is not int or anchor_check != expected_anchor:
        fail("recovery original-publication verification differs")
    summary = read(recovery / "public/artifacts/public-verification-only.json")
    validate_summary(summary, supplemental, driver)
    receipt_hashes = validate_receipts(recovery / "public", summary, assets)
    return {
        "schema": "arras.hosted-recovered-070-qualification.v1",
        "qualification_phase": "hosted-composite-admission"
        if os.environ.get("GITHUB_ACTIONS") == "true"
        else "local-preflight",
        "qualifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "qualification_driver_sha": os.environ.get("GITHUB_WORKFLOW_SHA"),
        "qualification_run_id": os.environ.get("GITHUB_RUN_ID"),
        "qualification_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "raw_receipts_sha256": receipt_hashes,
        "original_provenance_sha256": hashlib.sha256(
            (original / "provenance/release-driver-provenance.json").read_bytes()
        ).hexdigest(),
        "anchor_sha256": hashlib.sha256(
            (recovery / "anchor/original-publication-verification.json").read_bytes()
        ).hexdigest(),
        "recovery_summary_sha256": hashlib.sha256(
            (recovery / "public/artifacts/public-verification-only.json").read_bytes()
        ).hexdigest(),
        "status": "passed",
        "origin": "hosted-recovered-0.7.0",
        "version": VERSION,
        "tag": TAG,
        "source_sha": SOURCE,
        "tag_object_sha": TAG_OBJECT,
        "wheel": WHEEL,
        "wheel_name": WHEEL,
        "wheel_sha256": WHEEL_SHA,
        "npm_sha256": NPM_SHA,
        "sums_sha256": SUMS_SHA,
        "evidence_sha256": EVIDENCE_SHA,
        "original_run_id": ORIGINAL_RUN,
        "original_driver_sha": ORIGINAL_DRIVER,
        "original_conclusion": "failure",
        "recovery_run_id": run_id,
        "recovery_driver_sha": driver,
        "recovery_run_attempt": str(supplemental["run_attempt"]),
        "recovery_conclusion": "success",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["metadata", "original", "recovery", "output"]:
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--recovery-run-id", required=True)
    parser.add_argument("--expected-recovery-driver-sha", required=True)
    args = parser.parse_args()
    result = qualify(
        args.metadata,
        args.original,
        args.recovery,
        args.recovery_run_id,
        args.expected_recovery_driver_sha,
    )
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
