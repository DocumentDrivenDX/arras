#!/usr/bin/env python3
"""Admit immutable local assets and retain distinct hosted qualification evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from _umf_admission_receipt import validate_receipt
from verify_local_registry_origin import (
    ASSETS,
    EXPECTED_SOURCE,
    EXPECTED_SUMS_SHA256,
    EXPECTED_TAG,
    EXPECTED_TAG_OBJECT,
    validate,
)


def remote_identity() -> dict:
    repository = os.environ["GITHUB_REPOSITORY"]
    if repository != "DocumentDrivenDX/arras":
        raise ValueError("local backfill is restricted to DocumentDrivenDX/arras")

    def api(endpoint: str) -> dict:
        return json.loads(subprocess.check_output(["gh", "api", f"repos/{repository}/{endpoint}"]))

    ref = api(f"git/ref/tags/{EXPECTED_TAG}")
    if ref.get("object") != {
        "sha": EXPECTED_TAG_OBJECT,
        "type": "tag",
        "url": f"https://api.github.com/repos/{repository}/git/tags/{EXPECTED_TAG_OBJECT}",
    }:
        raise ValueError("remote annotated tag differs")
    tag = api(f"git/tags/{EXPECTED_TAG_OBJECT}")
    if (
        tag.get("sha") != EXPECTED_TAG_OBJECT
        or tag.get("tag") != EXPECTED_TAG
        or tag.get("object", {}).get("sha") != EXPECTED_SOURCE
        or tag.get("object", {}).get("type") != "commit"
    ):
        raise ValueError("remote tag peel differs")
    release = api(f"releases/tags/{EXPECTED_TAG}")
    if (
        release.get("id") != 430104745
        or release.get("tag_name") != EXPECTED_TAG
        or release.get("immutable") is not True
        or release.get("draft") is not False
        or release.get("prerelease") is not False
    ):
        raise ValueError("immutable public release identity differs")
    pins = {**ASSETS, "SHA256SUMS": EXPECTED_SUMS_SHA256}
    assets = release.get("assets", [])
    if len(assets) != len(pins) or {asset["name"] for asset in assets} != set(pins):
        raise ValueError("remote release inventory differs")
    for asset in assets:
        if (
            asset.get("digest") != f"sha256:{pins[asset['name']]}"
            or asset.get("state") != "uploaded"
        ):
            raise ValueError("remote asset digest or state differs")
    return {"ref": ref, "tag": tag, "release": release}


def admit(destination: Path) -> None:
    metadata = remote_identity()
    destination.mkdir(parents=True, exist_ok=False)
    for name in ["SHA256SUMS", *ASSETS]:
        subprocess.run(
            [
                "curl",
                "--disable",
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--proto",
                "=https",
                "--proto-redir",
                "=https",
                "--max-time",
                "120",
                "--output",
                str(destination / name),
                f"https://github.com/DocumentDrivenDX/arras/releases/download/{EXPECTED_TAG}/{name}",
            ],
            check=True,
        )
    identity = validate(destination, EXPECTED_TAG, EXPECTED_SOURCE, EXPECTED_TAG_OBJECT)
    Path("local-origin.json").write_text(json.dumps(identity, indent=2) + "\n")
    Path("local-remote.json").write_text(json.dumps(metadata, indent=2) + "\n")


def finish(assets: Path, evidence: Path, output: Path) -> None:
    identity = validate(assets, EXPECTED_TAG, EXPECTED_SOURCE, EXPECTED_TAG_OBJECT)
    remote_identity()
    required = [
        "source/source-pytest.xml",
        "source/truss-pytest.xml",
        "installed/native-verification.json",
        "installed/umf-admission-installed.json",
        "installed/public-distribution.json",
        "installed/public-doctor.json",
        "installed/public-extension.json",
        "ui/qualification-linux.json",
        "installed/native-cohort-binding.json",
        "downstream/consumer.xml",
    ]
    records = {}
    for name in required:
        path = evidence / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"missing qualification receipt: {name}")
        records[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    native = json.loads((evidence / "installed/native-verification.json").read_text())
    if native.get("status") != "passed":
        raise ValueError("installed native qualification did not pass")
    validate_evidence(evidence, identity)
    output.mkdir(parents=True)
    (output / "registry-publication-identity.json").write_text(
        json.dumps(identity, indent=2) + "\n"
    )
    receipt = {
        "schema": "arras.hosted-local-origin-qualification.v1",
        "status": "passed",
        "origin": identity,
        "repository": os.environ["GITHUB_REPOSITORY"],
        "workflow_sha": os.environ["GITHUB_WORKFLOW_SHA"],
        "run_id": os.environ["GITHUB_RUN_ID"],
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "receipts": records,
        "scope": "Fresh Linux source, Truss, exact public wheel native/UMF/distribution/doctor/extension, UI and packed-theme; original Mac visual/managed evidence remains separately scoped in local proof.",
        "publication_origin": "local; no original hosted Release producer",
    }
    (output / "hosted-local-origin-qualification.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )


def validate_evidence(evidence: Path, identity: dict) -> None:
    def read(name: str) -> dict:
        return json.loads((evidence / name).read_text())

    wheel_sha = identity["wheel_sha256"]
    binding = read("installed/native-cohort-binding.json")
    if binding.get("status") != "bound" or binding.get("wheel", {}).get("sha256") != wheel_sha:
        raise ValueError("native binding differs from exact wheel")
    native = read("installed/native-verification.json")
    if native.get("status") != "passed" or native.get("runtime", {}).get("python") != "3.11":
        raise ValueError("native qualification status or interpreter differs")
    validate_receipt(
        read("installed/umf-admission-installed.json"),
        version="0.6.5",
        wheel_name=identity["wheel"],
        wheel_sha256=wheel_sha,
        phase="public-download",
        repository=Path(__file__).resolve().parents[2],
    )
    distribution = read("installed/public-distribution.json")
    if (
        distribution.get("source_wheel", {}).get("sha256") != wheel_sha
        or distribution.get("sdist", {}).get("sha256") != ASSETS["arras-0.6.5.tar.gz"]
        or distribution.get("npm", {}).get("sha256") != identity["npm_sha256"]
        or distribution.get("qualification") != ["artifact-inspected", "installed-consumer-tested"]
    ):
        raise ValueError("public distribution qualification differs")
    doctor = read("installed/public-doctor.json")
    if doctor.get("status") != "passed" or doctor.get("wheel", {}).get("sha256") != wheel_sha:
        raise ValueError("public doctor qualification differs")
    extension = read("installed/public-extension.json")
    if (
        extension.get("arras_wheel", {}).get("sha256") != wheel_sha
        or extension.get("environment", {}).get("dependency_mode")
        != "fresh-public-index-resolution"
        or extension.get("qualification") != "installed-artifact consumer and fixed memory corpus"
    ):
        raise ValueError("fresh extension qualification differs")
    ui = read("ui/qualification-linux.json")
    acceptance = ui.get("acceptance_suite", {})
    if (
        ui.get("schema") != "arras.ui.downstream-qualification.v1"
        or ui.get("cohort", {}).get("wheel", {}).get("sha256") != wheel_sha
        or ui.get("cohort", {}).get("npm", {}).get("sha256") != identity["npm_sha256"]
    ):
        raise ValueError("UI qualification cohort differs")
    if (
        acceptance.get("status") != "passed"
        or acceptance.get("visual", {}).get("status") != "skipped-non-Darwin"
        or len(ui.get("routes", [])) != 2
    ):
        raise ValueError("UI qualification scope differs")
    projects = acceptance.get("projects", [])
    if {project.get("name") for project in projects} != {"chromium", "schema-admin", "browser"}:
        raise ValueError("UI mandatory project set differs")
    for project in projects:
        if (
            project.get("expected", 0) <= 0
            or project.get("passed") != project["expected"]
            or project.get("failed") != 0
            or project.get("skipped") != 0
        ):
            raise ValueError("UI project did not pass all expected tests")
    for name in ["source/source-pytest.xml", "source/truss-pytest.xml", "downstream/consumer.xml"]:
        root = ET.parse(evidence / name).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        if (
            not suites
            or sum(int(suite.get("tests", "0")) for suite in suites) <= 0
            or any(int(suite.get(key, "0")) for suite in suites for key in ["failures", "errors"])
        ):
            raise ValueError(f"test qualification did not pass: {name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["admit", "finish", "recheck"])
    parser.add_argument("--assets", type=Path, default=Path("local-assets"))
    parser.add_argument("--evidence", type=Path, default=Path("evidence"))
    parser.add_argument("--output", type=Path, default=Path("verified"))
    args = parser.parse_args()
    if args.mode == "admit":
        admit(args.assets)
    elif args.mode == "finish":
        finish(args.assets, args.evidence, args.output)
    else:
        remote_identity()


if __name__ == "__main__":
    main()
