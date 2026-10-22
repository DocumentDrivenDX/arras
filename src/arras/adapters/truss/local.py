# SPDX-License-Identifier: MIT OR Apache-2.0
"""A local Truss for the dev host (TR-14): a throwaway PostgreSQL, or a persistent server it attaches to.
Never a deployed app's database.

`LocalTruss` starts `truss.LocalPostgres` (the `truss-test` dependency group: PostgreSQL 18.6 on a unix
socket) in a temporary directory, turns on password authentication so a person's token is a real
password, creates the installer role and a database, installs Truss through the adapter's own
`migrate`, and hands out what a host would: a `TrussBackend` over per-person connections and the
installing connection, people as login roles, and a module's reader and writer roles. The cluster
superuser has a password of its own (no pg_hba rule trusts a connection) and is used only for role
DDL and grants, as a database administrator would, never as a person.
Everything is removed on `close`; nothing is kept between runs.

With a `url` it attaches to a PostgreSQL server that is already running instead: the URL names the
installing role (LOGIN, CREATEROLE, not a superuser, owner of an existing database whose `pg_hba`
asks it for its password) and that role does all the DDL. Nothing about the server or the database is
changed except what Truss and the dev host put in that database: Truss is installed or verified
(`migrate`), people and a module's roles are made when absent with the role prefix `PERSISTENT_PREFIX`
(role names are cluster-wide, and a developer's own role may be named like a person), and `close` drops
nothing and stops nothing. `reset` removes what the dev host made (Truss's schema and roles, the
prefixed roles the installing role administers) and installs again; it never touches a role or a
database it did not create. The cluster's superuser is not used, so a role the dev host did not make
cannot be altered.

It is not the test harness (`tests/truss_harness.py`), which clones template databases and exists to
prove the adapter; this is the smallest provisioning a developer's own run needs. `truss` and
`psycopg` are imported inside functions.
"""

from __future__ import annotations

import re
import secrets
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol

from arras.adapters.truss import ModuleAccess, TrussBackend, create_backend
from arras.adapters.truss.endpoint import Endpoint, connect, endpoint_source, parse_credentialed
from arras.results import MigrationResult
from arras.types import Principal

INSTALLER = "arras_installer"  # owns the database; LOGIN CREATEROLE, never a superuser
DATABASE = "arras"
OUTAGES = ("unreachable", "access_denied")
PERSISTENT_OUTAGES = (
    "unreachable",
)  # a revoked CONNECT could lock the installing role out for good
PERSISTENT_PREFIX = "arrasdev_"  # the roles the dev host makes on a server it does not own
_TRUSS_OWNER = re.compile(r"truss_owner_([0-9a-f]+)")


class CredentialSource(Protocol):
    """Host-owned credential lookup: creation is allowed only for an absent person role."""

    def __call__(self, role: str, *, create: bool) -> str: ...


def _ident(name: str) -> Any:
    from psycopg import sql

    return sql.Identifier(name)


def _usable_credential(token: Any, role: str) -> str:
    if not isinstance(token, str) or not token:
        raise ValueError(f"no usable host-owned credential is available for {role!r}")
    return token


class LocalTruss:
    """One local database with Truss installed and the roles a host needs around it."""

    def __init__(
        self,
        name: str = "primary",
        *,
        directory: Path | None = None,
        url: str | None = None,
        credential_source: CredentialSource | None = None,
        reset: bool = False,
    ) -> None:
        if reset and url is None:
            raise ValueError("reset needs a persistent server to attach to")
        self.name = name
        self.persistent = url is not None
        self.prefix = PERSISTENT_PREFIX if self.persistent else ""
        self.installer = INSTALLER
        self.outages = PERSISTENT_OUTAGES if self.persistent else OUTAGES
        # a throwaway's root holds its cluster; an attached server has none, and an outage points
        # at a path under a directory that does not exist
        self.root = (
            Path("/nonexistent")
            if self.persistent
            else directory
            or Path(
                tempfile.mkdtemp(prefix="ar-")  # short: a socket path limit
            )
        )
        self._own_root = not self.persistent and directory is None
        self._url = url
        self._credential_source = credential_source
        self._reset = reset
        self._installer_password = secrets.token_urlsafe(18)
        self.superuser_password: str | None = (
            None if self.persistent else secrets.token_urlsafe(18)  # the cluster's postgres role
        )
        self._runtime: Any = None
        self._su: Any = None
        self._params: dict[str, Any] = {}
        self._endpoint: Endpoint | None = None
        self._outage: str | None = None
        self._tokens: dict[str, str] = {}
        self.created_people: set[str] = set()
        self._created_roles: set[str] = set()
        self._registrar: str | None = None
        self.migration: MigrationResult | None = None
        self.backend: TrussBackend | None = None

    # -- lifecycle
    def open(self) -> LocalTruss:
        if self.persistent:
            return self._attach()
        from psycopg import connect as psycopg_connect
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict
        from truss import LocalPostgres

        try:
            runtime = LocalPostgres(self.root / "pg")
            runtime.__enter__()
            self._runtime = runtime
            self._params = dict(conninfo_to_dict(self._runtime.info.connection_uri))
            self._su = psycopg_connect(**self._params, autocommit=True)
            su = self._su
            su.execute(
                sql.SQL("CREATE ROLE {} LOGIN CREATEROLE PASSWORD {}").format(
                    _ident(self.installer), sql.Literal(self._installer_password)
                )
            )
            su.execute(
                sql.SQL("ALTER ROLE postgres PASSWORD {}").format(
                    sql.Literal(self.superuser_password)
                )
            )
            hba = Path(su.execute("SHOW hba_file").fetchone()[0])
            # the cluster starts out trusting every local user; replace its rules whole, so that no
            # role, the superuser included, connects without its password, and nothing else (no
            # replication, no network) is let in
            hba.write_text("local all all scram-sha-256\n")
            su.execute("SELECT pg_reload_conf()")
            su.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    _ident(DATABASE), _ident(self.installer)
                )
            )
            self._endpoint = Endpoint(str(self._params["host"]), DATABASE, sslmode="disable")
            self.backend = create_backend(self.name, self._person_source, self._installing)
            self.migration = self.backend.migrate()
        except BaseException:
            self.close()  # no postgres process or root outlives a failed open
            raise
        return self

    def _attach(self) -> LocalTruss:
        """Attach to the server the URL names, as its installing role: nothing is created but
        what Truss and the dev host put in that database. A failure closes only the connection."""
        assert self._url is not None
        try:
            self._endpoint, self.installer, self._installer_password = parse_credentialed(self._url)
            self._url = None
            su = self._dial()
            self._su = su
            who = su.execute(
                "SELECT rolsuper, rolcreaterole FROM pg_roles WHERE rolname = current_user"
            ).fetchone()
            if who is None or not who[1]:
                raise ValueError(f"{self.installer!r} needs CREATEROLE: Truss's installing role")
            if self._reset:
                self._drop_what_was_made()
            self.backend = create_backend(self.name, self._person_source, self._installing)
            self.migration = self.backend.migrate()
        except BaseException:
            self.close()
            raise
        return self

    def _dial(self) -> Any:
        """The installing role's own connection (autocommit), asked for its password."""
        import psycopg

        assert self._endpoint is not None
        return psycopg.connect(
            **self._endpoint.parameters(),
            user=self.installer,
            password=self._installer_password,
            autocommit=True,
        )

    def close(self) -> None:
        """A throwaway is stopped and removed; an attached server is left running as it is, with
        everything in it."""
        if self._su is not None:
            self._su.close()
            self._su = None
        if self._runtime is not None:
            self._runtime.__exit__(None, None, None)
            self._runtime = None
        if self._own_root:
            shutil.rmtree(self.root, ignore_errors=True)

    @property
    def created_roles(self) -> frozenset[str]:
        """Managed role names created by this instance, for host bootstrap decisions."""
        return frozenset(self._created_roles)

    def __enter__(self) -> LocalTruss:
        return self.open()

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- connections
    def _current(self) -> Endpoint:
        assert self._endpoint is not None
        if self._outage == "unreachable":
            return replace(self._endpoint, host=str(self.root / "nowhere"))
        return self._endpoint

    def _person_source(self, principal: Principal) -> Any:
        return endpoint_source(self._current())(principal)

    def _installing(self) -> Any:
        return connect(self._current(), self.installer, self._installer_password)

    @property
    def endpoint(self) -> Endpoint:
        """Where the database is (a socket directory): what a handle for it would name."""
        assert self._endpoint is not None
        return self._endpoint

    @property
    def su(self) -> Any:
        """The connection that does the role DDL: the cluster superuser on a throwaway, the
        installing role on an attached server (opened again if the server restarted)."""
        if self._su is None:
            raise RuntimeError("the local Truss is not open")
        if self.persistent and (self._su.closed or self._su.broken):
            self._su = self._dial()
        return self._su

    @property
    def registrar_role(self) -> str:
        """Truss's registrar role. Its name is in the install's result only on the run that
        installed; on a later attach it is read from the installation: the registrar named like the
        owner of Truss's schema, which the installing role administers."""
        if self.migration is not None and self.migration.registrar_role is not None:
            return self.migration.registrar_role
        if self._registrar is None and self.persistent:
            row = self.su.execute(
                "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'truss'"
            ).fetchone()
            found = _TRUSS_OWNER.fullmatch(row[0]) if row else None
            registrar = f"truss_registrar_{found.group(1)}" if found else None
            if registrar is not None and self._administered(registrar):
                self._registrar = registrar
        if self._registrar is None:
            raise RuntimeError("the local Truss was installed by someone else: no registrar role")
        return self._registrar

    # -- people and roles
    def role(self, user: str) -> str:
        """The database role of a person: the name with the role prefix of a persistent server."""
        return self.prefix + user

    def _exists(self, role: str) -> bool:
        return bool(self.su.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role]).fetchone())

    def _administered(self, role: str) -> bool:
        """Whether the installing role administers `role`: it made it (or was given it), so the
        dev host may alter or drop it. A role it did not make is never touched."""
        return bool(
            self.su.execute(
                "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid "
                "JOIN pg_roles u ON u.oid = m.member "
                "WHERE r.rolname = %s AND u.rolname = current_user AND m.admin_option",
                [role],
            ).fetchone()
        )

    def _made(self) -> list[tuple[str, bool]]:
        """The prefixed roles the installing role administers, as (name, can log in)."""
        rows = self.su.execute(
            "SELECT r.rolname, r.rolcanlogin FROM pg_auth_members m "
            "JOIN pg_roles r ON r.oid = m.roleid JOIN pg_roles u ON u.oid = m.member "
            "WHERE u.rolname = current_user AND m.admin_option AND starts_with(r.rolname, %s) "
            "ORDER BY r.rolname",
            [self.prefix],
        ).fetchall()
        return [(str(name), bool(login)) for name, login in rows]

    def person(self, user: str) -> Principal:
        """Return the person's own login, creating it only when the role is absent."""
        from psycopg import sql

        role = self.role(user)
        if self.persistent or user not in self._tokens:
            created = False
            try:
                with self.su.transaction():
                    # PostgreSQL advisory locks are database-scoped. The duplicate-role check
                    # after CREATE also handles another host racing from a different database.
                    self.su.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [role])
                    if self._exists(role):
                        if not self.persistent:
                            raise ValueError(f"{role!r} is a role of the database already")
                        token = self._existing_person_token(role)
                    else:
                        token = self._credential(role, create=True)
                        self.su.execute(
                            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                                _ident(role), sql.Literal(token)
                            )
                        )
                        created = True
            except Exception as error:
                state = getattr(error, "sqlstate", None)
                constraint = getattr(getattr(error, "diag", None), "constraint_name", None)
                duplicate = state == "42710" or (
                    state == "23505" and constraint == "pg_authid_rolname_index"
                )
                if not duplicate:
                    raise
                # A same-name role may have appeared in another database while this
                # transaction was creating it. Never alter it; verify ownership and login.
                if not self._exists(role):
                    raise ValueError(f"could not create person role {role!r}") from None
                token = self._existing_person_token(role)
            if created:
                self.created_people.add(user)
                self._created_roles.add(role)
            self._tokens[user] = token
        return Principal(role, self._tokens[user])

    def _credential(self, role: str, *, create: bool) -> str:
        source = self._credential_source
        if source is None:
            if self.persistent:
                raise ValueError(
                    "persistent person credentials need a host-owned credential source"
                )
            return secrets.token_urlsafe(24)
        try:
            token = source(role, create=create)
        except Exception:
            raise ValueError(f"no usable host-owned credential is available for {role!r}") from None
        return _usable_credential(token, role)

    def _existing_person_token(self, role: str) -> str:
        if not self._administered(role):
            raise ValueError(f"{role!r} is not administered by this installer")
        source = self._credential_source
        if source is None:
            raise ValueError("persistent person credentials need a host-owned credential source")
        try:
            token = self._credential(role, create=False)
        except Exception:
            raise ValueError(
                f"the stored credential for {role!r} is missing or unavailable"
            ) from None
        try:
            with connect(self._current(), role, token) as person:
                actual = person.execute("SELECT current_user").fetchone()[0]
            if actual != role:
                raise ValueError
        except Exception as error:
            if getattr(error, "sqlstate", None) in {"28P01", "28000"}:
                raise ValueError(
                    f"the stored credential for {role!r} was refused; coordinated rotation is required"
                ) from None
            raise ValueError(
                f"could not verify the stored credential for {role!r}; database authentication is unavailable"
            ) from None
        return token

    def token(self, user: str) -> str:
        return self._tokens[user]

    def set_password(self, user: str, token: str) -> None:
        """Replace a person's token (the password of their role), for a host whose tokens have a
        shape of their own (the MCP process reads a JWT)."""
        from psycopg import sql

        if self.persistent:
            raise ValueError("persistent person credentials require coordinated rotation")
        if user not in self._tokens:
            raise KeyError(user)
        self.su.execute(
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(_ident(self.role(user)), sql.Literal(token))
        )
        self._tokens[user] = token

    def reader_role(self, module: str) -> str:
        return f"{self.prefix}{module}_reader"

    def writer_role(self, module: str) -> str:
        return f"{self.prefix}{module}_writer"

    def auditor_role(self, module: str) -> str:
        """The module's audit role (Truss's `ModuleAuditGrant`): a person in it reads the module's
        `changes` and `loads` and nothing of its data."""
        return f"{self.prefix}{module}_auditor"

    def membership(self, user: str, role: str, *, grant: bool) -> None:
        """Make `user` a member of `role` (`WITH SET FALSE`, as a DBA grants) or end it."""
        from psycopg import sql

        text = "GRANT {} TO {} WITH SET FALSE" if grant else "REVOKE {} FROM {}"
        self.su.execute(sql.SQL(text).format(_ident(role), _ident(self.role(user))))

    def module_roles(self, module: str) -> tuple[str, str]:
        """The module's reader and writer roles, created (NOLOGIN) when they are not there. On a
        persistent server a role that is there must be one the installing role administers."""
        from psycopg import sql

        roles = (self.reader_role(module), self.writer_role(module))
        for role in roles:
            if not self._exists(role):
                self.su.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(_ident(role)))
                self._created_roles.add(role)
            elif self.persistent and not self._administered(role):
                raise ValueError(f"{role!r} is a role this dev host did not make")
        return roles

    def known_modules(self) -> list[str]:
        """The modules of an earlier run on a persistent server: those with both roles here."""
        made = {name for name, login in self._made() if not login}
        found: list[str] = []
        for name in sorted(made):
            if name.startswith(self.prefix) and name.endswith("_reader"):
                module = name[len(self.prefix) : -len("_reader")]
                if module and self.writer_role(module) in made:
                    found.append(module)
        return found

    def _drop_what_was_made(self) -> None:
        """Remove what the dev host and Truss's install put in this database: Truss's schema, its
        owner and registrar roles and the prefixed roles the installing role administers. A role it
        does not administer, and every database, stays."""
        from psycopg import sql

        su = self._su
        owner = su.execute(
            "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'truss'"
        ).fetchone()
        found = _TRUSS_OWNER.fullmatch(owner[0]) if owner else None
        su.execute("DROP SCHEMA IF EXISTS truss CASCADE")
        ours = [name for name, _ in self._made()]  # own nothing: only privileges on Truss's schema
        owner_role = f"truss_owner_{found.group(1)}" if found else None
        registrar = f"truss_registrar_{found.group(1)}" if found else None
        for role in [*ours, *(r for r in (registrar, owner_role) if r)]:
            if self._exists(role) and self._administered(role):
                if role == owner_role:  # the privileges it still holds here, which block a drop
                    su.execute(sql.SQL("DROP OWNED BY {}").format(_ident(role)))
                su.execute(sql.SQL("DROP ROLE {}").format(_ident(role)))
        self._tokens.clear()
        self.created_people.clear()
        self._created_roles.clear()
        self._registrar = None

    def configure_module(self, module: str, document_id: str) -> None:
        """Hand a registered module's roles to Truss. The backend takes its module access when it
        is built, so a module registered later is configured through a second instance over the
        same database: the grant persists inside Truss."""
        from psycopg import sql

        reader, writer = self.module_roles(module)
        auditor = self.auditor_role(module)
        if not self._exists(auditor):
            self.su.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT").format(_ident(auditor)))
            self._created_roles.add(auditor)
        once = create_backend(
            self.name,
            self._person_source,
            self._installing,
            module_access={module: ModuleAccess(document_id, reader, writer, auditor)},
        )
        once.configure_access()

    def expire(self, user: str, *, restore: bool = False) -> None:
        from psycopg import sql

        until = "infinity" if restore else "2000-01-01"
        self.su.execute(
            sql.SQL("ALTER ROLE {} VALID UNTIL {}").format(
                _ident(self.role(user)), sql.Literal(until)
            )
        )

    # -- outage, as a real failure
    def outage(self, reason: str | None) -> None:
        """`unreachable` points every connection at a socket that is not there; `access_denied`
        (a throwaway only) revokes CONNECT; `None` restores. Another reason is a `ValueError`."""
        if reason is not None and reason not in self.outages:
            raise ValueError(f"outage is one of {self.outages}")
        assert self._endpoint is not None
        database = self._endpoint.dbname
        if self._outage == "access_denied":
            for who in ("PUBLIC", self.installer):
                self.su.execute(f'GRANT CONNECT ON DATABASE "{database}" TO {who}')
        self._outage = None
        if reason == "access_denied":
            for who in ("PUBLIC", self.installer):
                self.su.execute(f'REVOKE CONNECT ON DATABASE "{database}" FROM {who}')
            self.su.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND usename <> 'postgres'",
                [database],
            )
        self._outage = reason


__all__ = ["DATABASE", "INSTALLER", "OUTAGES", "PERSISTENT_PREFIX", "LocalTruss"]
