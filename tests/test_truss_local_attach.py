# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The persistent server's world (P1) without a database: a scripted installing connection shows
which statements `LocalTruss` and `TrussBox` send, in which order, and what they leave alone."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("psycopg")

from arras.adapters.truss import local as local_module  # noqa: E402
from arras.adapters.truss.endpoint import Endpoint  # noqa: E402
from arras.adapters.truss.local import PERSISTENT_PREFIX, LocalTruss  # noqa: E402
from arras.devtruss import BATCH, TrussBox  # noqa: E402
from arras.errors import Conflict  # noqa: E402
from arras.graphfile import GraphFile  # noqa: E402

URL = "postgresql://inst:pw@localhost:5432/db"


class Answer:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows


class Su:
    """An installing connection over a made-up cluster: `roles` exist, `administered` are the ones
    the installing role administers, `held` is who is a member of what."""

    closed = False
    broken = False

    def __init__(
        self,
        roles: set[str] = frozenset(),  # type: ignore[assignment]
        administered: set[str] = frozenset(),  # type: ignore[assignment]
        logins: set[str] = frozenset(),  # type: ignore[assignment]
        held: dict[str, list[str]] | None = None,
        owner: str | None = None,
    ) -> None:
        self.roles, self.administered, self.logins = set(roles), set(administered), set(logins)
        self.held = held or {}
        self.owner = owner
        self.log: list[str] = []

    def execute(self, query: Any, params: Any = None) -> Answer:
        text = query if isinstance(query, str) else query.as_string()
        if "pg_advisory_xact_lock" in text:
            self.log.append(text)
            return Answer([])
        if "pg_roles WHERE rolname = %s" in text and "FROM pg_auth_members" not in text:
            return Answer([(1,)] if params[0] in self.roles else [])
        if "r.rolname = %s AND u.rolname = current_user" in text:
            return Answer([(1,)] if params[0] in self.administered else [])
        if "starts_with" in text:
            made = sorted(r for r in self.administered if r.startswith(params[0]))
            return Answer([(r, r in self.logins) for r in made])
        if "nspname = 'truss'" in text:
            return Answer([(self.owner,)] if self.owner else [])
        if "SELECT g.rolname" in text:
            return Answer([(g,) for g in self.held.get(params[0], [])])
        if text.startswith("CREATE ROLE"):
            role = text.split()[2].strip('"')
            self.roles.add(role)
            self.administered.add(role)
        self.log.append(text)
        return Answer([])

    @contextmanager
    def transaction(self):
        yield self


class Credentials:
    def __init__(self, tokens: dict[str, str] | None = None) -> None:
        self.tokens = tokens or {}
        self.calls: list[tuple[str, bool]] = []

    def __call__(self, role: str, *, create: bool) -> str:
        self.calls.append((role, create))
        if role in self.tokens:
            return self.tokens[role]
        if not create:
            raise ValueError("missing")
        self.tokens[role] = "stable-token"
        return self.tokens[role]


def attached(su: Su, credential_source: Credentials | None = None) -> LocalTruss:
    local = LocalTruss(url=URL, credential_source=credential_source)
    local._su = su
    local._endpoint = Endpoint("localhost", "db")
    return local


def test_a_throwaway_names_its_roles_as_before_and_an_attached_one_prefixes_them() -> None:
    assert LocalTruss().prefix == "" and LocalTruss().role("alice") == "alice"
    assert LocalTruss().reader_role("catalog") == "catalog_reader"
    assert LocalTruss().outages == ("unreachable", "access_denied")
    local = LocalTruss(url=URL)
    assert local.role("alice") == f"{PERSISTENT_PREFIX}alice" == "arrasdev_alice"
    assert local.reader_role("catalog") == "arrasdev_catalog_reader"
    assert local.writer_role("catalog") == "arrasdev_catalog_writer"
    assert local.outages == ("unreachable",)  # a revoked CONNECT could lock the installer out


def test_reset_needs_a_server_to_attach_to() -> None:
    with pytest.raises(ValueError, match="persistent server"):
        LocalTruss(reset=True)


def test_a_missing_role_is_created_and_returns_the_prefixed_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    su = Su()
    credentials = Credentials()
    local = attached(su, credentials)
    who = local.person("alice")
    assert who.user == "arrasdev_alice" and who.token == local.token("alice")
    assert any(q.startswith('CREATE ROLE "arrasdev_alice" LOGIN PASSWORD') for q in su.log)
    assert credentials.calls == [("arrasdev_alice", True)]
    assert local.created_people == {"alice"} and local.created_roles == {"arrasdev_alice"}

    @contextmanager
    def authenticate(endpoint: Any, user: str, password: str):
        assert password == "stable-token"
        yield SimpleNamespace(execute=lambda query: Answer([(user,)]))

    monkeypatch.setattr(local_module, "connect", authenticate)
    assert local.person("alice") == who
    assert sum(q.startswith('CREATE ROLE "arrasdev_alice"') for q in su.log) == 1
    assert credentials.calls == [("arrasdev_alice", True), ("arrasdev_alice", False)]


def test_a_persistent_role_reuses_its_credential_without_touching_role_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    su = Su(
        roles={"arrasdev_alice"},
        administered={"arrasdev_alice"},
        held={"arrasdev_alice": ["arrasdev_catalog_writer", "truss_registrar_1"]},
    )
    credentials = Credentials({"arrasdev_alice": "old-stable-token"})
    local = attached(su, credentials)

    @contextmanager
    def authenticate(endpoint: Any, user: str, password: str):
        assert (user, password) == ("arrasdev_alice", "old-stable-token")
        yield SimpleNamespace(execute=lambda query: Answer([(user,)]))

    monkeypatch.setattr(local_module, "connect", authenticate)
    who = local.person("alice")
    assert who.token == local.token("alice") == "old-stable-token"
    assert local.person("alice") == who
    assert credentials.calls == [("arrasdev_alice", False)] * 2
    assert not any(q.startswith(("CREATE ROLE", "ALTER ROLE", "GRANT", "REVOKE")) for q in su.log)
    assert su.held["arrasdev_alice"] == [
        "arrasdev_catalog_writer",
        "truss_registrar_1",
    ]
    assert local.created_people == set() and local.created_roles == set()


def test_a_role_the_installing_role_does_not_administer_is_never_touched() -> None:
    su = Su(roles={"arrasdev_alice"})
    with pytest.raises(ValueError, match="not administered"):
        attached(su, Credentials({"arrasdev_alice": "stable-token"})).person("alice")
    assert not any(q.startswith(("CREATE ROLE", "ALTER ROLE", "GRANT", "REVOKE")) for q in su.log)
    su = Su(
        roles={"arrasdev_catalog_reader", "arrasdev_catalog_writer"},
        administered={"arrasdev_catalog_writer"},
    )
    with pytest.raises(ValueError, match="did not make"):
        attached(su).module_roles("catalog")
    assert not any(q.startswith(("CREATE ROLE", "ALTER ROLE", "GRANT", "REVOKE")) for q in su.log)


def test_a_throwaway_refuses_a_role_that_is_there_already() -> None:
    local = LocalTruss()
    local._su = Su(roles={"alice"})
    with pytest.raises(ValueError, match="is a role of the database already"):
        local.person("alice")


def test_persistent_person_requires_stored_credentials_and_never_repairs() -> None:
    su = Su(roles={"arrasdev_alice"}, administered={"arrasdev_alice"})
    with pytest.raises(ValueError, match="credential source"):
        attached(su).person("alice")
    credentials = Credentials()
    with pytest.raises(ValueError, match="stored credential.*missing"):
        attached(su, credentials).person("alice")
    assert credentials.calls == [("arrasdev_alice", False)]
    assert not any(q.startswith(("CREATE ROLE", "ALTER ROLE", "GRANT", "REVOKE")) for q in su.log)


def test_credential_source_must_return_a_nonempty_string() -> None:
    class InvalidCredential:
        def __call__(self, role: str, *, create: bool) -> Any:
            return 7

    su = Su()
    local = LocalTruss(url=URL, credential_source=InvalidCredential())
    local._su = su
    with pytest.raises(ValueError, match="no usable host-owned credential"):
        local.person("alice")
    assert not any(q.startswith(("CREATE ROLE", "ALTER ROLE")) for q in su.log)


def test_unrelated_unique_violation_during_create_is_not_treated_as_role_race() -> None:
    class UniqueViolation(Exception):
        sqlstate = "23505"
        diag = SimpleNamespace(constraint_name="unrelated_index")

    class BrokenCreate(Su):
        def execute(self, query: Any, params: Any = None) -> Answer:
            text = query if isinstance(query, str) else query.as_string()
            if text.startswith('CREATE ROLE "arrasdev_alice"'):
                self.log.append(text)
                raise UniqueViolation
            return super().execute(query, params)

    su = BrokenCreate()
    with pytest.raises(UniqueViolation):
        attached(su, Credentials()).person("alice")
    assert not su.roles
    assert len(su.log) == 2  # the advisory lock and failed CREATE only


def test_refused_existing_person_credential_is_scrubbed_and_never_repaired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    su = Su(roles={"arrasdev_alice"}, administered={"arrasdev_alice"})
    credentials = Credentials({"arrasdev_alice": "wrong-secret"})
    local = attached(su, credentials)

    @contextmanager
    def reject(endpoint: Any, user: str, password: str):
        error: Any = RuntimeError(f"password authentication failed: {password}")
        error.sqlstate = "28P01"
        raise error
        yield  # pragma: no cover

    monkeypatch.setattr(local_module, "connect", reject)
    with pytest.raises(ValueError, match="stored credential") as error:
        local.person("alice")
    assert "wrong-secret" not in str(error.value)
    assert not any(q.startswith(("CREATE ROLE", "ALTER ROLE", "GRANT", "REVOKE")) for q in su.log)


def test_database_outage_during_credential_probe_is_not_reported_as_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    su = Su(roles={"arrasdev_alice"}, administered={"arrasdev_alice"})
    local = attached(su, Credentials({"arrasdev_alice": "private-token"}))

    @contextmanager
    def unavailable(endpoint: Any, user: str, password: str):
        raise RuntimeError(f"connection failed while using {password}")
        yield  # pragma: no cover

    monkeypatch.setattr(local_module, "connect", unavailable)
    with pytest.raises(ValueError, match="authentication is unavailable") as error:
        local.person("alice")
    assert "private-token" not in str(error.value)
    assert "rotation" not in str(error.value)


def test_module_roles_are_created_when_absent() -> None:
    su = Su(roles={"arrasdev_catalog_reader"}, administered={"arrasdev_catalog_reader"})
    assert attached(su).module_roles("catalog") == (
        "arrasdev_catalog_reader",
        "arrasdev_catalog_writer",
    )
    assert su.log == ['CREATE ROLE "arrasdev_catalog_writer" NOLOGIN']


def test_the_modules_of_an_earlier_run_are_the_ones_with_both_roles() -> None:
    su = Su(
        administered={
            "arrasdev_a_reader",
            "arrasdev_a_writer",
            "arrasdev_b_reader",  # no writer: not a module
            "arrasdev_alice",  # a person
        },
        logins={"arrasdev_alice"},
    )
    assert attached(su).known_modules() == ["a"]


def test_the_registrar_of_an_earlier_install_is_found_from_the_schema_owner() -> None:
    su = Su(
        roles={"truss_registrar_ab12"},
        administered={"truss_registrar_ab12"},
        owner="truss_owner_ab12",
    )
    assert attached(su).registrar_role == "truss_registrar_ab12"
    with pytest.raises(RuntimeError, match="installed by someone else"):
        attached(Su(owner="truss_owner_ab12")).registrar_role  # noqa: B018
    with pytest.raises(RuntimeError, match="installed by someone else"):
        attached(Su()).registrar_role  # noqa: B018


def test_the_install_names_the_registrar_when_it_ran() -> None:
    local = attached(Su())
    local.migration = SimpleNamespace(registrar_role="truss_registrar_new")  # type: ignore[assignment]
    assert local.registrar_role == "truss_registrar_new"


def test_reset_drops_the_schema_then_only_what_the_installing_role_administers() -> None:
    su = Su(
        roles={
            "arrasdev_alice",
            "arrasdev_foreign",  # prefixed, not made by it
            "arrasdev_catalog_reader",
            "truss_owner_ab12",
            "truss_registrar_ab12",
            "alice",
        },
        administered={
            "arrasdev_alice",
            "arrasdev_catalog_reader",
            "truss_owner_ab12",
            "truss_registrar_ab12",
        },
        owner="truss_owner_ab12",
    )
    local = attached(su)
    local._tokens["alice"] = "t"
    local._drop_what_was_made()
    assert su.log == [
        "DROP SCHEMA IF EXISTS truss CASCADE",
        'DROP ROLE "arrasdev_alice"',
        'DROP ROLE "arrasdev_catalog_reader"',
        'DROP ROLE "truss_registrar_ab12"',
        'DROP OWNED BY "truss_owner_ab12"',
        'DROP ROLE "truss_owner_ab12"',
    ]
    assert local._tokens == {}


def test_reset_with_no_truss_installed_still_clears_the_people() -> None:
    su = Su(roles={"arrasdev_carol"}, administered={"arrasdev_carol"})
    attached(su)._drop_what_was_made()
    assert su.log == ["DROP SCHEMA IF EXISTS truss CASCADE", 'DROP ROLE "arrasdev_carol"']


def test_a_truss_owner_it_does_not_administer_is_not_dropped() -> None:
    su = Su(roles={"truss_owner_ab12", "truss_registrar_ab12"}, owner="truss_owner_ab12")
    attached(su)._drop_what_was_made()
    assert su.log == ["DROP SCHEMA IF EXISTS truss CASCADE"]


def test_closing_an_attached_server_closes_the_connection_and_nothing_else() -> None:
    su = Su()
    closed: list[bool] = []
    su.close = lambda: closed.append(True)  # type: ignore[attr-defined]
    local = attached(su)
    local.close()
    assert closed == [True] and su.log == []  # no DROP, no shutdown, no removed root
    assert not local._own_root


def test_a_revoked_connect_outage_is_a_throwaway_control() -> None:
    su = Su()
    local = attached(su)
    local._endpoint = SimpleNamespace(dbname="db", host="h")  # type: ignore[assignment]
    with pytest.raises(ValueError, match="unreachable"):
        local.outage("access_denied")
    assert su.log == []


def test_a_closed_connection_is_opened_again(monkeypatch) -> None:
    fresh = Su()
    local = attached(Su())
    local._su.closed = True  # the server restarted
    monkeypatch.setattr(local, "_dial", lambda: fresh)
    assert local.su is fresh and local.su is fresh


def test_membership_names_the_prefixed_role() -> None:
    su = Su()
    local = attached(su)
    local.membership("alice", "arrasdev_catalog_reader", grant=True)
    local.membership("alice", "arrasdev_catalog_reader", grant=False)
    local.expire("alice")
    assert su.log == [
        'GRANT "arrasdev_catalog_reader" TO "arrasdev_alice" WITH SET FALSE',
        'REVOKE "arrasdev_catalog_reader" FROM "arrasdev_alice"',
        "ALTER ROLE \"arrasdev_alice\" VALID UNTIL '2000-01-01'",
    ]


# -- the box: seed only when nothing is there
class FakeSession:
    def __init__(self, world: dict[str, Any]) -> None:
        self.world = world

    def modules(self) -> list[Any]:
        return self.world["modules"]

    def query(self, module: str, sql: str, limit: int = 50) -> Any:
        self.world["queries"].append(sql)
        return SimpleNamespace(rows=self.world["rows"].get(sql, []))

    def invoke(self, action: str, inputs: dict[str, Any]) -> None:
        self.world["invoked"].append(action)

    def invoke_batch(self, action: str, items: list[Any], *, atomic: bool) -> None:
        assert atomic
        if self.world.get("refuse_batches"):
            raise Conflict("exists", "a step of the batch")
        self.world.setdefault("batches", []).append((action, len(items)))

    def import_records(self, module: str, records: Any, *, load_id: str) -> Any:
        self.world.setdefault("imports", []).append((module, tuple(records), load_id))
        return SimpleNamespace(rejected=self.world.get("rejected", ()))


def box(persistent: bool, rows: dict[str, list[Any]] | None = None) -> Any:
    world: dict[str, Any] = {"queries": [], "invoked": [], "rows": rows or {}}
    mod = SimpleNamespace(
        name="catalog",
        entity_types=[
            SimpleNamespace(key="code", local_name="UseCase"),
            SimpleNamespace(key="code", local_name="Solution"),
        ],
    )
    world["modules"] = [mod]
    b = TrussBox.__new__(TrussBox)
    b.persistent = persistent
    b.people = {"alice": object(), "root": object()}  # type: ignore[dict-item]
    b._pending = []
    b._seed = None if persistent else True
    b.arras = SimpleNamespace(session=lambda who: FakeSession(world))  # type: ignore[assignment]
    b.world = world  # type: ignore[attr-defined]
    return b


USE_CASE = 'SELECT x."code" FROM "catalog"."UseCase" x LIMIT 1'
SOLUTION = 'SELECT x."code" FROM "catalog"."Solution" x LIMIT 1'


def test_an_empty_database_is_seeded_after_every_module_is_registered() -> None:
    b = box(True)
    b._pending.append(("catalog", [("catalog.AddUseCase", {})], None))
    b._pending.append(("notes", [("notes.AddNote", {})], None))
    extra: list[TrussBox] = []
    assert b.seeded is None
    b.finish(extra.append)
    assert b.seeded is True
    assert b.world["queries"] == [USE_CASE, SOLUTION]  # each entity type asked for one row
    assert b.world["invoked"] == ["catalog.AddUseCase", "notes.AddNote"] and extra == [b]


def test_a_database_that_holds_an_entity_is_not_seeded() -> None:
    b = box(True, {SOLUTION: [{"code": "sol-1"}]})
    b._pending.append(("catalog", [("catalog.AddUseCase", {})], None))
    extra: list[TrussBox] = []
    b.finish(extra.append)
    assert b.seeded is False and b.world["invoked"] == [] and extra == []
    assert b._pending == []


def test_a_throwaway_never_asks_and_runs_what_it_was_given() -> None:
    b = box(False)
    extra: list[TrussBox] = []
    b.finish(extra.append)
    assert b.seeded is True and b.world["queries"] == [] and extra == [b]


def _steps(*runs: tuple[str, int]) -> list[tuple[str, dict[str, Any]]]:
    return [(action, {"n": i}) for action, count in runs for i in range(count)]


def test_a_seed_sends_a_run_of_one_action_as_atomic_batches_of_at_most_the_batch_size() -> None:
    b = box(False)
    b._run(_steps(("catalog.AddUseCase", BATCH + 5), ("catalog.AddSolution", 1), ("catalog.X", 2)))
    assert b.world["batches"] == [
        ("catalog.AddUseCase", BATCH),
        ("catalog.AddUseCase", 5),
        ("catalog.X", 2),
    ]
    assert b.world["invoked"] == ["catalog.AddSolution"]  # a run of one is one step


def test_a_batch_the_backend_refuses_is_run_again_one_step_at_a_time() -> None:
    b = box(False)
    b.world["refuse_batches"] = True
    b._run(_steps(("catalog.AddUseCase", 3)))
    assert b.world["invoked"] == ["catalog.AddUseCase"] * 3 and "batches" not in b.world


def test_a_graph_file_loads_after_the_steps_as_the_administrator_and_a_rejection_is_an_error() -> (
    None
):
    b = box(False)
    graph = GraphFile("catalog", ({"type": "UseCase", "key": "a"},))
    b._import(graph)
    assert b.world["imports"] == [("catalog", graph.records, "file:catalog")]
    b._import(None)
    assert len(b.world["imports"]) == 1
    b.world["rejected"] = (SimpleNamespace(kind="record", identity="UseCase/a", reason="no"),)
    with pytest.raises(ValueError, match="1 records were rejected"):
        b._import(graph)


def test_a_database_known_to_be_empty_is_seeded_without_asking_what_it_holds() -> None:
    b = box(True)
    b._seed = True  # what `TrussBox(reset=True)` sets: a reset database is empty
    b._pending.append(("catalog", [("catalog.AddUseCase", {})], None))
    b.finish()
    assert b.world["queries"] == [] and b.world["invoked"] == ["catalog.AddUseCase"]
