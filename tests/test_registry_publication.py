from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".github/scripts/verify_registry_publication.py"
SPEC = importlib.util.spec_from_file_location("registry_publication", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
registry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(registry)

TAG = "v0.6.2"
VERSION = "0.6.2"
RUN_ID = "12345"
SOURCE_SHA = "1" * 40
DRIVER_SHA = "2" * 40
TAG_SHA = "3" * 40
REPOSITORY = "DocumentDrivenDX/arras"


def release_context() -> tuple[dict[str, Any], ...]:
    run = {
        "id": int(RUN_ID),
        "repository": {"full_name": REPOSITORY},
        "path": ".github/workflows/release.yml",
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": DRIVER_SHA,
        "status": "completed",
        "conclusion": "success",
        "workflow_id": 18,
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
        "installed-downstream / Install verified wheel and run explicit qualification stages",
        "Verify anonymous public release bundle",
        "Fresh installed UMF admission proof on exact wheel",
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
    workflow = {"id": 18, "path": ".github/workflows/release.yml", "state": "active"}
    provenance = {
        "schema": "arras.release-driver-provenance.v1",
        "event": "workflow_dispatch",
        "driver": {
            "sha": DRIVER_SHA,
            "workflow_sha": DRIVER_SHA,
            "ref": "refs/heads/main",
            "workflow_ref": f"{REPOSITORY}/.github/workflows/release.yml@refs/heads/main",
            "run_id": RUN_ID,
            "run_attempt": "1",
        },
        "target": {
            "tag": TAG,
            "tag_object_sha": TAG_SHA,
            "source_sha": SOURCE_SHA,
            "version": VERSION,
        },
    }
    tag_ref = {"ref": f"refs/tags/{TAG}", "object": {"sha": TAG_SHA, "type": "tag"}}
    tag_object = {
        "sha": TAG_SHA,
        "tag": TAG,
        "object": {"sha": SOURCE_SHA, "type": "commit"},
    }
    names_assets = {
        "SHA256SUMS",
        f"arras-{VERSION}-py3-none-any.whl",
        f"arras-{VERSION}.tar.gz",
        f"documentdrivendx-arras-ui-{VERSION}.tgz",
    }
    release = {
        "tag_name": TAG,
        "draft": False,
        "prerelease": False,
        "assets": [{"name": name} for name in sorted(names_assets)],
    }
    return run, jobs, workflow, provenance, tag_ref, tag_object, release


def validate(*context: dict[str, Any], **kwargs: Any) -> dict[str, str]:
    return registry.validate_publication_context(
        *context,
        expected_asset_names={
            "SHA256SUMS",
            f"arras-{VERSION}-py3-none-any.whl",
            f"arras-{VERSION}.tar.gz",
            f"documentdrivendx-arras-ui-{VERSION}.tgz",
        },
        repository=REPOSITORY,
        default_branch="main",
        requested_run_id=RUN_ID,
        **kwargs,
    )


def test_successful_publication_requires_exact_original_run_and_all_ten_gates() -> None:
    context = release_context()
    result = validate(*context)
    assert result["tag"] == TAG
    assert result["source_sha"] == SOURCE_SHA
    assert result["tag_object_sha"] == TAG_SHA
    assert result["version"] == VERSION

    run, jobs, workflow, provenance, tag_ref, tag_object, release = context
    failed = json.loads(json.dumps(jobs))
    failed["jobs"][2]["conclusion"] = "failure"
    with pytest.raises(registry.RegistryPublicationError, match="did not succeed"):
        validate(run, failed, workflow, provenance, tag_ref, tag_object, release)
    missing = json.loads(json.dumps(jobs))
    missing["jobs"].pop(8)
    missing["total_count"] -= 1
    with pytest.raises(registry.RegistryPublicationError, match="missing mandatory gates"):
        validate(run, missing, workflow, provenance, tag_ref, tag_object, release)


@pytest.mark.parametrize("conclusion", ["failure", "skipped"])
def test_installed_downstream_gate_requires_success(conclusion: str) -> None:
    run, jobs, workflow, provenance, tag_ref, tag_object, release = release_context()
    downstream = next(
        job
        for job in jobs["jobs"]
        if job["name"]
        == "installed-downstream / Install verified wheel and run explicit qualification stages"
    )
    downstream["conclusion"] = conclusion
    with pytest.raises(registry.RegistryPublicationError, match="did not succeed"):
        validate(run, jobs, workflow, provenance, tag_ref, tag_object, release)


def test_installed_downstream_gate_rejects_missing_wrong_suffix_and_duplicate_names() -> None:
    context = release_context()
    run, jobs, workflow, provenance, tag_ref, tag_object, release = context
    correct_name = (
        "installed-downstream / Install verified wheel and run explicit qualification stages"
    )

    missing = json.loads(json.dumps(jobs))
    missing["jobs"] = [job for job in missing["jobs"] if job["name"] != correct_name]
    missing["total_count"] = len(missing["jobs"])
    with pytest.raises(registry.RegistryPublicationError, match="missing mandatory gates"):
        validate(run, missing, workflow, provenance, tag_ref, tag_object, release)

    wrong_suffix = json.loads(json.dumps(jobs))
    downstream = next(job for job in wrong_suffix["jobs"] if job["name"] == correct_name)
    downstream["name"] = "installed-downstream / Install verified wheel"
    with pytest.raises(registry.RegistryPublicationError, match="missing mandatory gates"):
        validate(run, wrong_suffix, workflow, provenance, tag_ref, tag_object, release)

    duplicate = json.loads(json.dumps(jobs))
    duplicate["jobs"].append(dict(duplicate["jobs"][7]))
    duplicate["total_count"] = len(duplicate["jobs"])
    with pytest.raises(registry.RegistryPublicationError, match="duplicate names"):
        validate(run, duplicate, workflow, provenance, tag_ref, tag_object, release)


def test_publication_rejects_wrong_run_source_event_or_release_identity() -> None:
    context = release_context()
    run, jobs, workflow, provenance, tag_ref, tag_object, release = context
    altered = json.loads(json.dumps(run))
    altered["id"] += 1
    with pytest.raises(registry.RegistryPublicationError, match="requested run id"):
        validate(altered, jobs, workflow, provenance, tag_ref, tag_object, release)
    with pytest.raises(registry.RegistryPublicationError, match="manual source pin"):
        validate(
            run,
            jobs,
            workflow,
            provenance,
            tag_ref,
            tag_object,
            release,
            expected_source_sha="4" * 40,
        )
    altered_release = json.loads(json.dumps(release))
    altered_release["tag_name"] = "v0.6.3"
    with pytest.raises(registry.RegistryPublicationError, match="another tag"):
        validate(run, jobs, workflow, provenance, tag_ref, tag_object, altered_release)


def test_remote_tag_movement_and_annotated_target_mismatch_fail_closed() -> None:
    context = release_context()
    run, jobs, workflow, provenance, tag_ref, tag_object, release = context
    moved_ref = json.loads(json.dumps(tag_ref))
    moved_ref["object"]["sha"] = "4" * 40
    with pytest.raises(registry.RegistryPublicationError, match="tag object differs"):
        validate(run, jobs, workflow, provenance, moved_ref, tag_object, release)
    moved_target = json.loads(json.dumps(tag_object))
    moved_target["object"]["sha"] = "5" * 40
    with pytest.raises(registry.RegistryPublicationError, match="no longer targets"):
        validate(run, jobs, workflow, provenance, tag_ref, moved_target, release)


def test_successful_tag_push_provenance_is_supported() -> None:
    run, jobs, workflow, provenance, tag_ref, tag_object, release = release_context()
    run.update(event="push", head_branch=TAG, head_sha=SOURCE_SHA)
    provenance["event"] = "push"
    provenance["driver"].update(
        sha=SOURCE_SHA,
        workflow_sha=SOURCE_SHA,
        ref=f"refs/tags/{TAG}",
        workflow_ref=f"{REPOSITORY}/.github/workflows/release.yml@refs/tags/{TAG}",
    )
    result = validate(run, jobs, workflow, provenance, tag_ref, tag_object, release)
    assert result["driver_sha"] == SOURCE_SHA


def _write_wheel(path: Path, metadata: bytes) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("arras-0.6.2.dist-info/METADATA", metadata)


def _write_sdist(path: Path, metadata: bytes) -> None:
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo("arras-0.6.2/PKG-INFO")
        info.size = len(metadata)
        archive.addfile(info, io.BytesIO(metadata))


@pytest.mark.parametrize(
    "requirement",
    [
        "umf-core @ https://example.invalid/umf.whl ; extra == 'umf'",
        "umf-core @ file:///tmp/umf.whl ; extra == 'umf'",
        "umf-core @ git+https://example.invalid/umf.git ; extra == 'umf'",
        "umf-core @ ../dist/umf.whl ; extra == 'umf'",
        "umf-core@https://example.invalid/umf.whl ; extra == 'umf'",
        "umf-core [native] @file:///tmp/umf.whl ; extra == 'umf'",
    ],
)
def test_pypi_preflight_rejects_all_direct_references_even_in_an_extra(
    requirement: str, tmp_path: Path
) -> None:
    wheel = tmp_path / "arras-0.6.2-py3-none-any.whl"
    sdist = tmp_path / "arras-0.6.2.tar.gz"
    bad = (
        f"Metadata-Version: 2.4\nName: arras\nVersion: 0.6.2\nRequires-Dist: {requirement}\n\n"
    ).encode()
    _write_wheel(wheel, bad)
    _write_sdist(sdist, bad)
    failures = registry.pypi_incompatible_direct_requirements(wheel, sdist)
    assert set(failures) == {wheel.name, sdist.name}
    assert all("extra == 'umf'" in values[0] for values in failures.values())


def test_pypi_preflight_accepts_version_pins_and_normal_requirements(tmp_path: Path) -> None:
    wheel = tmp_path / "arras-0.6.2-py3-none-any.whl"
    sdist = tmp_path / "arras-0.6.2.tar.gz"
    metadata = b"Metadata-Version: 2.4\nName: arras\nVersion: 0.6.2\nRequires-Dist: umf-core==0.10.0 ; extra == 'umf'\nRequires-Dist: graphql-core>=3.3,<3.4\n\n"
    _write_wheel(wheel, metadata)
    _write_sdist(sdist, metadata)
    assert registry.pypi_incompatible_direct_requirements(wheel, sdist) == {}


def test_npm_registry_check_distinguishes_absent_matching_and_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"verified release tarball"
    digest = hashlib.sha256(payload).hexdigest()

    def absent(url: str) -> None:
        return None

    monkeypatch.setattr(registry, "_registry_json", absent)
    assert registry.check_npm_registry("@documentdrivendx/arras-ui", VERSION, digest) == "absent"

    def existing(url: str) -> dict[str, Any]:
        return {
            "name": "@documentdrivendx/arras-ui",
            "version": VERSION,
            "dist": {"tarball": "https://registry.npmjs.org/package.tgz"},
        }

    def download(url: str) -> bytes:
        return payload

    monkeypatch.setattr(registry, "_registry_json", existing)
    monkeypatch.setattr(registry, "_download_public", download)
    assert registry.check_npm_registry("@documentdrivendx/arras-ui", VERSION, digest) == "matching"

    def collision(url: str) -> bytes:
        return b"different bytes"

    monkeypatch.setattr(registry, "_download_public", collision)
    with pytest.raises(registry.RegistryPublicationError, match="version collision"):
        registry.check_npm_registry("@documentdrivendx/arras-ui", VERSION, digest)


def test_pypi_registry_check_verifies_metadata_and_served_file_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = b"wheel payload"
    sdist = b"sdist payload"
    expected = {
        "arras-0.6.2-py3-none-any.whl": hashlib.sha256(wheel).hexdigest(),
        "arras-0.6.2.tar.gz": hashlib.sha256(sdist).hexdigest(),
    }

    def absent(url: str) -> None:
        return None

    monkeypatch.setattr(registry, "_registry_json", absent)
    assert registry.check_pypi_registry("arras", VERSION, expected) == "absent"
    metadata = {
        "info": {"name": "arras", "version": VERSION},
        "urls": [
            {
                "filename": name,
                "digests": {"sha256": digest},
                "url": f"https://files.pythonhosted.org/{name}",
            }
            for name, digest in expected.items()
        ],
    }

    def existing(url: str) -> dict[str, Any]:
        return metadata

    def download(url: str) -> bytes:
        return wheel if url.endswith(".whl") else sdist

    monkeypatch.setattr(registry, "_registry_json", existing)
    monkeypatch.setattr(registry, "_download_public", download)
    assert registry.check_pypi_registry("arras", VERSION, expected) == "matching"

    def collision(url: str) -> bytes:
        return b"different bytes"

    monkeypatch.setattr(registry, "_download_public", collision)
    with pytest.raises(registry.RegistryPublicationError, match="served registry file bytes"):
        registry.check_pypi_registry("arras", VERSION, expected)


def test_registry_visibility_wait_retries_only_absence_and_requires_matching_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = iter([0.0, 0.0])
    monkeypatch.setattr(registry.time, "monotonic", lambda: next(clock))

    def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(registry.time, "sleep", no_sleep)
    states = iter(["absent", "matching"])
    assert registry.wait_for_registry_match(lambda: next(states), timeout_seconds=1) == "matching"
    monkeypatch.setattr(registry.time, "monotonic", lambda: 0.0)
    assert registry.wait_for_registry_match(lambda: "matching", timeout_seconds=600) == "matching"

    clock = iter([0.0, 0.0, 1.0])
    monkeypatch.setattr(registry.time, "monotonic", lambda: next(clock))
    with pytest.raises(registry.RegistryPublicationError, match="visibility timeout"):
        registry.wait_for_registry_match(lambda: "absent", timeout_seconds=1)

    with pytest.raises(registry.RegistryPublicationError, match="1 to 600 seconds"):
        registry.wait_for_registry_match(lambda: "matching", timeout_seconds=601)

    def unauthorized() -> str:
        raise registry.RegistryPublicationError("HTTP 401")

    clock = iter([0.0])
    monkeypatch.setattr(registry.time, "monotonic", lambda: next(clock))
    with pytest.raises(registry.RegistryPublicationError, match="HTTP 401"):
        registry.wait_for_registry_match(unauthorized, timeout_seconds=1)


def test_registry_authorization_and_server_errors_are_not_treated_as_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.error
    import urllib.request
    from email.message import Message

    def unauthorized(request: Any, timeout: int) -> Any:
        raise urllib.error.HTTPError(request.full_url, 401, "unauthorized", Message(), None)

    monkeypatch.setattr(urllib.request, "urlopen", unauthorized)
    with pytest.raises(registry.RegistryPublicationError, match="HTTP 401"):
        registry._registry_json("https://registry.npmjs.org/%40documentdrivendx%2Farras-ui/0.6.2")


@pytest.mark.parametrize(
    "requested,failed,code,pending",
    [
        ("registry.npmjs.org", "registry.npmjs.org", 404, True),
        ("registry.npmjs.org", "registry.npmjs.org", 403, False),
        ("registry.npmjs.org", "registry.npmjs.org", 500, False),
        ("registry.npmjs.org", "other.invalid", 404, False),
        ("files.pythonhosted.org", "files.pythonhosted.org", 404, False),
    ],
)
def test_only_same_host_npm_tarball_404_is_pending(
    monkeypatch: pytest.MonkeyPatch, requested: str, failed: str, code: int, pending: bool
) -> None:
    import urllib.error
    from email.message import Message

    def failure(_request: Any, timeout: int) -> Any:
        raise urllib.error.HTTPError(
            f"https://{failed}/package.tgz", code, "failure", Message(), None
        )

    monkeypatch.setattr(registry.urllib.request, "urlopen", failure)
    with pytest.raises(registry.RegistryPublicationError) as caught:
        registry._download_public(f"https://{requested}/package.tgz")
    assert isinstance(caught.value, registry.RegistryArtifactPendingError) is pending


def test_pending_tarball_wait_is_bounded_and_requires_matching_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(registry.time, "sleep", sleeps.append)
    monkeypatch.setattr(registry.time, "monotonic", lambda: 0.0)
    outcomes = iter(["pending", "matching"])

    def eventually_visible() -> str:
        value = next(outcomes)
        if value == "pending":
            raise registry.RegistryArtifactPendingError("accepted tarball not visible")
        return value

    assert registry.wait_for_registry_match(eventually_visible, 600) == "matching"
    assert sleeps == [5]
    clock = iter([0.0, 0.0, 1.0])
    monkeypatch.setattr(registry.time, "monotonic", lambda: next(clock))

    def still_pending() -> str:
        raise registry.RegistryArtifactPendingError("accepted tarball not visible")

    with pytest.raises(registry.RegistryPublicationError, match="visibility timeout"):
        registry.wait_for_registry_match(still_pending, 1)


def test_pending_preflight_never_reports_absent_or_authorizes_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def pending(*args: Any, **kwargs: Any) -> str:
        raise registry.RegistryArtifactPendingError("accepted tarball not visible")

    monkeypatch.setattr(registry, "check_npm_registry", pending)
    receipt = tmp_path / "preflight.json"
    github_output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    args = registry._parser().parse_args(
        ["check-npm", "--version", "0.7.0", "--sha256", "a" * 64, "--output", str(receipt)]
    )
    assert registry._execute(args) == 1
    assert not receipt.exists() and not github_output.exists()


def test_visibility_wait_never_retries_a_version_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def metadata(_url: str) -> dict[str, Any]:
        return {
            "name": "@documentdrivendx/arras-ui",
            "version": "0.7.0",
            "dist": {"tarball": "https://registry.npmjs.org/package.tgz"},
        }

    def collision(_url: str) -> bytes:
        return b"wrong bytes"

    monkeypatch.setattr(
        registry,
        "_registry_json",
        metadata,
    )
    monkeypatch.setattr(registry, "_download_public", collision)
    sleeps: list[float] = []
    monkeypatch.setattr(registry.time, "sleep", sleeps.append)
    monkeypatch.setattr(registry.time, "monotonic", lambda: 0.0)
    with pytest.raises(registry.RegistryPublicationError, match="version collision"):
        registry.wait_for_registry_match(
            lambda: registry.check_npm_registry("@documentdrivendx/arras-ui", "0.7.0", "a" * 64),
            600,
        )
    assert sleeps == []


@pytest.mark.parametrize("outcome", [None, "failure", "skipped", "cancelled", "success"])
def test_action_capable_publication_requires_its_action_job(outcome: str | None) -> None:
    jobs = release_context()[1]
    if outcome is not None:
        jobs["jobs"].append(
            {
                "name": "Fresh installed generated-action proof when the wheel requires it",
                "conclusion": outcome,
            }
        )
        jobs["total_count"] += 1
    if outcome == "success":
        registry._validate_jobs(jobs, "0.7.0", actions_required=True)
    else:
        with pytest.raises(registry.RegistryPublicationError, match="mandatory"):
            registry._validate_jobs(jobs, "0.7.0", actions_required=True)


def test_historical_pure_core_publication_keeps_the_original_ten_gates() -> None:
    registry._validate_jobs(release_context()[1], "0.6.5", actions_required=False)


@pytest.mark.parametrize("pin,action_job", [("0.10.0", False), ("0.10.5", False), ("0.10.5", True)])
def test_validate_release_inputs_hands_actual_wheel_capability_to_job_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pin: str,
    action_job: bool,
) -> None:
    """Bundle validation is isolated; real wheel parsing and context/job handoff run."""
    import argparse

    context = release_context()
    jobs, release = context[1], context[6]
    if action_job:
        jobs["jobs"].append(
            {
                "name": "Fresh installed generated-action proof when the wheel requires it",
                "conclusion": "success",
            }
        )
        jobs["total_count"] += 1
    inputs: dict[str, Path] = {}
    for name, value in zip(
        ["run", "jobs", "workflow", "provenance", "tag_ref", "tag_object", "release"],
        context,
        strict=True,
    ):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value))
        inputs[name] = path
    assets = tmp_path / "assets"
    assets.mkdir()
    wheel = assets / f"arras-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            f"arras-{VERSION}.dist-info/METADATA",
            f"Name: arras\nVersion: {VERSION}\nRequires-Dist: umf-core=={pin}; extra == 'umf'\n",
        )
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    (assets / "release-evidence.json").write_text(
        json.dumps({"release_artifacts": {"wheel": {"filename": wheel.name, "sha256": digest}}})
    )
    (assets / "SHA256SUMS").write_text("synthetic bundle boundary\n")
    entries = {a["name"]: "a" * 64 for a in release["assets"] if a["name"] != "SHA256SUMS"}

    def verified_bundle(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], dict[str, str]]:
        return {}, entries

    monkeypatch.setattr(registry._public_assets, "_validate_trusted", verified_bundle)
    args = argparse.Namespace(
        **inputs,
        assets=assets,
        expected_wheel_sha256="",
        expected_sums_sha256="",
        repository=REPOSITORY,
        default_branch="main",
        run_id=RUN_ID,
        expected_tag="",
        expected_source_sha="",
        expected_tag_object_sha="",
    )
    if pin == "0.10.5" and not action_job:
        with pytest.raises(registry.RegistryPublicationError, match="mandatory gates"):
            registry.validate_release_inputs(args)
    else:
        result = registry.validate_release_inputs(args)
        assert result["wheel_sha256"] == digest
