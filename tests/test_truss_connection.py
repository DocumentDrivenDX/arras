# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The Truss adapter's connection layer (TR-04): per-person calls over a host-supplied source.

The unit tests are always on: a recording connection and a fake Truss host through the layer's
`Toolkit` seam (Truss adopts only a real `psycopg.Connection`). The Truss-marked tests run a real call
against PostgreSQL 18.6 (`uv run --extra truss --group truss-test pytest -m truss`).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from arras.adapters.truss import CommitUnknown, Connections, classify_connect_error
from arras.adapters.truss import connection as connection_module
from arras.adapters.truss.connection import Toolkit, _is_operational, failure_error
from arras.errors import Refused, Unavailable
from arras.types import Principal

# the fixture and the helper of the harness self-tests: one real PostgreSQL per module
from test_truss_harness import _world, cluster  # noqa: F401

CAROL = Principal("carol", "carol-token")


class FakeConn:
    def __init__(self, *, role: str = "none", autocommit: bool = False, status: int = 0) -> None:
        self.log: list[str] = []
        self.role = role
        self.autocommit = autocommit
        self.info = SimpleNamespace(transaction_status=status)
        self.closed = False
        self.broken = False
        self.commit_raises: Exception | None = None
        # the transaction status a refused COMMIT leaves: a real server ends the transaction (0,
        # idle) before ReadyForQuery; None means idle
        self.commit_leaves_status: int | None = None
        self.commit_breaks = False
        self.immediate_raises: Exception | None = None
        self.mode_raises: Exception | None = None

    def execute(self, sql: str) -> Any:
        self.log.append(sql)
        if sql.startswith("SET CONSTRAINTS") and self.immediate_raises:
            raise self.immediate_raises
        if sql.startswith("SET TRANSACTION") and self.mode_raises:
            raise self.mode_raises
        if sql.startswith("SET TRANSACTION"):
            self.info.transaction_status = 2  # INTRANS
        return SimpleNamespace(fetchone=lambda: (self.role,))

    def commit(self) -> None:
        if self.commit_raises:
            self.info.transaction_status = (
                0 if self.commit_leaves_status is None else self.commit_leaves_status
            )
            self.broken = self.commit_breaks
            raise self.commit_raises
        self.log.append("commit")
        self.info.transaction_status = 0

    def rollback(self) -> None:
        self.log.append("rollback")
        self.info.transaction_status = 0

    def close(self) -> None:
        self.log.append("close")
        self.closed = True


class FakeHost:
    def __init__(self, log: list[str], detaches: bool = True) -> None:
        self.log = log
        self.detaches = detaches

    def detach(self) -> bool:
        self.log.append("detach")
        return self.detaches


class Rig:
    """A source that records every call and a toolkit whose host logs into the connection's log."""

    def __init__(
        self,
        *,
        detaches: bool = True,
        adopt_error: Exception | None = None,
        begin_error: Exception | None = None,
        **conn: Any,
    ):
        self.conn_args = conn
        self.detaches = detaches
        self.adopt_error = adopt_error
        self.begin_error = begin_error
        self.principals: list[Principal] = []
        self.conns: list[FakeConn] = []
        self.adopted: list[tuple[int, int, bool]] = []

    @contextmanager
    def source(self, principal: Principal) -> Iterator[FakeConn]:
        self.principals.append(principal)
        conn = FakeConn(**self.conn_args)
        self.conns.append(conn)
        yield conn

    def toolkit(self) -> Toolkit:
        def adopt_host(conn: FakeConn, statement: int, operation: int) -> FakeHost:
            if self.adopt_error:
                raise self.adopt_error
            conn.log.append("adopt")
            self.adopted.append((statement, operation, False))
            return FakeHost(conn.log, self.detaches)

        def begin(host: FakeHost, read_only: bool) -> tuple[str, str]:
            if self.begin_error:
                raise self.begin_error
            return ("tx", "assembly")

        return Toolkit(adopt_host, begin)

    def connections(self, **kw: Any) -> Connections:
        return Connections("truss", self.source, toolkit=self.toolkit(), **kw)


def test_a_read_begins_read_only_and_rolls_back_in_order() -> None:
    rig = Rig()
    with rig.connections().read(CAROL, "query") as call:
        assert (call.tx, call.assembly, call.principal) == ("tx", "assembly", CAROL)
    assert rig.conns[0].log == [
        "SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ ONLY",
        "SET LOCAL statement_timeout = '10000ms'",
        "SELECT current_setting('role')",
        "adopt",
        "detach",
        "rollback",
    ]


def test_a_write_begins_and_commits_after_detach() -> None:
    rig = Rig()
    with rig.connections().write(CAROL, "apply"):
        pass
    log = rig.conns[0].log
    assert log[0] == "SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ WRITE"
    assert log[-3:] == ["detach", "SET CONSTRAINTS ALL IMMEDIATE", "commit"]


def test_a_dry_run_write_rolls_back() -> None:
    rig = Rig()
    with rig.connections().write(CAROL, "apply") as call:
        call.rollback = True
    # the deferred checks run inside a dry run too: they would otherwise never be exercised
    assert rig.conns[0].log[-3:] == ["detach", "SET CONSTRAINTS ALL IMMEDIATE", "rollback"]


@pytest.mark.parametrize("dry", [False, True])
def test_a_deferred_check_that_fails_is_raised_from_the_call_and_commits_nothing(dry: bool) -> None:
    psycopg = pytest.importorskip("psycopg")
    rig = Rig()
    with pytest.raises(Unavailable) as caught:
        with rig.connections().write(CAROL, "apply") as call:
            rig.conns[0].immediate_raises = _stated(
                psycopg.errors.ObjectNotInPrerequisiteState, "55000"
            )
            call.rollback = dry
    assert caught.value.reason == "unreachable" and not isinstance(caught.value, CommitUnknown)
    assert caught.value.detail == "a deferred check of the write failed"
    assert "secret-host" not in str(caught.value)
    log = rig.conns[0].log
    # rolled back, and the connection is idle again, so it stays open
    assert "commit" not in log and log[-1] == "rollback" and not rig.conns[0].closed


def test_a_deferred_check_that_times_out_is_a_statement_timeout_and_keeps_the_connection() -> None:
    psycopg = pytest.importorskip("psycopg")
    rig = Rig()
    with pytest.raises(Unavailable) as caught:
        with rig.connections().write(CAROL, "apply"):
            rig.conns[0].immediate_raises = _stated(psycopg.errors.QueryCanceled, "57014")
    assert caught.value.reason == "unreachable" and caught.value.detail == "statement timeout"
    assert "commit" not in rig.conns[0].log and not rig.conns[0].closed


@pytest.mark.parametrize("state", ["08006", "57P01", None])
def test_a_deferred_check_that_loses_the_connection_closes_it(state: str | None) -> None:
    psycopg = pytest.importorskip("psycopg")
    rig = Rig()
    with pytest.raises(Unavailable) as caught:
        with rig.connections().write(CAROL, "apply"):
            rig.conns[0].immediate_raises = _stated(psycopg.OperationalError, state)
    assert caught.value.reason == "unreachable" and not isinstance(caught.value, CommitUnknown)
    assert caught.value.detail != "a deferred check of the write failed"
    assert "secret-host" not in str(caught.value)
    assert "commit" not in rig.conns[0].log and rig.conns[0].closed


def test_a_deferred_check_that_raises_a_non_psycopg_error_closes_the_connection() -> None:
    rig = Rig()
    with pytest.raises(Unavailable) as caught:
        with rig.connections().write(CAROL, "apply"):
            rig.conns[0].immediate_raises = RuntimeError("secret-host")
    assert caught.value.detail == "database error" and "secret-host" not in str(caught.value)
    assert rig.conns[0].closed


def test_a_deferred_check_whose_rollback_fails_closes_the_connection() -> None:
    psycopg = pytest.importorskip("psycopg")
    rig = Rig()
    with pytest.raises(Unavailable) as caught:
        with rig.connections().write(CAROL, "apply"):
            conn = rig.conns[0]
            conn.immediate_raises = _stated(psycopg.errors.ObjectNotInPrerequisiteState, "55000")

            def broken_rollback() -> None:
                raise RuntimeError("gone")

            conn.rollback = broken_rollback  # type: ignore[method-assign]
    assert caught.value.reason == "unreachable"
    assert rig.conns[0].closed


def test_a_read_runs_no_deferred_checks() -> None:
    rig = Rig()
    with rig.connections().read(CAROL, "q"):
        pass
    assert "SET CONSTRAINTS ALL IMMEDIATE" not in rig.conns[0].log


def test_an_exception_detaches_rolls_back_and_propagates_without_closing() -> None:
    rig = Rig()
    with pytest.raises(KeyError):
        with rig.connections().write(CAROL, "apply"):
            raise KeyError("boom")
    assert rig.conns[0].log[-2:] == ["detach", "rollback"]
    assert not rig.conns[0].closed


@pytest.mark.parametrize("mode", ["read", "write"])
def test_a_failed_transaction_mode_statement_is_rolled_back_not_left_on_the_connection(
    mode: str,
) -> None:
    rig = Rig()
    original_source = rig.source

    @contextmanager
    def source(principal: Principal) -> Iterator[FakeConn]:
        with original_source(principal) as conn:
            conn.mode_raises = KeyError("mode refused")
            yield conn

    connections = Connections("truss", source, toolkit=rig.toolkit())
    with pytest.raises(KeyError):
        with getattr(connections, mode)(CAROL, "apply"):
            pytest.fail("the body must not run")
    assert "rollback" in rig.conns[0].log and "adopt" not in rig.conns[0].log


def test_the_statement_timeout_is_the_validated_integer() -> None:
    rig = Rig()
    with rig.connections(statement_timeout_ms=1, operation_timeout_ms=60_000).read(CAROL, "q"):
        pass
    assert "SET LOCAL statement_timeout = '1ms'" in rig.conns[0].log
    assert rig.adopted == [(1, 60_000, False)]


@pytest.mark.parametrize("bad", [0, 60_001, -5, 1.5, "10", True, None])
def test_timeouts_outside_one_to_sixty_thousand_are_refused_at_construction(bad: Any) -> None:
    rig = Rig()
    with pytest.raises(ValueError):
        rig.connections(statement_timeout_ms=bad)
    with pytest.raises(ValueError):
        rig.connections(operation_timeout_ms=bad)


@pytest.mark.parametrize("token", ["", None])
def test_no_token_is_refused_before_the_source_is_called(token: Any) -> None:
    rig = Rig()
    connections = rig.connections()
    for mode in (connections.read, connections.write):
        with pytest.raises(Refused) as caught:
            with mode(Principal("carol", token), "query"):
                pytest.fail("the body must not run")
        assert caught.value.reason == "token_expired"
    assert rig.principals == []


def test_each_call_gets_its_own_connection_for_its_own_principal() -> None:
    rig = Rig()
    connections = rig.connections()
    bob = Principal("bob", "bob-token")
    with connections.read(CAROL, "a"):
        pass
    with connections.read(bob, "b"):
        pass
    with connections.write(CAROL, "c"):
        pass
    assert rig.principals == [CAROL, bob, CAROL]
    assert len({id(c) for c in rig.conns}) == 3


@pytest.mark.parametrize(
    ("conn", "detail"),
    [
        ({"autocommit": True}, "autocommit"),
        ({"status": 1}, "not idle"),
        ({"role": "carol_owner"}, "role"),
    ],
)
def test_a_connection_that_arrives_wrong_is_refused_before_adoption(
    conn: dict[str, Any], detail: str
) -> None:
    rig = Rig(**conn)
    with pytest.raises(Unavailable) as caught:
        with rig.connections().read(CAROL, "query"):
            pytest.fail("the body must not run")
    assert caught.value.reason == "access_denied" and detail in caught.value.detail
    assert "adopt" not in rig.conns[0].log


def test_a_connection_with_a_session_role_is_closed_for_the_pool_to_discard() -> None:
    rig = Rig(role="carol_owner")
    with pytest.raises(Unavailable):
        with rig.connections().read(CAROL, "query"):
            pytest.fail("the body must not run")
    assert rig.conns[0].closed and "adopt" not in rig.conns[0].log
    # the other wrong arrivals are not the layer's to close: nothing was changed on them
    arrivals: list[dict[str, Any]] = [{"autocommit": True}, {"status": 1}]
    for arrival in arrivals:
        other = Rig(**arrival)
        with pytest.raises(Unavailable):
            with other.connections().read(CAROL, "query"):
                pass
        assert not other.conns[0].closed


@pytest.mark.parametrize("mode", ["read", "write"])
def test_a_missing_truss_extra_is_not_configured_for_every_call(mode: str) -> None:
    rig = Rig()
    connections = rig.connections()
    with pytest.raises(Unavailable) as caught:
        with getattr(connections, mode)(CAROL, "query"):
            raise ModuleNotFoundError("No module named 'truss'")
    assert (caught.value.reason, caught.value.detail) == (
        "not_configured",
        "the truss extra is not installed",
    )
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert rig.conns[0].log[-1] == "rollback"


def test_an_import_error_while_adopting_is_not_configured() -> None:
    rig = Rig(adopt_error=ImportError("No module named 'truss'"))
    with pytest.raises(Unavailable) as caught:
        with rig.connections().read(CAROL, "query"):
            pass
    assert (caught.value.reason, caught.value.detail) == (
        "not_configured",
        "the truss extra is not installed",
    )


@pytest.mark.parametrize("error", [ValueError, RuntimeError, OSError])
def test_another_exception_from_truss_is_unreachable_and_carries_none_of_its_text(
    error: type[Exception],
) -> None:
    rig = Rig()
    with pytest.raises(Unavailable) as caught:
        with rig.connections().read(CAROL, "query"):
            raise error("select secret from t where token = 'carol-token'")
    assert (caught.value.reason, caught.value.detail) == ("unreachable", "truss error")
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert "secret" not in str(caught.value) and "carol-token" not in repr(caught.value)


@pytest.mark.parametrize(
    "error", [AssertionError, TypeError, AttributeError, NameError, KeyError, NotImplementedError]
)
def test_a_programming_error_is_never_swallowed(error: type[Exception]) -> None:
    rig = Rig()
    with pytest.raises(error):
        with rig.connections().write(CAROL, "apply"):
            raise error("bug")


def test_the_layer_never_sets_a_role_or_session_state() -> None:
    rig = Rig()
    connections = rig.connections()
    with connections.read(CAROL, "a"):
        pass
    with connections.write(CAROL, "b"):
        pass
    for conn in rig.conns:
        for sql in conn.log:
            assert "SET ROLE" not in sql.upper()
            assert not sql.upper().startswith("SET ") or sql.startswith(
                (
                    "SET TRANSACTION ISOLATION LEVEL",
                    "SET LOCAL statement_timeout",
                    "SET CONSTRAINTS ALL IMMEDIATE",
                )
            )
            assert "autocommit" not in sql.lower()


def test_a_quarantined_connection_is_closed_not_committed() -> None:
    rig = Rig(detaches=False)
    with pytest.raises(Unavailable) as caught:
        with rig.connections().write(CAROL, "apply"):
            pass
    assert caught.value.reason == "unreachable"
    log = rig.conns[0].log
    assert "commit" not in log and log[-1] == "close"


def test_a_failure_that_reports_the_transaction_unusable_closes_the_connection() -> None:
    rig = Rig()
    failure = SimpleNamespace(code="transaction_unusable", sql_state="57P01", catalog_code=None)
    with pytest.raises(Unavailable):
        with rig.connections().read(CAROL, "query") as call:
            call.unwrap(SimpleNamespace(status="error", error=failure))
    assert rig.conns[0].closed


def test_unwrap_returns_the_value_and_maps_permission_denied_to_refused() -> None:
    rig = Rig()
    with rig.connections().read(CAROL, "query") as call:
        assert call.unwrap(SimpleNamespace(status="ok", value=7)) == 7
        denied = SimpleNamespace(code="execution_obligation", sql_state="42501", catalog_code=None)
        with pytest.raises(Refused) as caught:
            call.unwrap(SimpleNamespace(status="error", error=denied))
        assert caught.value.reason == "no_access"
    assert not rig.conns[0].closed


def test_a_value_error_at_adoption_is_unavailable_and_the_connection_is_released() -> None:
    rig = Rig(adopt_error=ValueError("Selected psycopg/libpq/PostgreSQL tuple required"))
    with pytest.raises(Unavailable) as caught:
        with rig.connections().read(CAROL, "query"):
            pass
    assert caught.value.reason == "unsupported_version"
    assert rig.conns[0].log[-1] == "rollback"


@pytest.mark.parametrize(
    ("text", "reason", "detail", "closed"),
    [
        (
            "Connection already attached or quarantined",
            "unreachable",
            "the connection is quarantined",
            True,
        ),
        (
            "Live non-pipeline connection required",
            "access_denied",
            "the connection is in pipeline mode",
            False,
        ),
        ("Selected psycopg/libpq/PostgreSQL tuple required", "unsupported_version", None, False),
    ],
)
def test_each_adoption_value_error_maps_by_its_message(
    text: str, reason: str, detail: str | None, closed: bool
) -> None:
    rig = Rig(adopt_error=ValueError(text))
    with pytest.raises(Unavailable) as caught:
        with rig.connections().read(CAROL, "query"):
            pass
    assert caught.value.reason == reason
    if detail:
        assert caught.value.detail == detail
    assert text not in str(caught.value)
    assert rig.conns[0].closed is closed


def test_a_profile_refusal_at_adoption_is_access_denied() -> None:
    failure = SimpleNamespace(
        code="invalid_transaction",
        message="Unsupported requested transaction profile",
        sql_state=None,
        catalog_code=None,
    )
    rig = Rig(begin_error=connection_module._Refusal(failure))
    with pytest.raises(Unavailable) as caught:
        with rig.connections().read(CAROL, "query"):
            pytest.fail("the body must not run")
    assert caught.value.reason == "access_denied"
    assert caught.value.detail == "the transaction profile differs"


def test_an_operation_invalid_transaction_is_unreachable_and_does_not_quarantine() -> None:
    rig = Rig()
    failure = SimpleNamespace(
        code="invalid_transaction",
        message="Original transaction/profile admission refused",
        sql_state=None,
        catalog_code=None,
    )
    with rig.connections().read(CAROL, "query") as call:
        with pytest.raises(Unavailable) as caught:
            call.unwrap(SimpleNamespace(status="error", error=failure))
        assert caught.value.reason == "unreachable"
        assert caught.value.detail == "truss invalid_transaction"
        assert not call.quarantined
    assert not rig.conns[0].closed


def test_a_closed_connection_is_lost_not_busy() -> None:
    rig = Rig(status=4)  # UNKNOWN, what a closed psycopg connection reports
    original = rig.source

    @contextmanager
    def closed(principal: Principal) -> Iterator[FakeConn]:
        with original(principal) as conn:
            conn.closed = True
            yield conn

    connections = rig.connections()
    connections._source = closed
    with pytest.raises(Unavailable) as caught:
        with connections.read(CAROL, "query"):
            pytest.fail("the body must not run")
    assert caught.value.reason == "unreachable" and caught.value.detail == "connection lost"
    assert rig.conns[0].log == []


def test_a_value_error_on_a_dead_connection_is_unreachable() -> None:
    rig = Rig(adopt_error=ValueError("tuple"))
    connections = rig.connections()
    original = rig.source

    @contextmanager
    def dying(principal: Principal) -> Iterator[FakeConn]:
        with original(principal) as conn:
            conn.closed = True
            yield conn

    connections._source = dying
    with pytest.raises(Unavailable) as caught:
        with connections.read(CAROL, "query"):
            pass
    assert caught.value.reason == "unreachable"


def test_a_commit_that_raises_closes_the_connection_and_the_outcome_is_unknown() -> None:
    rig = Rig()
    with pytest.raises(CommitUnknown) as caught:
        with rig.connections().write(CAROL, "apply"):
            rig.conns[0].commit_raises = RuntimeError("the connection is lost: secret-host")
    assert caught.value.reason == "unreachable" and caught.value.detail == "outcome unknown"
    assert "secret-host" not in str(caught.value) and rig.conns[0].closed


def _stated(base: type, state: str | None) -> Any:
    class Stated(base):  # type: ignore[misc]
        @property
        def sqlstate(self) -> str | None:  # type: ignore[override]
            return state

    return Stated("server said: secret-host")


def test_a_commit_the_server_refused_is_a_definite_failure_and_the_connection_stays_open() -> None:
    psycopg = pytest.importorskip("psycopg")
    rig = Rig()
    with pytest.raises(Unavailable) as caught:
        with rig.connections().write(CAROL, "apply"):
            rig.conns[0].commit_raises = _stated(
                psycopg.errors.ObjectNotInPrerequisiteState, "55000"
            )
    assert not isinstance(caught.value, CommitUnknown)
    assert caught.value.reason == "unreachable" and caught.value.detail == "the commit was refused"
    assert "secret-host" not in str(caught.value)
    assert not rig.conns[0].closed and "close" not in rig.conns[0].log


@pytest.mark.parametrize(("state", "leaves"), [("55000", 2), ("XX000", 3), ("55000", 1)])
def test_a_sqlstate_commit_error_on_a_connection_that_is_not_idle_is_unknown(
    state: str, leaves: int
) -> None:
    psycopg = pytest.importorskip("psycopg")
    rig = Rig()
    with pytest.raises(CommitUnknown) as caught:
        with rig.connections().write(CAROL, "apply"):
            rig.conns[0].commit_raises = _stated(psycopg.errors.InternalError, state)
            rig.conns[0].commit_leaves_status = leaves
    assert caught.value.reason == "unreachable" and caught.value.detail == "outcome unknown"
    assert "secret-host" not in str(caught.value) and rig.conns[0].closed


@pytest.mark.parametrize("state", ["25P04", "57P04"])
def test_a_sqlstate_commit_error_that_breaks_the_connection_is_unknown_and_closes_it(
    state: str,
) -> None:
    psycopg = pytest.importorskip("psycopg")
    rig = Rig()
    with pytest.raises(CommitUnknown) as caught:
        with rig.connections().write(CAROL, "apply"):
            rig.conns[0].commit_raises = _stated(psycopg.OperationalError, state)
            rig.conns[0].commit_breaks = True
    assert caught.value.detail == "outcome unknown" and "secret-host" not in str(caught.value)
    assert rig.conns[0].closed and "close" in rig.conns[0].log


@pytest.mark.parametrize("state", [None, "08006", "57P01", "57P03"])
def test_a_commit_that_may_have_committed_is_unknown_and_closes_the_connection(
    state: str | None,
) -> None:
    psycopg = pytest.importorskip("psycopg")
    rig = Rig()
    with pytest.raises(CommitUnknown) as caught:
        with rig.connections().write(CAROL, "apply"):
            rig.conns[0].commit_raises = _stated(psycopg.OperationalError, state)
    assert caught.value.detail == "outcome unknown" and "secret-host" not in str(caught.value)
    assert rig.conns[0].closed


@pytest.mark.parametrize(
    ("code", "detail"),
    [
        ("retry", "retry the call"),
        ("cancelled", "timed out or cancelled"),
        ("other", "truss other"),
    ],
)
def test_failure_error_maps_retry_and_cancelled_to_fixed_details(code: str, detail: str) -> None:
    error = failure_error("truss", "apply", SimpleNamespace(code=code, sql_state=None))
    assert isinstance(error, Unavailable) and error.reason == "unreachable"
    assert error.detail == detail


@pytest.mark.parametrize("kind", ["InterfaceError", "ProgrammingError"])
def test_a_non_operational_psycopg_error_from_the_layers_statement_is_a_database_error(
    kind: str,
) -> None:
    psycopg = pytest.importorskip("psycopg")
    rig = Rig()
    conns = rig.connections()
    error = _stated(getattr(psycopg, kind), "25P03")

    original = FakeConn.execute

    def failing(self: FakeConn, sql: str) -> Any:
        if sql.startswith("SET LOCAL"):
            raise error
        return original(self, sql)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(FakeConn, "execute", failing)
        with pytest.raises(Unavailable) as caught:
            with conns.read(CAROL, "query"):
                pass  # pragma: no cover
    assert caught.value.reason == "unreachable" and caught.value.detail == "database error"
    assert "secret-host" not in str(caught.value)


@pytest.mark.parametrize(
    ("message", "kind", "reason"),
    [
        (
            'connection failed: connection to server on socket "/x/y" failed: No such file or '
            "directory",
            Unavailable,
            "unreachable",
        ),
        ("connection is bad: failed to resolve host 'db.internal'", Unavailable, "unreachable"),
        ("connection timeout expired", Unavailable, "unreachable"),
        ("the connection is lost", Unavailable, "unreachable"),
        ('FATAL:  permission denied for database "app"', Unavailable, "access_denied"),
        ('FATAL:  password authentication failed for user "carol"', Refused, "token_expired"),
        ('FATAL:  role "carol" is not permitted to log in', Refused, "no_access"),
        ("something nobody has seen", Unavailable, "unreachable"),
    ],
)
def test_connect_failures_are_classified_by_the_drivers_message(
    message: str, kind: type, reason: str
) -> None:
    error: Any = classify_connect_error("truss", "query", Exception(message))
    assert type(error) is kind and error.reason == reason
    for secret in ("/x/y", "db.internal", "carol"):
        assert secret not in str(error)


def test_without_psycopg_loaded_no_error_is_operational_and_a_body_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "psycopg", raising=False)
    assert _is_operational(KeyError()) is False
    rig = Rig()
    with pytest.raises(KeyError):
        with rig.connections().read(CAROL, "query"):
            raise KeyError("boom")
    assert "psycopg" not in sys.modules  # the layer did not import it


def test_an_aborted_write_transaction_is_rolled_back_not_committed() -> None:
    rig = Rig()
    with pytest.raises(Unavailable) as caught:
        with rig.connections().write(CAROL, "apply"):
            rig.conns[0].info.transaction_status = 3  # INERROR
    assert caught.value.reason == "unreachable"
    assert caught.value.detail == "the transaction was aborted"
    log = rig.conns[0].log
    assert "commit" not in log and log[-1] == "rollback" and not rig.conns[0].closed


def test_an_aborted_transaction_whose_rollback_raises_closes_the_connection() -> None:
    rig = Rig()

    def boom() -> None:
        raise RuntimeError("gone")

    with pytest.raises(Unavailable) as caught:
        with rig.connections().write(CAROL, "apply"):
            rig.conns[0].info.transaction_status = 3
            rig.conns[0].rollback = boom  # type: ignore[method-assign]
    assert caught.value.detail == "the transaction was aborted" and rig.conns[0].closed


def test_an_operational_error_with_a_sqlstate_inside_the_body_is_not_a_connect_failure() -> None:
    psycopg = pytest.importorskip("psycopg")

    class Stated(psycopg.OperationalError):
        def __init__(self, message: str, state: str) -> None:
            self._state = state
            super().__init__(message)

        @property
        def sqlstate(self) -> str:  # type: ignore[override]
            return self._state

    cases = [
        ("57014", "statement timeout"),
        ("55P03", "database error"),
        ("08006", "cannot connect"),  # class 08 stays a connect failure
        ("57P01", "cannot connect"),  # so do 57P01 to 57P03
    ]
    for state, detail in cases:
        rig = Rig()
        with pytest.raises(Unavailable) as caught:
            with rig.connections().read(CAROL, "query"):
                raise Stated("the connection is lost: secret", state)
        assert caught.value.reason == "unreachable" and caught.value.detail == detail
        assert "secret" not in str(caught.value)


def test_a_connect_failure_on_enter_is_classified() -> None:
    psycopg = pytest.importorskip("psycopg")

    @contextmanager
    def failing(principal: Principal) -> Iterator[Any]:
        raise psycopg.OperationalError("FATAL: password authentication failed for user 'carol'")
        yield  # pragma: no cover

    with pytest.raises(Refused) as caught:
        with Connections("truss", failing, toolkit=Rig().toolkit()).read(CAROL, "query"):
            pass
    assert caught.value.reason == "token_expired"


# -- Truss-marked: a real call on PostgreSQL 18.6


class Capture:
    """Wraps a world's source to remember each connection it yielded."""

    def __init__(self, world: Any) -> None:
        self.world = world
        self.conns: list[Any] = []
        self.calls = 0
        self.returned: list[tuple[bool, int, tuple[str]]] = []  # as each connection went back

    @contextmanager
    def __call__(self, principal: Principal) -> Iterator[Any]:
        self.calls += 1
        with self.world.connection_source(principal) as conn:
            self.conns.append(conn)
            yield conn
            self.returned.append(
                (
                    conn.closed,
                    int(conn.info.transaction_status),
                    conn.execute("show statement_timeout").fetchone(),
                )
            )
            conn.rollback()


@pytest.mark.truss
def test_a_call_runs_as_that_person_for_a_read_and_for_a_write(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster)
    seen = Capture(h.world)
    connections = Connections("truss", seen)
    for user in ("carol", "bob"):
        for mode in (connections.read, connections.write):
            with mode(h.principal(user), "probe") as call:
                conn = seen.conns[-1]
                assert conn.execute("select session_user").fetchone() == (user,)
                catalog = call.unwrap(call.assembly.reader_catalog_in_transaction(call.tx))
                assert type(catalog).__name__ != "CatalogRefused"
    assert len(seen.conns) == 4 and len({id(c) for c in seen.conns}) == 4
    # as each connection went back: open, idle (settled) and with no session timeout left
    assert seen.returned == [(False, 0, ("0",))] * 4


@pytest.mark.truss
def test_a_non_member_is_refused_by_postgres_not_by_the_layer(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster)
    connections = Connections("truss", h.world.connection_source)
    with connections.read(h.principal("dave"), "probe") as call:
        refused = call.unwrap(call.assembly.reader_catalog_in_transaction(call.tx))
        assert type(refused).__name__ == "CatalogRefused"


@pytest.mark.truss
def test_a_lost_backend_surfaces_as_unreachable_and_the_next_call_gets_a_new_connection(
    cluster: Any,  # noqa: F811
) -> None:
    h = _world(cluster)
    seen = Capture(h.world)
    connections = Connections("truss", seen)
    with pytest.raises(Unavailable) as caught:
        with connections.read(h.principal("carol"), "probe") as call:
            pid = seen.conns[-1].execute("select pg_backend_pid()").fetchone()[0]
            cluster.su.execute(f"select pg_terminate_backend({int(pid)})")
            call.unwrap(call.assembly.reader_catalog_in_transaction(call.tx))
    assert caught.value.reason == "unreachable"
    assert seen.conns[0].closed
    with connections.read(h.principal("carol"), "probe") as call:
        assert seen.conns[1] is not seen.conns[0] and not seen.conns[1].closed
        catalog = call.unwrap(call.assembly.reader_catalog_in_transaction(call.tx))
        assert type(catalog).__name__ != "CatalogRefused"


class KeepOpen:
    """A source that hands one live connection back without closing it, and records `closed` at the
    moment control returns to it. The test closes the connection."""

    def __init__(self, world: Any, principal: Principal) -> None:
        self.conn = world._connect(principal.user, principal.token)
        self.closed_on_return: list[bool] = []

    @contextmanager
    def __call__(self, principal: Principal) -> Iterator[Any]:
        try:
            yield self.conn
        finally:
            self.closed_on_return.append(self.conn.closed)


@pytest.mark.truss
def test_the_adapter_closes_a_live_connection_that_truss_quarantined(
    cluster: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Truss 0.0.44 has no deterministic trigger that quarantines a LIVE connection (see the plan's
    # TR-04 row), so the flag `unwrap` sets on `transaction_unusable` and `commit_unknown` is set here.
    h = _world(cluster)
    carol = h.principal("carol")
    source = KeepOpen(h.world, carol)
    try:
        connections = Connections("truss", source)
        with pytest.raises(Unavailable) as caught:
            with connections.read(carol, "probe") as call:
                assert not source.conn.closed
                call.quarantined = True
        assert caught.value.reason == "unreachable"
        assert caught.value.detail == "the connection was quarantined"
        assert source.closed_on_return == [True]
        # mutant: a `_close` that does nothing leaves the live connection open, which this
        # observation shows, so the assertion above fails for it
        monkeypatch.setattr(connection_module, "_close", lambda conn: None)
        live = KeepOpen(h.world, carol)
        try:
            with pytest.raises(Unavailable):
                with Connections("truss", live).read(carol, "probe") as call:
                    call.quarantined = True
            assert live.closed_on_return == [False]
        finally:
            live.conn.close()
        monkeypatch.undo()
        fresh = Capture(h.world)
        with Connections("truss", fresh).read(carol, "probe") as call:
            catalog = call.unwrap(call.assembly.reader_catalog_in_transaction(call.tx))
            assert type(catalog).__name__ != "CatalogRefused"
    finally:
        source.conn.close()


@pytest.mark.truss
def test_an_aborted_write_transaction_is_not_committed_and_is_unavailable(
    cluster: Any,  # noqa: F811
) -> None:
    h = _world(cluster)
    carol = h.principal("carol")
    source = KeepOpen(h.world, carol)
    try:
        with pytest.raises(Unavailable) as caught:
            with Connections("truss", source).write(carol, "probe"):
                source.conn.execute("create temp table scratch (n int)")
                try:
                    source.conn.execute("select 1/0")
                except Exception:
                    pass
        assert caught.value.reason == "unreachable"
        assert caught.value.detail == "the transaction was aborted"
        assert source.closed_on_return == [False]  # rolled back, not closed
        assert int(source.conn.info.transaction_status) == 0
        assert source.conn.execute("select to_regclass('pg_temp.scratch')").fetchone() == (None,)
    finally:
        source.conn.close()


@pytest.mark.truss
def test_no_token_is_refused_before_the_harness_source_is_called(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster)
    seen = Capture(h.world)
    with pytest.raises(Refused):
        with Connections("truss", seen).read(h.principal("anon"), "query"):
            pytest.fail("the body must not run")
    assert seen.calls == 0


@pytest.mark.truss
def test_real_connect_failures_are_classified(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster)
    connections = Connections("truss", h.world.connection_source)

    def attempt(principal: Principal) -> Any:
        with pytest.raises((Refused, Unavailable)) as caught:
            with connections.read(principal, "query"):
                pytest.fail("the body must not run")
        return caught.value

    h.outage("unreachable")
    error = attempt(h.principal("carol"))
    assert isinstance(error, Unavailable) and error.reason == "unreachable"
    h.outage("access_denied")
    error = attempt(h.principal("carol"))
    assert isinstance(error, Unavailable) and error.reason == "access_denied"
    h.outage(None)
    error = attempt(h.borrowed("dave", "alice"))
    assert isinstance(error, Refused) and error.reason == "token_expired"
    h.expire("bob")
    error = attempt(h.principal("bob"))
    assert isinstance(error, Refused) and error.reason == "token_expired"


@pytest.mark.truss
def test_a_deferred_trigger_fails_inside_the_call_before_the_commit(
    cluster: Any,  # noqa: F811
) -> None:
    # No Arras write reaches a deferred Truss trigger deterministically at this slice (see the
    # plan's TR-04 row), so a deferred constraint trigger on a temporary table in the call's own
    # transaction raises 55000, the way Truss's barrier does. The layer runs SET CONSTRAINTS ALL
    # IMMEDIATE before it settles, so the trigger fires inside the call and nothing is committed.
    h = _world(cluster)
    carol = h.principal("carol")
    source = KeepOpen(h.world, carol)
    try:
        with pytest.raises(Unavailable) as caught:
            with Connections("truss", source).write(carol, "probe"):
                for sql in (
                    "create temp table refusal (id int)",
                    "create function pg_temp.refuse() returns trigger language plpgsql as "
                    "$$ begin raise exception 'secret-barrier' using errcode = '55000'; end $$",
                    "create constraint trigger refuse after insert on refusal initially deferred "
                    "for each row execute function pg_temp.refuse()",
                    "insert into refusal values (1)",
                ):
                    source.conn.execute(sql)
        assert not isinstance(caught.value, CommitUnknown)
        assert caught.value.reason == "unreachable"
        assert caught.value.detail == "a deferred check of the write failed"
        assert "secret-barrier" not in str(caught.value)
        assert source.closed_on_return == [False]  # idle again, so it stays open
    finally:
        source.conn.close()


@pytest.mark.parametrize("code", ["transaction_unusable", "commit_unknown"])
def test_a_failure_that_leaves_the_transaction_unusable_or_its_commit_unknown_quarantines(
    code: str,
) -> None:
    rig = Rig()
    failure = SimpleNamespace(code=code, sql_state=None, catalog_code=None)
    with pytest.raises(Unavailable):
        with rig.connections().read(CAROL, "query") as call:
            with pytest.raises(Unavailable):
                call.unwrap(SimpleNamespace(status="error", error=failure))
            assert call.quarantined
    other = SimpleNamespace(code="invalid_transaction", sql_state=None, catalog_code=None)
    with rig.connections().read(CAROL, "query") as call:
        with pytest.raises(Unavailable):
            call.unwrap(SimpleNamespace(status="error", error=other))
        assert not call.quarantined  # a failure that leaves the connection usable does not


def test_an_unauthorized_catalog_code_is_refused_like_permission_denied() -> None:
    failure = SimpleNamespace(
        code="invalid_transaction", sql_state=None, catalog_code="unauthorized"
    )
    error = failure_error("truss", "query", failure)
    assert isinstance(error, Refused) and error.reason == "no_access"
    other = SimpleNamespace(code="invalid_transaction", sql_state=None, catalog_code="profile")
    assert isinstance(failure_error("truss", "query", other), Unavailable)


@pytest.mark.truss
def test_a_call_leaves_no_server_notice_on_the_connection(cluster: Any) -> None:  # noqa: F811
    """`SET TRANSACTION` as the first statement is the transaction's own; a second `BEGIN` drew a
    server WARNING ("there is already a transaction in progress") on every call."""
    h = _world(cluster)
    notices: list[str] = []

    @contextmanager
    def source(principal: Principal) -> Iterator[Any]:
        with h.world.connection_source(principal) as conn:
            conn.add_notice_handler(lambda diag: notices.append(str(diag.message_primary)))
            yield conn
            conn.rollback()

    connections = Connections("truss", source)
    for mode in (connections.read, connections.write):
        with mode(h.principal("carol"), "probe") as call:
            call.unwrap(call.assembly.reader_catalog_in_transaction(call.tx))
    assert notices == []
