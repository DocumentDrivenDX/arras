#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Compare anonymous release downloads with the trusted assembled release stage."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import NoReturn

if __package__:
    from . import _umf_actions_receipt as _actions_receipt
    from . import _umf_admission_receipt as _umf_receipt
else:
    import _umf_actions_receipt as _actions_receipt
    import _umf_admission_receipt as _umf_receipt

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
_BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,199}\Z")
_MAX_SUMS = 64 * 1024
_MAX_FILE = 512 * 1024 * 1024
_MAX_TOTAL = 1024 * 1024 * 1024
_PUBLISHED_COMPONENTS = {
    "acceptance-inventory-neutral-theme.json",
    "acceptance-resources-neutral-theme.json",
    "consumer-qualification.json",
    "doctor-installed.json",
    "distribution-verification.json",
    "native-cohort-binding.json",
    "native-cohort.json",
    "native-find-links.html",
    "native-qualification.json",
    "playwright-summary-neutral-theme.json",
    "ui-qualification.json",
}
_UMF_COMPONENT = "umf-admission-installed.json"
_UMF_ACTIONS_COMPONENT = "umf-actions-installed.json"


class AssetError(ValueError):
    """A release asset input did not match the reviewed inventory."""


def _fail(message: str) -> NoReturn:
    raise AssetError(message)


def _expected_names(version: str, wheel: str, *, actions_required: bool = False) -> set[str]:
    names = {
        wheel,
        f"arras-{version}.tar.gz",
        f"documentdrivendx-arras-ui-{version}.tgz",
        "distribution-verification.json",
        "doctor-installed.json",
        "native-qualification.json",
        "native-cohort-binding.json",
        "native-cohort.json",
        "ui-qualification.json",
        "consumer-qualification.json",
        "release-evidence.json",
        "acceptance-inventory-neutral-theme.json",
        "acceptance-resources-neutral-theme.json",
        "playwright-summary-neutral-theme.json",
        "native-find-links.html",
    }
    if _umf_receipt.required_for_version(version):
        names.add(_UMF_COMPONENT)
    if actions_required:
        names.add(_UMF_ACTIONS_COMPONENT)
    return names


def _read_sums(path: Path) -> tuple[bytes, dict[str, str]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        _fail(f"cannot read SHA256SUMS: {exc.strerror or type(exc).__name__}")
    if len(raw) > _MAX_SUMS:
        _fail("SHA256SUMS exceeds its size limit")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        _fail("SHA256SUMS is not ASCII")
    entries: dict[str, str] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]{0,199})", line)
        if match is None:
            _fail("SHA256SUMS contains a malformed entry")
        digest, name = match.groups()
        if name in entries or name in {".", "..", "SHA256SUMS"}:
            _fail("SHA256SUMS contains a duplicate or reserved name")
        if Path(name).name != name or "/" in name or "\\" in name:
            _fail("SHA256SUMS contains a non-basename path")
        entries[name] = digest
    if not entries:
        _fail("SHA256SUMS is empty")
    return raw, entries


def _regular_inventory(directory: Path, allowed: set[str]) -> dict[str, Path]:
    try:
        root = directory.resolve(strict=True)
        if not root.is_dir() or directory.is_symlink():
            _fail("release asset directory must be a real directory")
        children = list(directory.iterdir())
    except OSError as exc:
        _fail(f"cannot inspect release asset directory: {exc.strerror or type(exc).__name__}")
    result: dict[str, Path] = {}
    identities: set[tuple[int, int]] = set()
    for item in children:
        name = item.name
        if name not in allowed or not _BASENAME.fullmatch(name):
            _fail("release asset directory contains an unexpected filename")
        if item.is_symlink() or not item.is_file():
            _fail("release asset directory contains a non-regular file")
        resolved = item.resolve(strict=True)
        if resolved.parent != root or name in result:
            _fail("release asset directory contains an aliased filename")
        metadata = item.stat()
        identity = (metadata.st_dev, metadata.st_ino)
        if identity in identities:
            _fail("release asset directory contains hard-linked aliases")
        identities.add(identity)
        size = metadata.st_size
        if size > _MAX_FILE:
            _fail("release asset exceeds its size limit")
        result[name] = item
    return result


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                total += len(block)
                if total > _MAX_FILE:
                    _fail("release asset exceeds its size limit")
                digest.update(block)
    except OSError as exc:
        _fail(f"cannot read release asset: {exc.strerror or type(exc).__name__}")
    return digest.hexdigest()


def _validate_umf_component(
    directory: Path,
    *,
    version: str,
    wheel: str,
    wheel_sha256: str,
    entry_sha256: str,
    aggregate: dict[str, object],
) -> None:
    proof_path = directory / _UMF_COMPONENT
    try:
        proof = _umf_receipt.strict_json_loads(proof_path.read_text(encoding="utf-8"))
        _umf_receipt.validate_public_projection(
            proof, version=version, wheel_name=wheel, wheel_sha256=wheel_sha256
        )
    except _umf_receipt.AdmissionReceiptError as exc:
        _fail(f"trusted UMF admission receipt is invalid: {exc}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"trusted UMF admission receipt is invalid: {type(exc).__name__}")
    binding = aggregate.get("umf_admission")
    if (
        not isinstance(binding, dict)
        or set(binding) != {"filename", "sha256", "qualification_phase", "status"}
        or binding
        != {
            "filename": _UMF_COMPONENT,
            "sha256": entry_sha256,
            "qualification_phase": "release-build",
            "status": "passed",
        }
        or hashlib.sha256(proof_path.read_bytes()).hexdigest() != entry_sha256
    ):
        _fail("trusted aggregate does not bind the exact UMF admission receipt")


def _validate_actions_component(
    directory: Path,
    *,
    version: str,
    wheel: str,
    wheel_sha256: str,
    entry_sha256: str,
    aggregate: dict[str, object],
) -> None:
    proof_path = directory / _UMF_ACTIONS_COMPONENT
    try:
        proof = _actions_receipt.strict_json_loads(proof_path.read_text(encoding="utf-8"))
        _actions_receipt.validate_public_projection(
            proof,
            version=version,
            wheel_name=wheel,
            wheel_sha256=wheel_sha256,
            phase="release-build",
            wheel_path=directory / wheel,
            repository=Path(__file__).resolve().parents[2],
        )
    except _actions_receipt.ActionReceiptError as exc:
        _fail(f"trusted UMF actions receipt is invalid: {exc}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"trusted UMF actions receipt is invalid: {type(exc).__name__}")
    binding = aggregate.get("umf_actions")
    if (
        not isinstance(binding, dict)
        or set(binding) != {"filename", "sha256", "qualification_phase", "status"}
        or binding
        != {
            "filename": _UMF_ACTIONS_COMPONENT,
            "sha256": entry_sha256,
            "qualification_phase": "release-build",
            "status": "passed",
        }
        or hashlib.sha256(proof_path.read_bytes()).hexdigest() != entry_sha256
    ):
        _fail("trusted aggregate does not bind the exact UMF actions receipt")


def _validate_components(
    aggregate: dict[str, object],
    entries: dict[str, str],
    *,
    version: str,
    actions_required: bool,
) -> None:
    expected = _PUBLISHED_COMPONENTS | (
        {_UMF_COMPONENT} if _umf_receipt.required_for_version(version) else set()
    )
    if actions_required:
        expected.add(_UMF_ACTIONS_COMPONENT)
    components = aggregate.get("published_components")
    if not isinstance(components, dict) or set(components) != expected:
        _fail("trusted release aggregate has an invalid published-component inventory")
    for name in sorted(expected):
        digest = components[name]
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest) or digest != entries[name]:
            _fail(f"trusted published-component digest differs from its emitted asset: {name}")


def _trusted_inventory(
    directory: Path, version: str, wheel: str, wheel_sha256: str
) -> tuple[bytes, dict[str, str], bool]:
    optional_names = {_UMF_COMPONENT, _UMF_ACTIONS_COMPONENT}
    inventory = _regular_inventory(
        directory, _expected_names(version, wheel) | optional_names | {"SHA256SUMS"}
    )
    if wheel not in inventory:
        _fail("trusted release wheel is missing")
    try:
        actions_required = _actions_receipt.required_for_wheel(
            inventory[wheel], wheel_sha256=wheel_sha256
        )
    except _actions_receipt.ActionReceiptError as exc:
        _fail(f"trusted release wheel action capability is invalid: {exc}")
    names = _expected_names(version, wheel, actions_required=actions_required)
    if set(inventory) != names | {"SHA256SUMS"}:
        _fail("trusted assembled release inventory is incomplete")
    sums_raw, entries = _read_sums(inventory["SHA256SUMS"])
    if set(entries) != names:
        _fail("trusted SHA256SUMS does not list the exact release inventory")
    if entries.get(wheel) != wheel_sha256:
        _fail("trusted SHA256SUMS differs from the verified build wheel digest")
    total = 0
    for name, expected in entries.items():
        path = inventory[name]
        total += path.stat().st_size
        if total > _MAX_TOTAL:
            _fail("release asset inventory exceeds its total size limit")
        if _digest(path) != expected:
            _fail(f"trusted release asset checksum failed: {name}")
    return sums_raw, entries, actions_required


def _read_trusted_aggregate(directory: Path) -> dict[str, object]:
    try:
        aggregate = _umf_receipt.strict_json_loads(
            (directory / "release-evidence.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        _fail(f"trusted release aggregate is invalid: {type(exc).__name__}")
    if not isinstance(aggregate, dict):
        _fail("trusted release aggregate is not an object")
    return aggregate


def _validate_release_artifacts(
    aggregate: dict[str, object],
    entries: dict[str, str],
    *,
    version: str,
    wheel: str,
    wheel_sha256: str,
) -> None:
    artifacts = aggregate.get("release_artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"wheel", "sdist", "npm"}:
        _fail("trusted release aggregate has an invalid release-artifact inventory")
    expected_artifacts = {
        "wheel": (wheel, wheel_sha256),
        "sdist": (f"arras-{version}.tar.gz", entries[f"arras-{version}.tar.gz"]),
        "npm": (
            f"documentdrivendx-arras-ui-{version}.tgz",
            entries[f"documentdrivendx-arras-ui-{version}.tgz"],
        ),
    }
    for artifact, (filename, digest) in expected_artifacts.items():
        identity = artifacts[artifact]
        if (
            not isinstance(identity, dict)
            or set(identity) != {"filename", "sha256"}
            or identity.get("filename") != filename
            or not isinstance(identity.get("sha256"), str)
            or not _DIGEST.fullmatch(identity["sha256"])
            or identity["sha256"] != digest
        ):
            _fail(f"trusted release aggregate differs from the verified {artifact} identity")


def _validate_optional_receipts(
    directory: Path,
    aggregate: dict[str, object],
    entries: dict[str, str],
    *,
    version: str,
    wheel: str,
    wheel_sha256: str,
    actions_required: bool,
) -> None:
    if _umf_receipt.required_for_version(version):
        _validate_umf_component(
            directory,
            version=version,
            wheel=wheel,
            wheel_sha256=wheel_sha256,
            entry_sha256=entries[_UMF_COMPONENT],
            aggregate=aggregate,
        )
    elif "umf_admission" in aggregate:
        _fail("legacy release aggregate has an unsupported UMF admission component")
    if actions_required:
        _validate_actions_component(
            directory,
            version=version,
            wheel=wheel,
            wheel_sha256=wheel_sha256,
            entry_sha256=entries[_UMF_ACTIONS_COMPONENT],
            aggregate=aggregate,
        )
    elif "umf_actions" in aggregate:
        _fail("release aggregate has an unsupported UMF actions component")


def _validate_trusted(
    directory: Path, version: str, wheel: str, wheel_sha256: str
) -> tuple[bytes, dict[str, str]]:
    sums_raw, entries, actions_required = _trusted_inventory(
        directory, version, wheel, wheel_sha256
    )
    aggregate = _read_trusted_aggregate(directory)
    expected_schema = (
        3 if actions_required else 2 if _umf_receipt.required_for_version(version) else 1
    )
    if (
        not isinstance(aggregate, dict)
        or type(aggregate.get("schema_version")) is not int
        or aggregate.get("schema_version") != expected_schema
        or aggregate.get("status") != "passed"
        or aggregate.get("version") != version
    ):
        _fail("trusted release aggregate has an unsupported schema, status or version")

    _validate_release_artifacts(
        aggregate, entries, version=version, wheel=wheel, wheel_sha256=wheel_sha256
    )
    _validate_components(aggregate, entries, version=version, actions_required=actions_required)
    _validate_optional_receipts(
        directory,
        aggregate,
        entries,
        version=version,
        wheel=wheel,
        wheel_sha256=wheel_sha256,
        actions_required=actions_required,
    )
    return sums_raw, entries


def _wheel_npm_bytes(wheel_path: Path, version: str) -> bytes:
    expected = f"arras/ui/npm/documentdrivendx-arras-ui-{version}.tgz"
    try:
        with zipfile.ZipFile(wheel_path) as archive:
            matches = [item for item in archive.infolist() if item.filename == expected]
            if len(matches) != 1 or matches[0].filename.endswith("/"):
                _fail("public wheel does not carry exactly one selected npm tarball")
            return archive.read(matches[0])
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        _fail(f"cannot inspect public wheel npm payload: {type(exc).__name__}")


def _safe_output(path: Path, *inputs: Path) -> Path:
    target = path.resolve()
    for source in inputs:
        resolved = source.resolve(strict=True)
        if target == resolved or resolved in target.parents:
            _fail("helper output must not overwrite or be inside an input directory")
    if path.exists() or path.is_symlink():
        _fail("helper output path must be new")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _require_distinct_asset_dirs(trusted: Path, public: Path) -> None:
    try:
        trusted_root = trusted.resolve(strict=True)
        public_root = public.resolve(strict=True)
    except OSError as exc:
        _fail(
            f"trusted and public release directories must exist: {exc.strerror or type(exc).__name__}"
        )
    if (
        trusted_root == public_root
        or trusted_root in public_root.parents
        or public_root in trusted_root.parents
    ):
        _fail("trusted and anonymous public release directories must be separate")


def run(args: argparse.Namespace) -> dict[str, object]:
    if not _VERSION.fullmatch(args.expected_version):
        _fail("expected version must be a stable numeric release")
    expected_wheel = f"arras-{args.expected_version}-py3-none-any.whl"
    if args.expected_wheel != expected_wheel:
        _fail("expected wheel filename does not match the release version")
    if not _DIGEST.fullmatch(args.expected_wheel_sha256):
        _fail("expected wheel digest is malformed")
    if not _DIGEST.fullmatch(args.expected_sums_sha256):
        _fail("expected SHA256SUMS digest is malformed")
    _require_distinct_asset_dirs(args.trusted_dir, args.public_dir)
    trusted_sums, trusted_entries = _validate_trusted(
        args.trusted_dir, args.expected_version, expected_wheel, args.expected_wheel_sha256
    )
    if hashlib.sha256(trusted_sums).hexdigest() != args.expected_sums_sha256:
        _fail("trusted SHA256SUMS differs from the assembler job output")
    output = _safe_output(args.output, args.trusted_dir, args.public_dir)
    expected_names = set(trusted_entries) | {"SHA256SUMS"}

    if args.phase == "plan":
        public_files = _regular_inventory(args.public_dir, {"SHA256SUMS"})
        if set(public_files) != {"SHA256SUMS"}:
            _fail("public download directory must contain only its downloaded SHA256SUMS")
        public_sums, public_entries = _read_sums(public_files["SHA256SUMS"])
        if public_sums != trusted_sums or public_entries != trusted_entries:
            _fail("public SHA256SUMS differs from the trusted assembled release")
        output.write_text(
            "".join(f"{name}\n" for name in sorted(trusted_entries)), encoding="ascii"
        )
        return {"status": "planned", "asset_count": len(trusted_entries)}

    if args.phase != "verify":
        _fail("unknown helper phase")
    public_files = _regular_inventory(args.public_dir, expected_names)
    if set(public_files) != expected_names:
        _fail("public downloaded release inventory is incomplete")
    public_sums, public_entries = _read_sums(public_files["SHA256SUMS"])
    if public_sums != trusted_sums or public_entries != trusted_entries:
        _fail("public SHA256SUMS differs from the trusted assembled release")
    total = 0
    for name, expected in trusted_entries.items():
        total += public_files[name].stat().st_size
        if total > _MAX_TOTAL:
            _fail("public release asset inventory exceeds its total size limit")
        if _digest(public_files[name]) != expected:
            _fail(f"public release asset differs from the trusted assembled asset: {name}")
    wheel_npm = _wheel_npm_bytes(public_files[expected_wheel], args.expected_version)
    npm_name = f"documentdrivendx-arras-ui-{args.expected_version}.tgz"
    if wheel_npm != public_files[npm_name].read_bytes():
        _fail("public npm tarball differs from the exact bytes carried by the public wheel")
    receipt = {
        "schema_version": 1,
        "status": "passed",
        "version": args.expected_version,
        "wheel": {"filename": expected_wheel, "sha256": args.expected_wheel_sha256},
        "sums_sha256": args.expected_sums_sha256,
        "asset_count": len(trusted_entries),
        "assets": [
            {"filename": name, "sha256": trusted_entries[name]} for name in sorted(trusted_entries)
        ],
        "npm_matches_wheel_payload": True,
    }
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("plan", "verify"))
    parser.add_argument("--trusted-dir", type=Path, required=True)
    parser.add_argument("--public-dir", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-wheel", required=True)
    parser.add_argument("--expected-wheel-sha256", required=True)
    parser.add_argument("--expected-sums-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except (AssetError, OSError) as exc:
        print(f"public release asset verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
