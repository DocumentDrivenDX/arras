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
    assert "publish-pypi:" not in workflow and "publish-npm:" not in workflow
    assert "ARRAS_PUBLISH_PYPI" not in workflow and "ARRAS_PUBLISH_NPM" not in workflow
    assert "verify_registry_publication.py pypi-metadata" in job_text(workflow, "build")


def test_release_ui_driver_binds_temporary_theme_to_exact_wheel_before_browser_suite() -> None:
    workflow = RELEASE.read_text()
    ui = job_text(workflow, "ui-qualification")
    assert re.search(
        r"(?ms)uses: actions/checkout@v4\n        with:\n          ref: \$\{\{ github.workflow_sha \}\}\n          path: release-driver",
        ui,
    )
    assert '--expected-driver-sha "$EXPECTED_DRIVER_SHA"' in ui
    assert "--receipt artifacts/ui-qualification-driver-provenance.json" in ui
    self_test = ui.index("bind-downstream-theme.mjs --self-test")
    browser_suite = ui.index("npm run e2e -- --project=chromium")
    assert self_test < browser_suite
    assert "ui-qualification-driver-provenance.json" in ui
    assert (
        "cp ../release-driver/ui/scripts/run-downstream-qualification.mjs scripts/release-driver/"
        in ui
    )
    assert "cp ../release-driver/ui/scripts/bind-downstream-theme.mjs scripts/release-driver/" in ui
    assert "ARRAS_DOWNSTREAM_UI_DIR: ${{ github.workspace }}/ui" in ui
    assert "node scripts/release-driver/run-downstream-qualification.mjs" in ui
    public_download = job_text(workflow, "downloaded-release")
    assert "ref: ${{ github.workflow_sha }}" in public_download
    assert "node release-driver/ui/scripts/bind-downstream-theme.mjs --self-test" in public_download
    assert (
        "cp ../release-driver/ui/scripts/run-downstream-qualification.mjs scripts/release-driver/"
        in public_download
    )
    assert "node scripts/release-driver/run-downstream-qualification.mjs" in public_download
    fallback = (ROOT / ".github/workflows/verify-published-release.yml").read_text()
    anonymous = job_text(fallback, "anonymous-public-consumer")
    assert "node verification-driver/ui/scripts/bind-downstream-theme.mjs --self-test" in anonymous
    assert (
        "cp ../verification-driver/ui/scripts/run-downstream-qualification.mjs scripts/release-driver/"
        in anonymous
    )
    assert "node scripts/release-driver/run-downstream-qualification.mjs" in anonymous


def test_neutral_theme_peer_binding_self_test_preserves_source_and_unknown_metadata() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to test the release driver helper")
    helper = ROOT / "ui/scripts/bind-downstream-theme.mjs"
    result = subprocess.run(
        [node, str(helper), "--self-test"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "peer binding checks passed" in result.stdout


def test_ci_qualifies_the_built_wheel_doctor_before_candidate_admission() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    check = job_text(workflow, "check")
    doctor = "uv run --no-sync python tools/verify_doctor.py"
    assert "name: Verify installed doctor against the built wheel" in check
    assert doctor in check
    assert check.index("uv build --wheel && uv build --sdist") < check.index(doctor)
    assert check.index(doctor) < check.index("Verify installed extension host")
    assert check.index(doctor) < check.index("Verify installed UMF admission")
    assert "name: arras-doctor-installed" in check
    assert "path: artifacts/doctor-installed.json" in check
    candidate_artifact = check.split("name: arras-installed-candidate-artifacts", 1)[1]
    assert "artifacts/doctor-installed.json" not in candidate_artifact


def test_registry_publishing_is_separate_oidc_only_after_public_release_gates() -> None:
    workflow_path = ROOT / ".github/workflows/publish-registries.yml"
    workflow = workflow_path.read_text()
    assert 'workflows: ["Release"]' in workflow
    assert "workflow_run:" in workflow and "workflow_dispatch:" in workflow
    assert "release-driver-provenance" in workflow and "release-assets" in workflow
    assert "verify_public_release_assets.py plan" in workflow
    assert "verify_public_release_assets.py verify" in workflow
    assert "expected_tag_object_sha" in workflow
    assert "expected_sums_sha256" in workflow and "expected_wheel_sha256" in workflow
    assert "environment: npm" in workflow and "environment: pypi" in workflow
    assert workflow.count("id-token: write") == 2
    assert "NODE_AUTH_TOKEN" not in workflow and "NPM_TOKEN" not in workflow
    assert "ARRAS_PUBLISH_NPM" not in workflow and "ARRAS_PUBLISH_PYPI" not in workflow
    assert "--provenance" in workflow and "gh-action-pypi-publish@release/v1" in workflow
    assert "check-npm" in workflow and "check-pypi" in workflow
    assert "npm install --prefix" in workflow and "python3 -m venv" in workflow
    assert workflow.count("ref: ${{ github.workflow_sha }}") == 6
    assert workflow.count('test "$(git rev-parse HEAD)" = "$EXPECTED_DRIVER_SHA"') == 6
    assert workflow.count("--wait-for-present") == 2
    npm_publish = job_text(workflow, "npm-publish")
    pypi_publish = job_text(workflow, "pypi-publish")
    assert "timeout-minutes: 20" in npm_publish
    assert "--visibility-timeout 600" in npm_publish
    assert "--visibility-timeout 180" in pypi_publish
    assert workflow.count("publisher_workflow_sha") == 2
    assert '"install_scope": "plain-index-base"' in workflow
    assert "id: npm-upload" in workflow
    assert "if: steps.upload-check.outputs.status == 'absent'" in workflow
    assert "NPM_UPLOAD_OUTCOME: ${{ steps.npm-upload.outcome }}" in workflow
    assert (
        '"publication_mode": "oidc_upload" if os.environ["NPM_UPLOAD_OUTCOME"] == "success" else "existing_exact_bytes"'
        in workflow
    )
    assert '"oidc_trusted_publisher": os.environ["NPM_UPLOAD_OUTCOME"] == "success"' in workflow


def test_release_rebuild_must_match_the_selected_qualification_wheel_before_upload() -> None:
    build = job_text(RELEASE.read_text(), "build")
    selected = (
        "ef8dec70d8e0089e776166303bc622b573825f2a4e071791a316b58e22a40d0d"
        "  dist/arras-0.6.3-py3-none-any.whl"
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
    wheel = tmp_path / "dist/arras-0.6.3-py3-none-any.whl"
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
