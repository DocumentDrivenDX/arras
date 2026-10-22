# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
from typing import Any, cast

import arras.conformance as conformance
from arras.conformance import run_corpus
from arras.errors import Invalid
from arras.types import Principal

_MODULE_TEXT = conformance.load_corpus()["_module_text"]


def corpus(
    *,
    setup: list[dict[str, Any]] | None = None,
    steps: list[dict[str, Any]] | None = None,
    version: int = 13,
) -> dict[str, Any]:
    return {
        "version": version,
        "_module_text": _MODULE_TEXT,
        "fixtures": {"empty": setup or []},
        "cases": [
            {
                "id": "lifecycle.empty",
                "tags": ["store"],
                "fixture": "empty",
                "steps": steps or [],
            }
        ],
    }


class _Harness:
    roles = ("reader", "provider")
    corpus_version = 13

    def __init__(
        self,
        closed: list[str],
        name: str,
        *,
        fail_setup: bool = False,
        fail_close: bool = False,
        fail_foreign: bool = False,
    ):
        self.closed = closed
        self.name = name
        self.fail_setup = fail_setup
        self.fail_close = fail_close
        self.fail_foreign = fail_foreign

    def close(self) -> None:
        self.closed.append(self.name)
        if self.fail_close:
            raise RuntimeError("synthetic cleanup detail")

    def foreign_token(self) -> str:
        if self.fail_foreign:
            raise RuntimeError("sensitive synthetic provisioning detail")
        return "foreign"

    def grant(self, *_: Any, **__: Any) -> None:
        if self.fail_setup:
            raise RuntimeError("synthetic setup detail")

    def principal(self, _: str) -> Principal:
        return Principal("test", "token")

    @staticmethod
    def backend() -> Any:
        class Backend:
            @staticmethod
            def reached(*_: Any) -> None:
                raise Invalid([])

        return Backend()


def test_runner_closes_probe_and_case_once_and_reports_cleanup_failure(monkeypatch: Any) -> None:
    monkeypatch.setattr(conformance, "load_corpus", lambda: corpus())
    closed: list[str] = []
    made = 0

    def factory() -> _Harness:
        nonlocal made
        made += 1
        return _Harness(closed, "probe" if made == 1 else "case", fail_close=made == 2)

    report = run_corpus(cast(Any, factory))
    assert closed == ["probe", "case"]
    assert report.results[0].status == "passed"
    assert [(r.case, r.status) for r in report.results[1:]] == [
        ("lifecycle.empty.cleanup", "harness_error")
    ]
    assert "RuntimeError" in report.results[1].message
    assert "synthetic cleanup detail" not in report.results[1].message
    assert not report.passed


def test_newer_corpus_closes_only_the_probe(monkeypatch: Any) -> None:
    monkeypatch.setattr(conformance, "load_corpus", lambda: corpus(version=14))
    closed: list[str] = []
    report = run_corpus(cast(Any, lambda: _Harness(closed, "probe")))
    assert report.newer_corpus
    assert closed == ["probe"]
    assert report.results == []


def test_probe_metadata_is_snapshotted_before_close(monkeypatch: Any) -> None:
    monkeypatch.setattr(conformance, "load_corpus", lambda: corpus())

    class MutatesMetadata(_Harness):
        limits = {"lifecycle.empty": conformance.Limit("step 0 (query)", "Invalid")}

        def close(self) -> None:
            super().close()
            self.roles = ()
            self.limits.clear()

    made = 0

    def factory() -> MutatesMetadata:
        nonlocal made
        made += 1
        return MutatesMetadata([], f"resource-{made}")

    report = run_corpus(cast(Any, factory))
    assert report.roles == ("reader", "provider")
    assert len(report.results) == 1 and report.results[0].status == "failed"
    assert "is gone" in report.results[0].message


def test_setup_and_cleanup_failures_both_remain_visible(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        conformance,
        "load_corpus",
        lambda: corpus(setup=[{"op": "grant", "user": "x", "modules": {}}]),
    )
    closed: list[str] = []
    made = 0

    def factory() -> _Harness:
        nonlocal made
        made += 1
        return _Harness(
            closed,
            "probe" if made == 1 else "case",
            fail_setup=made == 2,
            fail_close=made == 2,
        )

    report = run_corpus(cast(Any, factory))
    assert closed == ["probe", "case"]
    original = next(r for r in report.results if r.case == "lifecycle.empty")
    cleanup = next(r for r in report.results if r.case == "lifecycle.empty.cleanup")
    assert original.status == "harness_error" and "RuntimeError" in original.message
    assert cleanup.status == "harness_error"


def test_foreign_token_setup_failure_is_reported_and_closed(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        conformance,
        "load_corpus",
        lambda: corpus(
            steps=[
                {
                    "op": "reached",
                    "as": "test",
                    "token": "$foreign",
                    "expect": {"error": "Invalid"},
                }
            ]
        ),
    )
    closed: list[str] = []
    made = 0

    def factory() -> _Harness:
        nonlocal made
        made += 1
        return _Harness(closed, "probe" if made == 1 else "case", fail_foreign=made == 2)

    report = run_corpus(cast(Any, factory))
    assert closed == ["probe", "case"]
    [failure] = report.results
    assert failure.status == "harness_error"
    assert "RuntimeError" in failure.message
    assert "sensitive" not in failure.message


def test_legacy_harness_without_close_remains_supported(monkeypatch: Any) -> None:
    monkeypatch.setattr(conformance, "load_corpus", lambda: corpus())

    class Legacy:
        roles = ("reader", "provider")
        corpus_version = 13

        def foreign_token(self) -> str:
            return "foreign"

    report = run_corpus(cast(Any, Legacy))
    assert report.passed
