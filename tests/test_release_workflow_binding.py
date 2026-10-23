from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / ".github/workflows/release.yml"
DOWNSTREAM = ROOT / ".github/workflows/downstream.yml"
CI = ROOT / ".github/workflows/ci.yml"


def job_text(workflow: str, name: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)", workflow)
    assert match is not None, name
    return match.group(1)


def test_recovery_validates_driver_and_target_before_payload_checkout() -> None:
    workflow = RELEASE.read_text()
    assert "workflow_dispatch:" in workflow
    assert "release_tag:" in workflow and "expected_source_sha:" in workflow
    check = job_text(workflow, "check")
    assert "ref: ${{ github.workflow_sha }}" in check
    assert "python3 .github/scripts/release_target.py validate" in check
    assert check.index("release_target.py validate") < check.index(
        "ref: ${{ steps.version.outputs.source_sha }}"
    )
    assert "fetch-depth: 0" in check
    assert "name: release-driver-provenance" in check
    assert "source_sha: ${{ steps.version.outputs.source_sha }}" in check
    assert "driver_sha: ${{ steps.version.outputs.driver_sha }}" in check
    assert "workflow_ref: ${{ steps.version.outputs.workflow_ref }}" in check


def test_every_payload_job_pins_and_asserts_the_validated_target_commit() -> None:
    workflow = RELEASE.read_text()
    for name in (
        "truss",
        "build",
        "umf-admission",
        "installed-native",
        "assemble-evidence",
        "ui-qualification",
        "downloaded-release",
    ):
        job = job_text(workflow, name)
        assert "ref: ${{ needs.check.outputs.source_sha }}" in job, name
        assert "git rev-parse HEAD" in job and "$ARRAS_SOURCE_SHA" in job, name

    release = job_text(workflow, "github-release")
    assert "ref: ${{ needs.check.outputs.driver_sha }}" in release
    assert "ref: ${{ needs.check.outputs.source_sha }}" in release
    assert release.index("release_target.py recheck") < release.index("gh release create")
    assert "cd driver" in release
    assert "source/docs/helix/05-deploy/release-notes.md" in release
    assert "ARRAS_DRIVER_SHA" in release and "ARRAS_TARGET_SOURCE_SHA" in release
    assert "ARRAS_WORKFLOW_REF" in release
    assert "ARRAS_RUN_ID" in release and "ARRAS_RUN_ATTEMPT" in release
    assert "release-driver-provenance" not in release


def test_reusable_consumer_binds_its_checkout_to_caller_source() -> None:
    downstream = DOWNSTREAM.read_text()
    assert re.search(r"(?ms)^      source_sha:.*?required: false.*?default: \"\"", downstream)
    assert "${{ inputs.source_sha || github.sha }}" in downstream
    assert "ref: ${{ inputs.source_sha || github.sha }}" in downstream
    assert "Assert consumer checkout HEAD" in downstream
    caller = job_text(RELEASE.read_text(), "installed-downstream")
    assert "source_sha: ${{ needs.check.outputs.source_sha }}" in caller


def test_release_builds_ui_before_running_integration_and_keeps_current_run_gates() -> None:
    workflow = RELEASE.read_text()
    ui = job_text(workflow, "ui-qualification")
    command = next(line for line in ui.splitlines() if "npm run check &&" in line)
    assert command.index("npm run build") < command.index("npm run test:integration")
    assert re.search(
        r"(?m)^    needs: \[check, build, github-release\]$",
        job_text(workflow, "installed-downstream"),
    )
    assert re.search(
        r"(?m)^    needs: \[check, build, assemble-evidence, github-release, installed-downstream\]$",
        job_text(workflow, "downloaded-release"),
    )
    assert "needs: [github-release, installed-downstream, downloaded-release]" in job_text(
        workflow, "publish-pypi"
    )
    assert "needs: [github-release, installed-downstream, downloaded-release]" in job_text(
        workflow, "publish-npm"
    )


def test_umf_admission_is_required_before_assembly_and_repeated_from_public_wheel() -> None:
    workflow = RELEASE.read_text()
    proof = job_text(workflow, "umf-admission")
    assert re.search(r"(?m)^    needs: \[check, build\]$", proof)
    assert "Fresh installed UMF admission proof on exact wheel" in proof
    assert "ref: ${{ needs.check.outputs.source_sha }}" in proof
    assert "release-build-inputs/${{ needs.build.outputs.wheel_name }}" in proof
    assert "--qualification-phase release-build" in proof
    assembly = job_text(workflow, "assemble-evidence")
    assert re.search(
        r"(?m)^    needs: \[check, build, umf-admission, umf-actions, installed-native, ui-qualification\]$",
        assembly,
    )
    assert "--umf-admission-receipt umf-admission/umf-admission-installed.json" in assembly
    public = job_text(workflow, "downloaded-release")
    assert "public-release-assets/${{ needs.build.outputs.wheel_name }}" in public
    assert "--qualification-phase public-download" in public
    assert 'outputs.append("public-umf-admission-installed.json")' in public
    recovery = Path(__file__).parents[1] / ".github/workflows/verify-published-release.yml"
    recovery_text = recovery.read_text()
    anonymous = job_text(recovery_text, "anonymous-public-consumer")
    assert "public-release-assets/${{ needs.trusted-publication.outputs.wheel_name }}" in anonymous
    assert "--qualification-phase public-download" in anonymous
    assert 'receipts.append("public-umf-admission-installed.json")' in anonymous


def test_ci_qualifies_installed_actions_when_the_built_wheel_requires_them() -> None:
    workflow = CI.read_text()
    check = job_text(workflow, "check")
    assert "steps.umf-actions-requirement.outputs.required" in check
    assert "--check-requirement" in check
    assert "--qualification-phase local-installed" in check
    assert "name: arras-umf-actions-installed" in check
    assert "path: artifacts/umf-actions-installed.json" in check
    assert "if-no-files-found: warn" in check

    tests = job_text(workflow, "test")
    assert "needs: check" in tests
    assert (
        tests.count(
            "ARRAS_REQUIRE_UMF_ACTIONS: ${{ needs.check.outputs.umf_actions_required == 'true' && '1' || '0' }}"
        )
        == 2
    )
