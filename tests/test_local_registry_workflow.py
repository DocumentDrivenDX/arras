from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_local_qualification_is_required_before_publisher_join():
    publisher = (ROOT / ".github/workflows/publish-registries.yml").read_text()
    qualifier = (ROOT / ".github/workflows/qualify-local-registry.yml").read_text()
    assert "needs: [verify-hosted-release, qualify-local, qualify-hosted-recovery]" in publisher
    assert "needs.qualify-local.result == 'success'" in publisher
    assert "needs.verify-hosted-release.result == 'skipped'" in publisher
    assert "needs: [admit, source, installed, ui, downstream]" in qualifier
    assert qualifier.count("name: registry-verified-release-0.6.5") == 1
    assert qualifier.index("local_registry_qualification.py finish") < qualifier.index(
        "name: registry-verified-release-0.6.5"
    )
    assert "inputs.get('publication_run_id')" in qualifier
    assert "--python 3.11" in qualifier
    assert "python_version: '3.11'" in qualifier


def test_publisher_requires_verified_job_success_despite_skipped_ancestor():
    publisher = (ROOT / ".github/workflows/publish-registries.yml").read_text()
    for name in ["npm-preflight", "npm-publish", "pypi-preflight", "pypi-publish"]:
        text = publisher.split(f"\n  {name}:\n", 1)[1].split("\n  ", 1)[0]
        assert "!cancelled()" in text
        assert "needs.verify-release.result == 'success'" in text
    assert "local_registry_qualification.py recheck" in publisher


def test_qualifier_never_rebuilds_or_republishes_release_assets():
    workflow = (ROOT / ".github/workflows/qualify-local-registry.yml").read_text()
    for command in [
        "gh release create",
        "gh release upload",
        "uv build",
        "npm run build:wheel",
        "npm publish",
    ]:
        assert command not in workflow
    for command in [
        "tools/verify_native.py",
        "tools/verify_umf_admission.py",
        "tools/verify_distribution.py",
        "tools/verify_doctor.py",
        "tools/verify_extension_host.py",
        "test:packed-browser",
        "run-downstream-qualification.mjs",
    ]:
        assert command in workflow


def test_truss_requirement_is_scoped_to_native_test_command():
    workflow = (ROOT / ".github/workflows/qualify-local-registry.yml").read_text()
    assert "ARRAS_REQUIRE_TRUSS=1 uv run --no-sync pytest -m truss" in workflow
    assert "ARRAS_REQUIRE_TRUSS:" not in workflow
