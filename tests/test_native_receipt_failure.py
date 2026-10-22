# SPDX-License-Identifier: MIT OR Apache-2.0
"""The release fallback always retains a structured failure, without erasing verifier detail."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).parents[1] / ".github/scripts/ensure_native_receipt_failure.py"
_SPEC = importlib.util.spec_from_file_location("ensure_native_receipt_failure", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
receipt_fallback = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(receipt_fallback)


@pytest.mark.parametrize(
    "initial",
    [
        None,
        "{not json",
        "[]",
        '{"schema_version":1,"status":"not_started"}',
        '{"schema_version":1,"status":"pending"}',
        '{"schema_version":1}',
        '{"schema_version":1,"status":"passed","error":"unexpected success receipt"}',
    ],
)
def test_unusable_or_pending_receipts_become_structured_failures(
    tmp_path: Path, initial: str | None
) -> None:
    path = tmp_path / "native.json"
    if initial is not None:
        path.write_text(initial, encoding="utf-8")
    result = receipt_fallback.ensure_failure(path, 23)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert result == saved
    assert saved["schema_version"] == 1
    assert saved["status"] == "failed"
    assert saved["exit_code"] == 23
    assert "stdout/stderr" in saved["error"]


def test_valid_failure_receipt_and_quarantine_diagnostics_are_preserved(
    tmp_path: Path,
) -> None:
    path = tmp_path / "native.json"
    original: dict[str, Any] = {
        "schema_version": 1,
        "status": "failed",
        "error": "native conformance failed",
        "inputs": {"cohort": {"sha256": "abc"}},
        "runtime": {"python": "3.11"},
        "cli": {"exit_code": 1, "stderr": "native failure"},
        "cleanup": {"private_temp_root": "/tmp/arras-native-owned"},
    }
    original_bytes = (json.dumps(original) + "\n").encode()
    path.write_bytes(original_bytes)
    result = receipt_fallback.ensure_failure(path, 23)
    assert result == original
    assert path.read_bytes() == original_bytes


def test_nonzero_exit_is_required_and_symlink_receipt_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "native.json"
    with pytest.raises(ValueError, match="positive integer"):
        receipt_fallback.ensure_failure(path, 0)
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        receipt_fallback.ensure_failure(link, 1)
