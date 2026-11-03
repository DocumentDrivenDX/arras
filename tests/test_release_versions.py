"""Version-coupled consumers must refuse stale release metadata before a tag."""

from __future__ import annotations

import importlib.util
import json
import shutil
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
    path.write_text(text.replace(VERSION, "0.0.0", 1))
    assert versions.check(candidate)


def test_actual_old_example_dependency_conflict_is_caught(candidate: Path) -> None:
    path = candidate / "examples/extension_host/pyproject.toml"
    path.write_text(path.read_text().replace(f"arras=={VERSION}", "arras==0.7.0"))
    assert any("extension-host dependency" in error for error in versions.check(candidate))


def test_missing_example_metadata_refuses(candidate: Path) -> None:
    (candidate / "examples/extension_host/pyproject.toml").unlink()
    assert any("cannot read release metadata" in error for error in versions.check(candidate))


@pytest.mark.parametrize("package", ["arras", "@documentdrivendx/arras-ui"])
def test_each_doctor_package_expectation_is_checked(candidate: Path, package: str) -> None:
    path = candidate / "examples/extension_host/doctor-request.json"
    request = json.loads(path.read_text())
    del request["expected_packages"][package]
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
