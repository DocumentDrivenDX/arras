#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Reject stale active release and explicit consumer version pins before tagging."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _read(root: Path, name: str, errors: list[str]) -> dict[str, Any]:
    try:
        raw = (root / name).read_text(encoding="utf-8")
        value = json.loads(raw) if name.endswith(".json") else tomllib.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("expected an object")
        return value
    except (OSError, ValueError) as error:
        errors.append(f"{name}: cannot read release metadata ({type(error).__name__})")
        return {}


def _release_pin(root: Path, version: str) -> str | None:
    path = ".github/workflows/release.yml"
    try:
        workflow = (root / path).read_text(encoding="utf-8")
    except OSError:
        return None
    case = re.search(rf"(?m)^\s*{re.escape(version)}\)\s*$(.*?)^\s*;;", workflow, re.S)
    filename = f"dist/arras-{version}-py3-none-any.whl"
    command = rf"echo '([0-9a-f]{{64}})  {re.escape(filename)}' \| sha256sum --check --strict -"
    match = re.search(command, case.group(1)) if case is not None else None
    return match.group(1) if match is not None else None


def _artifact_errors(root: Path, version: str, directory: Path) -> list[str]:
    digest = _release_pin(root, version)
    wheels = list(directory.glob("arras-*.whl"))
    if [path.name for path in wheels] != [f"arras-{version}-py3-none-any.whl"]:
        return ["candidate wheel: selected versioned file is missing or ambiguous"]
    if digest is None or hashlib.sha256(wheels[0].read_bytes()).hexdigest() != digest:
        return ["candidate wheel: bytes do not match the selected qualified digest"]
    return []


def _built_asset_errors(root: Path, version: str) -> list[str]:
    errors: list[str] = []
    page = _read(root, "src/arras/ui/static/asset-manifest.json", errors)
    staged = _read(root, "ui/.pack/package/package.json", errors)
    if page.get("package", {}).get("version") != version:
        errors.append("built page manifest: version differs from the active release")
    if staged.get("name") != "@documentdrivendx/arras-ui" or staged.get("version") != version:
        errors.append("staged npm package: identity differs from the active release")
    archives = list((root / "src/arras/ui/npm").glob("*.tgz"))
    if [path.name for path in archives] != [f"documentdrivendx-arras-ui-{version}.tgz"]:
        return [*errors, "carried npm archive: expected only the active versioned filename"]
    try:
        with tarfile.open(archives[0], "r:gz") as archive:
            stream = archive.extractfile("package/package.json")
            if stream is None:
                raise ValueError("missing npm package manifest")
            package = json.load(stream)
        if package.get("name") != "@documentdrivendx/arras-ui" or package.get("version") != version:
            errors.append("carried npm package: identity differs from the active release")
    except (OSError, ValueError, KeyError, tarfile.TarError):
        errors.append("carried npm package: cannot read the built manifest")
    return errors


def check(
    root: Path,
    *,
    require_release_pin: bool = False,
    built_assets: bool = False,
    artifacts_dir: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    project = _read(root, "pyproject.toml", errors)
    version = project.get("project", {}).get("version")
    if (
        not isinstance(version, str)
        or re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version) is None
    ):
        return [*errors, "pyproject.toml: expected a numeric X.Y.Z release version"]
    lock = _read(root, "uv.lock", errors)
    catalog = _read(root, "src/arras/public-api.json", errors).get("distribution", {})
    example = _read(root, "examples/extension_host/pyproject.toml", errors).get("project", {})
    doctor = _read(root, "examples/extension_host/doctor-request.json", errors).get(
        "expected_packages", {}
    )
    packages = [
        item.get("version")
        for item in lock.get("package", [])
        if isinstance(item, dict) and item.get("name") == "arras"
    ]
    dependencies = [
        item
        for item in example.get("dependencies", [])
        if isinstance(item, str) and re.match(r"^arras(?:\[|\s|[=<>!~@]|$)", item, re.I)
    ]
    expected = [
        ("uv.lock Arras package", packages, [version]),
        ("public catalog distribution", catalog.get("version"), version),
        ("public catalog npm distribution", catalog.get("npm", {}).get("version"), version),
        ("extension-host dependency", dependencies, [f"arras=={version}"]),
        ("doctor expected Arras", doctor.get("arras"), version),
        ("doctor expected npm", doctor.get("@documentdrivendx/arras-ui"), version),
    ]
    for label, actual, wanted in expected:
        if actual != wanted:
            errors.append(f"{label}: stale or missing; expected {wanted!r}, found {actual!r}")
    try:
        heading = re.search(r"(?m)^## (\d+\.\d+\.\d+)\b", (root / "CHANGELOG.md").read_text())
        if heading is None or heading.group(1) != version:
            errors.append("CHANGELOG.md: first release heading does not match the active version")
    except OSError:
        errors.append("CHANGELOG.md: cannot read active release heading")
    if require_release_pin and _release_pin(root, version) is None:
        errors.append(
            f".github/workflows/release.yml: {version} needs its exact wheel filename and qualified digest guard"
        )
    if built_assets:
        errors.extend(_built_asset_errors(root, version))
    if artifacts_dir is not None:
        errors.extend(_artifact_errors(root, version, artifacts_dir))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--require-release-pin", action="store_true")
    parser.add_argument("--built-assets", action="store_true")
    parser.add_argument("--artifacts-dir", type=Path)
    args = parser.parse_args()
    errors = check(
        args.root,
        require_release_pin=args.require_release_pin,
        built_assets=args.built_assets,
        artifacts_dir=args.artifacts_dir,
    )
    print(json.dumps({"status": "failed" if errors else "passed", "errors": errors}, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
