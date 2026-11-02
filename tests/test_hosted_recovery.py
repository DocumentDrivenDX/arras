from __future__ import annotations

import copy
import importlib.util
import itertools
import re
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / ".github/scripts"))
SPEC = importlib.util.spec_from_file_location(
    "hosted_recovery_control", ROOT / ".github/scripts/qualify_hosted_recovery.py"
)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
sys.path.pop(0)

NAMES = [
    "check",
    "Truss adapter on PostgreSQL 18.6",
    "build",
    "Installed native adapter on Linux x86_64",
    "assemble-evidence",
    "UI and packed-theme release qualification",
    "github-release",
    "installed-downstream / Install verified wheel and run explicit qualification stages",
    "Verify anonymous public release bundle",
    "Fresh installed UMF admission proof on exact wheel",
    "Fresh installed generated-action proof when the wheel requires it",
]
RECOVERY_NAMES = [
    "Verify the original publication provenance",
    "Re-test the published wheel in a fresh consumer / Install verified wheel and run explicit qualification stages",
    "Re-verify anonymous public assets and consumers",
]


def original_jobs() -> dict[str, Any]:
    jobs: list[dict[str, Any]] = [
        {
            "name": name,
            "status": "completed",
            "conclusion": "failure" if name == NAMES[8] else "success",
        }
        for name in NAMES
    ]
    jobs[6]["steps"] = [{"name": "Create the release", "conclusion": "success"}]
    return {"jobs": jobs, "total_count": len(jobs)}


def recovery_context() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    run: dict[str, Any] = dict(
        id=41520267978,
        repository={"full_name": "DocumentDrivenDX/arras"},
        path=".github/workflows/verify-published-release.yml",
        event="workflow_dispatch",
        head_branch="main",
        head_sha="d2ad21fd916f8d455faac25f20ece209b00b49d0",
        status="completed",
        conclusion="success",
        workflow_id=123,
        run_attempt=1,
    )
    workflow = dict(id=123, path=run["path"], state="active")
    jobs = dict(
        total_count=3,
        jobs=[dict(name=n, status="completed", conclusion="success") for n in RECOVERY_NAMES],
    )
    return run, workflow, jobs


def test_only_the_actual_isolated_download_failure_is_recoverable() -> None:
    gate.validate_original_jobs(original_jobs())


@pytest.mark.parametrize("index", range(len(NAMES)))
@pytest.mark.parametrize("result", ["failure", "skipped", "cancelled"])
def test_each_other_original_gate_must_succeed(index: int, result: str) -> None:
    value = original_jobs()
    value["jobs"][index]["conclusion"] = result
    if index == 8 and result == "failure":
        gate.validate_original_jobs(value)
    else:
        with pytest.raises(ValueError):
            gate.validate_original_jobs(value)


@pytest.mark.parametrize(
    "mutation",
    [
        "extra-failure",
        "duplicate",
        "missing",
        "unfinished",
        "no-publication-step",
        "original-success",
    ],
)
def test_original_incomplete_or_different_failure_scope_refuses(mutation: str) -> None:
    value = original_jobs()
    if mutation == "extra-failure":
        value["jobs"].append(dict(name="unexpected", status="completed", conclusion="failure"))
        value["total_count"] += 1
    elif mutation == "duplicate":
        value["jobs"].append(copy.deepcopy(value["jobs"][0]))
        value["total_count"] += 1
    elif mutation == "missing":
        value["jobs"].pop(7)
    elif mutation == "unfinished":
        value["jobs"][0]["status"] = "in_progress"
    elif mutation == "no-publication-step":
        value["jobs"][6]["steps"] = []
    else:
        value["jobs"][8]["conclusion"] = "success"
    with pytest.raises(ValueError):
        gate.validate_original_jobs(value)


def test_actual_recovery_job_display_names_and_full_success_are_required() -> None:
    run, workflow, jobs = recovery_context()
    gate.validate_recovery_run(run, workflow, jobs, str(run["id"]), run["head_sha"])
    for index in range(3):
        for status in ["failure", "skipped", "cancelled"]:
            changed = copy.deepcopy(jobs)
            changed["jobs"][index]["conclusion"] = status
            with pytest.raises(ValueError):
                gate.validate_recovery_run(run, workflow, changed, str(run["id"]), run["head_sha"])


@pytest.mark.parametrize(
    "key,value",
    [
        ("path", ".github/workflows/ci.yml"),
        ("head_branch", "other"),
        ("event", "pull_request"),
        ("status", "in_progress"),
        ("conclusion", "failure"),
        ("repository", {"full_name": "other/arras"}),
        ("workflow_id", None),
        ("run_attempt", 0),
    ],
)
def test_recovery_api_identity_must_match(key: str, value: Any) -> None:
    run, workflow, jobs = recovery_context()
    run[key] = value
    with pytest.raises(ValueError):
        gate.validate_recovery_run(run, workflow, jobs, str(run["id"]), run["head_sha"])


def summary() -> dict[str, Any]:
    run, _, _ = recovery_context()
    return dict(
        schema_version=1,
        status="passed",
        purpose="verification-only; no release assets were created or changed",
        release=dict(tag=gate.TAG, source_sha=gate.SOURCE),
        published_wheel=dict(filename=gate.WHEEL, sha256=gate.WHEEL_SHA),
        umf_actions_required=True,
        original_publication=dict(
            run_id=gate.ORIGINAL_RUN,
            run_attempt="1",
            driver_sha=gate.ORIGINAL_DRIVER,
            workflow_ref=f"{gate.REPOSITORY}/.github/workflows/release.yml@refs/heads/main",
            tag_object_sha=gate.TAG_OBJECT,
            sums_sha256=gate.SUMS_SHA,
            evidence_sha256=gate.EVIDENCE_SHA,
        ),
        verification=dict(
            run_id=str(run["id"]),
            run_attempt="1",
            driver_sha=run["head_sha"],
            workflow_ref=f"{gate.REPOSITORY}/{gate.RECOVERY_PATH}@refs/heads/main",
        ),
    )


@pytest.mark.parametrize(
    "section,key",
    [
        ("original_publication", "run_id"),
        ("original_publication", "run_attempt"),
        ("original_publication", "driver_sha"),
        ("original_publication", "tag_object_sha"),
        ("original_publication", "sums_sha256"),
        ("original_publication", "evidence_sha256"),
        ("verification", "run_id"),
        ("verification", "run_attempt"),
        ("verification", "driver_sha"),
        ("published_wheel", "sha256"),
        ("release", "source_sha"),
    ],
)
def test_summary_cannot_transfer_old_identity_or_stale_attempt(section: str, key: str) -> None:
    run, _, _ = recovery_context()
    value = summary()
    gate.validate_summary(value, run, run["head_sha"])
    value[section][key] = "wrong"
    with pytest.raises(ValueError):
        gate.validate_summary(value, run, run["head_sha"])


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "checksum", "symlink"])
def test_raw_receipt_inventory_refuses_before_semantic_validation(
    tmp_path: Path, mutation: str
) -> None:
    records: list[dict[str, str]] = []
    receipt_names: set[str] = gate.RECEIPTS
    for name in sorted(receipt_names):
        path = tmp_path / (name if name.startswith("tests/") else f"artifacts/{name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
        records.append(
            dict(filename=name, sha256=gate.hashlib.sha256(path.read_bytes()).hexdigest())
        )
    if mutation == "missing":
        records.pop()
    elif mutation == "duplicate":
        records[-1] = records[0]
    elif mutation == "unknown":
        records[0]["filename"] = "../other.json"
    elif mutation == "checksum":
        records[0]["sha256"] = "0" * 64
    else:
        first = tmp_path / "artifacts" / records[0]["filename"]
        first.unlink()
        first.symlink_to(tmp_path / "unrelated")
    with pytest.raises(ValueError):
        gate.validate_receipts(tmp_path, {"receipts": records}, tmp_path / "assets")


def test_three_origins_join_only_one_success_with_other_origins_skipped() -> None:
    text = (ROOT / ".github/workflows/publish-registries.yml").read_text()
    join = text.split("  verify-release:\n", 1)[1].split("    needs:", 1)[0]
    expression = " ".join(join.split("    if: >-\n", 1)[1].split())
    for results in itertools.product(["success", "skipped", "failure", "cancelled"], repeat=3):
        for cancelled in [False, True]:
            actual = expression.replace("always()", "True").replace(
                "!cancelled()", str(not cancelled)
            )
            for name, result in zip(
                ["verify-hosted-release", "qualify-local", "qualify-hosted-recovery"],
                results,
                strict=True,
            ):
                actual = actual.replace(f"needs.{name}.result", repr(result))
            actual = actual.replace("&&", "and").replace("||", "or")
            expected = (
                not cancelled and results.count("success") == 1 and results.count("skipped") == 2
            )
            assert eval(actual, {"__builtins__": {}}, {}) is expected
    assert (
        "inputs.origin == 'hosted'"
        in text.split("  verify-hosted-release:\n", 1)[1].split("    runs-on:", 1)[0]
    )
    workflow = (ROOT / ".github/workflows/qualify-hosted-recovery.yml").read_text()
    for command in ["gh release create", "gh release upload", "uv build", "npm publish"]:
        assert command not in workflow
    assert workflow.index("qualify_hosted_recovery.py") < workflow.index(
        "name: registry-verified-release-0.7.0"
    )


@pytest.mark.parametrize("version", [True, 1.0, "1", None])
def test_summary_requires_integer_schema(version: Any) -> None:
    run, _, _ = recovery_context()
    value = summary()
    value["schema_version"] = version
    with pytest.raises(ValueError):
        gate.validate_summary(value, run, run["head_sha"])


@pytest.mark.parametrize(
    "mutation", ["producer-run", "producer-driver", "source", "tag-object", "cohort", "attempt"]
)
def test_wrong_original_producer_pins_refuse_before_bundle_loading(
    tmp_path: Path, mutation: str
) -> None:
    run: dict[str, Any] = dict(
        id=int(gate.ORIGINAL_RUN),
        repository={"full_name": gate.REPOSITORY},
        path=".github/workflows/release.yml",
        event="workflow_dispatch",
        head_branch="main",
        head_sha=gate.ORIGINAL_DRIVER,
        status="completed",
        conclusion="failure",
        workflow_id=123,
        run_attempt=1,
    )
    proof: dict[str, Any] = dict(
        schema="arras.release-driver-provenance.v1",
        event="workflow_dispatch",
        driver=dict(
            ref="refs/heads/main",
            run_attempt="1",
            run_id=gate.ORIGINAL_RUN,
            sha=gate.ORIGINAL_DRIVER,
            workflow_sha=gate.ORIGINAL_DRIVER,
            workflow_ref=f"{gate.REPOSITORY}/.github/workflows/release.yml@refs/heads/main",
        ),
        target=dict(
            source_sha=gate.SOURCE,
            tag=gate.TAG,
            tag_object_sha=gate.TAG_OBJECT,
            version=gate.VERSION,
        ),
    )
    if mutation == "producer-run":
        run["id"] = 123
    elif mutation == "producer-driver":
        run["head_sha"] = "0" * 40
    elif mutation == "source":
        proof["target"]["source_sha"] = "0" * 40
    elif mutation == "tag-object":
        proof["target"]["tag_object_sha"] = "0" * 40
    elif mutation == "cohort":
        proof["target"]["version"] = "0.6.5"
    else:
        run["run_attempt"] = 2
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    original = tmp_path / "original"
    (original / "provenance").mkdir(parents=True)
    (original / "provenance/release-driver-provenance.json").write_text(gate.json.dumps(proof))
    for name, value in [
        ("run", run),
        ("workflow", dict(id=123, path=run["path"], state="active")),
        ("jobs", original_jobs()),
    ]:
        (metadata / f"original-{name}.json").write_text(gate.json.dumps(value))
    with pytest.raises(ValueError):
        gate.qualify(
            metadata,
            original,
            tmp_path / "absent-recovery",
            "41520267978",
            "d2ad21fd916f8d455faac25f20ece209b00b49d0",
        )


@pytest.mark.parametrize(
    "filename,job",
    [
        ("release.yml", "installed-downstream"),
        ("verify-published-release.yml", "installed-consumer"),
    ],
)
def test_future_reusable_consumer_uses_supported_python(filename: str, job: str) -> None:
    text = (ROOT / ".github/workflows" / filename).read_text()
    block = re.split(r"\n  [a-z][a-z0-9-]*:", text.split(f"\n  {job}:\n", 1)[1], maxsplit=1)[0]
    assert 'python_version: "3.11"' in block
