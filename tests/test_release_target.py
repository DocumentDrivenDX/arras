from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".github/scripts/release_target.py"
SPEC = importlib.util.spec_from_file_location("release_target", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
release_target = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_target)


def git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=path, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def test_tag_push_selector_requires_semver_ref_and_event_commit() -> None:
    sha = "a" * 40
    assert release_target.select_target(
        event_name="push",
        ref="refs/tags/v0.5.1",
        ref_name="v0.5.1",
        github_sha=sha,
        default_branch="main",
    ) == ("v0.5.1", sha)
    for kwargs in (
        {"ref": "refs/heads/main", "ref_name": "v0.5.1"},
        {"ref": "refs/tags/v0.5.1;touch", "ref_name": "v0.5.1;touch"},
        {"ref": "refs/tags/v0.5.1", "ref_name": "v0.5.2"},
    ):
        with pytest.raises(release_target.ReleaseTargetError):
            release_target.select_target(
                event_name="push",
                github_sha=sha,
                default_branch="main",
                **kwargs,
            )
    with pytest.raises(release_target.ReleaseTargetError, match="event commit"):
        release_target.select_target(
            event_name="push",
            ref="refs/tags/v0.5.1",
            ref_name="v0.5.1",
            github_sha=sha,
            default_branch="main",
            expected_sha="b" * 40,
        )


def test_manual_selector_is_default_branch_only_and_fails_closed() -> None:
    target = "1234567890abcdef1234567890abcdef12345678"
    assert release_target.select_target(
        event_name="workflow_dispatch",
        ref="refs/heads/main",
        ref_name="main",
        github_sha="f" * 40,
        default_branch="main",
        requested_tag="v0.5.1",
        expected_sha=target,
    ) == ("v0.5.1", target)
    bad_requests = (
        {"ref": "refs/heads/release", "default_branch": "main"},
        {"requested_tag": "v0.5.1;echo hacked"},
        {"requested_tag": "v0.5.1", "expected_sha": "../main"},
        {"requested_tag": "v0.5.1", "expected_sha": "a" * 39},
        {"event_name": "pull_request"},
    )
    base = {
        "event_name": "workflow_dispatch",
        "ref": "refs/heads/main",
        "ref_name": "main",
        "github_sha": "f" * 40,
        "default_branch": "main",
        "requested_tag": "v0.5.1",
        "expected_sha": target,
    }
    for overrides in bad_requests:
        with pytest.raises(release_target.ReleaseTargetError):
            release_target.select_target(**(base | overrides))


@pytest.fixture
def remote_release_repo(tmp_path: Path) -> dict[str, str | Path]:
    remote = tmp_path / "origin.git"
    work = tmp_path / "work"
    remote.mkdir()
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    work.mkdir()
    git(work, "init", "-b", "main")
    git(work, "config", "user.email", "release-test@example.invalid")
    git(work, "config", "user.name", "Release test")
    git(work, "remote", "add", "origin", str(remote))
    (work / "pyproject.toml").write_text('[project]\nname = "arras"\nversion = "0.5.1"\n')
    git(work, "add", "pyproject.toml")
    git(work, "commit", "-m", "tagged source")
    source_sha = git(work, "rev-parse", "HEAD")
    git(work, "tag", "v0.5.1")
    git(work, "tag", "v0.5.0")
    git(work, "push", "origin", "main", "--tags")
    subprocess.run(
        ["git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"],
        check=True,
        capture_output=True,
    )
    (work / "pyproject.toml").write_text('[project]\nname = "arras"\nversion = "0.5.2"\n')
    git(work, "add", "pyproject.toml")
    git(work, "commit", "-m", "new driver")
    driver_sha = git(work, "rev-parse", "HEAD")
    git(work, "push", "origin", "main")
    return {"work": work, "remote": remote, "source_sha": source_sha, "driver_sha": driver_sha}


def invoke_validate(
    repo: dict[str, str | Path], tmp_path: Path, *, tag: str = "v0.5.1", sha: str | None = None
) -> subprocess.CompletedProcess[str]:
    output = tmp_path / "github-output"
    env = os.environ | {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_NAME": "main",
        "GITHUB_SHA": str(repo["driver_sha"]),
        "GITHUB_WORKFLOW_SHA": str(repo["driver_sha"]),
        "GITHUB_WORKFLOW_REF": "org/arras/.github/workflows/release.yml@refs/heads/main",
        "GITHUB_RUN_ID": "12345",
        "GITHUB_RUN_ATTEMPT": "1",
        "DEFAULT_BRANCH": "main",
        "RELEASE_TAG": tag,
        "EXPECTED_SOURCE_SHA": sha or str(repo["source_sha"]),
        "GITHUB_OUTPUT": str(output),
        "PROVENANCE_DIR": str(tmp_path / "artifacts"),
    }
    return subprocess.run(
        [sys.executable, str(SCRIPT), "validate"],
        cwd=repo["work"],
        env=env,
        capture_output=True,
        text=True,
    )


def test_cli_resolves_immutable_existing_tag_and_separates_driver_provenance(
    remote_release_repo: dict[str, str | Path], tmp_path: Path
) -> None:
    result = invoke_validate(remote_release_repo, tmp_path)
    assert result.returncode == 0, result.stderr
    outputs = (tmp_path / "github-output").read_text()
    assert f"source_sha={remote_release_repo['source_sha']}\n" in outputs
    assert f"driver_sha={remote_release_repo['driver_sha']}\n" in outputs
    assert "tag=v0.5.1\n" in outputs and "version=0.5.1\n" in outputs
    assert re.search(r"tag_object_sha=[0-9a-f]{40}\n", outputs)
    provenance = (tmp_path / "artifacts/release-driver-provenance.json").read_text()
    assert str(remote_release_repo["driver_sha"]) in provenance
    assert str(remote_release_repo["source_sha"]) in provenance


@pytest.mark.parametrize(
    ("tag", "sha", "error"),
    [
        ("v9.9.9", None, "does not exist"),
        ("v0.5.1", "a" * 40, "does not match"),
        ("v0.5.0", None, "version does not match"),
        ("v0.5.1;echo bad", None, "versioned vX.Y.Z"),
    ],
)
def test_cli_rejects_missing_moved_mismatched_or_malformed_target(
    remote_release_repo: dict[str, str | Path],
    tmp_path: Path,
    tag: str,
    sha: str | None,
    error: str,
) -> None:
    result = invoke_validate(remote_release_repo, tmp_path, tag=tag, sha=sha)
    assert result.returncode != 0
    assert error in result.stderr


def test_cli_rejects_default_branch_driver_mismatch(
    remote_release_repo: dict[str, str | Path], tmp_path: Path
) -> None:
    result = invoke_validate(remote_release_repo, tmp_path)
    env = os.environ | {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/other",
        "GITHUB_REF_NAME": "other",
        "GITHUB_SHA": str(remote_release_repo["driver_sha"]),
        "GITHUB_WORKFLOW_SHA": str(remote_release_repo["driver_sha"]),
        "DEFAULT_BRANCH": "main",
        "RELEASE_TAG": "v0.5.1",
        "EXPECTED_SOURCE_SHA": str(remote_release_repo["source_sha"]),
    }
    failed = subprocess.run(
        [sys.executable, str(SCRIPT), "validate"],
        cwd=remote_release_repo["work"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert failed.returncode != 0 and "default branch" in failed.stderr


def test_publication_recheck_rejects_a_moved_remote_tag(
    remote_release_repo: dict[str, str | Path], tmp_path: Path
) -> None:
    work = Path(remote_release_repo["work"])
    git(work, "tag", "-f", "v0.5.1", str(remote_release_repo["driver_sha"]))
    git(work, "push", "--force", "origin", "refs/tags/v0.5.1")
    env = os.environ | {
        "TARGET_TAG": "v0.5.1",
        "TARGET_SOURCE_SHA": str(remote_release_repo["source_sha"]),
        "TARGET_TAG_OBJECT_SHA": str(remote_release_repo["source_sha"]),
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "recheck"], cwd=work, env=env, capture_output=True, text=True
    )
    assert result.returncode != 0 and "moved" in result.stderr


def test_publication_recheck_runs_from_driver_checkout_in_actions_workspace(
    remote_release_repo: dict[str, str | Path], tmp_path: Path
) -> None:
    workspace = tmp_path / "job-workspace"
    workspace.mkdir()
    driver = workspace / "driver"
    source = workspace / "source"
    git(workspace, "clone", str(remote_release_repo["remote"]), str(driver))
    git(workspace, "clone", str(remote_release_repo["remote"]), str(source))
    git(source, "checkout", str(remote_release_repo["source_sha"]))
    helper = driver / ".github/scripts/release_target.py"
    helper.parent.mkdir(parents=True)
    helper.write_bytes(SCRIPT.read_bytes())
    tag_object = git(driver, "rev-parse", "refs/tags/v0.5.1")
    env = os.environ | {
        "TARGET_TAG": "v0.5.1",
        "TARGET_SOURCE_SHA": str(remote_release_repo["source_sha"]),
        "TARGET_TAG_OBJECT_SHA": tag_object,
        "EXPECTED_DRIVER_SHA": str(remote_release_repo["driver_sha"]),
    }
    workflow_shell = (
        "set -euo pipefail; "
        'test "$(git -C driver rev-parse HEAD)" = "$EXPECTED_DRIVER_SHA"; '
        'test "$(git -C source rev-parse HEAD)" = "$TARGET_SOURCE_SHA"; '
        f'cd driver; "{sys.executable}" .github/scripts/release_target.py recheck'
    )
    result = subprocess.run(
        ["bash", "-c", workflow_shell],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_remote_fetch_failure_fails_closed(remote_release_repo: dict[str, str | Path]) -> None:
    work = Path(remote_release_repo["work"])
    git(work, "remote", "set-url", "origin", str(work / "missing-origin"))
    result = invoke_validate(remote_release_repo, work / "not-created")
    assert result.returncode != 0
    assert "could not query the remote tag" in result.stderr or "does not exist" in result.stderr
