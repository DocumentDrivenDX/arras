# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic, reportOptionalSubscript=false, reportArgumentType=false, reportCallIssue=false
"""Persistent Truss credentials and grants survive host restarts without being rotated or healed.

Each test owns a PostgreSQL 18.6 cluster through ``External``; these tests never use a developer's
configured database.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from arras.adapters.truss.local import LocalTruss
from arras.devtruss import PEOPLE, TrussBox
from arras.errors import ArrasError
from arras.sandbox import SANDBOX_STEPS, catalog_document
from test_truss_persistent import DATABASE, External, _require

pytestmark = pytest.mark.truss


@pytest.fixture
def server() -> Iterator[External]:
    _require()
    external = External()
    try:
        yield external
    finally:
        external.close()


class _CredentialMap:
    """Stable per-role fixture credentials with explicit lookup and creation semantics."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        from threading import Lock

        self.values = dict(values or {})
        self.lock = Lock()

    def __call__(self, role: str, *, create: bool) -> str:
        import secrets

        with self.lock:
            if role in self.values:
                return self.values[role]
            if not create:
                raise KeyError(role)
            token = secrets.token_urlsafe(24)
            self.values[role] = token
            return token


def _credentials(*, wrong_role: str | None = None) -> _CredentialMap:
    values = {
        f"arrasdev_{name}": f"persistent-test-credential:arrasdev_{name}:v1" for name in PEOPLE
    }
    if wrong_role is not None:
        values[wrong_role] = "wrong-secret"
    return _CredentialMap(values)


def _attach(server: External, credential_source: _CredentialMap | None = None) -> TrussBox:
    source = credential_source or _credentials()
    box = TrussBox(url=server.url, credential_source=source)
    try:
        box.load(catalog_document(), SANDBOX_STEPS)
        box.finish()
    except BaseException:
        box.close()
        raise
    return box


def _role_state(server: External, role: str) -> tuple[object, ...]:
    """Read sensitive catalog fields only for equality checks; never return or print a secret."""
    return tuple(
        server.sql(
            "SELECT rolcanlogin, rolvaliduntil::text, rolpassword FROM pg_authid "
            "WHERE rolname = '" + role.replace("'", "''") + "'"
        )[0]
    )


def _is_member(server: External, role: str, member: str) -> bool:
    return bool(
        server.sql(
            "SELECT 1 FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid "
            "JOIN pg_roles u ON u.oid = m.member WHERE g.rolname = '"
            + role.replace("'", "''")
            + "' AND u.rolname = '"
            + member.replace("'", "''")
            + "'"
        )
    )


def _memberships(server: External, member: str) -> list[str]:
    rows = server.sql(
        "SELECT g.rolname FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid "
        "JOIN pg_roles u ON u.oid = m.member WHERE u.rolname = '"
        + member.replace("'", "''")
        + "' ORDER BY g.rolname"
    )
    return [str(row[0]) for row in rows]


def test_shared_credentials_authenticate_old_principal_after_restart(server: External) -> None:
    source = _credentials()
    first = _attach(server, source)
    alice = first.people["alice"]
    original_token = alice.token
    try:
        second = _attach(server, source)
        try:
            assert second.people["alice"].token == original_token
            assert second.people["bob"].token == source.values["arrasdev_bob"]
            # Both host instances authenticate fresh connections using the unchanged old principal.
            for host in (first, second):
                rows = (
                    host.arras.session(alice)
                    .query(
                        "catalog",
                        "SELECT x.code FROM catalog.UseCase x ORDER BY x.code LIMIT 100",
                        limit=100,
                    )
                    .rows
                )
                assert [str(row["code"]) for row in rows] == ["uc-alerts", "uc-pipeline"]
        finally:
            second.close()

        # Restart B again while A remains live and verify the shared credential still authenticates.
        third = _attach(server, source)
        try:
            assert third.people["alice"].token == original_token
            first.arras.session(alice).query(
                "catalog", "SELECT x.code FROM catalog.UseCase x LIMIT 1", limit=1
            )
            third.arras.session(alice).query(
                "catalog", "SELECT x.code FROM catalog.UseCase x LIMIT 1", limit=1
            )
        finally:
            third.close()
    finally:
        first.close()


def test_restart_preserves_revocations_unrelated_membership_and_role_attributes(
    server: External,
) -> None:
    source = _credentials()
    first = _attach(server, source)
    first.close()
    server.sql("CREATE ROLE unrelated_readers NOLOGIN")
    server.sql("REVOKE arrasdev_catalog_writer FROM arrasdev_bob GRANTED BY arras_installer")
    server.sql("GRANT unrelated_readers TO arrasdev_bob")
    assert not _is_member(server, "arrasdev_catalog_writer", "arrasdev_bob")
    before = _role_state(server, "arrasdev_bob")

    second = _attach(server, source)
    try:
        assert _role_state(server, "arrasdev_bob") == before
        assert not _is_member(server, "arrasdev_catalog_writer", "arrasdev_bob")
        assert _is_member(server, "unrelated_readers", "arrasdev_bob")
        with pytest.raises(ArrasError):
            second.arras.session(second.people["bob"]).invoke(
                "catalog.AddUseCase",
                {"code": "uc-revoked", "name": "Revoked", "workArea": "x"},
            )
    finally:
        second.close()


def test_expired_existing_person_is_not_reenabled_or_regranted(server: External) -> None:
    source = _credentials()
    first = _attach(server, source)
    first.close()
    server.sql("ALTER ROLE arrasdev_carol VALID UNTIL '2000-01-01'")
    server.sql("REVOKE arrasdev_catalog_reader FROM arrasdev_carol GRANTED BY arras_installer")
    assert not _is_member(server, "arrasdev_catalog_reader", "arrasdev_carol")
    before = _role_state(server, "arrasdev_carol")

    with pytest.raises(ValueError):
        _attach(server, source)
    assert _role_state(server, "arrasdev_carol") == before
    assert not _is_member(server, "arrasdev_catalog_reader", "arrasdev_carol")


@pytest.mark.parametrize("source_kind", ["missing", "wrong"])
def test_missing_or_wrong_credential_refuses_existing_role_without_mutation(
    server: External, source_kind: str
) -> None:
    source = _credentials()
    first = _attach(server, source)
    first.close()
    before = _role_state(server, "arrasdev_alice")
    membership_before = server.sql(
        "SELECT g.rolname FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid "
        "JOIN pg_roles u ON u.oid = m.member WHERE u.rolname = 'arrasdev_alice' "
        "ORDER BY g.rolname"
    )

    if source_kind == "missing":
        source.values.pop("arrasdev_alice")
    else:
        source.values["arrasdev_alice"] = "wrong-secret"
    credentials_before = source.values.copy()
    with pytest.raises(ValueError):
        TrussBox(url=server.url, credential_source=source)

    assert source.values == credentials_before
    assert _role_state(server, "arrasdev_alice") == before
    assert (
        server.sql(
            "SELECT g.rolname FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid "
            "JOIN pg_roles u ON u.oid = m.member WHERE u.rolname = 'arrasdev_alice' "
            "ORDER BY g.rolname"
        )
        == membership_before
    )


def test_concurrent_first_creation_serializes_to_one_stable_person_role(server: External) -> None:
    from concurrent.futures import ThreadPoolExecutor

    # Install once, then give each LocalTruss its own installing connection while racing one role.
    _attach(server).close()
    source = _credentials()
    hosts = [LocalTruss(url=server.url, credential_source=source).open() for _ in range(2)]
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            principals = list(pool.map(lambda host: host.person("quinn"), hosts))
        assert [principal.user for principal in principals] == [
            "arrasdev_quinn",
            "arrasdev_quinn",
        ]
        assert principals[0].token == principals[1].token == source.values["arrasdev_quinn"]
        assert server.sql("SELECT count(*) FROM pg_roles WHERE rolname = 'arrasdev_quinn'") == [
            (1,)
        ]
    finally:
        for host in hosts:
            host.close()


def test_cross_database_first_creation_recovers_global_role_conflict(server: External) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    second_database = "arras_truss_race_peer"
    server.sql(f"CREATE DATABASE {second_database} OWNER arras_installer")
    source = _credentials()
    hosts = [
        LocalTruss(
            url=server.url.replace(f"/{DATABASE}?", f"/{database}?"),
            credential_source=source,
        ).open()
        for database in (DATABASE, second_database)
    ]
    barrier = Barrier(2)
    try:
        for host in hosts:
            original_exists = host._exists
            waited = [False]

            def synchronized_exists(
                role: str, *, _original=original_exists, _waited=waited
            ) -> bool:
                result = _original(role)
                if role == "arrasdev_quinn" and not _waited[0]:
                    _waited[0] = True
                    if not result:
                        barrier.wait(timeout=8)
                return result

            host._exists = synchronized_exists  # type: ignore[method-assign]

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(host.person, "quinn") for host in hosts]
            try:
                principals = [future.result(timeout=20) for future in futures]
            except BaseException:
                barrier.abort()
                raise

        assert [principal.user for principal in principals] == [
            "arrasdev_quinn",
            "arrasdev_quinn",
        ]
        assert principals[0].token == principals[1].token == source.values["arrasdev_quinn"]
        assert server.sql("SELECT count(*) FROM pg_roles WHERE rolname = 'arrasdev_quinn'") == [
            (1,)
        ]
    finally:
        barrier.abort()
        for host in hosts:
            host.close()


def test_unowned_prefix_role_is_refused_without_takeover(server: External) -> None:
    server.sql("CREATE ROLE arrasdev_foreign LOGIN PASSWORD 'foreign-original'")
    before = _role_state(server, "arrasdev_foreign")
    host = LocalTruss(url=server.url, credential_source=_credentials()).open()
    try:
        with pytest.raises(ValueError, match="not administered"):
            host.person("foreign")
        assert _role_state(server, "arrasdev_foreign") == before
    finally:
        host.close()
        server.sql("DROP ROLE arrasdev_foreign")


def test_cached_person_with_stale_credentials_is_refused_before_grant_reconciliation(
    server: External,
) -> None:
    source = _credentials()
    host = _attach(server, source)
    host.person("erin", "editor")
    role = "arrasdev_erin"
    memberships_before = _memberships(server, role)
    credentials_before = source.values.copy()

    # The host still has Erin cached, while the database now rejects its stored credential.
    server.sql("ALTER ROLE arrasdev_erin PASSWORD 'externally-rotated' VALID UNTIL '2000-01-01'")
    try:
        with pytest.raises(ValueError, match="credential"):
            host.person("erin", "viewer")
        assert _memberships(server, role) == memberships_before
        assert source.values == credentials_before
    finally:
        host.close()


def test_host_loaded_before_module_preserves_revoked_grants_on_later_load(server: External) -> None:
    source = _credentials()
    host_a = TrussBox(url=server.url, credential_source=source)
    host_b = TrussBox(url=server.url, credential_source=source)
    document = catalog_document()
    try:
        host_a.load(document, SANDBOX_STEPS).finish()
        server.sql("CREATE ROLE unrelated_module_readers NOLOGIN")
        server.sql("REVOKE arrasdev_catalog_writer FROM arrasdev_bob GRANTED BY arras_installer")
        assert not _is_member(server, "arrasdev_catalog_writer", "arrasdev_bob")
        server.sql("GRANT unrelated_module_readers TO arrasdev_bob")
        assert not _is_member(server, "arrasdev_catalog_writer", "arrasdev_bob")

        # B was initialized before the module existed. Its first load must grant only roles it made.
        host_b.load(document, SANDBOX_STEPS).finish()
        assert not _is_member(server, "arrasdev_catalog_writer", "arrasdev_bob")
        assert _is_member(server, "unrelated_module_readers", "arrasdev_bob")

        # Repeating the same load on A also leaves the administrator's revocation intact.
        host_a.load(document).finish()
        assert not _is_member(server, "arrasdev_catalog_writer", "arrasdev_bob")
        assert _is_member(server, "unrelated_module_readers", "arrasdev_bob")

        for host in (host_a, host_b):
            with pytest.raises(ArrasError):
                host.arras.session(host.people["bob"]).invoke(
                    "catalog.AddUseCase",
                    {
                        "code": f"uc-denied-{host.name}",
                        "name": "Denied",
                        "workArea": "x",
                    },
                )
    finally:
        host_b.close()
        host_a.close()


def test_person_reconciles_managed_grants_across_hosts_and_keeps_unrelated_membership(
    server: External,
) -> None:
    source = _credentials()
    first = _attach(server, source)
    first.person("erin", "editor")
    first.close()
    server.sql("CREATE ROLE unrelated_operators NOLOGIN")
    server.sql("GRANT unrelated_operators TO arrasdev_erin")

    second = _attach(server, source)
    try:
        viewer = second.person("erin", "viewer")
        assert viewer.user == "arrasdev_erin"
        assert _is_member(server, "arrasdev_catalog_reader", "arrasdev_erin")
        assert not _is_member(server, "arrasdev_catalog_writer", "arrasdev_erin")
        assert _is_member(server, "unrelated_operators", "arrasdev_erin")
    finally:
        second.close()
