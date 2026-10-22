# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The Truss conformance harness (TR-03): its always-on checks, the stub run, and Truss-marked
self-tests that drive Truss directly over a built world.

The stub run and the self-tests (all Truss-marked, so the default run starts no database) need PostgreSQL 18.6 (`--extra truss --group truss-test`):
without them they skip with the reason, and fail instead when ARRAS_REQUIRE_TRUSS=1 (the `truss`
CI job sets it, so a broken environment cannot pass by skipping).
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import truss_harness
from arras.conformance import Report, load_corpus, run_corpus, tags
from arras.umf import parse_module
from truss_harness import Cluster, TrussHarness, available, foreign_token

ROOT = Path(__file__).resolve().parent.parent


def _require() -> None:
    reason = available()
    if reason is None:
        return
    if os.environ.get("ARRAS_REQUIRE_TRUSS") == "1":
        pytest.fail(f"ARRAS_REQUIRE_TRUSS=1 and the Truss harness cannot run: {reason}")
    pytest.skip(reason)


@pytest.fixture(scope="module")
def cluster() -> Iterator[Cluster]:
    _require()
    c = Cluster()
    try:
        yield c
    finally:
        c.close()


@pytest.fixture(scope="module")
def stub_report(cluster: Cluster) -> Report:
    return run_corpus(lambda: TrussHarness(cluster, build=TrussHarness.unbuilt))


# -- always on: no PostgreSQL, no Truss


def test_the_harness_claims_the_current_corpus() -> None:
    assert TrussHarness.corpus_version == load_corpus()["version"] == 13
    assert TrussHarness.roles == ("reader", "provider")


def test_importing_the_harness_loads_neither_psycopg_nor_truss() -> None:
    code = (
        f"import sys; sys.path.insert(0, {str(ROOT / 'tests')!r}); import truss_harness; "
        "print(sorted(m for m in ('psycopg', 'truss', 'pgserver') if m in sys.modules))"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"


def test_a_foreign_token_has_the_released_shape_and_a_new_installation_each_time() -> None:
    def decoded(token: str) -> dict[str, Any]:
        return json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))

    a, b = decoded(foreign_token()), decoded(foreign_token())
    assert a["interfaceVersion"] == "truss-receipt-position/0.1.0"
    assert a["positionProfile"]["identity"] == "truss-authority-receipt-visibility"
    assert a["installationId"] != b["installationId"]


def test_the_harness_says_why_it_cannot_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(truss_harness.importlib.util, "find_spec", lambda name: None)
    assert "pgserver" in (available() or "")
    monkeypatch.setattr(truss_harness.importlib.util, "find_spec", lambda name: object())
    assert available() is None  # no `bun`, no other tool: Truss prepares a module in process


class _NoWorld:
    """A cluster that cannot build a world: every fixture fails, as with no PostgreSQL."""

    def begin_world(self, module: Any, document: bytes) -> Any:
        raise OSError("no PostgreSQL here")


def test_a_harness_that_cannot_build_its_world_passes_no_case() -> None:
    report = run_corpus(lambda: TrussHarness(_NoWorld()))  # type: ignore[arg-type]
    assert report.results
    assert not report.passed
    assert {r.status for r in report.results} == {"harness_error"}


# -- the stub: PostgreSQL 18.6 required


def _assert_the_stub_fails_every_case(report: Report) -> None:
    corpus = load_corpus()
    wanted = [c["id"] for c in corpus["cases"] if tags(TrussHarness.roles) & set(c["tags"])]
    assert [r.case for r in report.results] == wanted  # the reader-only cases skip
    assert not report.newer_corpus
    assert not any(r.ok for r in report.results)  # `ok` is true for host_specific as well
    # each case failed in the stub, not in the harness
    assert [r for r in report.results if "not built yet" not in r.message] == []
    assert not report.passed


@pytest.mark.truss
def test_the_stub_fails_every_corpus_case_under_the_truss_marker(stub_report: Report) -> None:
    _assert_the_stub_fails_every_case(stub_report)


# -- Truss-marked self-tests: Truss directly, no adapter

MODULE_TEXT = load_corpus()["_module_text"]


def _world(cluster: Cluster, fixture: str = "empty") -> Any:
    h = TrussHarness(cluster)
    h.install(parse_module(MODULE_TEXT), MODULE_TEXT.encode())
    for step in load_corpus()["fixtures"][fixture][1:]:
        if step["op"] == "grant":
            h.grant(step["user"], step["modules"], step.get("admin", False))
        elif step["op"] == "seed":
            h.seed(step["as"], step["records"])
    return h


def _read(h: Any, user: str, work: Any) -> Any:
    from truss_harness import transaction

    with h.world.connection_source(h.principal(user)) as conn:
        with transaction(conn, read_only=True) as (assembly, handle):
            return work(assembly, handle)


@pytest.mark.truss
def test_each_person_connects_as_themselves_with_no_role(cluster: Cluster) -> None:
    h = _world(cluster)
    for user in ("alice", "carol", "bob", "dave"):
        with h.world.connection_source(h.principal(user)) as conn:
            row = conn.execute("select session_user, current_setting('role')").fetchone()
            assert row == (user, "none")
            assert conn.execute("show statement_timeout").fetchone() == ("0",)


@pytest.mark.truss
def test_a_member_reads_the_catalog_and_a_non_member_is_refused(cluster: Cluster) -> None:
    h = _world(cluster)
    catalog = truss_harness.ok(_read(h, "carol", lambda a, t: a.reader_catalog_in_transaction(t)))
    assert [m["moduleId"] for m in catalog.modules] == ["catalog"]
    refused = _read(h, "dave", lambda a, t: a.reader_catalog_in_transaction(t))
    assert type(refused.value).__name__ == "CatalogRefused"


@pytest.mark.truss
def test_another_persons_token_and_an_expired_role_both_fail_at_connect(cluster: Cluster) -> None:
    import psycopg

    h = _world(cluster)
    with pytest.raises(psycopg.OperationalError, match="password authentication failed"):
        with h.world.connection_source(h.borrowed("dave", "alice")):
            pass
    h.expire("bob")
    with pytest.raises(psycopg.OperationalError, match="password authentication failed"):
        with h.world.connection_source(h.principal("bob")):
            pass


@pytest.mark.truss
def test_unreachable_and_access_denied_are_real_connect_failures(cluster: Cluster) -> None:
    import psycopg

    h = _world(cluster)
    h.outage("unreachable")
    with pytest.raises(psycopg.OperationalError, match="No such file or directory"):
        with h.world.connection_source(h.principal("carol")):
            pass
    h.outage("access_denied")
    for connect in (
        lambda: h.world.connection_source(h.principal("carol")),
        h.world.installing_connection,
    ):
        with pytest.raises(psycopg.OperationalError, match="permission denied for database"):
            with connect():
                pass
    h.outage(None)
    with h.world.connection_source(h.principal("carol")) as conn:
        assert conn.execute("select 1").fetchone() == (1,)


@pytest.mark.truss
def test_unsupported_version_makes_the_install_status_an_error_until_cleared(
    cluster: Cluster,
) -> None:
    from truss import Error, Ok

    h = _world(cluster)

    def status() -> Any:
        with h.world.installing_connection() as conn:
            with truss_harness.transaction(conn, read_only=True) as (a, t):
                return a.status_in_transaction(t)

    assert isinstance(status(), Ok) and status().value.installed
    h.outage("unsupported_version")
    refused = status()
    assert isinstance(refused, Error) and refused.error.catalog_code == "unsupported_profile"
    h.outage(None)
    assert status().value.installed


@pytest.mark.truss
def test_a_fixture_seeds_through_truss_as_the_person(cluster: Cluster) -> None:
    h = _world(cluster, "basic")
    rows = _read(
        h,
        "carol",
        lambda a, t: (
            a.compiled_execution(a.compiled_selection)
            .capability.query_in_transaction(
                t, sql="SELECT u.code FROM UseCase u", document_ids=("sandbox",), parameters={}
            )
            .value.rows
        ),
    )
    assert sorted(r[0] for r in rows) == ["uc-1", "uc-2"]


@pytest.mark.truss
def test_a_foreign_token_is_unavailable_not_invalid_on_truss(cluster: Cluster) -> None:
    h = _world(cluster)
    seen = _read(h, "carol", lambda a, t: a.reached_in_transaction(t, h.foreign_token()))
    # CONTRACT-004: Unavailable (tests/test_truss_reached.py)
    assert seen.value.reason == "epoch_profile"


@pytest.mark.truss
def test_the_next_world_leaves_nothing_of_the_last(cluster: Cluster) -> None:
    h = _world(cluster)
    first = h.world.db
    h2 = _world(cluster)
    su = cluster.su
    dbs = {r[0] for r in su.execute("select datname from pg_database").fetchall()}
    assert first not in dbs and h2.world.db in dbs
    users = {r[0] for r in su.execute("select rolname from pg_roles").fetchall()}
    assert {"alice", "carol", "bob", "dave"} <= users  # the new world's own, created once
    cluster.end_world()
    users = {r[0] for r in su.execute("select rolname from pg_roles").fetchall()}
    assert not users & {"alice", "carol", "bob", "dave"}
