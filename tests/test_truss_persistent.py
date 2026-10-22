# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic, reportOptionalSubscript=false, reportArgumentType=false, reportCallIssue=false
"""The dev host on a persistent PostgreSQL server (P1): a throwaway pgserver stands in for the
developer's own server. The installing role is what a database owner with CREATEROLE is (a
non-superuser), `pg_hba` asks every role for its password, and the cluster holds roles the dev
host did not make, one a superuser named like a sandbox person. Truss-marked: PostgreSQL 18.6.
"""

from __future__ import annotations

import secrets
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from arras.devtruss import PEOPLE, TrussBox
from arras.sandbox import SANDBOX_STEPS, catalog_document
from test_truss_harness import _require

pytestmark = pytest.mark.truss

INSTALLER = "arras_installer"
DATABASE = "arras_truss"
COUNT = "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100"


class External:
    """A running PostgreSQL the dev host does not own, as a Homebrew service is to it."""

    def __init__(self) -> None:
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict
        from truss import LocalPostgres

        self.root = Path(tempfile.mkdtemp(prefix="ar-"))
        self.password = secrets.token_urlsafe(18)
        self.runtime = LocalPostgres(self.root / "pg")
        self.runtime.__enter__()
        params = dict(conninfo_to_dict(self.runtime.info.connection_uri))
        self.socket = str(params["host"])
        self.params = params
        self.superuser = secrets.token_urlsafe(18)
        self.credentials: dict[str, str] = {}
        with psycopg.connect(**params, autocommit=True) as su:
            su.execute(
                sql.SQL("CREATE ROLE {} LOGIN CREATEROLE PASSWORD {}").format(
                    sql.Identifier(INSTALLER), sql.Literal(self.password)
                )
            )
            su.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(DATABASE), sql.Identifier(INSTALLER)
                )
            )
            su.execute(
                sql.SQL("ALTER ROLE postgres PASSWORD {}").format(sql.Literal(self.superuser))
            )
            su.execute("CREATE ROLE alice LOGIN SUPERUSER PASSWORD 'alice-own'")  # a person's name
            su.execute("CREATE ROLE bystander LOGIN PASSWORD 'bystander-own'")
            su.execute("CREATE DATABASE other")
            hba = Path(su.execute("SHOW hba_file").fetchone()[0])
            hba.write_text("local all all scram-sha-256\n")
            su.execute("SELECT pg_reload_conf()")
        self.url = f"postgresql://{INSTALLER}:{self.password}@/{DATABASE}?host={self.socket}"

    def credential_source(self, role: str, *, create: bool) -> str:
        token = self.credentials.get(role)
        if token is not None:
            return token
        if not create:
            raise ValueError("credential is missing")
        token = secrets.token_urlsafe(24)
        self.credentials[role] = token
        return token

    def sql(self, statement: str, db: str = DATABASE) -> list[Any]:
        import psycopg

        conn = psycopg.connect(
            **dict(self.params, dbname=db, user="postgres", password=self.superuser),
            autocommit=True,
        )
        with conn:
            cur = conn.execute(statement)
            return cur.fetchall() if cur.description else []

    def close(self) -> None:
        self.runtime.__exit__(None, None, None)
        shutil.rmtree(self.root, ignore_errors=True)


@pytest.fixture(scope="module")
def server() -> Iterator[External]:
    _require()
    s = External()
    try:
        yield s
    finally:
        s.close()


def attach(server: External, *, reset: bool = False) -> TrussBox:
    box = TrussBox(
        url=server.url,
        credential_source=server.credential_source,
        reset=reset,
    )
    try:
        box.load(catalog_document(), SANDBOX_STEPS)
        box.finish()
    except BaseException:
        box.close()
        raise
    return box


def codes(box: TrussBox) -> list[str]:
    alice = box.arras.session(box.people["alice"])
    return sorted(str(r["code"]) for r in alice.query("catalog", COUNT, limit=100).rows)


def _role_state(server: External, role: str) -> tuple[Any, ...]:
    role_literal = role.replace("'", "''")
    return tuple(
        server.sql(
            "SELECT rolcanlogin, rolvaliduntil::text, rolpassword FROM pg_authid "
            f"WHERE rolname = '{role_literal}'"
        )[0]
    )


def test_attaching_twice_installs_and_seeds_once_and_keeps_its_state(server: External) -> None:
    first = attach(server)
    assert first.truss.migration is not None and first.truss.migration.ran
    assert first.seeded is True
    assert codes(first) == ["uc-alerts", "uc-pipeline"]
    # state made by a person survives
    first.arras.session(first.people["alice"]).invoke(
        "catalog.AddUseCase", {"code": "uc-kept", "name": "Kept", "workArea": "finance"}
    )
    old_token = first.people["alice"].token
    first.close()  # drops nothing, stops nothing
    assert server.sql("SELECT count(*) FROM pg_roles WHERE rolname = 'arrasdev_alice'")[0][0] == 1
    assert server.sql("SELECT count(*) FROM pg_namespace WHERE nspname = 'truss'")[0][0] == 1

    second = attach(server)
    try:
        assert second.truss.migration is not None and not second.truss.migration.ran  # no reinstall
        assert second.seeded is False  # no reseed
        assert codes(second) == ["uc-alerts", "uc-kept", "uc-pipeline"]
        assert second.people["alice"].token == old_token
        assert second.people["alice"].user == "arrasdev_alice"
        # A's previously issued principal still authenticates via a fresh connection after B attaches.
        assert len(first.arras.session(first.people["alice"]).query("catalog", COUNT).rows) == 3
        # the roles and the module's grants work as a person: carol reads, cannot write
        carol = second.arras.session(second.people["carol"])
        assert len(carol.query("catalog", COUNT, limit=100).rows) == 3
        from arras.errors import ArrasError

        with pytest.raises(ArrasError):
            carol.invoke("catalog.AddUseCase", {"code": "uc-no", "name": "No", "workArea": "x"})
        assert set(second.modules) == {"catalog"}
    finally:
        second.close()


def test_a_start_preserves_grants_and_expiry_and_explicit_role_selection_is_managed(
    server: External,
) -> None:
    attach(server).close()
    third = attach(server)
    try:
        assert codes(third) == ["uc-alerts", "uc-kept", "uc-pipeline"]
        who = third.person("erin", "editor")
        assert who.user == "arrasdev_erin"
        third.set_token("carol", live=False)  # an expired token
        third.set_access("bob", "catalog", ["write"], grant=False)
        server.sql("CREATE ROLE independent_membership NOLOGIN")
        server.sql("GRANT independent_membership TO arrasdev_erin")
        third.set_token("erin", live=False)
    finally:
        third.close()
    try:
        with pytest.raises(ValueError, match="credential"):
            attach(server)
        assert server.sql(
            "SELECT rolvaliduntil < now() FROM pg_roles WHERE rolname = 'arrasdev_carol'"
        ) == [(True,)]
    finally:
        # Restore the fixture's deliberately expired principal as an explicit administrator action,
        # even when an assertion fails.
        server.sql("ALTER ROLE arrasdev_carol VALID UNTIL 'infinity'")
    fourth = attach(server)
    try:
        from arras.errors import ArrasError

        assert server.sql(
            "SELECT rolvaliduntil < now() FROM pg_roles WHERE rolname = 'arrasdev_erin'"
        ) == [(True,)]
        erin_before = _role_state(server, "arrasdev_erin")
        with pytest.raises(ValueError, match="credential"):
            fourth.person("erin", "viewer")  # an expired person is refused, never repaired
        assert _role_state(server, "arrasdev_erin") == erin_before
        assert server.sql(
            "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid "
            "JOIN pg_roles u ON u.oid = m.member WHERE r.rolname = 'independent_membership' "
            "AND u.rolname = 'arrasdev_erin'"
        ) == [(1,)]
        # Explicitly restore expiry, then select a new managed role. Only generated Arras roles
        # are reconciled; the independent membership remains.
        fourth.truss.expire("erin", restore=True)
        erin = fourth.person("erin", "viewer")
        bob = fourth.arras.session(fourth.people["bob"])
        with pytest.raises(ArrasError):
            bob.invoke(
                "catalog.AddUseCase", {"code": "uc-bob", "name": "Bob", "workArea": "finance"}
            )
        assert len(fourth.arras.session(fourth.people["carol"]).query("catalog", COUNT).rows) == 3
        with pytest.raises(ArrasError):
            fourth.arras.session(erin).invoke(
                "catalog.AddUseCase", {"code": "uc-erin", "name": "Erin", "workArea": "finance"}
            )
        assert server.sql(
            "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid "
            "JOIN pg_roles u ON u.oid = m.member WHERE r.rolname = 'independent_membership' "
            "AND u.rolname = 'arrasdev_erin'"
        ) == [(1,)]
    finally:
        fourth.close()


def test_the_dev_host_touches_no_role_or_database_it_did_not_make(server: External) -> None:
    box = attach(server)
    box.close()
    assert server.sql("SELECT rolsuper FROM pg_roles WHERE rolname = 'alice'") == [(True,)]
    names = {r[0] for r in server.sql("SELECT rolname FROM pg_roles")}
    assert {"alice", "bystander", INSTALLER, "postgres"} <= names
    for person in PEOPLE:
        assert f"arrasdev_{person}" in names and person not in names - {"alice"}
    # nothing made outside the one database
    assert server.sql("SELECT count(*) FROM pg_namespace WHERE nspname = 'truss'", "other") == [
        (0,)
    ]
    assert not any(n.startswith("truss_") for n in names - _own_truss(server))


def _own_truss(server: External) -> set[str]:
    return {r[0] for r in server.sql("SELECT rolname FROM pg_roles WHERE rolname LIKE 'truss_%'")}


def test_reset_drops_what_the_dev_host_made_and_starts_clean(server: External) -> None:
    attach(server).close()
    before = _own_truss(server)
    assert before  # Truss's owner and registrar roles
    server.sql("CREATE ROLE truss_owner_unrelated NOLOGIN")  # a role it did not make
    server.sql(
        "CREATE ROLE arrasdev_foreign NOLOGIN"
    )  # by the prefix alone, not made by the installer
    box = attach(server, reset=True)
    try:
        assert box.truss.migration is not None and box.truss.migration.ran  # installed again
        assert box.seeded is True and codes(box) == ["uc-alerts", "uc-pipeline"]
        after = _own_truss(server)
        assert before.isdisjoint(after - {"truss_owner_unrelated"})  # new roles, the old gone
        names = {r[0] for r in server.sql("SELECT rolname FROM pg_roles")}
        assert {
            "truss_owner_unrelated",
            "arrasdev_foreign",
            "alice",
            "bystander",
            INSTALLER,
        } <= names
        assert server.sql("SELECT rolsuper FROM pg_roles WHERE rolname = 'alice'") == [(True,)]
        dbs = {r[0] for r in server.sql("SELECT datname FROM pg_database")}
        assert {DATABASE, "other"} <= dbs
    finally:
        box.close()
    server.sql("DROP ROLE truss_owner_unrelated")
    server.sql("DROP ROLE arrasdev_foreign")


def test_a_role_it_did_not_make_is_never_taken_over(server: External) -> None:
    attach(server).close()
    server.sql("DROP ROLE IF EXISTS arrasdev_dave")  # an earlier run's, made by the installer
    server.sql("CREATE ROLE arrasdev_dave LOGIN PASSWORD 'not-the-dev-hosts'")
    try:
        with pytest.raises(ValueError, match="not administered"):
            TrussBox(url=server.url, credential_source=server.credential_source)
    finally:
        server.sql("DROP ROLE arrasdev_dave")


def test_a_revoked_connect_outage_is_refused_on_a_persistent_server(server: External) -> None:
    box = attach(server)
    try:
        with pytest.raises(ValueError, match="unreachable"):
            box.set_outage("primary", "access_denied")
        box.set_outage("primary", "unreachable")
        box.set_outage("primary", None)
        assert codes(box)
    finally:
        box.close()
