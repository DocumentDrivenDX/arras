#!/usr/bin/env python3
"""Validate the immutable Arras 0.6.5 local-origin registry backfill inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

EXPECTED_TAG = "v0.6.5"
EXPECTED_VERSION = "0.6.5"
EXPECTED_SOURCE = "ad597d248847da47523155842524bb451a97f8d8"
EXPECTED_TAG_OBJECT = "85beae38114650caa7ff25d9dde090e20071c4e4"
EXPECTED_SUMS_SHA256 = "dbe547fe5f05386759f6fed80fc85991b676e8ca6eeb67788b2b84dbba1919f8"
ASSETS = {
    "arras-0.6.5-py3-none-any.whl": "beed68b94567699313a44c5f8865ecfb6e1f34842d7c5ba5055ac866a664a98b",
    "arras-0.6.5.tar.gz": "838105bd625bfd611c00fc80597a22b0419b3d40e1a92134fb3f83fa2e814e51",
    "documentdrivendx-arras-ui-0.6.5.tgz": "26abe759e7bb918bf30c5144a34cff8deb7ecb4dd2ef531d41ec3ceab2155e0f",
    "installed-checks-public.json": "0fb06c9dffa527ae50d3c8ad99dff54059d084fef52e3f7311b9e8e1dabb0b90",
    "local-release-proof.json": "a2789f61dccc3be75c63ed5adb1435d7a8365d8941d3496eb47448e1dfbea238",
    "metadata-correspondence.json": "e1c7f9cfdaa58613b21b82419117da373cfa8d9d6386aed8fb948927e2218c81",
    "qualification-inputs-ebeb.tar.gz": "6d9d0ce52b9338efcac2eb6bce1aff692e038a526d09942f42cc7306aee19ccc",
}
SHA = re.compile(r"[0-9a-f]{64}\Z")


def validate(
    asset_dir: Path,
    expected_tag: str,
    expected_source: str,
    expected_tag_object: str,
    *,
    asset_pins: dict[str, str] = ASSETS,
    sums_sha256: str = EXPECTED_SUMS_SHA256,
) -> dict[str, Any]:
    if (expected_tag, expected_source, expected_tag_object) != (
        EXPECTED_TAG,
        EXPECTED_SOURCE,
        EXPECTED_TAG_OBJECT,
    ):
        raise ValueError("requested identity is not the pinned local 0.6.5 release")
    sums_path = asset_dir / "SHA256SUMS"
    if sums_path.is_symlink() or not sums_path.is_file():
        raise ValueError("SHA256SUMS is missing or not a regular file")
    if hashlib.sha256(sums_path.read_bytes()).hexdigest() != sums_sha256:
        raise ValueError("SHA256SUMS bytes differ from the pinned local release")
    rows: dict[str, str] = {}
    for line in sums_path.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)", line)
        if match is None or match.group(2) in rows:
            raise ValueError("SHA256SUMS is malformed or contains duplicate names")
        rows[match.group(2)] = match.group(1)
    if rows != asset_pins:
        raise ValueError("SHA256SUMS does not match the pinned seven payloads")
    if {p.name for p in asset_dir.iterdir()} != set(asset_pins) | {"SHA256SUMS"}:
        raise ValueError("asset directory does not contain exactly the pinned eight assets")
    for name, digest in asset_pins.items():
        path = asset_dir / name
        if (
            path.is_symlink()
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise ValueError(f"asset bytes differ from pinned release: {name}")
    proof = json.loads((asset_dir / "local-release-proof.json").read_text(encoding="utf-8"))
    if (
        proof.get("schema") != "arras.local-release-proof.v1"
        or proof.get("status") != "qualified-before-publication"
    ):
        raise ValueError("local proof schema or status is invalid")
    if (
        proof.get("tag"),
        proof.get("version"),
        proof.get("tagObjectSha"),
        proof.get("releaseSourceCommit"),
    ) != (EXPECTED_TAG, EXPECTED_VERSION, EXPECTED_TAG_OBJECT, EXPECTED_SOURCE):
        raise ValueError("local proof identity does not match the pinned release")
    if proof.get("transport") != "local; no Actions publication run":
        raise ValueError("local proof transport is not explicitly local")
    return {
        "schema": "arras.local-registry-origin.v1",
        "origin": "local-release-proof",
        "tag": EXPECTED_TAG,
        "version": EXPECTED_VERSION,
        "source_sha": EXPECTED_SOURCE,
        "tag_object_sha": EXPECTED_TAG_OBJECT,
        "sums_sha256": hashlib.sha256(sums_path.read_bytes()).hexdigest(),
        "wheel": "arras-0.6.5-py3-none-any.whl",
        "wheel_sha256": asset_pins["arras-0.6.5-py3-none-any.whl"],
        "npm_tarball": "documentdrivendx-arras-ui-0.6.5.tgz",
        "npm_sha256": asset_pins["documentdrivendx-arras-ui-0.6.5.tgz"],
        "local_proof_sha256": asset_pins["local-release-proof.json"],
        "assets": dict(asset_pins),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--tag-object", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate(args.assets, args.tag, args.source, args.tag_object)
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"local registry origin validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
