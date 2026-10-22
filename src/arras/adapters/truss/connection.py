# SPDX-License-Identifier: MIT OR Apache-2.0
"""The connection layer of the Truss adapter (ADR-017, CONTRACT-005): one person's call, one
connection, one Truss host and assembly, settled before the connection goes back.

The host supplies a `ConnectionSource`, a callable from a `Principal` to a context manager that yields
a psycopg connection authenticated as that person. This layer never creates a connection, never reads
the environment and never reuses a connection across calls. Per call it:

1. refuses a principal with no token before the source is called;
2. checks the connection arrived idle with autocommit off and the session role unset;
3. sets `SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ ONLY` (a read) or `... READ WRITE` (a write)
   as the first statement, in the transaction psycopg opens with it, sets `statement_timeout` with `SET LOCAL`
   (1 to 60,000 ms, which Truss requires) and adopts the transaction into a Truss host;
4. yields a `Call` holding the Truss assembly and transaction handle;
5. detaches the host, then rolls back (a read, a dry run or any failure) or commits (a write), and
   closes the connection when Truss quarantined it or the commit's outcome is unknown, because Truss
   keeps a quarantine on the connection object and the host's pool discards a closed connection. A
   write whose transaction is no longer in progress (an aborted transaction, which `COMMIT` would
   silently turn into a rollback) is rolled back and raises `Unavailable(unreachable)`, "the
   transaction was aborted"; Truss answers that state `invalid_transaction` without quarantining, so
   this check is the only guard.

Truss is imported inside functions and psycopg is never imported here (an error is recognized only
when psycopg is already loaded), so the base install needs neither. Exceptions carry no
token, SQL text, input value, socket path or host name: connect failures are classified from the
driver's message (psycopg gives no SQLSTATE for a connect failure) and the detail is a fixed phrase.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable, Generator, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from typing import Any, cast

from arras.errors import ArrasError, Refused, Unavailable
from arras.results import BackendStatus
from arras.types import Principal

# The per-person source the host supplies (CONTRACT-005): Principal -> a context manager yielding a
# `psycopg.Connection`. Typed loosely so this module needs no psycopg at import time.
ConnectionSource = Callable[[Principal], AbstractContextManager[Any]]
# The trusted connection the host supplies for install, module access and the install state.
InstallingSource = Callable[[], AbstractContextManager[Any]]

# psycopg opens the transaction (its implicit BEGIN) with the first statement on an autocommit-off
# connection, so the modes are set on that transaction; a second BEGIN would only draw a server WARNING
_MODE_READ = "SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ ONLY"
_MODE_WRITE = "SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ WRITE"
_INTRANS = 2  # psycopg.pq.TransactionStatus.INTRANS

INSTALLER = "installer"  # the user of a Call on the installing connection (never a person)
STATEMENT_TIMEOUT_MS = 10_000
OPERATION_TIMEOUT_MS = 60_000
_LOCK_TIMEOUT_MAX_MS = (
    2_147_483_647  # the largest value of the server's integer-millisecond settings
)
_BOUNDS = (1, 60_000)  # Truss refuses a statement or operation timeout outside this range

_UNREACHABLE = (
    "no such file or directory",
    "failed to resolve host",
    "connection refused",
    "connection timeout expired",
    "connection is bad",
    "connection is lost",
    "server closed the connection",
    "could not connect",
    "connection failed",
    "the database system is starting up",
    "the database system is shutting down",
    "terminating connection",
)


class CommitUnknown(Unavailable):
    """A write's COMMIT raised, so the outcome is not known. The connection is closed. The caller
    recovers by replaying the same request on a new connection (CONTRACT-004, the receipt replay)."""

    def __init__(self, backend: str) -> None:
        super().__init__(backend, "unreachable", "outcome unknown")


def classify_connect_error(backend: str, operation: str, exc: BaseException) -> ArrasError:
    """The library error for a failure to connect or a connection lost mid-call. The server and libpq
    word these, so a localized server may defeat the match: an unrecognized failure is `unreachable`.

    - an expired role, a wrong token and an unknown role all say `password authentication failed`
      (the server does not tell them apart): `Refused(token_expired)`;
    - a role that may not log in: `Refused(no_access)`;
    - a revoked CONNECT on the database: `Unavailable(access_denied)`;
    - no socket, no route, a refused or timed-out connection, a lost backend: `Unavailable(unreachable)`.
    """
    text = str(exc).lower()
    if "password authentication failed" in text:
        return Refused(backend, operation, "token_expired")
    if "not permitted to log in" in text:
        return Refused(backend, operation, "no_access")
    if "permission denied for database" in text:
        return Unavailable(backend, "access_denied", "connect refused by the database")
    if "too many connections" in text:
        return Unavailable(backend, "unreachable", "connection limit")
    if any(marker in text for marker in _UNREACHABLE):
        return Unavailable(backend, "unreachable", "cannot connect")
    return Unavailable(backend, "unreachable", "database error")


def failure_error(backend: str, operation: str, failure: Any) -> ArrasError:
    """The library error for a Truss `ExecutionFailure`: permission denied (a person who holds no
    grant) is `Refused(no_access)`; anything else is `Unavailable` naming Truss's code. Truss 0.0.45
    reports every `ValueError` inside an operation as one `invalid_transaction` message, so the code
    carries no profile meaning here: only the adoption step maps a profile refusal."""
    if getattr(failure, "sql_state", None) == "42501" or getattr(failure, "catalog_code", None) == (
        "unauthorized"
    ):
        return Refused(backend, operation, "no_access")
    code = getattr(failure, "code", "failure")
    if code == "retry":  # a serialization failure or a deadlock (40001, 40P01): nothing committed
        return Unavailable(backend, "unreachable", "retry the call")
    if code == "cancelled":
        # Truss reports a statement timeout (57014), an expired operation deadline and a refused
        # cancellation admission as `cancelled`; the code does not tell them apart
        return Unavailable(backend, "unreachable", "timed out or cancelled")
    return Unavailable(backend, "unreachable", f"truss {code}")


@dataclass
class Call:
    """One open call: the Truss assembly and transaction handle for one person's connection.

    `rollback` makes a write roll back instead of commit (a dry run). `unwrap` turns a Truss outcome
    into its value or the library error; a failure that quarantines the connection also marks the
    call so the connection is closed.
    """

    backend: str
    operation: str
    principal: Principal
    assembly: Any
    tx: Any
    read_only: bool
    rollback: bool = False
    quarantined: bool = False
    facts: Mapping[str, Any] = field(
        default_factory=lambda: cast("dict[str, Any]", {})
    )  # what the installing call read first

    def unwrap(
        self, outcome: Any, mapper: Callable[[str, str, Any], ArrasError] | None = None
    ) -> Any:
        """The value of an `Ok`; the library error of an `Error`, by `failure_error` or by the
        `mapper` an operation passes when it reads more of Truss's failure (the registry maps
        `catalog_code`)."""
        if getattr(outcome, "status", None) == "ok":
            return outcome.value
        failure = outcome.error
        if getattr(failure, "code", None) in ("transaction_unusable", "commit_unknown"):
            self.quarantined = True
        raise (mapper or failure_error)(self.backend, self.operation, failure)


@dataclass(frozen=True)
class Toolkit:
    """The two steps that touch Truss, a seam because Truss refuses anything but a real
    `psycopg.Connection`: tests with a recording connection pass their own."""

    adopt_host: Callable[[Any, int, int], Any]
    begin: Callable[[Any, bool], tuple[Any, Any]]


class _Refusal(Exception):
    """Truss refused to adopt the transaction or build the assembly (a failure with a `code`)."""

    def __init__(self, failure: Any) -> None:
        self.failure = failure


def _truss_adopt_host(conn: Any, statement_timeout_ms: int, operation_timeout_ms: int) -> Any:
    import truss

    return cast(Any, truss).adopt_psycopg_host(
        conn, statement_timeout_ms=statement_timeout_ms, operation_timeout_ms=operation_timeout_ms
    )


def _truss_begin(host: Any, read_only: bool) -> tuple[Any, Any]:
    from truss import CatalogRuntimeConfiguration, create_reference_assembly

    adopted = host.adopt_transaction(access_mode="read_only" if read_only else "read_write")
    if adopted.status != "ok":
        raise _Refusal(adopted.error)
    built = create_reference_assembly(CatalogRuntimeConfiguration(), host)
    if built.status != "ok":
        raise _Refusal(built)  # an AssemblyConstructionError, which has a `code` and no `.error`
    return adopted.value, built.value


TRUSS = Toolkit(_truss_adopt_host, _truss_begin)


def _timeout(name: str, value: object) -> int:
    low, high = _BOUNDS
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high} milliseconds")
    return value


def _wait_ms(seconds: float) -> int:
    if isinstance(seconds, bool) or not seconds > 0:
        raise ValueError("timeout must be a positive number of seconds")
    if seconds * 1000 >= _LOCK_TIMEOUT_MAX_MS:
        return _LOCK_TIMEOUT_MAX_MS
    return max(1, math.ceil(seconds * 1000))


def _first(row: Any) -> Any:
    if row is None:
        return None
    if isinstance(row, Mapping):
        return next(iter(cast(Mapping[str, Any], row).values()), None)
    return row[0]


def _is_operational(exc: BaseException) -> bool:
    psycopg = sys.modules.get("psycopg")  # only a loaded psycopg can have raised the error
    return psycopg is not None and isinstance(exc, psycopg.OperationalError)


# a bug in the caller or the adapter is never an availability failure
_PROGRAMMING = (
    AssertionError,
    TypeError,
    AttributeError,
    NameError,
    LookupError,
    NotImplementedError,
)
_CONNECT_STATES = ("57P01", "57P02", "57P03")
# the reasons a backend status can give (CONTRACT-004)
_OBSERVED = frozenset(
    {"not_configured", "unreachable", "access_denied", "migration_failed", "unsupported_version"}
)


def _is_psycopg_error(exc: BaseException) -> bool:
    psycopg = sys.modules.get("psycopg")
    return psycopg is not None and isinstance(exc, psycopg.Error)


def _commit_unknown(conn: Any, exc: BaseException) -> bool:
    """Whether a `COMMIT` that raised may have committed: Truss's own rule for an unknown commit
    outcome (_host_session.py). It is a definite refusal only when the error is a psycopg error with
    a SQLSTATE outside class 08 and `57P01` to `57P03`, and the connection is open, not broken and
    idle again (ReadyForQuery arrived after the ErrorResponse): the server reported the failed
    `COMMIT` and rolled the transaction back. In every other case the outcome is unknown: a
    non-psycopg error, no SQLSTATE, a failed connection, or a connection that is closed, broken or
    not idle after the error (a PANIC or a FATAL), whatever the SQLSTATE."""
    if not _is_psycopg_error(exc):
        return True
    state = getattr(exc, "sqlstate", None)
    if state is None or state.startswith("08") or state in _CONNECT_STATES:
        return True
    try:
        if conn.closed or getattr(conn, "broken", False):
            return True
        return int(conn.info.transaction_status) != 0  # psycopg.pq.TransactionStatus.IDLE
    except Exception:
        return True


def _operational_error(backend: str, operation: str, exc: BaseException) -> ArrasError:
    """An `OperationalError` is a connect failure when it has no SQLSTATE (psycopg gives none for a
    failure to connect) or one of class 08 or 57P01 to 57P03; one raised by a statement inside the body
    carries its state and is a timeout (57014) or a database error."""
    state = getattr(exc, "sqlstate", None)
    if state is None or state.startswith("08") or state in _CONNECT_STATES:
        return classify_connect_error(backend, operation, exc)
    if state == "57014":
        return Unavailable(backend, "unreachable", "statement timeout")
    return Unavailable(backend, "unreachable", "database error")


def _close(conn: Any) -> None:
    try:
        if not conn.closed:
            conn.close()
    except Exception:  # a dead connection may refuse to close; the host's pool drops it
        pass


class Connections:
    """Per-person calls over a host-supplied `ConnectionSource`.

    One host and one assembly per call: building them costs under 0.1 ms (measured, TR-04), so
    nothing is cached and nothing is shared between people or calls. The connection is the cost.
    """

    def __init__(
        self,
        backend: str,
        source: ConnectionSource,
        *,
        statement_timeout_ms: int = STATEMENT_TIMEOUT_MS,
        operation_timeout_ms: int = OPERATION_TIMEOUT_MS,
        toolkit: Toolkit | None = None,
        installing: InstallingSource | None = None,
    ) -> None:
        self.backend = backend
        self._source = source
        self._installing = installing
        self.statement_timeout_ms = _timeout("statement_timeout_ms", statement_timeout_ms)
        self.operation_timeout_ms = _timeout("operation_timeout_ms", operation_timeout_ms)
        self._toolkit = toolkit or TRUSS
        self._seen: BackendStatus | None = None

    def observed(self) -> BackendStatus | None:
        """What the last per-person call showed of the database: available when it reached Truss and
        began its transaction, and unavailable (with the reason it gave) when it could not get that
        far. None before any call. A person's refusal (an expired token, a missing grant) and an
        error inside the call say nothing of the database, and the installing connection is not a
        person's, so none of them is recorded. It is the only availability a host with no
        installing connection has, and no connection is made to learn it."""
        return self._seen

    def _observe(self, status: BackendStatus) -> None:
        self._seen = status

    def read(self, principal: Principal, operation: str) -> AbstractContextManager[Call]:
        """A read-only call: a `READ ONLY` transaction, always rolled back."""
        return self._call(principal, operation, True, self._source, True)

    def installer(self, operation: str) -> AbstractContextManager[Call] | None:
        """A read-only call on the installing connection, for the one read it is allowed (the
        install state: `status`); None when the host supplied no installing connection. Truss
        refuses an installer any business call, and no person is involved, so no token is checked."""
        if self._installing is None:
            return None
        installing = self._installing
        return self._call(Principal(INSTALLER, ""), operation, True, lambda _: installing(), False)

    def installer_write(
        self, operation: str, *, lock: int, timeout: float | None
    ) -> AbstractContextManager[Call] | None:
        """A read-write call on the installing connection, for install and module access;
        None when the host supplied none. The transaction takes `pg_advisory_xact_lock(lock)` before
        Truss adopts it, so the lock and everything after it are one transaction and release together
        at commit or rollback (it holds behind a transaction-mode pooler). `timeout` (seconds, None
        waits) bounds only that wait, through `lock_timeout` and `statement_timeout`: a wait that ends
        by either is `Unavailable(migration_failed)`, detail `timeout`. Truss then runs under the
        longest operation bound it admits (60 s), whatever `timeout` is."""
        if self._installing is None:
            return None
        installing = self._installing
        wait_ms = 0 if timeout is None else _wait_ms(timeout)
        name = self.backend

        def take_lock(conn: Any) -> Mapping[str, Any]:
            # Truss reports a role that cannot create roles as the one opaque refusal it gives for
            # everything, so the role's own attributes are read here, first, to name it afterwards
            row = conn.execute(
                "SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user"
            ).fetchone()
            facts = {"creates_roles": bool(_first(row))}
            try:
                conn.execute(f"SET LOCAL lock_timeout = '{wait_ms}ms'")
                conn.execute(f"SET LOCAL statement_timeout = '{wait_ms}ms'")
                conn.execute(f"SELECT pg_advisory_xact_lock({int(lock)})")
                conn.execute("SET LOCAL lock_timeout = '0ms'")
                return facts
            except Exception as exc:
                if getattr(exc, "sqlstate", None) in ("55P03", "57014"):
                    raise Unavailable(name, "migration_failed", "timeout") from None
                raise

        return self._call(
            Principal(INSTALLER, ""),
            operation,
            False,
            lambda _: installing(),
            False,
            before_adopt=take_lock,
            statement_ms=self.operation_timeout_ms,
        )

    def write(self, principal: Principal, operation: str) -> AbstractContextManager[Call]:
        """A read-write call: a `READ WRITE` transaction, committed when the block ends normally and `call.rollback`
        is false, rolled back otherwise."""
        return self._call(principal, operation, False, self._source, True)

    @contextmanager
    def _call(
        self,
        principal: Principal,
        operation: str,
        read_only: bool,
        source: Callable[[Principal], AbstractContextManager[Any]],
        person: bool,
        before_adopt: Callable[[Any], Mapping[str, Any]] | None = None,
        statement_ms: int | None = None,
    ) -> Generator[Call, None, None]:
        reached: list[bool] = []
        try:
            with self._enter(
                principal, operation, read_only, source, person, before_adopt, statement_ms, reached
            ) as call:
                yield call
        except Unavailable as exc:
            if person and not reached and exc.reason in _OBSERVED:
                self._observe(BackendStatus(False, cast(Any, exc.reason), exc.detail))
            raise

    @contextmanager
    def _enter(
        self,
        principal: Principal,
        operation: str,
        read_only: bool,
        source: Callable[[Principal], AbstractContextManager[Any]],
        person: bool,
        before_adopt: Callable[[Any], Mapping[str, Any]] | None,
        statement_ms: int | None,
        reached: list[bool],
    ) -> Generator[Call, None, None]:
        if person and not principal.token:
            raise Refused(self.backend, operation, "token_expired")

        def reach() -> None:
            reached.append(True)
            if person:
                self._observe(BackendStatus(True))

        try:
            with source(principal) as conn:
                yield from self._on(
                    conn,
                    principal,
                    operation,
                    read_only,
                    before_adopt,
                    statement_ms or self.statement_timeout_ms,
                    reach,
                )
        except ArrasError:
            raise
        except Exception as exc:
            if _is_operational(exc):
                raise _operational_error(self.backend, operation, exc) from None
            if _is_psycopg_error(exc):
                # any psycopg error escaping the call, the layer's own statements and the body
                # alike; the server's text is dropped
                raise Unavailable(self.backend, "unreachable", "database error") from None
            if isinstance(
                exc, ImportError
            ):  # ModuleNotFoundError too: the extra is absent or broken
                raise Unavailable(
                    self.backend, "not_configured", "the truss extra is not installed"
                ) from None
            if isinstance(exc, _PROGRAMMING):
                raise
            # Truss reports its own refusals as ValueError and RuntimeError whose text may carry
            # SQL or values: none of it leaves the layer
            raise Unavailable(self.backend, "unreachable", "truss error") from None

    def _on(
        self,
        conn: Any,
        principal: Principal,
        operation: str,
        read_only: bool,
        before_adopt: Callable[[Any], Mapping[str, Any]] | None,
        statement_ms: int,
        on_reach: Callable[[], None] | None = None,
    ) -> Iterator[Call]:
        name = self.backend
        if getattr(conn, "autocommit", False):
            raise Unavailable(name, "access_denied", "the connection has autocommit on")
        if conn.closed or getattr(conn, "broken", False):
            raise Unavailable(name, "unreachable", "connection lost")
        if int(conn.info.transaction_status) != 0:  # psycopg.pq.TransactionStatus.IDLE
            raise Unavailable(name, "access_denied", "the connection is not idle")
        host: Any = None
        call: Call | None = None
        try:
            conn.execute(_MODE_READ if read_only else _MODE_WRITE)
            # The value is a validated int: SET takes no bind parameters.
            conn.execute(f"SET LOCAL statement_timeout = '{statement_ms}ms'")
            self._require_no_role(conn)
            facts: Mapping[str, Any] = {}
            if before_adopt is not None:
                facts = before_adopt(conn)
                # Truss adopts only a live statement_timeout of 1 to 60,000 ms
                conn.execute(f"SET LOCAL statement_timeout = '{statement_ms}ms'")
            try:
                host = self._toolkit.adopt_host(conn, statement_ms, self.operation_timeout_ms)
            except ValueError as exc:
                if conn.closed or getattr(conn, "broken", False):
                    raise Unavailable(name, "unreachable", "connection lost") from None
                text = str(exc).lower()  # the message selects the detail and is never repeated
                if "attached or quarantined" in text:
                    _close(conn)
                    raise Unavailable(
                        name, "unreachable", "the connection is quarantined"
                    ) from None
                if "pipeline" in text:
                    raise Unavailable(
                        name, "access_denied", "the connection is in pipeline mode"
                    ) from None
                raise Unavailable(
                    name, "unsupported_version", "the driver or server is not the one Truss selects"
                ) from None
            try:
                tx, assembly = self._toolkit.begin(host, read_only)
            except _Refusal as refusal:
                if getattr(refusal.failure, "code", None) == "invalid_transaction":
                    raise Unavailable(
                        name, "access_denied", "the transaction profile differs"
                    ) from None
                raise failure_error(name, operation, refusal.failure) from None
            call = Call(name, operation, principal, assembly, tx, read_only, facts=facts)
            if on_reach is not None:
                on_reach()
            yield call
        except BaseException:
            self._abandon(conn, host, call)
            raise
        self._settle(conn, host, call)

    def _require_no_role(self, conn: Any) -> None:
        if _first(conn.execute("SELECT current_setting('role')").fetchone()) != "none":
            _close(conn)  # session state: the host's pool must discard the connection (D5)
            raise Unavailable(
                self.backend, "access_denied", "the connection has a session role set"
            )

    def _abandon(self, conn: Any, host: Any, call: Call | None) -> None:
        clean = not (call is not None and call.quarantined)
        if host is not None:
            try:
                clean = host.detach() is not False and clean
            except Exception:
                clean = False
        try:
            if not conn.closed:
                conn.rollback()
        except Exception:
            clean = False
        if not clean or conn.closed or getattr(conn, "broken", False):
            _close(conn)

    def _settle(self, conn: Any, host: Any, call: Call | None) -> None:
        name = self.backend
        assert call is not None
        try:
            clean = host.detach() is not False and not call.quarantined
        except Exception:
            clean = False
        if not clean:
            try:
                conn.rollback()
            except Exception:
                pass
            _close(conn)
            raise Unavailable(name, "unreachable", "the connection was quarantined")
        if not (call.read_only or call.rollback) and not self._in_progress(conn):
            try:
                conn.rollback()
            except Exception:
                _close(conn)
            raise Unavailable(name, "unreachable", "the transaction was aborted")
        if not call.read_only:
            # Truss's deferred checks run at COMMIT, which a dry run never reaches. Run now, they
            # fail inside the call for a dry run and a write alike, so a COMMIT that fails is only
            # ever an unknown outcome, and the write that raises here has committed nothing. A
            # server-reported error on an idle connection leaves the connection open, as a refused
            # COMMIT does; a timeout, a lost connection or a non-psycopg error maps as elsewhere.
            try:
                conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
            except Exception as exc:
                raise self._deferred_failure(conn, call.operation, exc) from None
        if call.read_only or call.rollback:
            try:
                conn.rollback()
            except Exception:
                _close(conn)
                raise Unavailable(name, "unreachable", "cannot settle the transaction") from None
            return
        try:
            conn.commit()
        except Exception as exc:
            if not _commit_unknown(conn, exc):
                # the server refused the COMMIT: the transaction rolled back and the connection is idle
                raise Unavailable(name, "unreachable", "the commit was refused") from None
            _close(conn)
            raise CommitUnknown(name) from None

    def _deferred_failure(self, conn: Any, operation: str, exc: Exception) -> ArrasError:
        """The error for a failed `SET CONSTRAINTS ALL IMMEDIATE`, after the rollback. The connection
        is closed only when the rollback failed or it is closed or broken, or the error is not one the
        server reported (a non-psycopg error, no SQLSTATE, class 08 or `57P01` to `57P03`)."""
        name = self.backend
        rolled_back = True
        try:
            conn.rollback()
        except Exception:
            rolled_back = False  # a dead connection; closed below
        state = getattr(exc, "sqlstate", None) if _is_psycopg_error(exc) else None
        connect = state is not None and (state.startswith("08") or state in _CONNECT_STATES)
        lost = not _is_psycopg_error(exc) or state is None or connect
        try:
            lost = lost or conn.closed or bool(getattr(conn, "broken", False))
        except Exception:
            lost = True
        if lost or not rolled_back:
            _close(conn)
            if _is_operational(exc):
                return _operational_error(name, operation, exc)
            if connect:
                return classify_connect_error(name, operation, exc)
            return Unavailable(name, "unreachable", "database error")
        if state == "57014":
            return Unavailable(name, "unreachable", "statement timeout")
        return Unavailable(name, "unreachable", "a deferred check of the write failed")

    @staticmethod
    def _in_progress(conn: Any) -> bool:
        try:
            return int(conn.info.transaction_status) == _INTRANS
        except Exception:
            return False
