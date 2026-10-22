#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Ensure a failed native verifier command leaves a valid structured failure receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def ensure_failure(path: Path, exit_code: int) -> dict[str, Any]:
    """Preserve a valid failed verifier receipt; repair absent or unusable receipts."""
    if type(exit_code) is not int or exit_code <= 0:
        raise ValueError("failure exit code must be a positive integer")
    if path.is_symlink():
        raise ValueError("failure receipt path must not be a symlink")
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        value = None
    if (
        isinstance(value, dict)
        and type(value.get("schema_version")) is int
        and value["schema_version"] == 1
        and value.get("status") == "failed"
        and isinstance(value.get("error"), str)
        and bool(value["error"].strip())
    ):
        return value
    receipt = dict(value) if isinstance(value, dict) else {"schema_version": 1}
    receipt.update(
        {
            "schema_version": 1,
            "status": "failed",
            "exit_code": exit_code,
            "error": "verifier did not leave a valid failure receipt; see retained stdout/stderr",
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--exit-code", required=True, type=int)
    args = parser.parse_args(argv)
    ensure_failure(args.receipt, args.exit_code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
