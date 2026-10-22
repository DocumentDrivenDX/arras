# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest

import arras.conformance.__main__ as cli
from arras.conformance import Report, Result


def test_memory_store_command_emits_each_category_and_nonempty_results() -> None:
    payload, status = cli.run("memory-store")
    assert status == 0
    assert payload["roles"] == ["reader", "provider"]
    assert payload["corpus_version"] >= 1
    assert payload["counts"]["passed"] > 0
    assert payload["results"]
    assert isinstance(payload["skipped"], list)


@pytest.mark.parametrize(
    ("report", "expected_status"),
    [
        (Report(results=[]), 1),
        (Report(newer_corpus=True, results=[Result("x", "passed")]), 1),
        (Report(results=[Result("x", "failed")]), 1),
        (Report(results=[Result("x", "harness_error")]), 1),
        (Report(results=[Result("x", "limit")]), 0),
        (Report(results=[Result("x", "host_specific")]), 0),
    ],
)
def test_exit_code_requires_a_nonempty_complete_applicable_report(
    monkeypatch: pytest.MonkeyPatch, report: Report, expected_status: int
) -> None:
    monkeypatch.setattr(cli, "run_corpus", lambda factory: report)
    payload, status = cli.run("memory-store")
    assert status == expected_status
    assert payload["newer_corpus"] is report.newer_corpus


def test_fixed_cli_prints_json_and_uses_only_named_backend_choices() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "arras.conformance", "--backend", "memory-replica"],
        check=False,
        capture_output=True,
        text=True,
    )
    payload: dict[str, Any] = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["backend"] == "memory-replica"
    assert payload["roles"] == ["reader"]
    assert payload["counts"]["passed"] > 0

    refused = subprocess.run(
        [sys.executable, "-m", "arras.conformance", "--backend", "arbitrary.module:factory"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert refused.returncode != 0
    assert "invalid choice" in refused.stderr


def test_newer_corpus_is_reported_and_not_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    report = Report(roles=("reader",), corpus_version=99, newer_corpus=True)
    monkeypatch.setattr(cli, "run_corpus", lambda factory: report)
    payload, status = cli.run("memory-replica")
    assert status == 1
    assert payload["newer_corpus"] is True
    assert payload["counts"]["passed"] == 0
