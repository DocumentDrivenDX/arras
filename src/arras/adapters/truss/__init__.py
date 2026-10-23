# SPDX-License-Identifier: MIT OR Apache-2.0
"""The Truss adapter (ADR-006, CONTRACT-004): Arras's backend over Truss on PostgreSQL.

`TrussBackend` has the whole `Provider` surface. The registry operations, `query`, `apply` (with its dry
run), `apply_batch`, `import_records` and `reached` are built; `changes` and `loads` raise `Unsupported`
(Truss has no journal read: `describe().audit` is False). The base install needs none of Truss or psycopg: nothing here
imports them at run time. They are the optional extra `truss` (`pip install arras[truss]`), and
`require_toolkit` is how the adapter says so when they are missing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from importlib import metadata

from arras import callscope, telemetry
from arras.actions import Plan
from arras.adapters.truss.apply import Applier
from arras.adapters.truss.audit import Auditor
from arras.adapters.truss.cache import CatalogCache
from arras.adapters.truss.connection import (
    OPERATION_TIMEOUT_MS,
    STATEMENT_TIMEOUT_MS,
    Call,
    CommitUnknown,
    Connections,
    ConnectionSource,
    InstallingSource,
    classify_connect_error,
)
from arras.adapters.truss.describe import NOT_INSTALLED
from arras.adapters.truss.describe import describe as _describe
from arras.adapters.truss.describe import status as _status
from arras.adapters.truss.export import Exporter
from arras.adapters.truss.lifecycle import Lifecycle, ModuleAccess, validate_tolerated_grantees
from arras.adapters.truss.load import Importer
from arras.adapters.truss.query import Reader
from arras.adapters.truss.reach import Visibility
from arras.adapters.truss.registry import Registry
from arras.adapters.truss.wire import Wire
from arras.errors import Unavailable, Unsupported
from arras.model import ModuleInfo
from arras.names import BACKEND_NAME
from arras.results import (
    Answer,
    BackendInfo,
    BackendStatus,
    BatchReceipt,
    ChangesPage,
    ImportResult,
    LoadsPage,
    MigrationResult,
    Receipt,
    RecordsPage,
    RegisteredDocument,
    RegistrationCheck,
    RegistryResult,
    Validation,
)
from arras.searchplan import TextMatch
from arras.types import Principal, Revision, Statement

# The pinned release (the optional extra `truss` in pyproject.toml names the same).
TOOLKIT_DISTRIBUTION = "truss-toolkit"
TOOLKIT_VERSION = "0.0.49"
EXTRA = "truss"

__all__ = [
    "EXTRA",
    "TOOLKIT_DISTRIBUTION",
    "TOOLKIT_VERSION",
    "Call",
    "CommitUnknown",
    "ConnectionSource",
    "Connections",
    "InstallingSource",
    "ModuleAccess",
    "TrussBackend",
    "classify_connect_error",
    "create_backend",
    "require_toolkit",
]


def require_toolkit() -> str:
    """The installed toolkit version, when it is the pinned one; `ImportError` naming the extra
    when the toolkit is absent or another release is installed."""
    try:
        found = metadata.version(TOOLKIT_DISTRIBUTION)
    except metadata.PackageNotFoundError:
        raise ImportError(
            f"{TOOLKIT_DISTRIBUTION} {TOOLKIT_VERSION} is not installed: install arras[{EXTRA}]"
        ) from None
    if found != TOOLKIT_VERSION:
        raise ImportError(
            f"{TOOLKIT_DISTRIBUTION} {found} is installed but {TOOLKIT_VERSION} is pinned: "
            f"install arras[{EXTRA}]"
        )
    return found


class TrussBackend:
    """A `Provider` over Truss. `connections` is the per-person call layer (and the installing
    connection for `status`). `changes` and `loads` read Truss's audit pages as the person, who needs
    Truss's own audit grant for the module (`ModuleAccess.auditor_role`)."""

    def __init__(
        self,
        name: str,
        connections: Connections | None = None,
        wire: Wire | None = None,
        module_access: Mapping[str, ModuleAccess] | None = None,
        *,
        tolerated_grantees: tuple[str, ...] = (),
    ) -> None:
        selected_grantees = validate_tolerated_grantees(tolerated_grantees)
        self.name = name
        self.connections = connections
        self._lifecycle = Lifecycle(
            name,
            connections,
            module_access,
            tolerated_grantees=selected_grantees,
        )
        self.cache = CatalogCache()
        self._registry = Registry(name, connections, self.cache) if connections else None
        self._reader = (
            Reader(name, connections, self._registry) if connections and self._registry else None
        )
        self._exporter = (
            Exporter(name, connections, self._registry, self._reader)
            if connections and self._registry and self._reader
            else None
        )
        self._applier = (
            Applier(name, connections, self._registry, wire)
            if connections and self._registry
            else None
        )

        self._auditor = (
            Auditor(
                name,
                connections,
                self._registry,
                self.cache,
                {m: a.document_id for m, a in (module_access or {}).items()},
                wire,
            )
            if connections and self._registry
            else None
        )
        self._visibility = Visibility(name, connections) if connections else None
        self._importer = (
            Importer(name, connections, self._registry, wire)
            if connections and self._registry
            else None
        )

    def _registry_or_unavailable(self) -> Registry:
        if self._registry is None:
            raise Unavailable(self.name, "not_configured", "no connection source")
        return self._registry

    def describe(self) -> BackendInfo:
        # inside an operation that has read the person's catalog, the types are that catalog's, so the
        # operation's answer is of one revision (and `describe` makes no read of its own)
        held = self._registry.scoped_modules() if self._registry is not None else None
        if held is not None:
            callscope.declare_consistent(self.name)
            return _describe(self.name, held.values())
        return _describe(self.name, self.cache.seen())

    def catalog(self, principal: Principal) -> Mapping[str, ModuleInfo]:
        return self._registry_or_unavailable().catalog(principal)

    def status(self) -> BackendStatus:
        out = _status(self.name, self.connections)
        failure = self._lifecycle.failure
        if out.available:
            self._lifecycle.settle(None)  # Truss is there: a failed install is over
        elif failure is not None and out.reason == "not_configured" and self.connections:
            # a failed install rolled back, so the store says only that Truss is absent
            if out.detail == NOT_INSTALLED:
                return BackendStatus(False, "migration_failed", failure)
        return out

    def migrate(self, *, timeout: float | None = None) -> MigrationResult:
        """Install-or-verify on the installing connection (CONTRACT-005): installs an absent Truss,
        leaves a present one of the pinned release alone (`ran` false) and refuses another release
        (`unsupported_version`). Concurrent calls run one install. It does not grant module access:
        that is `configure_access`, after a module is registered."""
        return self._lifecycle.migrate(timeout=timeout)

    def install_roles(self) -> tuple[str, str]:
        """The installation's (owner role, registrar role) names, for a host that no longer holds
        what `migrate` returned when it installed: read on the installing connection by Truss's
        administrator-only recovery. `Unavailable` for anything else."""
        return self._lifecycle.install_roles()

    def configure_access(
        self, modules: Sequence[str] | None = None, *, timeout: float | None = None
    ) -> None:
        """Hands the host's reader and writer roles for `modules` (all supplied, by default) to
        Truss, one module and one locked transaction at a time, in the order given, stopping at the
        first refusal (which names the module; earlier modules stay configured). Call it after a
        registration adds a module, and again only when a module is new or its roles change: the
        grants persist in Truss. Truss refuses a module it has not accepted."""
        self._lifecycle.configure_access(
            None if modules is None else tuple(modules), timeout=timeout
        )

    def query(
        self,
        principal: Principal,
        module: str,
        statement: Statement,
        *,
        limit: int,
        text: TextMatch | None = None,
    ) -> Answer:
        telemetry.annotate(backend=self.name)
        if self._reader is None:
            raise Unavailable(self.name, "not_configured", "no connection source")
        return self._reader.query(principal, module, statement, limit=limit, text=text)

    def shown(self, principal: Principal) -> Mapping[str, ModuleInfo] | None:
        """The modules this person was last shown by `catalog`, or None. It answers no access
        question: it is what `query_current` presents to Truss, which says whether it is current."""
        held = self.cache.shown(principal.user)
        return None if held is None else held[1]

    def query_current(
        self,
        principal: Principal,
        module: str,
        statement: Statement,
        *,
        limit: int,
        text: TextMatch | None = None,
    ) -> Answer | None:
        """`query` and the person's catalog in one operation of one transaction, or None when the
        catalog moved or nothing was shown (then `catalog` and `query` are asked in turn)."""
        telemetry.annotate(backend=self.name)
        if self._reader is None:
            raise Unavailable(self.name, "not_configured", "no connection source")
        return self._reader.query_current(principal, module, statement, limit=limit, text=text)

    def reached(self, principal: Principal, token: str) -> bool:
        telemetry.annotate(backend=self.name)
        if self._visibility is None:
            raise Unavailable(self.name, "not_configured", "no connection source")
        return self._visibility.reached(principal, token)

    def attach(self, principal: Principal, module: ModuleInfo) -> RegistryResult:
        raise Unsupported("attach", ["a provider takes register"])

    def apply(
        self,
        principal: Principal,
        plan: Plan,
        *,
        idempotency_key: str | None,
        dry_run: bool = False,
    ) -> Receipt | Validation:
        telemetry.annotate(backend=self.name)
        if self._applier is None:
            raise Unavailable(self.name, "not_configured", "no connection source")
        return self._applier.apply(
            principal, plan, idempotency_key=idempotency_key, dry_run=dry_run
        )

    def apply_batch(
        self,
        principal: Principal,
        plans: Sequence[Plan],
        *,
        atomic: bool,
        idempotency_key: str | None,
        stop_on_error: bool = False,
    ) -> BatchReceipt:
        telemetry.annotate(backend=self.name)
        if self._applier is None:
            raise Unavailable(self.name, "not_configured", "no connection source")
        return self._applier.apply_batch(
            principal,
            plans,
            atomic=atomic,
            idempotency_key=idempotency_key,
            stop_on_error=stop_on_error,
        )

    def import_records(
        self,
        principal: Principal,
        module: str,
        records: Sequence[Mapping[str, object]],
        *,
        load_id: str,
        initiated_by: str,
    ) -> ImportResult:
        telemetry.annotate(backend=self.name)
        if self._importer is None:
            raise Unavailable(self.name, "not_configured", "no connection source")
        return self._importer.import_records(
            principal, module, records, load_id=load_id, initiated_by=initiated_by
        )

    def export_records(
        self, principal: Principal, module: str, *, limit: int, after: str | None
    ) -> RecordsPage:
        telemetry.annotate(backend=self.name)
        if self._exporter is None:
            raise Unavailable(self.name, "not_configured", "no connection source")
        return self._exporter.export_records(principal, module, limit=limit, after=after)

    def changes(
        self,
        principal: Principal,
        *,
        module: str | None,
        type: str | None,
        key: str | None,
        by: str | None,
        action: str | None,
        group: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        after: str | None,
    ) -> ChangesPage:
        telemetry.annotate(backend=self.name)
        if self._auditor is None:
            raise Unavailable(self.name, "not_configured", "no connection source")
        return self._auditor.changes(
            principal,
            module=module,
            type=type,
            key=key,
            by=by,
            action=action,
            group=group,
            since=since,
            until=until,
            limit=limit,
            after=after,
        )

    def loads(
        self, principal: Principal, module: str, *, limit: int, after: str | None
    ) -> LoadsPage:
        telemetry.annotate(backend=self.name)
        if self._auditor is None:
            raise Unavailable(self.name, "not_configured", "no connection source")
        return self._auditor.loads(principal, module, limit=limit, after=after)

    def register(
        self,
        principal: Principal,
        document: bytes,
        module: ModuleInfo,
        *,
        unknown_endpoint: str,
        expected_revision: Revision | None = None,
    ) -> RegistryResult:
        return self._registry_or_unavailable().register(
            principal,
            document,
            module,
            unknown_endpoint=unknown_endpoint,
            expected_revision=expected_revision,
        )

    def validate_register(
        self,
        principal: Principal,
        document: bytes,
        module: ModuleInfo,
        *,
        unknown_endpoint: str,
    ) -> RegistrationCheck:
        return self._registry_or_unavailable().validate_register(
            principal, document, module, unknown_endpoint=unknown_endpoint
        )

    def document(self, principal: Principal, module: str) -> RegisteredDocument:
        return self._registry_or_unavailable().document(principal, module)


def create_backend(
    name: str,
    source: ConnectionSource | None,
    installing: InstallingSource | None = None,
    *,
    module_access: Mapping[str, ModuleAccess] | None = None,
    tolerated_grantees: tuple[str, ...] = (),
    statement_timeout_ms: int = STATEMENT_TIMEOUT_MS,
    operation_timeout_ms: int = OPERATION_TIMEOUT_MS,
) -> TrussBackend:
    """The Truss adapter for a host to register under `name` (CONTRACT-005; D3, D6).

    `source` is the per-person `ConnectionSource`; `installing` is the trusted connection that only
    `migrate`, module access and the install-state read behind `status()` use (without it
    the backend is `not_configured`: it serves nothing it cannot verify). `module_access` maps a
    module's name to its `ModuleAccess`. A `source` of None gives a backend that is `not_configured`.
    It never connects, imports Truss or psycopg, or reads the environment; a bad `name` is a
    `ValueError`, a programming error rather than an availability failure.
    """
    selected_grantees = validate_tolerated_grantees(tolerated_grantees)
    if not isinstance(name, str) or not BACKEND_NAME.fullmatch(name):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError(f"a backend name matches {BACKEND_NAME.pattern}")
    if source is None:
        return TrussBackend(
            name,
            None,
            None,
            module_access,
            tolerated_grantees=selected_grantees,
        )
    connections = Connections(
        name,
        source,
        statement_timeout_ms=statement_timeout_ms,
        operation_timeout_ms=operation_timeout_ms,
        installing=installing,
    )
    return TrussBackend(
        name,
        connections,
        None,
        module_access,
        tolerated_grantees=selected_grantees,
    )
