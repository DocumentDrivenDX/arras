#!/usr/bin/env python3
"""Resolve an immutable release tag from a separately identified workflow driver."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

TAG_RE = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
SHA_RE = re.compile(r"[0-9a-fA-F]{40}\Z")


class ReleaseTargetError(ValueError):
    """A release request does not bind an existing immutable source tag."""


def select_target(
    *,
    event_name: str,
    ref: str,
    ref_name: str,
    github_sha: str,
    default_branch: str,
    requested_tag: str = "",
    expected_sha: str = "",
) -> tuple[str, str]:
    """Return the exact tag and expected source commit for a supported event."""
    if event_name == "push":
        tag = ref_name
        if not TAG_RE.fullmatch(tag) or ref != f"refs/tags/{tag}":
            raise ReleaseTargetError("push must target a versioned vX.Y.Z tag")
        if not SHA_RE.fullmatch(github_sha):
            raise ReleaseTargetError("push source commit must be a full 40-hex SHA")
        if expected_sha and expected_sha.lower() != github_sha.lower():
            raise ReleaseTargetError("push source commit does not match the event commit")
        return tag, github_sha.lower()

    if event_name == "workflow_dispatch":
        if not default_branch or ref != f"refs/heads/{default_branch}":
            raise ReleaseTargetError(
                "manual release recovery must run from the repository default branch"
            )
        if not TAG_RE.fullmatch(requested_tag):
            raise ReleaseTargetError("release_tag must be a versioned vX.Y.Z tag")
        if not SHA_RE.fullmatch(expected_sha):
            raise ReleaseTargetError("expected_source_sha must be a full 40-hex SHA")
        return requested_tag, expected_sha.lower()

    raise ReleaseTargetError("only tag pushes and default-branch manual recovery are supported")


def run_git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], check=False, capture_output=True, text=True, encoding="utf-8"
    )
    if check and result.returncode:
        raise ReleaseTargetError(f"git {' '.join(args[:2])} failed ({result.returncode})")
    return result.stdout.strip()


def remote_tag_identity(tag: str) -> tuple[str, str]:
    result = subprocess.run(
        ["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        raise ReleaseTargetError("could not query the remote tag")
    refs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) != 2 or not SHA_RE.fullmatch(fields[0]):
            raise ReleaseTargetError("remote returned an invalid tag identity")
        refs[fields[1]] = fields[0].lower()
    tag_ref = f"refs/tags/{tag}"
    peeled_ref = f"{tag_ref}^{{}}"
    if tag_ref not in refs:
        raise ReleaseTargetError("requested release tag does not exist on origin")
    object_sha = refs[tag_ref]
    commit_sha = refs.get(peeled_ref, object_sha)
    return object_sha, commit_sha


def local_tag_identity(tag: str) -> tuple[str, str]:
    tag_ref = f"refs/tags/{tag}"
    object_sha = run_git("rev-parse", tag_ref)
    commit_sha = run_git("rev-parse", f"{tag_ref}^{{commit}}")
    if not SHA_RE.fullmatch(object_sha) or not SHA_RE.fullmatch(commit_sha):
        raise ReleaseTargetError("local tag does not resolve to a commit")
    return object_sha.lower(), commit_sha.lower()


def ensure_tag_fetched(tag: str) -> tuple[str, str]:
    remote = remote_tag_identity(tag)
    local_ref = f"refs/tags/{tag}"
    exists = subprocess.run(["git", "show-ref", "--verify", "--quiet", local_ref]).returncode == 0
    if not exists:
        run_git("fetch", "--no-tags", "origin", f"{local_ref}:{local_ref}")
    local = local_tag_identity(tag)
    if local != remote:
        raise ReleaseTargetError("local tag identity differs from the current remote tag")
    return remote


def version_at(source_sha: str) -> str:
    raw = run_git("show", f"{source_sha}:pyproject.toml").encode()
    try:
        project = tomllib.loads(raw.decode("utf-8"))["project"]
        version = project["version"]
    except (UnicodeDecodeError, KeyError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseTargetError("tagged pyproject.toml has no valid project version") from exc
    if not isinstance(version, str) or not re.fullmatch(
        r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version
    ):
        raise ReleaseTargetError("tagged project version is not a numeric X.Y.Z version")
    return version


def write_outputs(values: dict[str, str]) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as stream:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise ReleaseTargetError("workflow output contains a line break")
            stream.write(f"{key}={value}\n")


def validate() -> None:
    env = os.environ
    event = env.get("GITHUB_EVENT_NAME", "")
    tag, expected_sha = select_target(
        event_name=event,
        ref=env.get("GITHUB_REF", ""),
        ref_name=env.get("GITHUB_REF_NAME", ""),
        github_sha=env.get("GITHUB_SHA", ""),
        default_branch=env.get("DEFAULT_BRANCH", ""),
        requested_tag=env.get("RELEASE_TAG", ""),
        expected_sha=env.get("EXPECTED_SOURCE_SHA", ""),
    )
    driver_sha = run_git("rev-parse", "HEAD").lower()
    workflow_sha = env.get("GITHUB_WORKFLOW_SHA", "").lower()
    if not SHA_RE.fullmatch(workflow_sha) or driver_sha != workflow_sha:
        raise ReleaseTargetError("checked-out driver does not match the workflow commit")
    workflow_ref = env.get("GITHUB_WORKFLOW_REF", "")
    if not re.fullmatch(r"[A-Za-z0-9_./@:-]+", workflow_ref):
        raise ReleaseTargetError("workflow reference contains unsupported characters")
    if (
        not env.get("GITHUB_RUN_ID", "").isdigit()
        or not env.get("GITHUB_RUN_ATTEMPT", "").isdigit()
    ):
        raise ReleaseTargetError("workflow run identity is invalid")
    if event == "workflow_dispatch" and driver_sha != env.get("GITHUB_SHA", "").lower():
        raise ReleaseTargetError("manual recovery driver is not the selected default-branch commit")

    tag_object_sha, source_sha = ensure_tag_fetched(tag)
    if source_sha != expected_sha:
        raise ReleaseTargetError("remote tag commit does not match the expected source commit")
    version = version_at(source_sha)
    if tag != f"v{version}":
        raise ReleaseTargetError("tagged project version does not match the release tag")

    values = {
        "tag": tag,
        "source_sha": source_sha,
        "tag_object_sha": tag_object_sha,
        "version": version,
        "driver_sha": driver_sha,
        "workflow_ref": workflow_ref,
        "umf_admission_required": str(
            tuple(int(part) for part in version.split(".")) >= (0, 6, 0)
        ).lower(),
    }
    write_outputs(values)
    provenance = {
        "schema": "arras.release-driver-provenance.v1",
        "event": event,
        "driver": {
            "sha": driver_sha,
            "ref": env.get("GITHUB_REF", ""),
            "workflow_ref": env.get("GITHUB_WORKFLOW_REF", ""),
            "workflow_sha": workflow_sha,
            "run_id": env.get("GITHUB_RUN_ID", ""),
            "run_attempt": env.get("GITHUB_RUN_ATTEMPT", ""),
        },
        "target": {
            "tag": tag,
            "tag_object_sha": tag_object_sha,
            "source_sha": source_sha,
            "version": version,
        },
    }
    output_dir = Path(env.get("PROVENANCE_DIR", "artifacts"))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "release-driver-provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = env.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(
                "## Release source binding\n\n"
                f"- Driver commit: `{driver_sha}`\n"
                f"- Driver workflow ref: `{provenance['driver']['workflow_ref']}`\n"
                f"- Run: `{provenance['driver']['run_id']}` attempt `{provenance['driver']['run_attempt']}`\n"
                f"- Target tag: `{tag}`\n"
                f"- Target source commit: `{source_sha}`\n"
                f"- Tagged package version: `{version}`\n"
            )


def recheck() -> None:
    env = os.environ
    tag = env.get("TARGET_TAG", "")
    source_sha = env.get("TARGET_SOURCE_SHA", "").lower()
    tag_object_sha = env.get("TARGET_TAG_OBJECT_SHA", "").lower()
    if (
        not TAG_RE.fullmatch(tag)
        or not SHA_RE.fullmatch(source_sha)
        or not SHA_RE.fullmatch(tag_object_sha)
    ):
        raise ReleaseTargetError("target identity for publication recheck is malformed")
    remote = remote_tag_identity(tag)
    if remote != (tag_object_sha, source_sha):
        raise ReleaseTargetError("remote tag moved after release qualification")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "recheck"))
    args = parser.parse_args()
    try:
        validate() if args.command == "validate" else recheck()
    except ReleaseTargetError as exc:
        print(f"release target validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
