# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The Truss adapter's lifecycle (TR-13): the factory, install-or-verify, module
access and `status`.

The always-on tests drive a scripted assembly through the connection layer's `Toolkit` seam and a
recording connection (Truss adopts only a real `psycopg.Connection`). The Truss-marked tests install
into real empty databases on PostgreSQL 18.6 (`uv run --extra truss --group truss-test pytest -m
truss`).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from arras import Arras
from arras.adapters.truss import (
    Connections,
    ModuleAccess,
    TrussBackend,
    create_backend,
)
from arras.adapters.truss.connection import Toolkit
from arras.adapters.truss.lifecycle import INSTALL_LOCK
from arras.errors import Refused, Unavailable
from arras.results import MigrationResult
from arras.types import Principal
from arras.umf import parse_module
from test_truss_connection import FakeConn
from test_truss_harness import MODULE_TEXT, _world, cluster  # noqa: F401

RELEASE = "truss-catalog-runtime/0.74-candidate"


needs_toolkit = pytest.mark.skipif(
    importlib.util.find_spec("truss") is None,
    reason="the truss extra is not installed",
)


def ok(value: Any) -> Any:
    return SimpleNamespace(status="ok", value=value)


def err(code: str = "invalid_transaction", **fields: Any) -> Any:
    fields.setdefault("sql_state", None)
    fields.setdefault("catalog_code", None)
    return SimpleNamespace(status="error", error=SimpleNamespace(code=code, **fields))


class Script:
    """A scripted Truss assembly: what it is asked, in order, and what it answers."""

    def __init__(self, *, installed: bool = False, revision: int = 0) -> None:
        self.installed = installed
        self.revision = revision
        self.installation_id = "inst-a" if installed else None
        self.refuse_modules: set[str] = set()
        self.calls: list[str] = []
        self.status_answer: Any = None
        self.install_answer: Any = None
        self.configure_answer: Any = None
        self.grants: tuple[Any, ...] = ()
        self.install_tolerated_grantees: tuple[str, ...] | None = None

    def status_in_transaction(self, tx: Any) -> Any:
        self.calls.append("status")
        return self.status_answer or ok(
            SimpleNamespace(
                installed=self.installed,
                installation_id=self.installation_id,
                revision=self.revision if self.installed else None,
                release_id=RELEASE if self.installed else None,
            )
        )

    def install_in_transaction(
        self, tx: Any, *, tolerated_grantees: tuple[str, ...] = ()
    ) -> Any:
        self.calls.append("install")
        self.install_tolerated_grantees = tolerated_grantees
        if self.install_answer is not None:
            return self.install_answer
        self.installed = True
        self.installation_id = "inst-a"
        return ok(
            SimpleNamespace(
                installation_id="inst-a",
                owner_role="truss_owner_0123456789abcdef",
                registrar_role="truss_registrar_0123456789abcdef",
                release_id=RELEASE,
            )
        )

    def configure_module_access_in_transaction(self, tx: Any, grants: tuple[Any, ...]) -> Any:
        self.calls.append("configure")
        self.grants = grants
        if self.refuse_modules & {g.module_id for g in grants}:
            return err()
        return self.configure_answer or ok(SimpleNamespace(grants=grants))


class StateError(Exception):
    def __init__(self, sqlstate: str | None) -> None:
        super().__init__("server text that must never appear")
        self.sqlstate = sqlstate


class LockConn(FakeConn):
    """A connection whose statements can be made to raise."""

    raises: dict[str, Exception]

    def __init__(self, raises: dict[str, Exception], creates_roles: bool = True, **kw: Any) -> None:
        super().__init__(**kw)
        self.raises = raises
        self.creates_roles = creates_roles

    def execute(self, sql: str) -> Any:
        if "rolcreaterole" in sql:
            self.log.append(sql)
            return SimpleNamespace(fetchone=lambda: (self.creates_roles,))
        for fragment, exc in self.raises.items():
            if fragment in sql:
                self.log.append(sql)
                raise exc
        return super().execute(sql)


class Rig:
    def __init__(self, script: Script | None = None, **kw: Any) -> None:
        self.script = script or Script()
        self.conns: list[FakeConn] = []
        self.raises: dict[str, Exception] = {}
        self.first_commit_raises: Exception | None = None
        self.source_error: Exception | None = None
        self.adopt_error: Exception | None = None
        self.creates_roles = True
        self.adopted: list[int] = []
        self.kw = kw

    @contextmanager
    def installing(self) -> Iterator[FakeConn]:
        if self.source_error:
            raise self.source_error
        conn = LockConn(self.raises, self.creates_roles)
        if self.first_commit_raises and not self.conns:
            conn.commit_raises = self.first_commit_raises
        self.conns.append(conn)
        yield conn

    @contextmanager
    def person(self, principal: Principal) -> Iterator[FakeConn]:
        raise AssertionError("a person's connection is never used by the lifecycle")
        yield  # pragma: no cover

    def toolkit(self) -> Toolkit:
        def adopt(conn: FakeConn, statement: int, operation: int) -> Any:
            if self.adopt_error:
                raise self.adopt_error
            conn.log.append("adopt")
            self.adopted.append(statement)
            return SimpleNamespace(detach=lambda: conn.log.append("detach") or True)

        return Toolkit(adopt, lambda host, read_only: ("tx", self.script))

    def backend(self, **kw: Any) -> TrussBackend:
        conns = Connections(
            "truss", self.person, installing=self.installing, toolkit=self.toolkit()
        )
        return TrussBackend("truss", conns, **dict(self.kw, **kw))


def test_migrate_installs_an_absent_truss_after_taking_the_lock() -> None:
    rig = Rig()
    result = rig.backend().migrate()
    assert result == MigrationResult(
        True, RELEASE, "truss_owner_0123456789abcdef", "truss_registrar_0123456789abcdef"
    )
    assert rig.script.calls == ["status", "install"]
    assert rig.script.install_tolerated_grantees == ()
    log = rig.conns[0].log
    assert log[0] == "SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ WRITE"
    lock = log.index(f"SELECT pg_advisory_xact_lock({INSTALL_LOCK})")
    assert lock < log.index("adopt")  # one transaction: the lock first, Truss after
    assert log[lock - 2 : lock] == [
        "SET LOCAL lock_timeout = '0ms'",
        "SET LOCAL statement_timeout = '0ms'",
    ]  # no timeout given: the wait is unbounded
    assert log[-3:] == ["detach", "SET CONSTRAINTS ALL IMMEDIATE", "commit"]
    assert "rollback" not in log
    assert rig.adopted == [60_000]  # Truss's longest admitted bound, never the unbounded wait


def test_migrate_verifies_a_present_truss_and_installs_nothing() -> None:
    selected = ("lakebase_reader",)
    rig = Rig(Script(installed=True), tolerated_grantees=selected)
    assert rig.backend().migrate() == MigrationResult(False, RELEASE)
    assert rig.script.calls == ["status"]
    assert rig.script.install_tolerated_grantees is None


def test_fresh_install_passes_the_exact_tolerated_tuple_once() -> None:
    selected = ("raw_reader", "lakebase_reader")
    rig = Rig(tolerated_grantees=selected)
    assert rig.backend().migrate().ran is True
    assert rig.script.install_tolerated_grantees is selected
    assert rig.script.calls == ["status", "install"]


@pytest.mark.parametrize(
    "bad",
    [
        ["reader"],
        ("reader",) * 33,
        ("",),
        ("x" * 64,),
        ("\x00role",),
        ("\ud800",),
        (type("RoleString", (str,), {})("reader"),),
    ],
)
def test_malformed_tolerated_grantees_are_rejected_before_connection_creation(
    bad: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    import arras.adapters.truss as adapter

    def no_connection(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the malformed carrier must fail before connection creation")

    monkeypatch.setattr(adapter, "Connections", no_connection)
    with pytest.raises(ValueError):
        create_backend("truss", lambda _principal: None, tolerated_grantees=bad)  # type: ignore[arg-type]


def test_the_migrate_timeout_bounds_the_lock_wait_not_truss() -> None:
    rig = Rig()
    rig.backend().migrate(timeout=600)  # far beyond Truss's 60 s bound
    log = rig.conns[0].log
    assert "SET LOCAL lock_timeout = '600000ms'" in log
    assert log[log.index("adopt") - 1] == "SET LOCAL statement_timeout = '60000ms'"
    assert rig.adopted == [60_000]
    rig = Rig()
    rig.backend().migrate(timeout=0.0004)
    assert "SET LOCAL lock_timeout = '1ms'" in rig.conns[0].log


@pytest.mark.parametrize("bad", [0, -1, float("nan"), True])
def test_a_timeout_that_is_not_positive_is_refused(bad: float) -> None:
    with pytest.raises(ValueError):
        Rig().backend().migrate(timeout=bad)


@pytest.mark.parametrize("state", ["55P03", "57014"])
def test_a_lock_wait_that_runs_out_is_a_migration_timeout_and_status_says_so(state: str) -> None:
    rig = Rig()
    rig.raises = {"pg_advisory_xact_lock": StateError(state)}
    backend = rig.backend()
    with pytest.raises(Unavailable) as caught:
        backend.migrate(timeout=0.3)
    assert (caught.value.reason, caught.value.detail) == ("migration_failed", "timeout")
    assert rig.script.calls == [] and "adopt" not in rig.conns[0].log
    assert rig.conns[0].log[-1] == "rollback"
    status = (
        backend.status()
    )  # the rolled-back install left Truss absent; the failure is remembered
    assert (status.available, status.reason, status.detail) == (
        False,
        "migration_failed",
        "timeout",
    )
    rig.raises = {}
    assert backend.migrate().ran is True
    assert backend.status().available is True


def test_the_remembered_failure_ends_when_truss_is_seen_installed() -> None:
    rig = Rig()
    rig.script.install_answer = err()
    backend = rig.backend()
    with pytest.raises(Unavailable):
        backend.migrate()
    assert backend.status().reason == "migration_failed"
    rig.script.installed = True  # someone else installed it
    rig.script.install_answer = None
    assert backend.status().available is True
    assert backend.status().available is True  # and the failure is not reported again


def test_an_install_failure_is_migration_failed_and_never_repeats_truss() -> None:
    rig = Rig()
    rig.script.install_answer = err(message="Original transaction/profile admission refused")
    with pytest.raises(Unavailable) as caught:
        rig.backend().migrate()
    assert (caught.value.reason, caught.value.detail) == (
        "migration_failed",
        "truss invalid_transaction",
    )
    assert "admission" not in str(caught.value)
    assert rig.conns[0].log[-1] == "rollback"


def test_an_installer_without_the_privileges_is_access_denied_never_refused() -> None:
    rig = Rig()
    rig.script.install_answer = err("execution_obligation", sql_state="42501")
    backend = rig.backend()
    with pytest.raises(Unavailable) as caught:
        backend.migrate()
    assert caught.value.reason == "access_denied" and not isinstance(caught.value, Refused)
    # a missing privilege is not a failed install: status does not claim migration_failed
    assert backend.status().reason != "migration_failed"


def test_an_installer_that_cannot_create_roles_is_access_denied_after_truss_refuses() -> None:
    rig = Rig()
    rig.creates_roles = False
    rig.script.install_answer = err()  # Truss's one opaque refusal
    backend = rig.backend()
    with pytest.raises(Unavailable) as caught:
        backend.migrate()
    assert caught.value.reason == "access_denied"
    assert rig.script.calls == ["status", "install"]  # the decision still came from the status read
    assert backend.status().reason != "migration_failed"


def test_another_release_is_unsupported_version_and_nothing_is_installed() -> None:
    rig = Rig()
    rig.script.status_answer = err(catalog_code="unsupported_profile")
    backend = rig.backend()
    with pytest.raises(Unavailable) as caught:
        backend.migrate()
    assert caught.value.reason == "unsupported_version"
    assert rig.script.calls == ["status"]
    assert backend.status().reason == "unsupported_version"


def test_no_installing_connection_is_not_configured() -> None:
    backend = create_backend("truss", Rig().person)
    with pytest.raises(Unavailable) as caught:
        backend.migrate()
    assert (caught.value.reason, caught.value.detail) == (
        "not_configured",
        "no installing connection",
    )
    assert backend.status().reason == "not_configured"


def _observing() -> tuple[Any, TrussBackend]:
    """A backend with no installing connection over the connection layer's recording rig."""
    from test_truss_connection import Rig as PersonRig

    person = PersonRig()
    return person, TrussBackend("truss", person.connections())


def test_with_no_installing_connection_status_says_nothing_is_known_until_a_call_is_seen() -> None:
    person, backend = _observing()
    status = backend.status()
    assert (status.available, status.reason, status.detail) == (
        False,
        "not_configured",
        "no installing connection",
    )
    assert person.principals == []  # a status never connects, as a person or as anyone


def test_with_no_installing_connection_status_follows_the_last_per_person_call() -> None:
    person, backend = _observing()
    with backend.connections.read(Principal("carol", "t"), "query"):  # type: ignore[union-attr]
        pass
    assert backend.status().available is True and backend.status().reason is None
    assert len(person.principals) == 1  # the one call; the status asked nothing more


def test_with_no_installing_connection_a_failure_to_reach_the_database_is_reported() -> None:
    psycopg = pytest.importorskip("psycopg")
    person, backend = _observing()
    conns = backend.connections
    assert conns is not None
    with conns.read(Principal("carol", "t"), "query"):
        pass

    @contextmanager
    def down(principal: Principal) -> Iterator[Any]:
        raise psycopg.OperationalError("connection refused: secret")
        yield  # pragma: no cover

    conns._source = down  # type: ignore[assignment]
    with pytest.raises(Unavailable):
        with conns.read(Principal("carol", "t"), "query"):
            pass
    status = backend.status()
    assert (status.available, status.reason, status.detail) == (
        False,
        "unreachable",
        "cannot connect",
    )
    assert "secret" not in status.detail
    conns._source = person.source  # type: ignore[assignment]
    with conns.read(Principal("carol", "t"), "query"):
        pass
    assert backend.status().available is True  # the outage ended


def test_what_one_person_is_refused_or_a_call_body_raises_is_not_an_outage() -> None:
    psycopg = pytest.importorskip("psycopg")
    person, backend = _observing()
    conns = backend.connections
    assert conns is not None
    with conns.read(Principal("carol", "t"), "query"):
        pass
    with pytest.raises(Refused):  # no token: the person's, before any connection
        with conns.read(Principal("carol", ""), "query"):
            pass

    @contextmanager
    def wrong(principal: Principal) -> Iterator[Any]:
        raise psycopg.OperationalError("FATAL: password authentication failed for user 'carol'")
        yield  # pragma: no cover

    real = conns._source
    conns._source = wrong  # type: ignore[assignment]
    with pytest.raises(Refused):  # a wrong or expired token is the person's
        with conns.read(Principal("carol", "t"), "query"):
            pass
    conns._source = real
    with pytest.raises(Unavailable):  # a body that is busy reached the database
        with conns.read(Principal("carol", "t"), "query"):
            raise Unavailable("truss", "busy", "later")
    assert backend.status().available is True


def test_the_installing_connection_governs_status_when_the_host_supplies_one() -> None:
    rig = Rig(Script(installed=True))
    backend = rig.backend()
    assert backend.status().available is True
    assert rig.conns  # asked on the installing connection


def test_truss_absent_is_not_configured_for_migrate_and_status() -> None:
    rig = Rig()
    rig.adopt_error = ImportError("No module named 'truss'")
    backend = rig.backend()
    with pytest.raises(Unavailable) as caught:
        backend.migrate()
    assert (caught.value.reason, caught.value.detail) == (
        "not_configured",
        "the truss extra is not installed",
    )
    assert backend.status().reason == "not_configured"


@needs_toolkit
def test_an_unreachable_installing_connection_is_unreachable() -> None:
    import psycopg

    rig = Rig()
    rig.source_error = psycopg.OperationalError("connection refused to /secret/socket")
    backend = rig.backend()
    with pytest.raises(Unavailable) as caught:
        backend.migrate()
    assert caught.value.reason == "unreachable" and "secret" not in str(caught.value)
    assert backend.status().reason == "unreachable"
    assert backend.status().reason == "unreachable"  # and status never raises


def test_a_commit_of_unknown_outcome_with_our_installation_id_returns_the_names() -> None:
    rig = Rig()
    rig.first_commit_raises = Exception("connection lost")  # no SQLSTATE: the outcome is unknown
    result = rig.backend().migrate()
    # the status read sees the id this call's install produced: the names it holds are returned
    assert result.ran is True and result.registrar_role == "truss_registrar_0123456789abcdef"
    assert result.owner_role == "truss_owner_0123456789abcdef"
    assert rig.conns[0].log[-1] == "close" and len(rig.conns) == 2


def test_a_commit_of_unknown_outcome_with_another_installation_id_is_not_ours() -> None:
    rig = Rig()
    rig.first_commit_raises = Exception("connection lost")
    original = rig.script.install_in_transaction

    def another_instance_won(tx: Any, *, tolerated_grantees: tuple[str, ...] = ()) -> Any:
        out = original(tx, tolerated_grantees=tolerated_grantees)
        rig.script.installation_id = "inst-b"  # the committed install is another instance's
        return out

    rig.script.install_in_transaction = another_instance_won  # type: ignore[method-assign]
    backend = rig.backend()
    result = backend.migrate()
    assert result == MigrationResult(False, RELEASE)
    assert result.owner_role is None and result.registrar_role is None
    assert backend.status().available is True


@pytest.mark.parametrize("read", ["absent", "failing"])
def test_a_commit_of_unknown_outcome_with_no_readable_truss_is_migration_failed(read: str) -> None:
    rig = Rig()
    rig.first_commit_raises = Exception("connection lost")
    backend = rig.backend()
    original = rig.script.install_in_transaction

    def install_then_vanish(tx: Any, *, tolerated_grantees: tuple[str, ...] = ()) -> Any:
        out = original(tx, tolerated_grantees=tolerated_grantees)
        if read == "absent":
            rig.script.installed = False  # the commit never happened
        else:
            rig.script.status_answer = err()  # the read fails
        return out

    rig.script.install_in_transaction = install_then_vanish  # type: ignore[method-assign]
    with pytest.raises(Unavailable) as caught:
        backend.migrate()
    assert (caught.value.reason, caught.value.detail) == ("migration_failed", "outcome unknown")


def test_a_commit_of_unknown_outcome_on_the_verify_path_is_settled_by_a_status_read() -> None:
    rig = Rig(Script(installed=True))
    rig.first_commit_raises = Exception("connection lost")
    assert rig.backend().migrate() == MigrationResult(False, RELEASE)
    assert len(rig.conns) == 2
    rig = Rig(Script(installed=True))
    rig.first_commit_raises = Exception("connection lost")
    first_read = rig.script.status_in_transaction

    def fail_after_the_first(tx: Any) -> Any:
        rig.script.status_in_transaction = lambda t: err()  # type: ignore[method-assign]
        return first_read(tx)

    rig.script.status_in_transaction = fail_after_the_first  # type: ignore[method-assign]
    with pytest.raises(Unavailable) as caught:
        rig.backend().migrate()
    assert caught.value.detail == "outcome unknown"


ACCESS = {"catalog": ModuleAccess("sandbox", "catalog_reader", "catalog_writer")}


def test_migrate_does_not_grant_module_access() -> None:
    for script in (Script(installed=True, revision=1), Script()):
        rig = Rig(script, module_access=ACCESS)
        rig.backend().migrate()
        assert "configure" not in rig.script.calls


@needs_toolkit
def test_configure_access_hands_the_host_roles_to_truss() -> None:
    rig = Rig(Script(installed=True, revision=1), module_access=ACCESS)
    rig.backend().configure_access()
    assert rig.script.calls == ["configure"]
    (grant,) = rig.script.grants
    assert (grant.document_id, grant.module_id, grant.reader_role, grant.writer_role) == (
        "sandbox",
        "catalog",
        "catalog_reader",
        "catalog_writer",
    )


@needs_toolkit
def test_configure_access_grants_one_module_per_transaction_and_stops_at_a_refusal() -> None:
    access = {
        "alpha": ModuleAccess("alpha", "alpha_r", "alpha_w"),
        "beta": ModuleAccess("beta", "beta_r", "beta_w"),
        "gamma": ModuleAccess("gamma", "gamma_r", "gamma_w"),
    }
    rig = Rig(Script(installed=True, revision=1), module_access=access)
    rig.script.refuse_modules = {"beta"}
    with pytest.raises(Unavailable) as caught:
        rig.backend().configure_access()
    assert caught.value.reason == "migration_failed"
    assert "'beta'" in (caught.value.detail or "") and "'gamma'" not in caught.value.detail
    assert "invalid_transaction" in caught.value.detail  # the mapped reason, no Truss text
    assert rig.script.calls == ["configure", "configure"]  # gamma was never tried
    first, second = rig.conns
    assert first.log[-1] == "commit" and second.log[-1] == "rollback"  # alpha stays configured


@needs_toolkit
def test_a_refused_module_access_is_migration_failed() -> None:
    rig = Rig(Script(installed=True, revision=1), module_access=ACCESS)
    rig.script.configure_answer = err()
    with pytest.raises(Unavailable) as caught:
        rig.backend().configure_access()
    assert caught.value.reason == "migration_failed" and "'catalog'" in caught.value.detail
    assert rig.conns[0].log[-1] == "rollback"


@needs_toolkit
def test_configure_access_names_modules_the_host_supplied() -> None:
    rig = Rig(Script(installed=True, revision=1), module_access=ACCESS)
    backend = rig.backend()
    backend.configure_access(["catalog"])
    assert rig.script.calls == ["configure"]
    with pytest.raises(ValueError):
        backend.configure_access(["unknown"])
    rig.script.calls.clear()
    backend.configure_access([])  # an empty list is a no-op
    Rig(module_access={}).backend().configure_access()  # nothing to hand over: no connection
    assert rig.script.calls == []


@pytest.mark.parametrize(
    ("document", "reader", "writer"),
    [("", "r", "w"), ("d", "", "w"), ("d", "r", "r"), ("d", "r" * 64, "w"), ("d", "r", "é" * 32)],
)
def test_module_access_refuses_roles_truss_would_refuse(
    document: str, reader: str, writer: str
) -> None:
    with pytest.raises(ValueError):
        ModuleAccess(document, reader, writer)


@needs_toolkit
def test_a_busy_catalog_is_busy_for_migrate_and_configure_access() -> None:
    # migrate and configure_access meet 55P03 from a concurrent registration
    busy = err("execution_obligation", sql_state="55P03")
    rig = Rig(Script(installed=True, revision=1), module_access=ACCESS)
    rig.script.configure_answer = busy
    with pytest.raises(Unavailable) as caught:
        rig.backend().configure_access()
    assert "the catalog is busy" in caught.value.detail
    rig = Rig()
    rig.script.install_answer = busy
    with pytest.raises(Unavailable) as caught:
        rig.backend().migrate()
    assert caught.value.detail == "the catalog is busy"


def test_the_factory_checks_the_name_and_never_connects() -> None:
    for bad in ("", "Truss", "1truss", "t" * 42, "a-b"):
        with pytest.raises(ValueError):
            create_backend(bad, None)
    code = (
        "import sys\n"
        "from arras.adapters.truss import create_backend\n"
        "b = create_backend('truss', None)\n"
        "assert b.status().reason == 'not_configured'\n"
        "assert not {'truss', 'psycopg'} & set(sys.modules), sorted(sys.modules)\n"
    )
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    backend = create_backend("truss_a", None)
    assert backend.name == "truss_a" and backend.status().detail == "no connection source"
    with pytest.raises(Unavailable) as caught:
        backend.migrate()
    assert caught.value.reason == "not_configured"


def test_arras_migrate_reaches_the_adapter_and_a_failure_is_reported() -> None:
    rig = Rig()
    backend = rig.backend()
    ar = Arras.start({"truss": backend})  # type: ignore[dict-item]
    assert ar.migrate(timeout=1).ran is True
    assert ar.migrate().ran is False
    rig.script.installed = False
    rig.raises = {"pg_advisory_xact_lock": StateError("55P03")}
    with pytest.raises(Unavailable):
        ar.migrate(timeout=0.1)
    assert ar.status()["truss"].reason == "migration_failed"


def test_two_connections_share_one_lock_key() -> None:
    first, second = Rig(), Rig()
    first.backend().migrate()
    second.backend().migrate()
    lock = f"SELECT pg_advisory_xact_lock({INSTALL_LOCK})"
    assert lock in first.conns[0].log and lock in second.conns[0].log
    assert -(2**63) <= INSTALL_LOCK < 2**63


def test_a_person_connection_is_never_used() -> None:
    rig = Rig()
    backend = rig.backend()
    backend.migrate()
    backend.status()
    threads = [threading.Thread(target=backend.status) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


# -- against PostgreSQL 18.6


def _login_and_super(conn: Any, role: str) -> tuple[bool, bool]:
    row = conn.execute(
        "SELECT rolcanlogin, rolsuper FROM pg_roles WHERE rolname = %s", [role]
    ).fetchone()
    return row[0], row[1]


@pytest.mark.truss
def test_migrate_installs_an_empty_database_once(cluster: Any) -> None:  # noqa: F811
    with cluster.bare_database() as bare:
        backend = bare.backend()
        assert backend.status().reason == "not_configured"  # Truss is not there yet
        first = backend.migrate()
        assert first.ran is True and first.revision == RELEASE
        assert first.owner_role and first.registrar_role
        assert first.owner_role != first.registrar_role
        with cluster.superuser(bare.db) as su:
            for role in (first.owner_role, first.registrar_role):
                assert _login_and_super(su, role) == (False, False)  # NOLOGIN, never a superuser
        assert backend.status().available is True
        assert backend.migrate() == MigrationResult(False, RELEASE)  # present: verified, no names


@pytest.mark.truss
def test_two_instances_migrating_together_run_one_install(cluster: Any) -> None:  # noqa: F811
    with cluster.bare_database() as bare:
        backends = [bare.backend(), bare.backend()]
        barrier = threading.Barrier(2)
        results: list[Any] = []

        def go(backend: TrussBackend) -> None:
            barrier.wait()
            try:
                results.append(backend.migrate(timeout=60))
            except Exception as exc:  # a failure must show in the assertion below
                results.append(exc)

        threads = [threading.Thread(target=go, args=(b,)) for b in backends]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(isinstance(r, MigrationResult) for r in results), results
        assert sorted(r.ran for r in results) == [False, True]


@pytest.mark.truss
def test_a_migrate_that_waits_longer_than_its_timeout_is_a_migration_timeout(cluster: Any) -> None:  # noqa: F811
    import time

    with cluster.bare_database() as bare:
        backend = bare.backend()
        with bare.installing_connection() as holder:
            holder.execute("BEGIN")
            holder.execute(f"SELECT pg_advisory_xact_lock({INSTALL_LOCK})")
            started = time.monotonic()
            with pytest.raises(Unavailable) as caught:
                backend.migrate(timeout=0.4)
            assert time.monotonic() - started < 5
            assert (caught.value.reason, caught.value.detail) == ("migration_failed", "timeout")
            assert backend.status().reason == "migration_failed"
            holder.rollback()
        assert backend.migrate().ran is True
        assert backend.status().available is True


@pytest.mark.truss
def test_an_installer_that_cannot_create_roles_is_access_denied(cluster: Any) -> None:  # noqa: F811
    with cluster.bare_database(owner="arras_plain") as bare:
        backend = bare.backend()
        with pytest.raises(Unavailable) as caught:
            backend.migrate()
        assert caught.value.reason == "access_denied"
        assert backend.status().reason != "migration_failed"


@pytest.mark.truss
def test_migrate_reports_the_outages_the_status_read_reports(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster)
    backend = h.backend()
    assert backend.migrate() == MigrationResult(False, RELEASE)  # a present Truss is verified
    h.outage("unsupported_version")
    with pytest.raises(Unavailable) as caught:
        backend.migrate()
    assert caught.value.reason == "unsupported_version"
    h.outage("unreachable")
    with pytest.raises(Unavailable) as caught:
        backend.migrate()
    assert caught.value.reason == "unreachable"
    h.outage("access_denied")
    with pytest.raises(Unavailable) as caught:
        backend.migrate()
    assert caught.value.reason == "access_denied"
    h.outage(None)
    assert backend.migrate().ran is False


@pytest.mark.truss
def test_install_then_register_then_configure_access_then_read(cluster: Any) -> None:  # noqa: F811
    from arras.types import Revision
    from truss_harness import document_id

    module = parse_module(MODULE_TEXT)
    document = MODULE_TEXT.encode()
    with cluster.bare_database() as bare:
        reader = bare.role("lc_reader")
        writer = bare.role("lc_writer")
        access = {module.name: ModuleAccess(document_id(document), reader, writer)}
        backend = bare.backend(module_access=access)
        migrated = backend.migrate()  # install-or-verify only: no module access
        assert migrated.ran is True and migrated.registrar_role
        alice = bare.person("lc_alice", migrated.registrar_role)
        carol = bare.person("lc_carol", reader)
        got = backend.register(alice, document, module, unknown_endpoint="reject")
        assert got.revision == Revision({"truss": 1})
        assert backend.migrate().ran is False  # and still none after a registration
        assert backend.catalog(carol) == {}  # no module access yet: nobody reads it
        backend.configure_access()  # after registration, the host's roles reach Truss
        assert set(backend.catalog(carol)) == {module.name}
        backend.configure_access([module.name])  # and the explicit call repeats harmlessly
        assert set(backend.catalog(carol)) == {module.name}


@pytest.mark.truss
def test_an_unregistered_module_fails_configure_access_not_migrate(cluster: Any) -> None:  # noqa: F811
    from truss_harness import document_id

    module = parse_module(MODULE_TEXT)
    document = MODULE_TEXT.encode()
    with cluster.bare_database() as bare:
        reader, writer = bare.role("lc_reader"), bare.role("lc_writer")
        ghost_reader, ghost_writer = bare.role("lc_ghost_r"), bare.role("lc_ghost_w")
        access = {
            module.name: ModuleAccess(document_id(document), reader, writer),
            "ghost": ModuleAccess("ghost_document", ghost_reader, ghost_writer),
        }
        backend = bare.backend(module_access=access)
        migrated = backend.migrate()
        assert migrated.ran is True and migrated.registrar_role
        alice = bare.person("lc_alice", migrated.registrar_role)
        carol = bare.person("lc_carol", reader)
        backend.register(alice, document, module, unknown_endpoint="reject")
        assert backend.migrate().ran is False  # the unregistered module does not fail it
        with pytest.raises(Unavailable) as caught:
            backend.configure_access()
        assert caught.value.reason == "migration_failed" and "'ghost'" in caught.value.detail
        assert set(backend.catalog(carol)) == {module.name}  # first in order: it stays configured
        backend.configure_access((module.name,))
        assert set(backend.catalog(carol)) == {module.name}


@pytest.mark.truss
def test_the_installing_calls_run_as_the_installer(cluster: Any) -> None:  # noqa: F811
    with cluster.bare_database() as bare:
        seen: list[str] = []

        @contextmanager
        def watched() -> Iterator[Any]:
            with bare.installing_connection() as conn:
                seen.append(conn.execute("SELECT session_user").fetchone()[0])
                conn.rollback()  # hand the connection over idle, as a source must
                yield conn

        backend = create_backend("truss", bare.connection_source, watched)
        backend.migrate()
        backend.status()
        assert seen == [bare.installer, bare.installer]


# -- Truss 0.0.44's typed install, grant and recovery outcomes (plan B8)


@dataclass(frozen=True)
class InstallRefused:
    code: str
    role_name: Any = None
    object_class: Any = None
    phase: Any = None


@dataclass(frozen=True)
class ModuleAccessError:
    index: int
    code: str


@dataclass(frozen=True)
class ModuleAccessBatchRefused:
    errors: tuple[ModuleAccessError, ...]


@dataclass(frozen=True)
class AuditAccessUpdated:
    document_id: str


@dataclass(frozen=True)
class LoadAuditUnavailable:
    reason: str


@dataclass(frozen=True)
class AdminInstallRecovery:
    owner_role: str
    registrar_role: str


@dataclass(frozen=True)
class LifecycleRefused:
    reason: str


class Typed(Script):
    """A scripted assembly that also answers the typed families."""

    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        self.audit_answer: Any = ok(AuditAccessUpdated("sandbox"))
        self.recovery_answer: Any = ok(AdminInstallRecovery("owner_x", "registrar_x"))
        self.audited: list[Any] = []
        self.installed_by_other = False

    def status_in_transaction(self, tx: Any) -> Any:
        if self.installed_by_other and "install" in self.calls:
            self.installed, self.installation_id, self.revision = True, "inst-b", 0
        return super().status_in_transaction(tx)

    def grant_module_audit_access_in_transaction(self, tx: Any, grant: Any) -> Any:
        self.calls.append("audit")
        self.audited.append(grant)
        return self.audit_answer

    def admin_install_recovery_in_transaction(self, tx: Any) -> Any:
        self.calls.append("recovery")
        return self.recovery_answer


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("busy", "busy"),
        ("incompatible", "unsupported_version"),
        ("unsupported_postgres", "unsupported_version"),
        ("unauthorized", "access_denied"),
        ("read_only", "access_denied"),
        ("invalid_roles", "migration_failed"),
        ("role_exists", "migration_failed"),
    ],
)
def test_a_typed_install_refusal_is_the_error_of_its_code_and_installs_nothing(
    code: str, reason: str
) -> None:
    rig = Rig(Typed())
    rig.script.install_answer = ok(InstallRefused(code))
    backend = rig.backend()
    with pytest.raises(Unavailable) as caught:
        backend.migrate()
    assert caught.value.reason == reason
    assert rig.conns[0].log[-1] == "rollback" and "commit" not in rig.conns[0].log
    assert backend.status().reason != "migration_failed" or reason == "migration_failed"


def test_a_third_party_grant_refusal_names_bounded_escaped_context_and_rolls_back() -> None:
    import json

    role = 'vendor"role\\line\n café'
    rig = Rig(Typed())
    rig.creates_roles = False  # typed detail must not enter the opaque missing-CREATEROLE mapping
    rig.script.install_answer = ok(
        InstallRefused(
            "third_party_grant",
            role_name=role,
            object_class="relation",
            phase="post_installation",
        )
    )
    with pytest.raises(Unavailable) as caught:
        rig.backend().migrate()
    assert caught.value.reason == "migration_failed"
    assert caught.value.detail == (
        f"truss third_party_grant role={json.dumps(role, ensure_ascii=True, separators=(',', ':'))} "
        "object_class=relation phase=post_installation"
    )
    assert "server" not in caught.value.detail
    assert rig.conns[0].log[-1] == "rollback" and "commit" not in rig.conns[0].log
    assert rig.script.calls == ["status", "install"]


def test_other_typed_migration_refusals_keep_the_missing_createrole_priority() -> None:
    rig = Rig(Typed())
    rig.creates_roles = False
    rig.script.install_answer = ok(InstallRefused("role_exists"))
    with pytest.raises(Unavailable) as caught:
        rig.backend().migrate()
    assert (caught.value.reason, caught.value.detail) == (
        "access_denied",
        "the installing role cannot create roles",
    )


@pytest.mark.parametrize(
    "context",
    [
        {"role_name": "bad\x00role", "object_class": "relation", "phase": "pre_ownership"},
        {"role_name": "x" * 64, "object_class": "relation", "phase": "pre_ownership"},
        {"role_name": "role", "object_class": "server text", "phase": "pre_ownership"},
        {"role_name": "role", "object_class": "relation", "phase": "unknown"},
        {"role_name": 7, "object_class": "relation", "phase": "pre_ownership"},
        {"role_name": "role", "object_class": ["relation"], "phase": "pre_ownership"},
        {"role_name": "role", "object_class": "relation", "phase": True},
        {"role_name": "\ud800", "object_class": "relation", "phase": "pre_ownership"},
    ],
)
def test_malformed_third_party_grant_context_is_generic_and_does_not_leak(context: dict[str, Any]) -> None:
    rig = Rig(Typed())
    rig.script.install_answer = ok(InstallRefused("third_party_grant", **context))
    with pytest.raises(Unavailable) as caught:
        rig.backend().migrate()
    assert (caught.value.reason, caught.value.detail) == (
        "migration_failed",
        "truss third_party_grant context unavailable",
    )
    assert "server text" not in caught.value.detail
    assert rig.conns[0].log[-1] == "rollback" and "commit" not in rig.conns[0].log


def test_an_install_refused_as_already_installed_is_verified_not_repeated() -> None:
    script = Typed()
    script.install_answer = ok(InstallRefused("already_installed"))
    script.installed_by_other = True
    rig = Rig(script)
    assert rig.backend().migrate() == MigrationResult(False, RELEASE)
    assert script.calls == ["status", "install", "status"]


def test_already_installed_that_the_status_does_not_show_is_a_failed_install() -> None:
    script = Typed()
    script.install_answer = ok(InstallRefused("already_installed"))
    with pytest.raises(Unavailable) as caught:
        Rig(script).backend().migrate()
    assert caught.value.reason == "migration_failed"


@needs_toolkit
def test_a_refused_grant_batch_is_not_taken_for_a_grant_and_names_its_codes_only() -> None:
    script = Typed(installed=True)
    script.configure_answer = ok(ModuleAccessBatchRefused((ModuleAccessError(0, "unknown_role"),)))
    rig = Rig(script, module_access={"catalog": ModuleAccess("sandbox", "r", "w")})
    with pytest.raises(Unavailable) as caught:
        rig.backend().configure_access()
    assert caught.value.reason == "migration_failed"
    assert "'catalog'" in caught.value.detail and "unknown_role" in caught.value.detail
    assert "commit" not in rig.conns[0].log  # an invalid batch changes nothing


@needs_toolkit
def test_a_modules_auditor_role_is_granted_with_its_access_and_a_refusal_stops_there() -> None:
    script = Typed(installed=True)
    access = {"catalog": ModuleAccess("sandbox", "r", "w", auditor_role="a")}
    rig = Rig(script, module_access=access)
    rig.backend().configure_access()
    assert script.calls == ["configure", "audit"]
    [grant] = script.audited
    assert (grant.document_id, grant.module_id, grant.auditor_role) == ("sandbox", "catalog", "a")
    refused = Typed(installed=True)
    refused.audit_answer = ok(LoadAuditUnavailable("unauthorized"))
    rig = Rig(refused, module_access=access)
    with pytest.raises(Unavailable) as caught:
        rig.backend().configure_access()
    assert "audit access refused (unauthorized)" in caught.value.detail
    assert "commit" not in rig.conns[0].log  # the module access is not left half granted


@needs_toolkit
def test_a_module_without_an_auditor_role_grants_no_audit() -> None:
    script = Typed(installed=True)
    Rig(
        script, module_access={"catalog": ModuleAccess("sandbox", "r", "w")}
    ).backend().configure_access()
    assert script.calls == ["configure"]


@pytest.mark.parametrize("auditor", ["r", "w", ""])
def test_an_auditor_role_is_a_role_of_its_own(auditor: str) -> None:
    with pytest.raises(ValueError):
        ModuleAccess("sandbox", "r", "w", auditor_role=auditor)


def test_the_install_roles_are_read_on_the_installing_connection_in_a_read_only_call() -> None:
    script = Typed(installed=True)
    rig = Rig(script)
    assert rig.backend().install_roles() == ("owner_x", "registrar_x")
    assert script.calls == ["recovery"]
    assert rig.conns[0].log[0].endswith("READ ONLY") and rig.conns[0].log[-1] == "rollback"


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("unauthorized", "access_denied"),
        ("profile", "unsupported_version"),
        ("installation", "not_configured"),
        ("observation", "busy"),
    ],
)
def test_a_refused_role_recovery_is_unavailable_for_its_reason(reason: str, expected: str) -> None:
    script = Typed(installed=True)
    script.recovery_answer = ok(LifecycleRefused(reason))
    with pytest.raises(Unavailable) as caught:
        Rig(script).backend().install_roles()
    assert caught.value.reason == expected


def test_the_install_roles_need_an_installing_connection() -> None:
    with pytest.raises(Unavailable) as caught:
        create_backend("truss", Rig().person).install_roles()
    assert caught.value.reason == "not_configured"
    with pytest.raises(Unavailable):
        TrussBackend("truss").install_roles()


@pytest.mark.truss
def test_the_install_roles_are_the_ones_the_install_gave(cluster: Any) -> None:  # noqa: F811
    with cluster.bare_database() as bare:
        backend = bare.backend()
        installed = backend.migrate()
        assert backend.install_roles() == (installed.owner_role, installed.registrar_role)
        assert backend.migrate().ran is False  # and a verify gives none: recovery is the way


@pytest.mark.truss
def test_a_typed_install_refusal_of_a_real_truss_changes_nothing(cluster: Any) -> None:  # noqa: F811
    with cluster.bare_database() as bare:
        backend = bare.backend()
        backend.migrate()
        # the same database again: Truss is there, the install is verified and nothing is installed
        assert backend.migrate().ran is False
        with bare.installing_connection() as conn:
            from truss_harness import transaction

            with transaction(conn) as (assembly, handle):
                refused = assembly.install_in_transaction(handle).value
                assert type(refused).__name__ == "InstallRefused"
                assert refused.code == "already_installed"
