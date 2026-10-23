#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded file and JSON primitives for the private release evidence assembler."""

from __future__ import annotations

import argparse
import ast
import email
import gzip
import hashlib
import html.parser
import io
import json
import os
import re
import shutil
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast
from urllib.parse import urlsplit

MAX_ARTIFACT = 512 * 1024 * 1024
MAX_JSON = 32 * 1024 * 1024
MAX_INDEX = 4 * 1024 * 1024
MAX_SUMS = 64 * 1024


def parse_arguments(argv: list[str] | None, description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--build-bundle", required=True, type=Path)
    parser.add_argument("--native-receipt", required=True, type=Path)
    parser.add_argument("--native-binding", required=True, type=Path)
    parser.add_argument("--native-cohort", required=True, type=Path)
    parser.add_argument("--native-index", required=True, type=Path)
    parser.add_argument("--ui-receipt", required=True, type=Path)
    parser.add_argument("--consumer-receipt", required=True, type=Path)
    parser.add_argument("--umf-admission-receipt", type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-wheel", required=True)
    parser.add_argument("--expected-wheel-sha256", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


CANONICAL_UI_SPECS = (
    "a11y.spec.ts",
    "brand.spec.ts",
    "browse-actions.spec.ts",
    "browse-history.spec.ts",
    "browse-new.spec.ts",
    "browse-retire.spec.ts",
    "browser.spec.ts",
    "cross-links.spec.ts",
    "flows.spec.ts",
    "host-isolation.spec.ts",
    "operator.spec.ts",
    "query.spec.ts",
    "routes.spec.ts",
    "schema-admin.spec.ts",
    "shortcuts.spec.ts",
    "umf-explorer.spec.ts",
    "visual.spec.ts",
)
DOCTOR_CASE_STATUSES = (
    ("positive installed wheel with page/theme/config/Brand/env/module inputs", 0),
    ("package pin", 1),
    ("contract pin", 1),
    ("Python export", 1),
    ("npm export", 1),
    ("role token", 1),
    ("unsupported range pin", 3),
    ("environment key name", 1),
    ("committed config key", 1),
    ("theme cohort", 1),
    ("legacy module document", 1),
    ("unsupported official UMF profile", 3),
    ("missing module profile", 3),
    ("Brand semantic validation", 1),
    ("duplicate request keys", 2),
    ("unknown CLI option redaction", 2),
    ("help before request access", 0),
    ("environment/file/network/subprocess/registration/import tripwires", 0),
    ("installed public launcher Brand/help/startup/alias probes", 0),
    ("installed SDK resources, direct/MCP/worker-backed ASGI, launcher names", 0),
)
DOCTOR_PHASE_SERVICES = {
    "direct": "extension-alpha+extension-beta",
    "mcp_frame": "extension-beta",
    "worker_backed_asgi_console": "extension-alpha",
    "worker_backed_asgi_operate": "extension-alpha",
    "concurrent_nested": "extension-alpha+extension-beta",
    "nested_ambient_restoration": "extension-alpha",
    "finish_time_snapshot": "extension-alpha",
    "provider_fault_isolation": "extension-alpha",
}
DOCTOR_FALSE_PASS_CONTROLS = (
    "MCP successful empty result",
    "ASGI successful HTTP 200 empty body",
    "finish-time ambient-context misrouting",
)
DOCTOR_TRIPWIRE_STATES = {
    "positive": (True, True),
    "invalid_config": (False, True),
    "unsupported": (False, False),
}
DOCTOR_LAUNCHER_PROBES = (
    "custom_mcp_help",
    "custom_mcp_unsupported_args",
    "alias_conflict_refused",
    "custom_devhost_help",
    "custom_devhost_unsupported_args",
    "custom_devhost_startup_forwarding",
)
DOCTOR_TELEMETRY_PROBES = (
    "public_direct_library",
    "public_mcp_frame",
    "public_worker_backed_asgi",
    "concurrent_and_nested_contexts",
    "default_deny_and_failure_isolation",
)
MAX_WHEEL_MEMBERS = 100_000
SHA_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[A-Za-z0-9.+-]*)\Z")


class AssemblyError(ValueError):
    """The selected release evidence is incomplete or inconsistent."""


def fail(message: str) -> NoReturn:
    raise AssemblyError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        fail(f"{label} must be nonempty text")
    return value


def digest(value: object, label: str) -> str:
    result = string(value, label)
    if SHA_PATTERN.fullmatch(result) is None:
        fail(f"{label} must be a lowercase SHA-256 digest")
    return result


def object_value(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        fail(f"{label} must be a JSON object")
    return cast(dict[str, Any], value)


def exact_object(value: object, label: str, expected: set[str]) -> dict[str, Any]:
    result = object_value(value, label)
    if set(result) != expected:
        fail(f"{label} must contain exactly {sorted(expected)}")
    return result


def validate_ui_suite_cohort(
    value: object, wheel_sha: str, npm_sha: str, theme_sha: str, runner_sha: str
) -> None:
    label = "UI acceptance suite cohort"
    expected = {
        "wheelSha256": wheel_sha,
        "npmSha256": npm_sha,
        "themeSha256": theme_sha,
        "runnerSha256": runner_sha,
    }
    selected = exact_object(value, label, set(expected))
    for name, expected_sha in expected.items():
        if digest(selected.get(name), f"{label}.{name}") != expected_sha:
            fail(f"{label}.{name} differs from the outer UI cohort")


def read_bounded(path: Path, limit: int, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        fail(f"cannot safely open {label}: {exc}")
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            fail(f"{label} must be a regular file")
        if info.st_size > limit:
            fail(f"{label} exceeds the {limit}-byte bound")
        chunks: list[bytes] = []
        total = 0
        while total <= limit:
            block = os.read(descriptor, min(1024 * 1024, limit + 1 - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
        raw = b"".join(chunks)
    except OSError as exc:
        fail(f"cannot read {label}: {exc}")
    finally:
        os.close(descriptor)
    if len(raw) > limit:
        fail(f"{label} exceeds the {limit}-byte bound")
    return raw


def input_file(path: Path, limit: int, label: str) -> tuple[Path, bytes]:
    absolute = path.absolute()
    for ancestor in (absolute, *absolute.parents):
        if ancestor.is_symlink():
            fail(f"{label} path must not traverse symlinks")
    raw = read_bounded(absolute, limit, label)
    return absolute.resolve(strict=True), raw


def parse_json_object(raw: bytes, label: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                fail(f"duplicate JSON key {key!r} in {label}")
            result[key] = value
        return result

    def invalid_constant(value: str) -> NoReturn:
        fail(f"non-JSON numeric constant {value!r} in {label}")

    try:
        return object_value(
            json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant), label
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{label} is not bounded UTF-8 JSON: {exc}")


def load_json(path: Path) -> dict[str, Any]:
    return parse_json_object(read_bounded(path, MAX_JSON, "JSON evidence"), path.name)


def artifact(path: Path, label: str) -> tuple[Path, bytes, str]:
    resolved, raw = input_file(path, MAX_ARTIFACT, label)
    if not raw:
        fail(f"{label} is empty")
    return resolved, raw, sha256(raw)


def path_alias(left: Path, right: Path) -> bool:
    if left.resolve() == right.resolve():
        return True
    return left.exists() and right.exists() and os.path.samefile(left, right)


def release_version(value: object) -> str:
    result = string(value, "expected version")
    if VERSION_PATTERN.fullmatch(result) is None:
        fail("expected version must be a normalized release version")
    return result


_fail = fail
_string = string
_digest = digest
_object = object_value
_keys = exact_object
_sha = sha256
_parse_json_object = parse_json_object
_input_file = input_file
_read = read_bounded
_artifact = artifact
_path_alias = path_alias
_version = release_version


def doctor_probe_hashes(source_path: Path) -> tuple[str, str]:
    resolved, raw = input_file(source_path, MAX_JSON, "trusted doctor verifier source")
    try:
        tree = ast.parse(raw.decode("utf-8"), filename=resolved.name)
    except (UnicodeDecodeError, SyntaxError) as exc:
        fail(f"trusted doctor verifier source cannot be parsed: {exc}")
    builders = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "telemetry_probe_script"
    ]
    if len(builders) != 1:
        fail("trusted doctor verifier must define one telemetry probe builder")
    literals: list[str] = []
    for node in ast.walk(builders[0]):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "write_text" or not node.args:
            continue
        value = node.args[0]
        encoding = next((item.value for item in node.keywords if item.arg == "encoding"), None)
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        if not isinstance(encoding, ast.Constant) or encoding.value != "utf-8":
            continue
        literals.append(value.value)
    if len(literals) != 1:
        fail("trusted doctor telemetry probe builder changed from the reviewed literal form")
    return sha256(raw), sha256(literals[0].encode("utf-8"))


# Archive, index, and sidecar input integrity helpers.
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _parse_sums(raw: bytes, expected: set[str]) -> dict[str, str]:
    if len(raw) > MAX_SUMS:
        _fail("build SHA256SUMS exceeds its size bound")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError:
        _fail("build SHA256SUMS must be ASCII")
    found: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/\\]+)", line)
        if match is None:
            _fail("build SHA256SUMS contains a malformed entry")
        digest, name = match.groups()
        if name in found:
            _fail(f"build SHA256SUMS repeats {name}")
        found[name] = digest
    if set(found) != expected:
        _fail("build SHA256SUMS must list exactly the five selected build assets")
    return found


def _safe_zip(path: Path) -> tuple[zipfile.ZipFile, list[str]]:
    try:
        archive = zipfile.ZipFile(path)
        names = archive.namelist()
    except (OSError, zipfile.BadZipFile) as exc:
        _fail(f"cannot inspect {path.name}: {exc}")
    if len(names) > MAX_WHEEL_MEMBERS or len(names) != len(set(names)):
        archive.close()
        _fail(f"{path.name} has too many or duplicate archive members")
    total = 0
    for name in names:
        item = PurePosixPath(name)
        if item.is_absolute() or ".." in item.parts or item.as_posix() != name.rstrip("/"):
            archive.close()
            _fail(f"{path.name} has an unsafe member path")
        try:
            total += archive.getinfo(name).file_size
        except KeyError:
            archive.close()
            _fail(f"{path.name} has malformed archive metadata")
        if total > MAX_ARTIFACT:
            archive.close()
            _fail(f"{path.name} uncompressed payload exceeds the bound")
    return archive, names


def _bounded_tar_stream(raw: bytes, label: str) -> io.BytesIO:
    if len(raw) > MAX_ARTIFACT:
        _fail(f"{label} compressed payload exceeds the bound")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
            expanded = compressed.read(MAX_ARTIFACT + 1)
    except (OSError, EOFError) as exc:
        _fail(f"cannot decompress {label}: {exc}")
    if len(expanded) > MAX_ARTIFACT:
        _fail(f"{label} uncompressed payload exceeds the bound")
    return io.BytesIO(expanded)


def _safe_tar_members(
    archive: tarfile.TarFile, label: str
) -> tuple[list[tarfile.TarInfo], dict[str, tarfile.TarInfo]]:
    members: list[tarfile.TarInfo] = []
    files: dict[str, tarfile.TarInfo] = {}
    total = 0
    for member in archive:
        if len(members) >= MAX_WHEEL_MEMBERS:
            _fail(f"{label} contains too many members")
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or path.as_posix() != member.name.rstrip("/"):
            _fail(f"{label} contains an unsafe member path")
        if member.name in files or not (member.isfile() or member.isdir()):
            _fail(f"{label} contains duplicate, link, or special members")
        members.append(member)
        files[member.name] = member
        total += max(member.size, 0)
        if total > MAX_ARTIFACT:
            _fail(f"{label} uncompressed payload exceeds the bound")
    return members, files


def _wheel_identity(path: Path, expected_name: str, version: str) -> bytes:
    archive, names = _safe_zip(path)
    try:
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        npm_names = [
            name for name in names if name.startswith("arras/ui/npm/") and name.endswith(".tgz")
        ]
        if len(metadata_names) != 1 or len(npm_names) != 1:
            _fail("Arras wheel must contain one METADATA and one wheel-carried npm archive")
        message = email.message_from_bytes(archive.read(metadata_names[0]))
        actual_name = message.get("Name", "").lower().replace("_", "-")
        if actual_name != "arras" or message.get("Version") != version:
            _fail("Arras wheel METADATA name/version do not match the release identity")
        expected_filename = f"arras-{version}-py3-none-any.whl"
        if path.name != expected_filename or path.name != expected_name:
            _fail("selected Arras wheel filename does not match its version")
        npm_bytes = archive.read(npm_names[0])
        if len(npm_bytes) > MAX_ARTIFACT:
            _fail("wheel-carried npm archive exceeds the size bound")
    finally:
        archive.close()
    return npm_bytes


def _sdist_identity(path: Path, version: str) -> None:
    try:
        _, compressed, _ = _artifact(path, "sdist")
        with tarfile.open(fileobj=_bounded_tar_stream(compressed, "sdist"), mode="r:") as archive:
            members, _ = _safe_tar_members(archive, "sdist")
            metadata: list[tarfile.TarInfo] = []
            for member in members:
                if member.isfile() and member.name.endswith("/PKG-INFO"):
                    metadata.append(member)
            if len(metadata) != 1:
                _fail("sdist must contain exactly one PKG-INFO")
            stream = archive.extractfile(metadata[0])
            if stream is None:
                _fail("sdist PKG-INFO cannot be read")
            message = email.message_from_bytes(stream.read(1024 * 1024 + 1))
            if message.get("Name", "").lower().replace("_", "-") != "arras":
                _fail("sdist PKG-INFO does not identify Arras")
            if message.get("Version") != version or path.name != f"arras-{version}.tar.gz":
                _fail("sdist name/version do not match the release identity")
    except (OSError, tarfile.TarError) as exc:
        _fail(f"cannot inspect sdist: {exc}")


def _npm_identity(raw: bytes, version: str) -> tuple[str, bytes]:
    try:
        with tarfile.open(fileobj=_bounded_tar_stream(raw, "npm archive"), mode="r:") as archive:
            members, files_by_name = _safe_tar_members(archive, "npm archive")
            package_json: list[tarfile.TarInfo] = []
            resources_json: list[tarfile.TarInfo] = []
            for member in members:
                if member.isfile() and member.name == "package/package.json":
                    package_json.append(member)
                if member.isfile() and member.name == "package/support/acceptance/resources.json":
                    resources_json.append(member)
            if len(package_json) != 1:
                _fail("npm archive must contain exactly package/package.json")
            stream = archive.extractfile(package_json[0])
            if stream is None:
                _fail("npm package metadata cannot be read")
            package = _parse_json_object(stream.read(1024 * 1024), "npm package metadata")
            if (
                package.get("name") != "@documentdrivendx/arras-ui"
                or package.get("version") != version
            ):
                _fail("npm package identity differs from the release")
            if len(resources_json) != 1:
                _fail("npm archive must contain its acceptance resources inventory")
            resources_stream = archive.extractfile(resources_json[0])
            if resources_stream is None:
                _fail("npm acceptance resources inventory cannot be read")
            resources_raw = resources_stream.read(MAX_JSON + 1)
            if len(resources_raw) > MAX_JSON:
                _fail("npm acceptance resources inventory exceeds the JSON bound")
            resources = _parse_json_object(resources_raw, "npm acceptance resources")
            _validate_resource_manifest(resources, files_by_name, archive)
            return f"documentdrivendx-arras-ui-{version}.tgz", resources_raw
    except (OSError, tarfile.TarError, json.JSONDecodeError) as exc:
        _fail(f"cannot inspect wheel-carried npm archive: {exc}")


def _validate_resource_manifest(
    resources: dict[str, Any], members: dict[str, tarfile.TarInfo], archive: tarfile.TarFile
) -> None:
    if (
        set(resources) != {"version", "specs", "expectedCounts", "files"}
        or type(resources.get("version")) is not int
        or resources.get("version") != 1
    ):
        _fail("npm acceptance resources inventory has an unsupported schema")
    specs = resources.get("specs")
    counts = _object(resources.get("expectedCounts"), "npm expectedCounts")
    files = _object(resources.get("files"), "npm resource files")
    if not isinstance(specs, list) or tuple(specs) != CANONICAL_UI_SPECS:
        _fail("npm acceptance resources inventory must enumerate 17 canonical specs")
    if not counts or not all(
        isinstance(key, str) and type(count) is int and count > 0 for key, count in counts.items()
    ):
        _fail("npm acceptance expectedCounts is malformed")
    expected_specs = {f"acceptance/e2e/{spec}" for spec in CANONICAL_UI_SPECS}
    if not expected_specs.issubset(files):
        _fail("npm acceptance resource files omit a canonical UI spec")
    for name, digest in files.items():
        safe = _safe_relative(name, "npm resource path")
        member_name = f"package/support/{safe}"
        member = members.get(member_name)
        if member is None or not member.isfile():
            _fail(f"npm acceptance resource is missing: {safe}")
        if not isinstance(digest, str) or _SHA.fullmatch(digest) is None:
            _fail(f"npm acceptance resource has invalid digest: {safe}")
        stream = archive.extractfile(member)
        if stream is None or _sha(stream.read(MAX_ARTIFACT + 1)) != digest:
            _fail(f"npm acceptance resource digest differs: {safe}")


def _safe_https(value: str, label: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        _fail(f"{label} must be credential-free HTTPS without query parameters")


class _Anchors(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.unsafe = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() not in {"html", "head", "body", "title", "a"}:
            self.unsafe = True
        if any(
            key.lower() not in {"href", "rel", "title"} or key.lower().startswith("on")
            for key, _ in attrs
        ):
            self.unsafe = True
        if tag.lower() == "a":
            self.hrefs.extend(value for key, value in attrs if key.lower() == "href" and value)


def _validate_index(raw: bytes, cohort: dict[str, Any]) -> None:
    if len(raw) > MAX_INDEX:
        _fail("native companion index exceeds its size bound")
    try:
        parser = _Anchors()
        parser.feed(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        _fail(f"native companion index is not safe UTF-8 HTML: {exc}")
    if parser.unsafe:
        _fail("native companion index contains active HTML content")
    expected = {
        f"{item['url']}#sha256={item['sha256']}"
        for item in cast(list[dict[str, Any]], cohort["native_wheels"])
    }
    if len(parser.hrefs) != len(set(parser.hrefs)) or set(parser.hrefs) != expected:
        _fail(
            "native companion index must contain exactly the selected credential-free wheel anchors"
        )


def _read_ui_sidecars(receipt_path: Path, suite: dict[str, Any]) -> dict[str, bytes]:
    canonical = _object(suite.get("canonical"), "UI canonical inventory")
    playwright = _object(suite.get("playwright"), "UI Playwright summary")
    names = (
        "acceptance-inventory-neutral-theme.json",
        "acceptance-resources-neutral-theme.json",
        "playwright-summary-neutral-theme.json",
    )
    references = (
        (canonical, "inventoryPath", "inventorySha256"),
        (canonical, "resourcesPath", "resourcesSha256"),
        (playwright, "reportPath", "sha256"),
    )
    sidecars: dict[str, bytes] = {}
    for name, (reference, path_key, digest_key) in zip(names, references, strict=True):
        if reference.get(path_key) != name:
            _fail(f"UI receipt must reference fixed sibling {name}")
        path = receipt_path.parent / name
        _, raw = _input_file(path, MAX_JSON, f"UI sidecar {name}")
        if _sha(raw) != _digest(reference.get(digest_key), f"UI sidecar digest {name}"):
            _fail(f"UI sidecar digest differs: {name}")
        sidecars[name] = raw
    return sidecars


def _safe_relative(value: object, label: str) -> str:
    raw = _string(value, label)
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or "\\" in raw:
        _fail(f"{label} must be a safe relative path")
    return raw


# Safe path handling and atomic output publication.


def _read_qualification_inputs(
    entries: tuple[tuple[str, Path, int], ...],
) -> dict[str, tuple[Path, bytes, str]]:
    selected: dict[str, tuple[Path, bytes, str]] = {}
    for label, path, limit in entries:
        resolved, raw = _input_file(path, limit, label)
        selected[label] = (resolved, raw, _sha(raw))
    return selected


def _check_output_target(output_dir: Path, build_bundle: Path, inputs: list[Path]) -> Path:
    output = output_dir.absolute()
    if output.exists() or output.is_symlink():
        _fail("output directory must be new")
    for ancestor in (output.parent, *output.parent.parents):
        if ancestor.exists() and ancestor.is_symlink():
            _fail("output directory path must not traverse symlinks")
    root = build_bundle.resolve(strict=True)
    resolved_output = output.resolve()
    if resolved_output == root or root in resolved_output.parents:
        _fail("output directory must be outside the verified build bundle")
    if any(
        resolved_output == item.resolve() or resolved_output in item.resolve().parents
        for item in inputs
    ):
        _fail("output directory must not contain or alias selected input files")
    for index, left in enumerate(inputs):
        if any(_path_alias(left, right) for right in inputs[index + 1 :]):
            _fail("selected evidence inputs must be distinct files")
    return output


def _publish_bundle(
    output_dir: Path,
    selected: dict[str, Path],
    projections: dict[str, Any],
    raw_files: dict[str, bytes],
    expected_digests: dict[str, str],
) -> None:
    if set(selected) & (set(projections) | set(raw_files)) or set(projections) & set(raw_files):
        _fail("release output names must be distinct across copied and projected files")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = output_dir.parent / f".{output_dir.name}.assemble-{os.getpid()}"
    if stage.exists() or stage.is_symlink():
        _fail("assembly staging path already exists")
    stage.mkdir(mode=0o700)
    try:
        for name, path in selected.items():
            _, raw, actual_digest = _artifact(path, name)
            if actual_digest != expected_digests[name]:
                _fail(f"selected build asset changed while assembling: {name}")
            (stage / name).write_bytes(raw)
        for name, data in projections.items():
            (stage / name).write_bytes(canonical_json(data))
        for name, data in raw_files.items():
            (stage / name).write_bytes(data)
        asset_names = sorted({*selected, *projections, *raw_files})
        sums = "".join(f"{_sha((stage / name).read_bytes())}  {name}\n" for name in asset_names)
        (stage / "SHA256SUMS").write_text(sums, encoding="ascii")
        expected_names = set(asset_names) | {"SHA256SUMS"}
        if {path.name for path in stage.iterdir()} != expected_names:
            _fail("assembled output inventory is not exact")
        stage.rename(output_dir)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


# Shape validation for bounded cohort receipt values.
def _validate_limits(value: object) -> dict[str, dict[str, str | None]]:
    limits = _object(value, "corpus limits")
    result: dict[str, dict[str, str | None]] = {}
    for case, raw in limits.items():
        _string(case, "limit case ID")
        item = _keys(raw, f"limit {case}", {"step", "error", "detail"})
        result[case] = {
            "step": _string(item["step"], f"limit {case}.step"),
            "error": _string(item["error"], f"limit {case}.error"),
            "detail": item["detail"]
            if item["detail"] is None
            else _string(item["detail"], f"limit {case}.detail"),
        }
    return result


def _unique_ids(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        _fail(f"{label} must be an array")
    result = [_string(item, label) for item in value]
    if len(result) != len(set(result)):
        _fail(f"{label} contains duplicate IDs")
    return result


# Native inventory scope is a fixed, bounded receipt value.
def _validate_native_scope(value: object) -> dict[str, str]:
    scope = _keys(value, "native binary scope", {"observed", "system_dynamic_link_audit"})
    expected = {
        "observed": "native files declared by installed Python distributions",
        "system_dynamic_link_audit": "not performed",
    }
    if scope != expected:
        _fail("native receipt has unsupported binary audit scope")
    return cast(dict[str, str], scope)


# Validated projection of the downstream memory corpus receipt.


# Closed native cohort input schema and identity validation.
def _validate_cohort(cohort: dict[str, Any], version: str, wheel_sha: str) -> None:
    expected = {"schema_version", "arras", "runtime", "find_links", "native_wheels", "corpus"}
    if (
        set(cohort) != expected
        or type(cohort.get("schema_version")) is not int
        or cohort["schema_version"] != 1
    ):
        _fail("bound native cohort has unsupported schema or fields")
    arras = _keys(cohort.get("arras"), "cohort.arras", {"version", "sha256"})
    if arras != {"version": version, "sha256": wheel_sha}:
        _fail("bound native cohort does not identify the selected wheel")
    runtime = _keys(cohort.get("runtime"), "cohort.runtime", {"python", "sys_platform", "machine"})
    if runtime.get("python") != "3.11" or not all(
        isinstance(v, str) and v for v in runtime.values()
    ):
        _fail("bound native cohort runtime is invalid")
    links = _keys(cohort.get("find_links"), "cohort.find_links", {"sha256"})
    _digest(links.get("sha256"), "cohort.find_links.sha256")
    wheels = cohort.get("native_wheels")
    if not isinstance(wheels, list) or not wheels:
        _fail("native cohort must select native wheels")
    seen: set[str] = set()
    for index, item in enumerate(wheels):
        wheel = _keys(
            item,
            f"cohort.native_wheels[{index}]",
            {"distribution", "version", "filename", "url", "sha256"},
        )
        distribution = re.sub(
            r"[-_.]+", "-", _string(wheel["distribution"], "native distribution").lower()
        )
        filename = _string(wheel["filename"], "native filename")
        if distribution in seen or Path(filename).name != filename or not filename.endswith(".whl"):
            _fail("native cohort contains duplicate or unsafe wheel entries")
        seen.add(distribution)
        _string(wheel["version"], "native wheel version")
        url = _string(wheel["url"], "native URL")
        _safe_https(url, "native URL")
        from urllib.parse import urlsplit

        if PurePosixPath(urlsplit(url).path).name != filename:
            _fail("native URL basename differs from selected wheel filename")
        _digest(wheel["sha256"], "native wheel SHA-256")
    corpus = _keys(cohort.get("corpus"), "cohort.corpus", {"version", "roles", "limits"})
    if type(corpus.get("version")) is not int or corpus["version"] <= 0:
        _fail("native corpus version must be a positive integer")
    if corpus.get("roles") != ["reader", "provider"]:
        _fail("native corpus roles are unsupported")
    _validate_limits(corpus.get("limits"))


def validate_ui_playwright_summary(value: dict[str, Any]) -> dict[str, Any]:
    summary = exact_object(
        value,
        "UI Playwright summary",
        {
            "schema",
            "status",
            "platform",
            "projects",
            "expectedTestCount",
            "unexpectedSkips",
        },
    )
    if (
        summary.get("schema") != "arras.ui.canonical-playwright-summary.v1"
        or summary.get("status") != "passed"
    ):
        fail("UI canonical Playwright summary is not a successful supported schema")
    projects = summary.get("projects")
    if not isinstance(projects, list):
        fail("UI Playwright summary projects must be an array")
    for raw_row in projects:
        row = exact_object(
            raw_row,
            "UI Playwright project summary",
            {"name", "expected", "discovered", "passed", "failed", "skipped"},
        )
        if any(
            type(row.get(field)) is not int
            for field in ("expected", "discovered", "passed", "failed", "skipped")
        ):
            fail("UI Playwright project summary counts must be integers")
    return summary


def doctor_evidence_sections(
    value: dict[str, Any],
) -> tuple[
    list[tuple[str, int]],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, dict[str, Any]],
]:
    cases = value.get("cases")
    if not isinstance(cases, list):
        fail("doctor receipt cases must be an array")
    case_results: list[tuple[str, int]] = []
    for raw in cases:
        case = exact_object(raw, "doctor case", {"name", "status", "codes"})
        name = string(case.get("name"), "doctor case name")
        status = case.get("status")
        codes = case.get("codes")
        if (
            type(status) is not int
            or not isinstance(codes, list)
            or not all(isinstance(code, str) and code for code in codes)
        ):
            fail("doctor case result is malformed")
        case_results.append((name, status))
    tripwire = object_value(value.get("tripwire_report"), "doctor tripwire report")
    for name in DOCTOR_TRIPWIRE_STATES:
        result = object_value(tripwire.get(name), f"doctor tripwire {name}")
        if type(result.get("ok")) is not bool or type(result.get("complete")) is not bool:
            fail(f"doctor tripwire {name} booleans are malformed")
    launcher = object_value(value.get("launcher_probes"), "doctor launcher probes")
    telemetry = object_value(value.get("telemetry_probes"), "doctor telemetry probes")
    if telemetry.get("false_pass_controls") != list(DOCTOR_FALSE_PASS_CONTROLS):
        fail("doctor telemetry false-pass controls are incomplete")
    phases_value = object_value(telemetry.get("phases"), "doctor telemetry phases")
    phases: dict[str, dict[str, Any]] = {}
    for name, raw in phases_value.items():
        phase = exact_object(
            raw, f"doctor telemetry phase {name}", {"spans", "events", "logs", "service_name"}
        )
        if (
            any(type(phase.get(key)) is not int for key in ("spans", "events", "logs"))
            or phase["spans"] <= 0
            or phase["logs"] <= 0
            or phase["events"] <= 0
            or not isinstance(phase.get("service_name"), str)
        ):
            fail(f"doctor telemetry phase {name} is malformed")
        phases[name] = phase
    return case_results, tripwire, launcher, telemetry, phases


def doctor_runtime(value: dict[str, Any]) -> dict[str, str]:
    """Validate and project the runtime identity recorded by doctor."""
    platform = exact_object(
        value.get("platform"), "doctor.platform", {"os", "architecture", "release"}
    )
    os_name = string(platform.get("os"), "doctor.platform.os")
    architecture = string(platform.get("architecture"), "doctor.platform.architecture")
    release = string(platform.get("release"), "doctor.platform.release")
    python_version = string(value.get("python"), "doctor.python")
    if os_name not in {"linux", "darwin", "win32"}:
        fail("doctor runtime operating system is unsupported")
    if architecture not in {"x86_64", "amd64", "AMD64", "arm64", "ARM64", "aarch64"}:
        fail("doctor runtime architecture is unsupported")
    if not release or not python_version:
        fail("doctor runtime release and Python version must be non-empty")
    return {
        "os": os_name,
        "architecture": architecture,
        "release": release,
        "python": python_version,
    }
