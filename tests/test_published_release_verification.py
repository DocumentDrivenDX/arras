from __future__ import annotations

import hashlib
import importlib.util
import json
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".github/scripts/verify_publication_provenance.py"
WORKFLOW = ROOT / ".github/workflows/verify-published-release.yml"
SPEC = importlib.util.spec_from_file_location("published_provenance", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
provenance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provenance)

TAG = "v1.2.3"
VERSION = "1.2.3"
RUN_ID = "98765"
SOURCE_SHA = "1" * 40
DRIVER_SHA = "2" * 40
TAG_OBJECT_SHA = "3" * 40
HEX64 = "a" * 64
WHEEL = f"arras-{VERSION}-py3-none-any.whl"
ASSET_NAMES = {
    WHEEL,
    f"arras-{VERSION}.tar.gz",
    f"documentdrivendx-arras-ui-{VERSION}.tgz",
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


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_dispatch_inputs_require_full_exact_identities() -> None:
    args = Namespace(
        release_tag=TAG,
        expected_source_sha=SOURCE_SHA,
        publication_run_id=RUN_ID,
        expected_publication_driver_sha=DRIVER_SHA,
        expected_sums_sha256=HEX64,
        expected_evidence_sha256=HEX64,
        expected_wheel_sha256=HEX64,
        expected_tag_object_sha=TAG_OBJECT_SHA,
    )
    provenance.validate_inputs(args)
    for field, invalid in (
        ("release_tag", "main"),
        ("expected_source_sha", "1" * 39),
        ("publication_run_id", "0"),
        ("expected_publication_driver_sha", "z" * 40),
        ("expected_sums_sha256", "a" * 63),
        ("expected_evidence_sha256", "../" + "a" * 61),
        ("expected_wheel_sha256", "A" * 64),
        ("expected_tag_object_sha", "3" * 39),
    ):
        invalid_args = Namespace(**vars(args))
        setattr(invalid_args, field, invalid)
        with pytest.raises(provenance.ProvenanceError):
            provenance.validate_inputs(invalid_args)


def run_metadata() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    run = {
        "id": int(RUN_ID),
        "repository": {"full_name": "DocumentDrivenDX/arras"},
        "path": ".github/workflows/release.yml",
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": DRIVER_SHA,
        "status": "completed",
        "conclusion": "failure",
        "workflow_id": 42,
        "run_attempt": 1,
    }
    names = [
        "check",
        "Truss adapter on PostgreSQL 18.6",
        "build",
        "Installed native adapter on Linux x86_64",
        "assemble-evidence",
        "UI and packed-theme release qualification",
        "github-release",
    ]
    jobs = {
        "total_count": len(names),
        "jobs": [
            {
                "name": name,
                "conclusion": "success",
                "steps": (
                    [{"name": "Create the release", "conclusion": "success"}]
                    if name == "github-release"
                    else []
                ),
            }
            for name in names
        ],
    }
    workflow = {"id": 42, "path": ".github/workflows/release.yml", "state": "active"}
    return run, jobs, workflow


def test_original_publication_requires_matching_run_and_successful_release_gates() -> None:
    run, jobs, workflow = run_metadata()
    kwargs = {
        "repository": "DocumentDrivenDX/arras",
        "run_id": RUN_ID,
        "tag": TAG,
        "source_sha": SOURCE_SHA,
        "driver_sha": DRIVER_SHA,
        "default_branch": "main",
    }
    provenance.validate_run(run, jobs, workflow, **kwargs)
    for field, invalid in (
        ("id", 2),
        ("repository", {"full_name": "attacker/fork"}),
        ("path", ".github/workflows/other.yml"),
        ("event", "push"),
        ("head_sha", SOURCE_SHA),
        ("conclusion", "success"),
    ):
        changed = dict(run)
        changed[field] = invalid
        with pytest.raises(provenance.ProvenanceError):
            provenance.validate_run(changed, jobs, workflow, **kwargs)
    failed_jobs = json.loads(json.dumps(jobs))
    failed_jobs["jobs"][2]["conclusion"] = "failure"
    with pytest.raises(provenance.ProvenanceError, match="required pre-publication"):
        provenance.validate_run(run, failed_jobs, workflow, **kwargs)
    truncated_jobs = {"total_count": 20, "jobs": jobs["jobs"]}
    with pytest.raises(provenance.ProvenanceError, match="not complete"):
        provenance.validate_run(run, truncated_jobs, workflow, **kwargs)


def test_original_driver_receipt_binds_tag_source_driver_and_run() -> None:
    receipt = {
        "schema": "arras.release-driver-provenance.v1",
        "driver": {
            "sha": DRIVER_SHA,
            "workflow_sha": DRIVER_SHA,
            "ref": "refs/heads/main",
            "workflow_ref": "DocumentDrivenDX/arras/.github/workflows/release.yml@refs/heads/main",
            "run_id": RUN_ID,
            "run_attempt": "1",
        },
        "target": {
            "tag": TAG,
            "source_sha": SOURCE_SHA,
            "version": VERSION,
            "tag_object_sha": TAG_OBJECT_SHA,
        },
    }
    provenance.validate_publication_receipt(
        receipt,
        tag=TAG,
        source_sha=SOURCE_SHA,
        driver_sha=DRIVER_SHA,
        run_id=RUN_ID,
        repository="DocumentDrivenDX/arras",
        default_branch="main",
        expected_tag_object_sha=TAG_OBJECT_SHA,
        expected_run_attempt=1,
    )
    changed = json.loads(json.dumps(receipt))
    changed["target"]["source_sha"] = DRIVER_SHA
    with pytest.raises(provenance.ProvenanceError):
        provenance.validate_publication_receipt(
            changed,
            tag=TAG,
            source_sha=SOURCE_SHA,
            driver_sha=DRIVER_SHA,
            run_id=RUN_ID,
            repository="DocumentDrivenDX/arras",
            default_branch="main",
            expected_tag_object_sha=TAG_OBJECT_SHA,
            expected_run_attempt=1,
        )


def make_bundle(directory: Path) -> tuple[str, str, str]:
    directory.mkdir()
    for name in ASSET_NAMES - {"release-evidence.json"}:
        (directory / name).write_bytes(f"fixture:{name}".encode())
    wheel_sha = sha((directory / WHEEL).read_bytes())
    aggregate = {
        "schema_version": 1,
        "status": "passed",
        "version": VERSION,
        "release_artifacts": {"wheel": {"filename": WHEEL, "sha256": wheel_sha}},
    }
    evidence_raw = (json.dumps(aggregate, sort_keys=True) + "\n").encode()
    (directory / "release-evidence.json").write_bytes(evidence_raw)
    sums_raw = "".join(
        f"{sha((directory / name).read_bytes())}  {name}\n" for name in sorted(ASSET_NAMES)
    ).encode()
    (directory / "SHA256SUMS").write_bytes(sums_raw)
    return sha(sums_raw), sha(evidence_raw), wheel_sha


def test_trusted_bundle_binds_exact_assets_aggregate_sums_and_wheel(tmp_path: Path) -> None:
    bundle = tmp_path / "release-assets"
    sums_sha, evidence_sha, wheel_sha = make_bundle(bundle)
    assert (
        provenance.validate_bundle(
            bundle,
            version=VERSION,
            expected_sums_sha256=sums_sha,
            expected_evidence_sha256=evidence_sha,
            expected_wheel_sha256=wheel_sha,
        )
        == WHEEL
    )
    with pytest.raises(provenance.ProvenanceError, match="wheel digest"):
        provenance.validate_bundle(
            bundle,
            version=VERSION,
            expected_sums_sha256=sums_sha,
            expected_evidence_sha256=evidence_sha,
            expected_wheel_sha256="f" * 64,
        )
    (bundle / "extra.bin").write_bytes(b"unexpected")
    with pytest.raises(provenance.ProvenanceError, match="unexpected or missing"):
        provenance.validate_bundle(
            bundle,
            version=VERSION,
            expected_sums_sha256=sums_sha,
            expected_evidence_sha256=evidence_sha,
            expected_wheel_sha256=wheel_sha,
        )


def test_verification_workflow_is_dispatch_only_read_only_and_reuses_existing_gates() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for name in (
        "release_tag",
        "expected_source_sha",
        "publication_run_id",
        "expected_publication_driver_sha",
        "expected_sums_sha256",
        "expected_evidence_sha256",
        "expected_wheel_sha256",
    ):
        assert f"      {name}:" in workflow
    assert "  workflow_dispatch:" in workflow
    assert "  push:" not in workflow
    assert "  contents: read" in workflow
    assert "  actions: read" in workflow
    assert "contents: write" not in workflow
    assert "id-token: write" not in workflow
    assert "environment:" not in workflow
    assert "gh release create" not in workflow
    assert "publish-pypi" not in workflow and "publish-npm" not in workflow
    assert "release_target.py validate" in workflow and "release_target.py recheck" in workflow
    assert "release-assets" in workflow and "release-driver-provenance" in workflow
    assert "verify_public_release_assets.py plan" in workflow
    assert "verify_public_release_assets.py verify" in workflow
    assert "uses: ./.github/workflows/downstream.yml" in workflow
    assert "npm run qualify:downstream" in workflow
    assert "curl --disable" in workflow
