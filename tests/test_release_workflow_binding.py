from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / ".github/workflows/release.yml"
DOWNSTREAM = ROOT / ".github/workflows/downstream.yml"


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


def test_release_rebuild_must_match_the_selected_qualification_wheel_before_upload() -> None:
    build = job_text(RELEASE.read_text(), "build")
    selected = (
        "259e16c7d4c8f6c56d9930ee5f16e74c4ab6b2c8a3ecffdb7d8b306c77b60f18"
        "  dist/arras-0.6.1-py3-none-any.whl"
    )
    assert f"echo '{selected}' | sha256sum --check --strict -" in build
    assert build.index("uv build --wheel && uv build --sdist") < build.index(selected)
    assert build.index(selected) < build.index("python tools/verify_distribution.py")
    assert build.index(selected) < build.index("uses: actions/upload-artifact@v4")


@pytest.mark.parametrize("state", ["matching", "changed", "missing"])
def test_release_wheel_hash_command_refuses_changed_or_missing_bytes(
    tmp_path: Path, state: str
) -> None:
    if shutil.which("sha256sum") is None or shutil.which("sh") is None:
        pytest.skip("the release runner's GNU sha256sum and POSIX shell are required")
    build = job_text(RELEASE.read_text(), "build")
    command = next(line.strip() for line in build.splitlines() if "sha256sum --check" in line)
    expected = b"selected qualification artifact\n"
    digest = hashlib.sha256(expected).hexdigest()
    command = re.sub(r"[0-9a-f]{64}", digest, command)
    wheel = tmp_path / "dist/arras-0.6.1-py3-none-any.whl"
    wheel.parent.mkdir()
    if state != "missing":
        wheel.write_bytes(expected if state == "matching" else b"different release artifact\n")
    result = subprocess.run(["sh", "-c", command], cwd=tmp_path, capture_output=True)
    assert (result.returncode == 0) is (state == "matching")


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
        r"(?m)^    needs: \[check, build, umf-admission, installed-native, ui-qualification\]$",
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
