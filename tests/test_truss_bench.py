# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The latency harness (`tests/bench_latency.py`, US-044) runs small on a throwaway local PostgreSQL:
it seeds the three samples, runs every operation a few times and prints the table, and `--enforce`
turns a missed target into a non-zero exit. Truss-marked and so skipped by a default `pytest`; the
targets themselves are not asserted here (a loaded machine would make that flaky), only that the
harness runs and judges.
"""

from __future__ import annotations

import pytest

import bench_latency
from test_truss_harness import _require

pytestmark = pytest.mark.truss

SMALL = ["--throwaway", "--runs", "3", "--warmup", "1", "--no-cold"]


def test_the_harness_runs_every_acceptance_criterion_and_prints_the_table(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _require()
    assert bench_latency.main(SMALL) == 0
    out = capsys.readouterr().out
    for label in ("AC1", "AC2", "AC3", "AC4"):
        assert label in out
    assert "[in-process warm]" in out and "p95" in out


def test_enforce_exits_non_zero_when_a_target_is_missed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _require()
    monkeypatch.setitem(bench_latency.TARGETS, "AC1", 0.000001)
    assert bench_latency.main([*SMALL, "--enforce"]) == 1
    assert "MISSED" in capsys.readouterr().out
