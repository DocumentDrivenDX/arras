#!/usr/bin/env python3
"""Reject stale active release and explicit consumer version pins before tagging."""

from __future__ import annotations

import argparse
import json
import re
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


def _release_pin_errors(root: Path, version: str) -> list[str]:
    path = ".github/workflows/release.yml"
    try:
        workflow = (root / path).read_text(encoding="utf-8")
    except OSError:
        return [f"{path}: cannot read exact-wheel selection"]
    case = re.search(rf"(?m)^\s*{re.escape(version)}\)\s*$(.*?)^\s*;;", workflow, re.S)
    filename = f"dist/arras-{version}-py3-none-any.whl"
    command = rf"echo '[0-9a-f]{{64}}  {re.escape(filename)}' \| sha256sum --check --strict -"
    if case is None or re.search(command, case.group(1)) is None:
        return [f"{path}: {version} needs its exact wheel filename and qualified digest guard"]
    return []


def check(root: Path, *, require_release_pin: bool = False) -> list[str]:
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
    if require_release_pin:
        errors.extend(_release_pin_errors(root, version))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--require-release-pin", action="store_true")
    args = parser.parse_args()
    errors = check(args.root, require_release_pin=args.require_release_pin)
    print(json.dumps({"status": "failed" if errors else "passed", "errors": errors}, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
