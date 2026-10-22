# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The Truss adapter against the whole conformance corpus (TR-12, CONTRACT-004).

One run of every `store` and `reader` case on the Truss harness, held to the adapter's declared
capabilities: each case passes, or ends at the step and in the refusal of a documented Truss limit
(`TrussHarness.LIMITS`, each carrying its truss-requirements ask on the corpus case). The run takes
about ten minutes; it is Truss-marked, so the default run starts no database.
"""

from __future__ import annotations

from typing import Any

import pytest

from arras.conformance import Report, load_corpus, run_corpus, tags
from test_truss_harness import cluster  # noqa: F401
from truss_harness import TrussHarness


@pytest.fixture(scope="module")
def report(cluster: Any) -> Report:  # noqa: F811
    return run_corpus(lambda: TrussHarness(cluster))


def _cases() -> dict[str, Any]:
    return {c["id"]: c for c in load_corpus()["cases"]}


# -- always on


def test_every_limit_names_a_case_for_the_roles_and_records_its_ask_on_the_case() -> None:
    cases = _cases()
    for case, limit in TrussHarness.LIMITS.items():
        assert case in cases, case
        assert tags(TrussHarness.roles) & set(cases[case]["tags"]), case
        assert limit.step.startswith("step "), (case, limit)
        assert limit.error in ("Invalid", "Unsupported", "Conflict", "PreconditionFailed"), (
            case,
            limit,
        )
        notes = cases[case].get("limits", [])
        assert any(
            f"truss-requirements {ask}" in n for n in notes for ask in ("R16", "R17", "R18.3")
        ), f"{case} records no Truss ask"


def test_a_stand_in_backend_is_held_to_no_limit() -> None:
    assert TrussHarness(None, build=TrussHarness.unbuilt).limits == {}  # type: ignore[arg-type]
    assert TrussHarness(None).limits == TrussHarness.LIMITS  # type: ignore[arg-type]


# -- against a real Truss


@pytest.mark.truss
def test_the_full_corpus_passes_at_the_declared_capabilities(report: Report) -> None:
    assert report.passed, [(r.case, r.message) for r in report.failed]
    assert not report.newer_corpus
    wanted = [c["id"] for c in load_corpus()["cases"] if tags(TrussHarness.roles) & set(c["tags"])]
    assert [r.case for r in report.results] == wanted
    # every case that did not run is the reader-only kind a provider has no part in
    skipped = {c["id"] for c in load_corpus()["cases"]} - set(wanted)
    assert set(report.skipped) == skipped
    assert all("reader-only" in _cases()[c]["tags"] for c in skipped)


@pytest.mark.truss
def test_the_cases_that_do_not_pass_are_the_documented_limits_each_at_its_step_and_refusal(
    report: Report,
) -> None:
    ended = {r.case: r for r in report.results if r.status != "passed"}
    assert set(ended) == set(TrussHarness.LIMITS)
    for case, limit in TrussHarness.LIMITS.items():
        got = ended[case]
        assert got.status == "limit", got
        assert got.message.startswith(limit.step), got
        # the refusal it ends in: the class and the detail, not only the step
        assert f"{limit.step}: {limit.error}({limit.detail})" in got.message, got
