# SPDX-License-Identifier: MIT OR Apache-2.0
"""Artifact-gate negative controls; these exercise the verifier's actual rejection paths."""

from __future__ import annotations

import email
import importlib.util
import io
import json
import re
import tarfile
import tomllib
from pathlib import Path
from typing import Any

import pytest

TOOL = Path(__file__).parents[1] / "tools/verify_distribution.py"
spec = importlib.util.spec_from_file_location("arras_distribution_verifier", TOOL)
assert spec and spec.loader
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def tar_bytes(members: list[tuple[str, bytes, str]]) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tf:
        for name, body, kind in members:
            info = tarfile.TarInfo(name)
            if kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = "../outside"
            else:
                info.size = len(body)
            tf.addfile(info, None if kind == "symlink" else io.BytesIO(body))
    return out.getvalue()


def npm_fixture(version: str = "0.5.0") -> tuple[dict[str, bytes], dict[str, Any]]:
    catalog = {
        "distribution": {
            "npm": {
                "name": "@example/pkg",
                "exports": {".": {"runtime": "dist/index.js", "types": "types/index.d.ts"}},
                "peer_dependencies": {"react": {"version": "^19", "optional": False}},
            }
        }
    }
    package = {
        "name": "@example/pkg",
        "version": version,
        "exports": {".": {"import": "./dist/index.js", "types": "./types/index.d.ts"}},
        "peerDependencies": {"react": "^19"},
        "peerDependenciesMeta": {},
    }
    extracted = {
        "package.json": json.dumps(package).encode(),
        "dist/index.js": b"export {};",
        "types/index.d.ts": b"export {};",
    }
    return extracted, catalog


def test_package_payload_comparison_rejects_python_and_static_asset_mutation() -> None:
    source = {"arras/api.py": b"api", "arras/ui/static/embed.html": b"page"}
    assert verifier.package_differences(source, dict(source)) == []
    assert verifier.package_differences(source, {**source, "arras/api.py": b"tampered"}) == [
        "arras/api.py"
    ]
    assert verifier.package_differences(
        source, {**source, "arras/ui/static/embed.html": b"missing"}
    ) == ["arras/ui/static/embed.html"]


def test_wheel_gate_rejects_missing_required_asset() -> None:
    with pytest.raises(SystemExit, match="omits required package file"):
        verifier.require_wheel_assets({"arras/py.typed": b"", "arras/public-api.json": b"{}"})


def test_artifact_gate_rejects_missing_ambiguous_or_stale_artifact_name(tmp_path: Path) -> None:
    artifact = tmp_path / "arras-0.5.0-py3-none-any.whl"
    artifact.write_bytes(b"wheel")
    verifier.one_artifact(artifact, "py3-none-any.whl", "0.5.0")
    with pytest.raises(SystemExit, match="expected"):
        verifier.one_artifact(artifact, "py3-none-any.whl", "0.6.0")
    artifact.unlink()
    with pytest.raises(SystemExit, match="missing or empty"):
        verifier.one_artifact(artifact, "py3-none-any.whl", "0.5.0")


def test_npm_gate_rejects_missing_export_target_and_version_mismatch() -> None:
    extracted, catalog = npm_fixture()
    verifier.verify_npm_package(extracted, "0.5.0", catalog)
    broken = dict(extracted)
    del broken["types/index.d.ts"]
    with pytest.raises(SystemExit, match="target"):
        verifier.verify_npm_package(broken, "0.5.0", catalog)
    with pytest.raises(SystemExit, match="name/version"):
        verifier.verify_npm_package(extracted, "0.6.0", catalog)


def test_npm_archive_gate_rejects_duplicate_alias_and_link_members() -> None:
    alias = tar_bytes(
        [("package/dist/index.js", b"one", "file"), ("package/dist/./index.js", b"two", "file")]
    )
    with pytest.raises(SystemExit, match="non-canonical"):
        verifier.unpack_npm(alias)
    duplicate = tar_bytes(
        [("package/package.json", b"{}", "file"), ("package/package.json", b"{}", "file")]
    )
    with pytest.raises(SystemExit, match="duplicate"):
        verifier.unpack_npm(duplicate)
    linked = tar_bytes([("package/escape", b"", "symlink")])
    with pytest.raises(SystemExit, match="link or special"):
        verifier.unpack_npm(linked)


def test_manifest_python_floor_must_match_wheel_metadata() -> None:
    manifest = {"distribution": {"python_requires": ">=3.11"}}
    verifier.verify_manifest_python_floor(manifest, ">=3.11")
    manifest["distribution"]["python_requires"] = ">=3.8"
    with pytest.raises(SystemExit, match="catalog python_requires"):
        verifier.verify_manifest_python_floor(manifest, ">=3.11")


def test_metadata_gate_rejects_python_floor_and_optional_dependency_drift() -> None:
    expected = verifier.expected_project_metadata()
    verifier.verify_metadata_headers(expected, expected, "fixture")

    stale_floor = dict(expected)
    stale_floor["requires_python"] = ">=3.8"
    with pytest.raises(SystemExit, match="requires-python"):
        verifier.verify_metadata_headers(stale_floor, expected, "fixture")

    stale_optional_dependency = dict(expected)
    dependencies = list(expected["requires_dist"])
    truss_requirement = next(
        i for i, value in enumerate(dependencies) if value.startswith("truss-toolkit")
    )
    pinned_requirement = dependencies[truss_requirement]
    pinned_version = re.search(r"==([^;\s]+)", pinned_requirement)
    assert pinned_version is not None, pinned_requirement
    stale_requirement = pinned_requirement.replace(
        f"=={pinned_version.group(1)}", f"=={pinned_version.group(1)}.post1", 1
    )
    assert stale_requirement != pinned_requirement
    dependencies[truss_requirement] = stale_requirement
    stale_optional_dependency["requires_dist"] = dependencies
    with pytest.raises(SystemExit, match="requires-dist"):
        verifier.verify_metadata_headers(stale_optional_dependency, expected, "fixture")


def test_optional_direct_url_metadata_preserves_urls_and_conjoins_existing_markers() -> None:
    project = tomllib.loads((verifier.ROOT / "pyproject.toml").read_text())["project"]
    source_requirements = project["optional-dependencies"]["umf"]
    expected = verifier.expected_project_metadata()
    normalized = [
        requirement
        for requirement in expected["requires_dist"]
        if requirement.startswith("umf-core @ ")
    ]

    assert len(normalized) == len(source_requirements) == 2
    for source, actual in zip(source_requirements, normalized, strict=True):
        source_body, separator, source_marker = source.partition(";")
        assert separator
        source_url = source_body.split("@", 1)[1].strip()
        assert actual.startswith(f"umf-core @ {source_url};")
        assert f"({source_marker.strip()}) and extra == 'umf'" in actual

    # These marker lines follow Hatch's observed METADATA/PKG-INFO serialization independently of
    # the expected-metadata helper; the source URL/hash bodies remain byte-exact.
    artifact_markers = (
        "sys_platform == 'linux' and platform_machine == 'x86_64'",
        "sys_platform == 'darwin' and platform_machine == 'arm64'",
    )
    artifact_requirements = [
        *[item for item in expected["requires_dist"] if not item.startswith("umf-core @ ")],
        *[
            f"{source.partition(';')[0].strip()}; ({marker}) and extra == 'umf'"
            for source, marker in zip(source_requirements, artifact_markers, strict=True)
        ],
    ]
    message = email.message_from_string(
        "Requires-Python: "
        + project["requires-python"]
        + "\n"
        + "".join(f"Provides-Extra: {extra}\n" for extra in project["optional-dependencies"])
        + "".join(f"Requires-Dist: {item}\n" for item in artifact_requirements)
        + "\n"
    )
    fields = verifier.message_metadata_fields(message)
    verifier.verify_metadata_headers(fields, expected, "Hatch metadata fixture")


def test_optional_direct_url_metadata_rejects_platform_extra_and_artifact_drift() -> None:
    expected = verifier.expected_project_metadata()
    source_requirements = [
        value for value in expected["requires_dist"] if value.startswith("umf-core @ ")
    ]
    assert len(source_requirements) == 2
    linux, macos = source_requirements
    digest_marker = "#sha256="
    digest_start = linux.index(digest_marker) + len(digest_marker)
    digest_changed = (
        linux[:digest_start]
        + ("0" if linux[digest_start] != "0" else "1")
        + linux[digest_start + 1 :]
    )
    mutations = [
        linux.replace("sys_platform == 'linux'", "sys_platform == 'darwin'", 1),
        linux.replace("platform_machine == 'x86_64'", "platform_machine == 'aarch64'", 1),
        linux.replace(" and extra == 'umf'", "", 1),
        linux.replace(" and platform_machine == 'x86_64'", " or platform_machine == 'x86_64'", 1),
        linux.replace("umf_core-", "umf_Core-", 1),
        digest_changed,
        macos.replace("sys_platform == 'darwin'", "sys_platform == 'Darwin'", 1),
    ]
    for changed in mutations:
        fields = dict(expected)
        requirements = list(expected["requires_dist"])
        index = requirements.index(linux if changed != mutations[-1] else macos)
        requirements[index] = changed
        fields["requires_dist"] = requirements
        with pytest.raises(SystemExit, match="requires-dist"):
            verifier.verify_metadata_headers(fields, expected, "wheel/sdist mutation")
