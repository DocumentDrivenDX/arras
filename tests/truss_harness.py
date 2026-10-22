# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The conformance harness for the Truss adapter: a real Truss on a local PostgreSQL 18.6.

What the harness builds, per corpus case (CONTRACT-004):

- one PostgreSQL server per test session (`truss.LocalPostgres`, the `truss-test` dependency group),
  with password (scram) authentication, so a person's token is a real password: another person's
  token and an expired role both fail at connect, as they would in production;
- a template database holding Truss's own install, the corpus module registered through Truss and
  module access configured, built once per document; each case clones it (about 0.3 s instead of the
  7 s installing Truss and registering the module cost, about 0.5 to 0.9 s of it preparing the module);
- a LOGIN role per person, named exactly as the person (Truss records `session_user` as the actor),
  with the module's reader and writer roles and, for `schema`, the installation's registrar role;
- `seed` through Truss's own import API as that person, so a read case does not wait for the
  adapter's `import_records`; `write` goes through the backend under test (it is the adapter's
  `apply`);
- `outage` as a real failure: a socket that is not there (`unreachable`), a revoked CONNECT
  (`access_denied`) and an install marker no supported release matches (`unsupported_version`).

Nothing here sets session state on a connection the adapter will use: connections arrive idle,
autocommit off, with no role and no statement timeout (CONTRACT-005). The superuser is used only for
role DDL, grants, outage tampering and dropping databases, never as a person.

`psycopg` and `truss` are imported inside functions, so the module imports in the default test run,
which has neither.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import secrets
import shutil
import tempfile
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from arras.actions import Plan
from arras.adapters.truss import TrussBackend, create_backend
from arras.backend import Backend
from arras.conformance import Limit
from arras.model import ModuleInfo
from arras.results import Receipt
from arras.types import Principal

INSTALLER = "arras_installer"  # owns the databases; needs CREATEROLE, never superuser
REGISTRAR = "arras_registrar"  # registers the module in a template; never a corpus person
STATEMENT_TIMEOUT_MS = 10_000
OPERATION_TIMEOUT_MS = 60_000
# the released token's shape, with an installation no database here holds
_TOKEN_PROFILE = {
    "identity": "truss-authority-receipt-visibility",
    "version": "0.1",
    "sha256": "97d54f46af687510fd3ae10aaa37c761d17d6b371d12171ea15a0d402b8855e9",
}


def available() -> str | None:
    """Why the real harness cannot run here, or None when it can."""
    if importlib.util.find_spec("pgserver") is None:
        return "pgserver-pg18 is not installed (uv sync --extra truss --group truss-test)"
    if importlib.util.find_spec("truss") is None or importlib.util.find_spec("psycopg") is None:
        return "the truss extra is not installed (uv sync --extra truss --group truss-test)"
    return None


def ok(outcome: Any) -> Any:
    """The value of a Truss `Ok`; anything else fails loudly with what Truss said."""
    from truss import Ok

    if not isinstance(outcome, Ok):
        raise RuntimeError(f"Truss refused the harness's own call: {outcome!r}")
    return outcome.value


@contextmanager
def transaction(conn: Any, read_only: bool = False) -> Iterator[tuple[Any, Any]]:
    """Adopt an idle psycopg connection for one Truss transaction: (assembly, transaction handle).
    The caller commits by leaving the block normally; an exception rolls back."""
    from truss import CatalogRuntimeConfiguration, adopt_psycopg_host, create_reference_assembly

    conn.execute("BEGIN READ ONLY" if read_only else "BEGIN")
    conn.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}ms'")
    host = adopt_psycopg_host(
        conn, statement_timeout_ms=STATEMENT_TIMEOUT_MS, operation_timeout_ms=OPERATION_TIMEOUT_MS
    )
    handle = ok(host.adopt_transaction(access_mode="read_only" if read_only else "read_write"))
    assembly = ok(create_reference_assembly(CatalogRuntimeConfiguration(), host))
    try:
        yield assembly, handle
    except BaseException:
        host.detach()
        conn.rollback()
        raise
    host.detach()
    conn.commit()


def document_id(document: bytes) -> str:
    """Truss's document id is the UMF document's own top-level `id`, not the module's name."""
    return json.loads(document)["id"]


def _ident(name: str) -> Any:
    from psycopg import sql

    return sql.Identifier(name)


class World:
    """One case's database, its people and its outage state."""

    def __init__(self, cluster: Cluster, template: _Template, db: str, module: ModuleInfo) -> None:
        self.cluster = cluster
        self.template = template
        self.db = db
        self.module = module
        self.document = template.document
        self.tokens: dict[str, str] = {}
        self.admins: set[str] = set()
        self.outage_reason: str | None = None
        self._release: str | None = None

    # -- names (one place, so the host's naming decision lands here)
    @property
    def registrar_role(self) -> str:
        return self.template.registrar_role

    @property
    def owner_role(self) -> str:
        return self.template.owner_role

    def reader_role(self, module: str) -> str:
        return f"{module}_reader"

    def writer_role(self, module: str) -> str:
        return f"{module}_writer"

    # -- people
    def grant(self, user: str, modules: Mapping[str, Sequence[str]], admin: bool) -> Principal:
        token = secrets.token_urlsafe(24)
        su = self.cluster.su
        from psycopg import sql

        su.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(_ident(user), sql.Literal(token))
        )
        self.tokens[user] = token
        for module, modes in modules.items():
            for mode in modes:
                role = self._role_for(module, mode)
                if role is not None:
                    su.execute(
                        sql.SQL("GRANT {} TO {} WITH SET FALSE").format(_ident(role), _ident(user))
                    )
        if admin:
            self.admins.add(user)
        return self.principal(user)

    def _role_for(self, module: str, mode: str) -> str | None:
        if module != self.module.name:
            raise ValueError(f"the world holds module {self.module.name!r}, not {module!r}")
        if mode == "read":
            return self.reader_role(module)
        if mode == "write":
            return self.writer_role(module)
        if mode == "schema":
            return self.registrar_role  # installation-wide (D3)
        if mode == "journal":
            return f"{module}_auditor"  # Truss's audit grant is a role of its own (plan B8)
        raise ValueError(f"unknown mode {mode!r}")

    def principal(self, user: str) -> Principal:
        return Principal(user, self.tokens[user], admin=user in self.admins)

    def expire(self, user: str) -> None:
        from psycopg import sql

        self.cluster.su.execute(
            sql.SQL("ALTER ROLE {} VALID UNTIL '2000-01-01'").format(_ident(user))
        )

    # -- connections: a NEW idle connection per call, autocommit off, no options, no role
    def _connect(self, user: str, password: str) -> Any:
        import psycopg

        params = dict(self.cluster.params, dbname=self.db, user=user, password=password)
        if self.outage_reason == "unreachable":
            params["host"] = str(self.cluster.root / "nowhere")
        return psycopg.connect(**params)

    @contextmanager
    def connection_source(self, principal: Principal) -> Iterator[Any]:
        conn = self._connect(principal.user, principal.token)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def installing_connection(self) -> Iterator[Any]:
        conn = self._connect(INSTALLER, self.cluster.installer_password)
        try:
            yield conn
        finally:
            conn.close()

    # -- outage
    def outage(self, reason: str | None) -> None:
        self._restore()
        if reason is None:
            return
        if reason == "unreachable":
            self._cut_sessions()
        elif reason == "access_denied":
            self._revoke_connect()
            self._cut_sessions()
        elif reason == "unsupported_version":
            self._tamper_marker()
        else:
            raise ValueError(f"unknown outage {reason!r}")
        self.outage_reason = reason

    def _restore(self) -> None:
        if self.outage_reason == "access_denied":
            for who in ("PUBLIC", INSTALLER):
                self._su_db_statement(f"GRANT CONNECT ON DATABASE {self._q(self.db)} TO {who}")
        elif self.outage_reason == "unsupported_version":
            self._tamper_marker(restore=True)
        self.outage_reason = None

    @staticmethod
    def _q(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    def _su_db_statement(self, statement: str) -> None:
        self.cluster.su.execute(statement)

    def _revoke_connect(self) -> None:
        for who in ("PUBLIC", INSTALLER):
            self._su_db_statement(f"REVOKE CONNECT ON DATABASE {self._q(self.db)} FROM {who}")

    def _cut_sessions(self) -> None:
        """Privileges and sockets bind at connect, so a pooled connection is cut as well."""
        self.cluster.su.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND usename <> 'postgres'",
            [self.db],
        )

    def _tamper_marker(self, restore: bool = False) -> None:
        """A test-only stand-in for another release: Truss 0.0.45 installs no other, and its marker is
        immutable except with the trigger off (recorded as a harness deviation in the plan)."""
        table = "truss.catalog_runtime_installation"
        with self.cluster.superuser(self.db) as su:
            if not restore:
                self._release = su.execute(f"SELECT release_id FROM {table}").fetchone()[0]
                su.execute(f"ALTER TABLE {table} DISABLE TRIGGER catalog_immutable")
                su.execute(
                    f"UPDATE {table} SET release_id = %s", ["truss-catalog-runtime/0.39-candidate"]
                )
            else:
                su.execute(f"UPDATE {table} SET release_id = %s", [self._release])
                su.execute(f"ALTER TABLE {table} ENABLE ALWAYS TRIGGER catalog_immutable")

    # -- seed, through Truss's own import API as the person
    def seed(self, user: str, records: Sequence[Mapping[str, object]]) -> None:
        from truss import CatalogDocument

        docs = (CatalogDocument(self.template.document_id, self.template.revision, self.document),)
        with self.connection_source(self.principal(user)) as conn:
            with transaction(conn) as (assembly, handle):
                _Seeder(self.module, assembly, handle, docs).run(records)

    def teardown(self) -> None:
        self.outage(None)
        su = self.cluster.su
        su.execute(f"DROP DATABASE IF EXISTS {self._q(self.db)} WITH (FORCE)")
        for user in self.tokens:
            su.execute(f"DROP ROLE IF EXISTS {self._q(user)}")


class _Seeder:
    """Load a fixture's records as one person: objects in one import, then the edges."""

    def __init__(self, module: ModuleInfo, assembly: Any, handle: Any, docs: Any) -> None:
        self.module, self.a, self.h, self.docs = module, assembly, handle, docs
        self.doc = docs[0].document_id
        self.mod = module.name
        self.created: dict[str, Any] = {}
        self._rels: dict[str, str] | None = None

    def _import(self, drafts: Sequence[Any]) -> list[Any]:
        """The fixture's records through Truss's batched import, as the person (load id `seed`)."""
        from truss.contracts import MapValue
        from truss.imports import ImportReported

        built = ok(self.a.build_import_records_in_transaction(self.h, tuple(drafts)))
        given = built.context.input(
            built.records, load_id="seed", asserted_origin=MapValue(entries=())
        )
        done = self.a.import_batched_in_transaction(self.h, given, documents=self.docs)
        if not isinstance(done.result, ImportReported):
            raise RuntimeError(f"the fixture did not import: {done!r}")
        return list(done.result.report.outcomes)

    def run(self, records: Sequence[Mapping[str, object]]) -> None:
        objects = [r for r in records if "type" in r]
        edges = [r for r in records if "relationship" in r]
        if objects:
            self._objects(objects)
        if edges:
            self._edges(edges)

    def _objects(self, objects: Sequence[Mapping[str, object]]) -> None:
        from truss.batched_import import ObjectImportDraft
        from truss.contracts import TextValue
        from truss.groups import AuthoredValue
        from truss.imports import ImportCreated

        built: list[Any] = []
        for r in objects:
            info = self.module.entity_type(str(r["type"]))
            assert info is not None, r
            values: dict[str, Any] = dict(r["properties"])  # type: ignore[arg-type]
            values[info.key] = r["key"]
            authored = tuple(
                AuthoredValue(name=k, value=TextValue(kind="string", text=str(v)))
                for k, v in values.items()
            )
            built.append(
                ObjectImportDraft(
                    document_id=self.doc,
                    module_id=self.mod,
                    record_id=str(r["type"]),
                    values=authored,
                )
            )
        for r, outcome in zip(objects, self._import(built), strict=True):
            if not isinstance(outcome, ImportCreated):
                raise ValueError(f"the corpus fixture did not load: {r} -> {outcome!r}")
            self.created[str(r["key"])] = outcome.identity

    def _relationship_id(self, name: str) -> str:
        if self._rels is None:
            catalog = ok(self.a.reader_catalog_in_transaction(self.h))
            self._rels = {
                rel["name"]: rel["authoredId"]
                for m in catalog.modules
                for rel in m["relationships"]
            }
        return self._rels[name]

    def _endpoint(self, key: str, types: Sequence[str]) -> Any:
        from truss import ObjectFound
        from truss.contracts import TypedIdentity

        if key in self.created:
            return self.created[key]
        for qualified in types:
            local = qualified.split(".", 1)[-1]
            found = ok(
                self.a.lookup_key_in_transaction(
                    self.h,
                    document_id=self.doc,
                    module_id=self.mod,
                    record_id=local,
                    key_id="identity",
                    values=(key,),
                )
            )
            if isinstance(found, ObjectFound):
                ref = ok(
                    self.a.get_type_reference_in_transaction(
                        self.h, document_id=self.doc, module_id=self.mod, record_id=local
                    )
                )
                o = found.object
                return TypedIdentity(
                    id=str(o.id),
                    type_id=str(o.type_id),
                    definition_pin=ref.definition_pin,
                    owner=ref.owner,
                )
        raise ValueError(f"the corpus fixture links {key!r}, which no record holds")

    def _edges(self, edges: Sequence[Mapping[str, object]]) -> None:
        from truss.batched_import import EdgeImportDraft
        from truss.groups import NullOrderKey
        from truss.imports import ImportCreated

        built: list[Any] = []
        for r in edges:
            rel = next(x for x in self.module.relationships if x.name == r["relationship"])
            built.append(
                EdgeImportDraft(
                    document_id=self.doc,
                    module_id=self.mod,
                    relationship_id=self._relationship_id(rel.name),
                    source_endpoint=self._endpoint(str(r["source"]), rel.source),
                    target_endpoint=self._endpoint(str(r["target"]), rel.target),
                    values=(),
                    order_key=NullOrderKey(),
                )
            )
        for r, outcome in zip(edges, self._import(built), strict=True):
            if not isinstance(outcome, ImportCreated):
                raise ValueError(f"the corpus fixture did not load: {r} -> {outcome!r}")


class _Template:
    def __init__(
        self, db: str, document: bytes, owner_role: str, registrar_role: str, module: str
    ) -> None:
        self.db = db
        self.document = document
        self.document_id = document_id(document)
        self.revision = hashlib.sha256(document).hexdigest()
        self.owner_role = owner_role
        self.registrar_role = registrar_role
        self.module = module


class Cluster:
    """One PostgreSQL server for a test session, and the worlds cloned on it."""

    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ar-"))  # short: a unix socket path is ~103 bytes
        self.installer_password = secrets.token_urlsafe(18)
        self.registrar_password = secrets.token_urlsafe(18)
        self._runtime: Any = None
        self._su: Any = None
        self.params: dict[str, Any] = {}
        self._templates: dict[str, _Template] = {}
        self._world: World | None = None
        self._counter = 0

    @property
    def su(self) -> Any:
        if self._su is None:
            self._start()
        return self._su

    def _start(self) -> None:
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        from truss import LocalPostgres

        self._runtime = LocalPostgres(self.root / "pg")
        self._runtime.__enter__()
        self.params = dict(conninfo_to_dict(self._runtime.info.connection_uri))
        self._su = psycopg.connect(**self.params, autocommit=True)
        from psycopg import sql

        for role, password, create in (
            (
                INSTALLER,
                self.installer_password,
                sql.SQL("CREATE ROLE {} LOGIN CREATEROLE PASSWORD {}"),
            ),
            (REGISTRAR, self.registrar_password, sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}")),
        ):
            self._su.execute(create.format(_ident(role), sql.Literal(password)))
        hba = Path(self._su.execute("SHOW hba_file").fetchone()[0])
        hba.write_text("local all postgres trust\nlocal all all scram-sha-256\n" + hba.read_text())
        self._su.execute("SELECT pg_reload_conf()")

    @contextmanager
    def superuser(self, db: str) -> Iterator[Any]:
        import psycopg

        conn = psycopg.connect(**dict(self.params, dbname=db), autocommit=True)
        try:
            yield conn
        finally:
            conn.close()

    def _as(self, user: str, password: str, db: str) -> Any:
        import psycopg

        return psycopg.connect(**dict(self.params, dbname=db, user=user, password=password))

    # -- the template: Truss's own install, the registered module, module access
    def _template(self, module: ModuleInfo, document: bytes, registered: bool = True) -> _Template:
        digest = hashlib.sha256(document).hexdigest()
        key = digest if registered else f"{digest}-empty"
        if key not in self._templates:
            self._templates[key] = self._build_template(module, document, digest, registered)
        return self._templates[key]

    def _build_template(
        self, module: ModuleInfo, document: bytes, digest: str, registered: bool = True
    ) -> _Template:
        """`registered` false leaves Truss installed with nothing registered (catalog head 0)."""
        from psycopg import sql
        from truss import CatalogDocument, ModuleAccessGrant, ModuleAuditGrant

        db = f"arras_t_{digest[:12]}" if registered else f"arras_e_{digest[:12]}"
        su = self.su
        su.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(_ident(db), _ident(INSTALLER)))
        for role in (f"{module.name}_reader", f"{module.name}_writer"):
            if not su.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role]).fetchone():
                su.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(_ident(role)))
        auditor = f"{module.name}_auditor"  # the journal grant: its own role, never a reader's
        if not su.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [auditor]).fetchone():
            su.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT").format(_ident(auditor)))
        inst = self._as(INSTALLER, self.installer_password, db)
        with transaction(inst) as (assembly, handle):
            installed = ok(assembly.install_in_transaction(handle))
        su.execute(
            sql.SQL("GRANT {} TO {} WITH SET FALSE").format(
                _ident(installed.registrar_role), _ident(REGISTRAR)
            )
        )
        if not registered:
            inst.close()
            return _Template(
                db, document, installed.owner_role, installed.registrar_role, module.name
            )
        doc = CatalogDocument(document_id(document), digest, document)
        reg = self._as(REGISTRAR, self.registrar_password, db)
        with transaction(reg) as (assembly, handle):
            prepared = assembly.prepare_catalog((doc,))
            ok(
                assembly.accept_in_transaction(
                    handle,
                    prepared,
                    request_key="harness-template",
                    origin_bytes=b'{"x-action":"register"}',
                )
            )
        reg.close()
        grant = ModuleAccessGrant(
            document_id(document), module.name, f"{module.name}_reader", f"{module.name}_writer"
        )
        with transaction(inst) as (assembly, handle):
            ok(assembly.configure_module_access_in_transaction(handle, (grant,)))
            audit = ModuleAuditGrant(
                document_id=document_id(document), module_id=module.name, auditor_role=auditor
            )
            if type(
                ok(assembly.grant_module_audit_access_in_transaction(handle, audit))
            ).__name__ != ("AuditAccessUpdated"):
                raise RuntimeError("Truss refused the harness's audit grant")
        inst.close()
        return _Template(db, document, installed.owner_role, installed.registrar_role, module.name)

    # -- a database with nothing installed, for the adapter's own `migrate`
    @contextmanager
    def bare_database(self, *, owner: str = INSTALLER) -> Iterator[Bare]:
        """An empty database owned by `owner` (the installer by default). A role other than the
        installer is created here, with LOGIN and no CREATEROLE, and dropped with the database."""
        from psycopg import sql

        self._counter += 1
        db = f"arras_bare{self._counter}"
        password = self.installer_password
        extra = owner != INSTALLER
        if extra:
            password = secrets.token_urlsafe(18)
            self.su.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    _ident(owner), sql.Literal(password)
                )
            )
        self.su.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(_ident(db), _ident(owner)))
        bare = Bare(self, db, owner, password)
        try:
            yield bare
        finally:
            bare.close()
            self.su.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(_ident(db)))
            for role in bare.roles:
                self.su.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(_ident(role)))
            if extra:
                self.su.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(_ident(owner)))

    # -- worlds
    def begin_world(self, module: ModuleInfo, document: bytes, registered: bool = True) -> World:
        """A fresh world; the previous one is disposed first, because the runner never closes a
        harness and a person's role name is cluster-wide."""
        self.end_world()
        from psycopg import sql

        template = self._template(module, document, registered)
        self._counter += 1
        db = f"arras_w{self._counter}"
        self.su.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {} OWNER {}").format(
                _ident(db), _ident(template.db), _ident(INSTALLER)
            )
        )
        self._world = World(self, template, db, module)
        return self._world

    def end_world(self) -> None:
        if self._world is not None:
            world, self._world = self._world, None
            world.teardown()

    def close(self) -> None:
        if self._su is not None:
            self.end_world()
            self._su.close()
            self._su = None
        if self._runtime is not None:
            self._runtime.__exit__(None, None, None)
            self._runtime = None
        shutil.rmtree(self.root, ignore_errors=True)


class Bare:
    """A database with no Truss in it, its installing connection and the people made on it."""

    def __init__(self, cluster: Cluster, db: str, installer: str, password: str) -> None:
        self.cluster = cluster
        self.db = db
        self.installer = installer
        self._password = password
        self.tokens: dict[str, str] = {}
        self.roles: list[str] = []

    def _connect(self, user: str, password: str) -> Any:
        import psycopg

        return psycopg.connect(
            **dict(self.cluster.params, dbname=self.db, user=user, password=password)
        )

    @contextmanager
    def installing_connection(self) -> Iterator[Any]:
        conn = self._connect(self.installer, self._password)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def connection_source(self, principal: Principal) -> Iterator[Any]:
        conn = self._connect(principal.user, principal.token)
        try:
            yield conn
        finally:
            conn.close()

    def role(self, name: str) -> str:
        """A NOLOGIN role (a module's reader or writer); the cluster is shared, so it is dropped
        with the database."""
        from psycopg import sql

        self.cluster.su.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(_ident(name)))
        self.roles.append(name)
        return name

    def person(self, user: str, *member_of: str) -> Principal:
        """A person who may log in, a member of each role `WITH SET FALSE` (as the DBA grants)."""
        from psycopg import sql

        token = secrets.token_urlsafe(24)
        su = self.cluster.su
        su.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(_ident(user), sql.Literal(token))
        )
        self.roles.append(user)
        self.tokens[user] = token
        for role in member_of:
            su.execute(sql.SQL("GRANT {} TO {} WITH SET FALSE").format(_ident(role), _ident(user)))
        return Principal(user, token)

    def backend(self, **kw: Any) -> TrussBackend:
        return create_backend("truss", self.connection_source, self.installing_connection, **kw)

    def close(self) -> None:
        pass


def foreign_token() -> str:
    """A token of the released shape that no database here issued: another installation's. Truss
    answers it `epoch_profile`, which CONTRACT-004 maps to Unavailable, not Invalid; only a
    reader-only corpus case expects it Invalid (tests/test_truss_reached.py records the difference)."""
    body = {
        "interfaceVersion": "truss-receipt-position/0.1.0",
        "positionProfile": _TOKEN_PROFILE,
        "installationId": str(uuid.uuid4()),
        "sourceEpoch": str(uuid.uuid4()),
        "receiptStorageRowId": "1",
        "writerXid": "770",
    }
    return (
        base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode())
        .rstrip(b"=")
        .decode()
    )


class TrussHarness:
    """The `Harness` for the Truss adapter. The world is built on first use: the runner makes a
    probe harness that reads only `roles` and `corpus_version`, and one per case."""

    roles = ("reader", "provider")
    corpus_version = 13

    # Truss 0.0.45 limits that end a corpus case, each at the step it ends (the runner holds the
    # case to that step, and fails it when it passes: the limit is gone). Each case carries the ask
    # in its corpus `limits` note; the corpus is not weakened (plan TR-12, truss-requirements).
    LIMITS = {
        # Weft refuses the repeated output name: the alias equals the relationship Truss appends
        "read.relationship-columns-follow-ends": Limit(
            "step 0 (query)", "Invalid", "wft-output-name"
        ),  # R17.2
        # a whole entity with more than 100 related keys is refused `limits`
        "read.relationship-columns-are-capped": Limit(
            "step 2 (query)", "Unsupported", "refused the statement (limits)"
        ),  # R17.2
        # the apply and reached steps pass; the read of the related keys is refused
        "action.applies-atomically-and-reads-back": Limit(
            "step 3 (query)", "Invalid", "wft-output-name"
        ),  # R17.2
        "action.conflict-rolls-back-the-unit": Limit(
            "step 4 (query)", "Invalid", "wft-output-name"
        ),  # R17.2
        # a keyed retry rebuilds its input from what exists now, and Truss answers a replay only for
        # byte-identical input: the original's deleted targets and unlinked edge cannot be named again
        "action.keyed-retry-of-a-delete-replays": Limit(
            "step 1 (apply)", "Conflict", "idempotency_key_reused"
        ),  # R18.3
        "action.keyed-retry-of-an-unlink-replays": Limit(
            "step 1 (apply)", "Conflict", "idempotency_key_reused"
        ),  # R18.3
        "action.keyed-retry-after-its-target-was-deleted-replays": Limit(
            "step 2 (apply)", "Conflict", "idempotency_key_reused"
        ),  # R18.3
        # Truss scopes a request to the person: the second person's create is new, and collides
        "action.same-key-from-another-person-replays": Limit(
            "step 1 (apply)", "PreconditionFailed", "fresh"
        ),  # R18.3
    }

    def __init__(self, cluster: Cluster, build: Callable[[TrussHarness], Backend] | None = None):
        self.cluster = cluster
        # the adapter under test is held to the limits; a stand-in backend fails every case
        self.limits: Mapping[str, Limit] = self.LIMITS if build is None else {}
        self._build = build or TrussHarness._adapter
        self._primes = build is None  # the adapter under test, not a stand-in
        self._world: World | None = None
        self._module: ModuleInfo | None = None
        self._backend: Backend | None = None

    @property
    def world(self) -> World:
        if self._world is None:
            raise RuntimeError("the harness has no world: install comes first")
        return self._world

    def _adapter(self) -> Backend:
        """The adapter over this world's connections: one per-person source and the installing one."""
        world = self.world
        return create_backend(  # type: ignore[return-value]
            "truss", world.connection_source, world.installing_connection
        )

    @staticmethod
    def unbuilt(_: TrussHarness) -> Backend:
        """A backend whose every operation is unbuilt, to prove the corpus fails against nothing."""
        return UnbuiltBackend()  # type: ignore[return-value]

    def backend(self) -> Backend:
        if self._backend is None:
            self._backend = self._build(self)
        return self._backend

    def install(self, module: ModuleInfo, document: bytes, registered: bool = True) -> None:
        self._module = module
        self._world = self.cluster.begin_world(module, document, registered)

    def grant(self, user: str, modules: Mapping[str, Sequence[str]], admin: bool) -> None:
        self.world.grant(user, modules, admin)
        if self._primes and any("read" in modes for modes in modules.values()):
            # `describe` takes no principal and states the types the adapter has served, and the
            # runner describes before it reads: serve a catalog once, as a host's first request would
            self.backend().catalog(self.principal(user))  # type: ignore[attr-defined]

    def principal(self, name: str) -> Principal:
        return Principal("anon", "") if name == "anon" else self.world.principal(name)

    def borrowed(self, user: str, token_owner: str) -> Principal:
        return Principal(user, self.world.tokens[token_owner])

    def foreign_token(self) -> str:
        return foreign_token()

    def seed(self, user: str, records: Sequence[Mapping[str, object]]) -> None:
        self.world.seed(user, records)

    def write(self, user: str, plan: Plan) -> str:
        receipt = cast(Any, self.backend()).apply(self.principal(user), plan, idempotency_key=None)
        assert isinstance(receipt, Receipt)
        return receipt.token

    def sync(self) -> None:
        pass  # Truss is both reader and provider

    def outage(self, reason: str | None) -> None:
        self.world.outage(reason)

    def expire(self, user: str) -> None:
        self.world.expire(user)


class UnbuiltBackend:
    """Every `Provider` operation raises, as the Truss adapter's skeleton did before it was built."""

    def __getattr__(self, name: str) -> Callable[..., Any]:
        if name.startswith("_"):
            raise AttributeError(name)

        def unbuilt(*args: Any, **kwargs: Any) -> Any:
            raise NotImplementedError(f"the Truss adapter's {name} is not built yet")

        return unbuilt
