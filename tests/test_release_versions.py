# SPDX-License-Identifier: MIT OR Apache-2.0
"""Version-coupled consumers must refuse stale release metadata before a tag."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import tarfile
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_release_versions", ROOT / "tools/check_release_versions.py"
)
assert SPEC is not None and SPEC.loader is not None
versions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(versions)
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
FILES = (
    "pyproject.toml",
    "uv.lock",
    "src/arras/public-api.json",
    "examples/extension_host/pyproject.toml",
    "examples/extension_host/doctor-request.json",
    "CHANGELOG.md",
    ".github/workflows/release.yml",
)


@pytest.fixture
def candidate(tmp_path: Path) -> Path:
    for name in FILES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


def test_aligned_candidate_metadata_passes(candidate: Path) -> None:
    assert versions.check(candidate) == []


@pytest.mark.parametrize("name", FILES[:-1])
def test_each_stale_active_version_refuses(candidate: Path, name: str) -> None:
    path = candidate / name
    text = path.read_text()
    assert VERSION in text
    # a lock file lists other packages, one of which may share this version: stale Arras's own entry
    own = f'name = "arras"\nversion = "{VERSION}"'
    stale = (
        text.replace(own, own.replace(VERSION, "0.0.0"), 1)
        if name == "uv.lock"
        else text.replace(VERSION, "0.0.0", 1)
    )
    assert stale != text
    path.write_text(stale)
    assert versions.check(candidate)


def test_actual_old_example_dependency_conflict_is_caught(candidate: Path) -> None:
    path = candidate / "examples/extension_host/pyproject.toml"
    path.write_text(path.read_text().replace(f"arras=={VERSION}", "arras==0.7.0"))
    assert any("extension-host dependency" in error for error in versions.check(candidate))


def test_missing_example_metadata_refuses(candidate: Path) -> None:
    (candidate / "examples/extension_host/pyproject.toml").unlink()
    assert any("cannot read release metadata" in error for error in versions.check(candidate))


@pytest.mark.parametrize("package", ["arras", "@documentdrivendx/arras-ui"])
@pytest.mark.parametrize("state", ["missing", "stale"])
def test_each_doctor_package_expectation_is_checked(
    candidate: Path, package: str, state: str
) -> None:
    path = candidate / "examples/extension_host/doctor-request.json"
    request = json.loads(path.read_text())
    if state == "missing":
        del request["expected_packages"][package]
    else:
        request["expected_packages"][package] = "0.7.0"
    path.write_text(json.dumps(request))
    assert any("doctor expected" in error for error in versions.check(candidate))


@pytest.mark.parametrize("state", ["matching", "missing", "wrong-filename", "unselected"])
def test_strict_release_selection_requires_own_filename_and_digest(
    candidate: Path, state: str
) -> None:
    path = candidate / ".github/workflows/release.yml"
    version = "99.0.0" if state == "unselected" else VERSION
    filename = (
        "arras-wrong.whl" if state == "wrong-filename" else f"arras-{VERSION}-py3-none-any.whl"
    )
    case = f"\n            {version})\n              echo '{'a' * 64}  dist/{filename}' | sha256sum --check --strict -\n              ;;\n"
    path.write_text(case if state != "missing" else "")
    assert bool(versions.check(candidate, require_release_pin=True)) == (state != "matching")


@pytest.mark.parametrize(
    "state", ["matching", "page", "staged", "carried-version", "carried-filename"]
)
def test_built_versioned_manifests_and_archive_are_checked(candidate: Path, state: str) -> None:
    page = candidate / "src/arras/ui/static/asset-manifest.json"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(json.dumps({"package": {"version": "0.0.0" if state == "page" else VERSION}}))
    staged = candidate / "ui/.pack/package/package.json"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(
        json.dumps(
            {
                "name": "@documentdrivendx/arras-ui",
                "version": "0.0.0" if state == "staged" else VERSION,
            }
        )
    )
    npm = candidate / "src/arras/ui/npm"
    npm.mkdir(parents=True, exist_ok=True)
    name_version = "0.0.0" if state == "carried-filename" else VERSION
    body = json.dumps(
        {
            "name": "@documentdrivendx/arras-ui",
            "version": "0.0.0" if state == "carried-version" else VERSION,
        }
    ).encode()
    with tarfile.open(npm / f"documentdrivendx-arras-ui-{name_version}.tgz", "w:gz") as archive:
        info = tarfile.TarInfo("package/package.json")
        info.size = len(body)
        archive.addfile(info, io.BytesIO(body))
    assert bool(versions.check(candidate, built_assets=True)) == (state != "matching")


@pytest.mark.parametrize("state", ["matching", "missing", "changed", "wrong-version"])
def test_actual_selected_wheel_bytes_are_checked(candidate: Path, state: str) -> None:
    payload = b"qualified candidate wheel bytes"
    digest = hashlib.sha256(payload).hexdigest()
    name = f"arras-{VERSION}-py3-none-any.whl"
    (candidate / ".github/workflows/release.yml").write_text(
        f"\n {VERSION})\n echo '{digest}  dist/{name}' | sha256sum --check --strict -\n ;;\n"
    )
    directory = candidate / "dist"
    directory.mkdir()
    if state != "missing":
        (
            directory / ("arras-99.0.0-py3-none-any.whl" if state == "wrong-version" else name)
        ).write_bytes(payload if state != "changed" else b"changed")
    assert bool(versions.check(candidate, artifacts_dir=directory)) == (state != "matching")
