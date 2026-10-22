#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Verify the exact Python artifacts and their carried npm consumer without publishing anything.

Run after `uv build --wheel && uv build --sdist` and the UI build:
  python tools/verify_distribution.py dist/arras-X.Y.Z-py3-none-any.whl dist/arras-X.Y.Z.tar.gz
The sdist is rebuilt in an isolated temporary directory; each wheel is installed into a fresh venv
and imported with Python isolated mode. This tool does not inspect the source tree as an import path.
"""

from __future__ import annotations

import argparse
import email
import hashlib
import json
import os
import platform
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from email.message import Message
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

ROOT = Path(__file__).resolve().parents[1]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(message: str) -> NoReturn:
    raise SystemExit(f"distribution verification failed: {message}")


def package_differences(left: dict[str, bytes], right: dict[str, bytes]) -> list[str]:
    return sorted(k for k in set(left) | set(right) if left.get(k) != right.get(k))


def read_project_version() -> str:
    import tomllib

    with (ROOT / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def normalize_requirement(value: str) -> str:
    """Normalize the limited PEP 508 requirement forms declared by this project."""
    import re

    requirement, separator, marker = value.partition(";")
    match = re.fullmatch(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[([^]]+)\])?(.*)\s*", requirement)
    if match is None:
        fail(f"cannot normalize project requirement {value!r}")
    name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
    extras = match.group(2)
    extra_part = (
        "[" + ",".join(sorted(x.strip().lower() for x in extras.split(","))) + "]" if extras else ""
    )
    specifiers = sorted(part.strip().lower() for part in match.group(3).split(",") if part.strip())
    normalized = name + extra_part + ",".join(specifiers)
    if separator:
        normalized_marker = re.sub(r"\s+", " ", marker.strip().replace('"', "'")).lower()
        normalized += ";" + normalized_marker
    return normalized


def metadata_signature(fields: dict[str, Any]) -> dict[str, Any]:
    requires_python = fields.get("requires_python")
    if not isinstance(requires_python, str):
        fail("distribution metadata omits Requires-Python")
    provides_extra_value = fields.get("provides_extra", [])
    requires_dist_value = fields.get("requires_dist", [])
    if not isinstance(provides_extra_value, list) or not isinstance(requires_dist_value, list):
        fail("distribution metadata has malformed dependency headers")
    provides_extra_items = cast(list[object], provides_extra_value)
    requires_dist_items = cast(list[object], requires_dist_value)
    if not all(isinstance(value, str) for value in provides_extra_items):
        fail("distribution metadata has malformed Provides-Extra")
    if not all(isinstance(value, str) for value in requires_dist_items):
        fail("distribution metadata has malformed Requires-Dist")
    provides_extra = cast(list[str], provides_extra_items)
    requires_dist = cast(list[str], requires_dist_items)
    return {
        "requires_python": requires_python.strip(),
        "provides_extra": sorted(value.lower() for value in provides_extra),
        "requires_dist": sorted(normalize_requirement(value) for value in requires_dist),
    }


def expected_project_metadata() -> dict[str, Any]:
    import tomllib

    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    fields = {
        "requires_python": project["requires-python"],
        "provides_extra": list(project.get("optional-dependencies", {})),
        "requires_dist": list(project.get("dependencies", [])),
    }
    for extra, dependencies in project.get("optional-dependencies", {}).items():
        fields["requires_dist"].extend(
            f"{requirement}; extra == '{extra}'" for requirement in dependencies
        )
    return metadata_signature(fields)


def verify_metadata_headers(
    fields: dict[str, Any], expected: dict[str, Any], label: str
) -> dict[str, Any]:
    actual = metadata_signature(fields)
    for header in ("requires_python", "requires_dist", "provides_extra"):
        if actual[header] != expected[header]:
            fail(
                f"{label} {header.replace('_', '-')} differs from source declarations: "
                f"{actual[header]!r} != {expected[header]!r}"
            )
    return actual


def message_metadata_fields(message: Message) -> dict[str, Any]:
    return {
        "requires_python": message.get("Requires-Python"),
        "requires_dist": message.get_all("Requires-Dist", []),
        "provides_extra": message.get_all("Provides-Extra", []),
    }


def verify_manifest_python_floor(manifest: dict[str, Any], requires_python: str) -> None:
    declared = manifest.get("distribution", {}).get("python_requires")
    if declared != requires_python:
        fail(
            "public API catalog python_requires differs from wheel Requires-Python: "
            f"{declared!r} != {requires_python!r}"
        )


def one_artifact(path: Path, suffix: str, version: str) -> None:
    expected = f"arras-{version}.tar.gz" if suffix == ".tar.gz" else f"arras-{version}-{suffix}"
    if path.name != expected:
        fail(f"artifact name {path.name!r} does not equal expected {expected!r}")
    if not path.is_file() or path.stat().st_size == 0:
        fail(f"missing or empty artifact: {path}")


def wheel_members(path: Path) -> tuple[dict[str, bytes], str, str, Message]:
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad:
                fail(f"corrupt wheel member {bad}")
            archive_names = z.namelist()
            if len(archive_names) != len(set(archive_names)):
                fail("wheel contains duplicate member names")
            for name in archive_names:
                if name.rstrip("/") != PurePosixPath(name).as_posix():
                    fail(f"wheel contains non-canonical member path {name}")
            names = [n for n in archive_names if not n.endswith("/")]
            members = {n: z.read(n) for n in names}
    except (OSError, zipfile.BadZipFile) as e:
        fail(f"cannot read wheel {path}: {e}")
    metadata = [n for n in members if n.endswith(".dist-info/METADATA")]
    if len(metadata) != 1:
        fail(f"wheel needs one METADATA, found {metadata}")
    msg = email.message_from_bytes(members[metadata[0]])
    return members, msg.get("Name", ""), msg.get("Version", ""), msg


def verify_record(members: dict[str, bytes]) -> None:
    records = [n for n in members if n.endswith(".dist-info/RECORD")]
    if len(records) != 1:
        fail(f"wheel needs one RECORD, found {records}")
    import csv
    import io

    rows = csv.reader(io.StringIO(members[records[0]].decode("utf-8")))
    seen: set[str] = set()
    for name, digest, size in rows:
        seen.add(name)
        if name not in members:
            fail(f"RECORD names missing wheel member {name}")
        if not digest:
            if name != records[0]:
                fail(f"unexpected unhashed wheel member {name}")
            continue
        algorithm, encoded = digest.split("=", 1)
        if algorithm != "sha256":
            fail(f"unsupported RECORD digest {algorithm}")
        import base64

        actual = (
            base64.urlsafe_b64encode(hashlib.sha256(members[name]).digest()).rstrip(b"=").decode()
        )
        if actual != encoded or str(len(members[name])) != size:
            fail(f"RECORD integrity mismatch for {name}")
    if seen != set(members):
        fail(f"wheel members absent from RECORD: {sorted(set(members) - seen)}")


def catalog(members: dict[str, bytes]) -> dict[str, Any]:
    try:
        value = json.loads(members["arras/public-api.json"])
    except (KeyError, json.JSONDecodeError) as e:
        fail(f"wheel has no valid public-api.json: {e}")
    if value.get("schema_version") != 1:
        fail("unsupported or missing public-api.json schema_version")
    return value


def unpack_npm(payload: bytes) -> dict[str, bytes]:
    with tempfile.TemporaryDirectory(prefix="arras-npm-check-") as tmp:
        tar_path = Path(tmp) / "package.tgz"
        tar_path.write_bytes(payload)
        try:
            with tarfile.open(tar_path, "r:gz") as tf:
                safe: list[tarfile.TarInfo] = []
                seen: set[str] = set()
                for member in tf.getmembers():
                    name = PurePosixPath(member.name)
                    if (
                        name.is_absolute()
                        or ".." in name.parts
                        or member.name.rstrip("/") != name.as_posix()
                    ):
                        fail(f"unsafe or non-canonical npm archive member {member.name}")
                    if member.name in seen:
                        fail(f"duplicate npm archive member {member.name}")
                    seen.add(member.name)
                    if not (member.isdir() or member.isfile()):
                        fail(f"npm archive contains a link or special member {member.name}")
                    safe.append(member)
                extracted: dict[str, bytes] = {}
                for member in safe:
                    if member.isfile() and member.name.startswith("package/"):
                        relative = member.name.removeprefix("package/")
                        stream = tf.extractfile(member)
                        if stream is None:
                            fail(f"npm archive member cannot be read: {member.name}")
                        extracted[relative] = stream.read()
                return extracted
        except (OSError, tarfile.TarError) as e:
            fail(f"cannot inspect npm tarball: {e}")


def verify_npm_package(extracted: dict[str, bytes], version: str, manifest: dict[str, Any]) -> None:
    try:
        package = json.loads(extracted["package.json"])
    except (KeyError, json.JSONDecodeError) as e:
        fail(f"npm package has no valid package.json: {e}")
    npm = manifest["distribution"]["npm"]
    if package.get("name") != npm["name"] or package.get("version") != version:
        fail("npm name/version disagree with catalog or Python artifact")
    exports = package.get("exports", {})
    if set(exports) != set(npm["exports"]):
        fail("npm export keys differ from the catalog")
    for name, spec in npm["exports"].items():
        actual = exports[name]
        for kind in ("runtime", "types", "style", "metadata"):
            if kind not in spec:
                continue
            expected = "./" + spec[kind]
            target = (
                actual
                if isinstance(actual, str)
                else actual.get("import" if kind == "runtime" else kind)
            )
            if target != expected or spec[kind] not in extracted:
                fail(f"npm {kind} target for {name} is missing or differs: {target!r}")
    expected_peers = {k: v["version"] for k, v in npm["peer_dependencies"].items()}
    if package.get("peerDependencies", {}) != expected_peers:
        fail("npm peer dependency names or ranges differ from catalog")
    actual_optional = {
        k: bool(v.get("optional", False))
        for k, v in package.get("peerDependenciesMeta", {}).items()
    }
    expected_optional = {
        k: bool(v["optional"]) for k, v in npm["peer_dependencies"].items() if v["optional"]
    }
    if actual_optional != expected_optional:
        fail("npm peer optionality differs from catalog")


def npm_payload(
    members: dict[str, bytes], version: str, manifest: dict[str, Any]
) -> tuple[str, bytes, dict[str, bytes]]:
    matches = [n for n in members if n.startswith("arras/ui/npm/") and n.endswith(".tgz")]
    expected = f"arras/ui/npm/documentdrivendx-arras-ui-{version}.tgz"
    if matches != [expected]:
        fail(
            f"wheel npm tarball missing, ambiguous, or stale: found {matches}, expected {expected}"
        )
    payload = members[expected]
    extracted = unpack_npm(payload)
    verify_npm_package(extracted, version, manifest)
    return Path(expected).name, payload, extracted


def require_wheel_assets(members: dict[str, bytes]) -> None:
    required = (
        "arras/py.typed",
        "arras/public-api.json",
        "arras/conformance/corpus.json",
        "arras/ui/static/embed.html",
    )
    for name in required:
        if name not in members:
            fail(f"wheel omits required package file {name}")
    if not any(name.startswith("arras/ui/static/umf-explorer/") for name in members):
        fail("wheel omits the UMF schema-browser assets")


def inspect_wheel(
    path: Path, version: str, expected_metadata: dict[str, Any]
) -> tuple[dict[str, bytes], dict[str, Any], str, bytes, dict[str, Any]]:
    members, name, actual, message = wheel_members(path)
    if name.lower().replace("_", "-") != "arras" or actual != version:
        fail(f"wheel metadata name/version mismatch: {name} {actual}")
    verify_record(members)
    signature = verify_metadata_headers(
        message_metadata_fields(message), expected_metadata, path.name
    )
    manifest = catalog(members)
    verify_manifest_python_floor(manifest, expected_metadata["requires_python"])
    require_wheel_assets(members)
    page = members["arras/ui/static/embed.html"].decode("utf-8")
    import re

    refs = re.findall(r"(?:src|href)=\"([^\"]+)\"", page)
    for ref in refs:
        if ref.startswith(("http:", "https:", "#", "data:")):
            continue
        relative = PurePosixPath("arras/ui/static") / PurePosixPath(ref)
        if ".." in PurePosixPath(ref).parts:
            fail(f"wheel page references an escaping asset {ref}")
        candidate = relative.as_posix()
        if candidate not in members and not any(
            n.startswith(candidate.rstrip("/") + "/") for n in members
        ):
            fail(f"wheel page references missing asset {ref}")
    licenses = [
        n
        for n in members
        if n.endswith(".dist-info/licenses/LICENSE-MIT")
        or n.endswith(".dist-info/licenses/LICENSE-APACHE")
    ]
    if len(licenses) != 2:
        fail(f"wheel must carry both licenses, found {licenses}")
    _, npm_bytes, _ = npm_payload(members, version, manifest)
    return members, manifest, path.name, npm_bytes, signature


def install_consumer(wheel: Path, temp: Path, role: str, npm_script: Path) -> dict[str, str]:
    envdir = temp / ("consumer-" + role)
    venv.EnvBuilder(with_pip=True).create(envdir)
    py = envdir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([str(py), "-m", "pip", "install", str(wheel)], check=True)
    probe = r"""import importlib, importlib.util, json, pathlib, sys
import arras
from arras import Arras, Placement, Principal
from arras.adapters.truss import create_backend, ModuleAccess, TrussBackend, InstallingSource, ConnectionSource
from arras.console import create_app as console_app, Request as ConsoleRequest
from arras.operate import create_app as operate_app, create_schema_app, Request as OperateRequest, operators_in_groups
from arras.testing import InMemory, example_module
from arras.ui import Brand, create_app as ui_app, npm_package
from arras.telemetry import dropped
from arras.conformance import Harness, Limit, Result, Report, run_corpus
root = pathlib.Path(arras.__file__).resolve().parent
catalog = json.loads((root / 'public-api.json').read_text())
assert catalog['schema_version'] == 1
assert arras.__all__ == catalog['python']['root_all']
for module_name, spec in catalog['python']['modules'].items():
 module = importlib.import_module(module_name)
 names = catalog['python']['root_all'] if spec['names'] == 'root_all' else spec['names']
 assert all(hasattr(module, name) for name in names), module_name
assert pathlib.Path(sys.prefix).resolve() in pathlib.Path(arras.__file__).resolve().parents
assert (root / 'public-api.json').is_file() and (root / 'py.typed').is_file()
assert (root / 'ui' / 'static' / 'embed.html').is_file()
assert dropped() >= 0 and npm_package().is_file()
assert not importlib.util.find_spec('truss') and not importlib.util.find_spec('psycopg')
box = InMemory(); box.register(example_module()); user = box.person('consumer', 'catalog', 'read')
assert box.arras.session(user).describe('catalog')
seen = []
app = ui_app(box.arras, principal_for_request=lambda _: user, authorize_operator=operators_in_groups('admins'), authorize_schema=lambda principal, module: seen.append((principal.user, module)) or False, brand=Brand(name='External Consumer'))
assert app.brand.name == 'External Consumer' and callable(app)
callback = app.apis['/api/schema'].authorize_schema
assert callback is not None and callback(user, 'catalog') is False and seen == [('consumer', 'catalog')]
import importlib.resources
corpus = importlib.resources.files('arras.conformance').joinpath('corpus.json').read_text()
assert json.loads(corpus)['version'] == catalog['resources']['conformance_corpus_version'] == 13
import arras.view
assert arras.view.VERSION == catalog['resources']['vocabularies'][0]['version']
import importlib.metadata
dist = importlib.metadata.distribution('graphql-core')
import hashlib
h = hashlib.sha256()
for entry in sorted(dist.files or [], key=str):
 p = pathlib.Path(dist.locate_file(entry))
 if p.is_file(): h.update(str(entry).encode()); h.update(p.read_bytes())
print(json.dumps({'python': sys.version.split()[0], 'platform': sys.platform, 'package': str(root), 'schema_callback': True, 'in_memory_operation': True, 'graphql_core': dist.version, 'graphql_core_inventory_sha256': h.hexdigest()}))
"""
    result = subprocess.run(
        [str(py), "-I", "-c", probe], cwd=temp, capture_output=True, text=True, check=True
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    with zipfile.ZipFile(wheel) as z:
        embedded = [n for n in z.namelist() if n.startswith("arras/ui/npm/") and n.endswith(".tgz")]
        if len(embedded) != 1:
            fail(f"{role} wheel contains {len(embedded)} npm artifacts")
        extracted_tgz = temp / f"{role}-ui.tgz"
        extracted_tgz.write_bytes(z.read(embedded[0]))
    manifest_path = temp / f"{role}-public-api.json"
    with zipfile.ZipFile(wheel) as z:
        manifest_path.write_bytes(z.read("arras/public-api.json"))
    consumer = subprocess.run(
        ["node", str(npm_script), str(extracted_tgz), str(manifest_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if consumer.returncode:
        fail(f"packed npm consumer failed for {role}: {consumer.stdout} {consumer.stderr}")
    payload["packed_npm_consumer"] = (
        consumer.stdout.strip().splitlines()[-1] if consumer.stdout.strip() else "passed"
    )
    payload["environment"] = role
    return payload


def verify_sdist_metadata(
    sdist: Path, version: str, expected_metadata: dict[str, Any]
) -> dict[str, Any]:
    with tarfile.open(sdist, "r:gz") as tf:
        names = [m.name for m in tf.getmembers()]
        if len(names) != len(set(names)):
            fail("sdist contains duplicate archive member names")
        info = [m for m in tf.getmembers() if m.isfile() and m.name.endswith("/PKG-INFO")]
        if len(info) != 1:
            fail(f"sdist needs one PKG-INFO, found {[m.name for m in info]}")
        stream = tf.extractfile(info[0])
        if stream is None:
            fail("sdist PKG-INFO cannot be read")
        metadata = email.message_from_bytes(stream.read())
        if (
            metadata.get("Name", "").lower().replace("_", "-") != "arras"
            or metadata.get("Version") != version
        ):
            fail("sdist metadata name/version disagree with pyproject.toml")
        return verify_metadata_headers(
            message_metadata_fields(metadata), expected_metadata, "sdist"
        )


def rebuild_from_sdist(sdist: Path, temp: Path) -> Path:
    source = temp / "sdist-source"
    source.mkdir()
    with tarfile.open(sdist, "r:gz") as tf:
        seen: set[str] = set()
        for member in tf.getmembers():
            rel = PurePosixPath(member.name)
            if rel.is_absolute() or ".." in rel.parts or member.name.rstrip("/") != rel.as_posix():
                fail(f"unsafe or non-canonical sdist archive member {member.name}")
            if member.name in seen:
                fail(f"duplicate sdist archive member {member.name}")
            seen.add(member.name)
            if not (member.isdir() or member.isfile()):
                fail(f"sdist contains a link or special member {member.name}")
        tf.extractall(source, filter="data")
    roots = [p for p in source.iterdir() if p.is_dir() and p.name.startswith("arras-")]
    if len(roots) != 1:
        fail(f"sdist must contain one project root, found {roots}")
    out = temp / "rebuilt"
    out.mkdir()
    cache = temp / "uv-cache"
    cache.mkdir()
    env = dict(os.environ, UV_CACHE_DIR=str(cache))
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out)], cwd=roots[0], env=env, check=True
    )
    wheels = list(out.glob("arras-*.whl"))
    if len(wheels) != 1:
        fail(f"expected one wheel rebuilt from the sdist, found {wheels}")
    return wheels[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("sdist", type=Path)
    parser.add_argument("--output", type=Path, help="write the JSON evidence receipt to this file")
    args = parser.parse_args()
    version = read_project_version()
    one_artifact(args.wheel, "py3-none-any.whl", version)
    one_artifact(args.sdist, ".tar.gz", version)
    expected_metadata = expected_project_metadata()
    sdist_metadata = verify_sdist_metadata(args.sdist, version, expected_metadata)
    with tempfile.TemporaryDirectory(prefix="arras-dist-verify-") as td:
        temp = Path(td)
        source_members, source_manifest, _, source_npm, source_metadata = inspect_wheel(
            args.wheel, version, expected_metadata
        )
        rebuilt = rebuild_from_sdist(args.sdist, temp)
        if rebuilt.name != args.wheel.name:
            fail(
                f"sdist rebuilt wheel filename {rebuilt.name} differs from source wheel {args.wheel.name}"
            )
        rebuilt_members, rebuilt_manifest, _, rebuilt_npm, rebuilt_metadata = inspect_wheel(
            rebuilt, version, expected_metadata
        )
        if source_npm != rebuilt_npm:
            fail("npm tarball bytes differ between source wheel and sdist-rebuilt wheel")
        if source_metadata != rebuilt_metadata or source_metadata != sdist_metadata:
            fail("Requires-Python/Requires-Dist/Provides-Extra differ between release artifacts")
        if source_members["arras/public-api.json"] != rebuilt_members["arras/public-api.json"]:
            fail("public API manifest bytes differ between source wheel and sdist-rebuilt wheel")
        if source_manifest != rebuilt_manifest:
            fail("public API manifests differ between source wheel and sdist-rebuilt wheel")
        source_package = {k: v for k, v in source_members.items() if k.startswith("arras/")}
        rebuilt_package = {k: v for k, v in rebuilt_members.items() if k.startswith("arras/")}
        changed = package_differences(source_package, rebuilt_package)
        if changed:
            fail(f"complete Arras package payload differs between wheels: {changed}")
        npm_script = ROOT / "ui/scripts/packed-consumer.mjs"
        source_consumer = install_consumer(args.wheel, temp, "source-wheel", npm_script)
        rebuilt_consumer = install_consumer(rebuilt, temp, "sdist-rebuilt-wheel", npm_script)
        inventory = {
            "python_interpreter": sys.version.split()[0],
            "platform": platform.platform(),
            "declared_python": source_manifest["distribution"]["declared_python"],
            "qualified_python": sys.version.split()[0],
            "source_wheel": {"file": args.wheel.name, "sha256": sha(args.wheel.read_bytes())},
            "sdist": {"file": args.sdist.name, "sha256": sha(args.sdist.read_bytes())},
            "sdist_rebuilt_wheel": {"file": rebuilt.name, "sha256": sha(rebuilt.read_bytes())},
            "npm": {
                "file": f"documentdrivendx-arras-ui-{version}.tgz",
                "sha256": sha(source_npm),
                "exact_between_wheels": True,
            },
            "consumers": {"source_wheel": source_consumer, "sdist_rebuilt_wheel": rebuilt_consumer},
            "javascript_consumer_cohort": "workspace-linked UI dependencies; package itself extracted from each verified wheel",
            "qualification": ["artifact-inspected", "installed-consumer-tested"],
            "not_qualified_without_observation": source_manifest["qualification"][
                "not_qualified_without_observation"
            ],
        }
        receipt = json.dumps(inventory, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(receipt)
        print(receipt, end="")


if __name__ == "__main__":
    main()
