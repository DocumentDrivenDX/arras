#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bind only a verified Arras wheel identity into the reviewed native cohort template."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, NoReturn, cast

_TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(_TOOLS))
try:
    import verify_native as _native
finally:
    sys.path.pop(0)

_TEMPLATE_KEYS = {"schema_version", "runtime", "find_links", "native_wheels", "corpus"}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class BindingError(ValueError):
    """The selected template, index or wheel cannot be safely bound."""


def _fail(message: str) -> NoReturn:
    raise BindingError(message)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _input_file(path: Path, label: str) -> Path:
    try:
        selected = path.resolve(strict=True)
    except OSError:
        _fail(f"{label} is missing")
    if not selected.is_file() or path.is_symlink():
        _fail(f"{label} must be a regular non-symlink file")
    return selected


def _unique_paths(paths: tuple[Path, ...], output: Path) -> None:
    resolved_inputs = [path.resolve() for path in paths]
    if len(set(resolved_inputs)) != len(resolved_inputs):
        _fail("selected template, find-links page and wheel must be distinct files")
    if output.resolve() in resolved_inputs:
        _fail("output must not alias a selected input")


def _canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _load_template(path: Path) -> dict[str, Any]:
    try:
        raw_template = _native._load_json_unique(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _fail(f"cannot load unique-key native template: {exc}")
    if not isinstance(raw_template, dict) or set(raw_template) != _TEMPLATE_KEYS:
        _fail("native template must contain exactly the five reviewed fields and omit arras")
    return cast(dict[str, Any], raw_template)


def _validated_bound_cohort(
    cohort: dict[str, Any],
    wheel: Path,
    links: Path,
    expected_version: str,
    expected_sha256: str,
) -> tuple[dict[str, Any], str, str]:
    try:
        actual_name, actual_version, _ = _native.wheel_metadata(wheel)
    except Exception as exc:
        _fail(f"cannot inspect selected wheel metadata: {exc}")
    if _canonical_name(actual_name) != "arras":
        _fail("selected wheel METADATA name must identify arras")
    if actual_version != expected_version:
        _fail("selected wheel METADATA version differs from the checked tag version")
    actual_sha256 = _sha(wheel)
    if actual_sha256 != expected_sha256:
        _fail("selected wheel bytes differ from the verified build digest")
    cohort["arras"] = {"version": actual_version, "sha256": actual_sha256}
    try:
        validated = _native.validate_cohort(cohort)
        links_sha = cast(dict[str, Any], validated["find_links"])["sha256"]
        native_wheels = cast(list[dict[str, Any]], validated["native_wheels"])
        _native.verify_find_links(links, links_sha, native_wheels)
    except Exception as exc:
        _fail(f"bound cohort or companion index failed strict validation: {exc}")
    return validated, actual_name, actual_version


def _write_outputs(
    output_path: Path,
    receipt_path: Path,
    template: Path,
    links: Path,
    wheel: Path,
    bound: dict[str, Any],
    actual_name: str,
    actual_version: str,
    actual_sha256: str,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    bound_bytes = (json.dumps(bound, indent=2, sort_keys=True) + "\n").encode()
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "status": "bound",
        "template": {"path": str(template), "sha256": _sha(template)},
        "find_links": {"path": str(links), "sha256": _sha(links)},
        "wheel": {
            "path": str(wheel),
            "name": actual_name,
            "version": actual_version,
            "sha256": actual_sha256,
        },
        "bound_manifest": {
            "path": str(output_path.resolve()),
            "sha256": hashlib.sha256(bound_bytes).hexdigest(),
        },
    }
    try:
        with output_path.open("xb") as stream:
            stream.write(bound_bytes)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        output_path.unlink(missing_ok=True)
        _fail(f"cannot write binding outputs: {exc}")
    return receipt


def bind(
    template_path: Path,
    find_links_path: Path,
    wheel_path: Path,
    *,
    expected_version: str,
    expected_sha256: str,
    output_path: Path,
    receipt_path: Path,
) -> dict[str, Any]:
    """Validate all inputs, preserve the reviewed template, and bind actual wheel identity."""
    template = _input_file(template_path, "native cohort template")
    links = _input_file(find_links_path, "native find-links index")
    wheel = _input_file(wheel_path, "verified Arras wheel")
    _unique_paths((template, links, wheel), output_path)
    _unique_paths((template, links, wheel), receipt_path)
    if output_path.resolve() == receipt_path.resolve():
        _fail("bound manifest and binding receipt must be distinct files")
    if output_path.exists() or receipt_path.exists():
        _fail("binding outputs already exist")
    if not isinstance(expected_version, str) or not expected_version:
        _fail("expected version must be nonempty text")
    if not isinstance(expected_sha256, str) or _SHA256.fullmatch(expected_sha256) is None:
        _fail("expected wheel SHA-256 must be lowercase hexadecimal")
    cohort = _load_template(template)
    bound, actual_name, actual_version = _validated_bound_cohort(
        cohort, wheel, links, expected_version, expected_sha256
    )
    return _write_outputs(
        output_path,
        receipt_path,
        template,
        links,
        wheel,
        bound,
        actual_name,
        actual_version,
        expected_sha256,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--find-links", required=True, type=Path)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--receipt-json", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = bind(
            args.template,
            args.find_links,
            args.wheel,
            expected_version=args.expected_version,
            expected_sha256=args.expected_sha256,
            output_path=args.output_json,
            receipt_path=args.receipt_json,
        )
    except Exception as exc:
        failure = {"schema_version": 1, "status": "failed", "error": str(exc)}
        args.receipt_json.parent.mkdir(parents=True, exist_ok=True)
        if not args.receipt_json.exists() and args.receipt_json.resolve() not in {
            args.template.resolve(),
            args.find_links.resolve(),
            args.wheel.resolve(),
            args.output_json.resolve(),
        }:
            args.receipt_json.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps({"status": receipt["status"], "receipt": str(args.receipt_json)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
