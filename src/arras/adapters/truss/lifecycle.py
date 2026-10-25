# SPDX-License-Identifier: MIT OR Apache-2.0
"""The Truss adapter's lifecycle (CONTRACT-005, D3): install-or-verify and module-access
configuration, both on the host's installing connection and never as a person. This adapter does
not upgrade an existing installation: `migrate` verifies the selected release and reports another
release as `unsupported_version`. Upstream administrative migrations are separate and are not
invoked here.

Each runs in one read-write transaction that first takes a transaction-scoped advisory lock
(`Connections.installer_write`), so two instances migrating together run one install: the loser
waits, then its status read sees the committed install. `migrate` is install-or-verify only; module
access is `configure_access`, one locked transaction per module, because Truss refuses a whole grant
batch for any module it has not accepted and the installer cannot list the accepted ones. The decision to install comes from Truss's
status read in that transaction, never from parsing an install error. In the original Truss 0.0.45
implementation, failures inside a group operation surfaced as the opaque `invalid_transaction`;
this is historical implementation evidence, not a guarantee about other upstream releases.

The owner and registrar role names exist only in the install's result. They are in memory here until
the commit. A commit of unknown outcome is settled by a status read on a new connection: `ran=True`
with the names is returned only when the installed installation id is the one this call's install
produced; another id means another instance installed (`ran=False`, no names); absent or unreadable
is `migration_failed`, detail `outcome unknown`.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, cast

from arras import telemetry
from arras.adapters.truss.connection import Call, CommitUnknown, Connections
from arras.errors import ArrasError, Unavailable
from arras.results import MigrationResult

# One key per database (advisory locks are database-scoped): the install and the module-access
# configuration share it, so no two of them overlap.
INSTALL_LOCK = int.from_bytes(
    hashlib.sha256(b"arras.truss.lifecycle").digest()[:8], "big", signed=True
)
_ROLE_BYTES = 63
_TOLERATED_OBJECT_CLASSES = frozenset(
    {"schema", "relation", "sequence", "routine", "type", "column"}
)
_TOLERATED_PHASES = frozenset({"pre_ownership", "post_installation"})


def validate_tolerated_grantees(value: object) -> tuple[str, ...]:
    """Validate only the safe immutable carrier and context-free bounds."""
    if type(value) is not tuple:
        raise ValueError("tolerated_grantees must be a tuple of at most 32 role names")
    selected = cast(tuple[object, ...], value)
    if len(selected) > 32:
        raise ValueError("tolerated_grantees must be a tuple of at most 32 role names")
    for role in selected:
        if type(role) is not str or not role or "\x00" in role:
            raise ValueError("tolerated_grantees contains an invalid role name")
        try:
            size = len(role.encode("utf-8", errors="strict"))
        except UnicodeEncodeError as error:
            raise ValueError("tolerated_grantees contains an invalid role name") from error
        if size > _ROLE_BYTES:
            raise ValueError("tolerated_grantees role name exceeds the UTF-8 byte bound")
    return cast(tuple[str, ...], selected)


def _third_party_grant_refusal(backend: str, refusal: Any) -> Unavailable:
    try:
        role = getattr(refusal, "role_name", None)
        object_class = getattr(refusal, "object_class", None)
        phase = getattr(refusal, "phase", None)
    except Exception:
        return Unavailable(
            backend, "migration_failed", "truss third_party_grant context unavailable"
        )
    if (
        type(role) is not str
        or not role
        or "\x00" in role
        or type(object_class) is not str
        or object_class not in _TOLERATED_OBJECT_CLASSES
        or type(phase) is not str
        or phase not in _TOLERATED_PHASES
    ):
        return Unavailable(
            backend, "migration_failed", "truss third_party_grant context unavailable"
        )
    try:
        if len(role.encode("utf-8", errors="strict")) > _ROLE_BYTES:
            raise ValueError
    except (UnicodeEncodeError, ValueError):
        return Unavailable(
            backend, "migration_failed", "truss third_party_grant context unavailable"
        )
    quoted_role = json.dumps(role, ensure_ascii=True, separators=(",", ":"))
    detail = f"truss third_party_grant role={quoted_role} object_class={object_class} phase={phase}"
    return Unavailable(backend, "migration_failed", detail)


@dataclass(frozen=True)
class ModuleAccess:
    """The host's roles for one module: Truss's document id (the UMF document's own `id`) and the
    reader and writer roles, which must already exist as distinct non-login roles, and optionally the
    role that may read the module's audit pages (`changes` and `loads`): a separate grant, never implied
    by reading or writing."""

    document_id: str
    reader_role: str
    writer_role: str
    auditor_role: str | None = None

    def __post_init__(self) -> None:
        roles = (self.reader_role, self.writer_role)
        if not self.document_id or not all(roles):
            raise ValueError("a module's access names a document and two roles")
        if self.reader_role == self.writer_role:
            raise ValueError("a module's reader and writer roles must differ")
        if self.auditor_role is not None:
            if not self.auditor_role or self.auditor_role in roles:
                raise ValueError("a module's auditor role is a role of its own")
            roles = (*roles, self.auditor_role)
        if any(len(role.encode()) > _ROLE_BYTES for role in roles):
            raise ValueError(f"a role name is at most {_ROLE_BYTES} bytes")


def _error(backend: str, operation: str, failure: Any) -> ArrasError:
    """The library error for a failed lifecycle operation. The code never carries a profile meaning
    except `unsupported_profile` from the status read; no Truss or server text is repeated."""
    if getattr(failure, "catalog_code", None) == "unsupported_profile":
        return Unavailable(backend, "unsupported_version", "the installed Truss is another release")
    state = getattr(failure, "sql_state", None)
    if state == "42501":
        return Unavailable(
            backend, "access_denied", "the installing connection lacks the install privileges"
        )
    if state == "55P03":
        # migrate and configure_access meet FOR SHARE / FOR UPDATE NOWAIT during a concurrent
        # registration
        return Unavailable(backend, "migration_failed", "the catalog is busy")
    code = getattr(failure, "code", "failure")
    if code == "cancelled":
        return Unavailable(backend, "migration_failed", "timeout")
    return Unavailable(backend, "migration_failed", f"truss {code}")


class _AlreadyInstalled(Exception):
    """Truss's typed refusal to install over an installation of the pinned release."""


def _install_refused(backend: str, code: str) -> Exception:
    """The error for a typed `InstallRefused` (nothing was installed, nothing is retried): `busy`
    is another installation or registration in progress, `incompatible` and `unsupported_postgres`
    a release or server Truss does not select, `unauthorized` the installer's missing privileges."""
    if code == "already_installed":
        return _AlreadyInstalled()
    if code == "busy":
        return Unavailable(backend, "busy", "another installation holds the database")
    if code in ("incompatible", "unsupported_postgres"):
        return Unavailable(backend, "unsupported_version", f"truss refused to install: {code}")
    if code in ("unauthorized", "read_only"):
        return Unavailable(
            backend, "access_denied", "the installing connection lacks the install privileges"
        )
    return Unavailable(backend, "migration_failed", f"truss refused to install: {code}")


class Lifecycle:
    """`migrate` and `configure_access` over one `Connections`."""

    def __init__(
        self,
        name: str,
        connections: Connections | None,
        access: Mapping[str, ModuleAccess] | None = None,
        *,
        tolerated_grantees: tuple[str, ...] = (),
    ) -> None:
        self.name = name
        self._connections = connections
        self._tolerated_grantees = validate_tolerated_grantees(tolerated_grantees)
        self._access = dict(access or {})
        self._lock = threading.Lock()
        self._failure: str | None = None

    @property
    def failure(self) -> str | None:
        """The detail of the last failed `migrate`, until a `migrate` succeeds or Truss is seen
        installed: `status()` reports it as `migration_failed` (the failed install rolled back, so
        the store itself says only that Truss is absent)."""
        with self._lock:
            return self._failure

    def settle(self, failure: str | None) -> None:
        with self._lock:
            self._failure = failure

    def _open(self, operation: str, timeout: float | None) -> AbstractContextManager[Call]:
        if self._connections is None:
            raise Unavailable(self.name, "not_configured", "no connection source")
        call = self._connections.installer_write(operation, lock=INSTALL_LOCK, timeout=timeout)
        if call is None:
            raise Unavailable(self.name, "not_configured", "no installing connection")
        return call

    def migrate(self, *, timeout: float | None = None) -> MigrationResult:
        with telemetry.operation("arras.backend.migrate", backend=self.name):
            return self._migrating(timeout)

    def _migrating(self, timeout: float | None) -> MigrationResult:
        try:
            result = self._migrate(timeout)
        except Unavailable as exc:
            failed = exc.reason == "migration_failed"
            self.settle((exc.detail or "failed") if failed else None)
            raise
        self.settle(None)
        return result

    def _migrate(self, timeout: float | None) -> MigrationResult:
        held: tuple[str, MigrationResult] | None = None  # our install's id and its result
        try:
            with self._open("migrate", timeout) as call:
                status = call.unwrap(call.assembly.status_in_transaction(call.tx), _error)
                if status.installed:
                    result = MigrationResult(False, status.release_id)
                else:
                    try:
                        done = self._install(call)
                    except _AlreadyInstalled:
                        # another installer finished first: it is verified, not installed here
                        again = call.unwrap(call.assembly.status_in_transaction(call.tx), _error)
                        if not again.installed:
                            raise Unavailable(
                                self.name, "migration_failed", "truss already_installed"
                            ) from None
                        return MigrationResult(False, again.release_id)
                    result = MigrationResult(
                        True, done.release_id, done.owner_role, done.registrar_role
                    )
                    held = (done.installation_id, result)
        except ImportError:
            raise Unavailable(
                self.name, "not_configured", "the truss extra is not installed"
            ) from None
        except CommitUnknown:
            seen = self._installed()
            if seen is None:
                raise Unavailable(self.name, "migration_failed", "outcome unknown") from None
            installation_id, release_id = seen
            if held is not None and held[0] == installation_id:
                return held[1]
            return MigrationResult(False, release_id)
        return result

    def _install(self, call: Call) -> Any:
        try:
            out = call.unwrap(
                call.assembly.install_in_transaction(
                    call.tx, tolerated_grantees=self._tolerated_grantees
                ),
                _error,
            )
        except Unavailable as exc:
            if exc.reason == "migration_failed" and call.facts.get("creates_roles") is False:
                # Truss's refusal for a role without CREATEROLE is its one opaque code
                raise Unavailable(
                    self.name, "access_denied", "the installing role cannot create roles"
                ) from None
            raise
        if type(out).__name__ == "InstallRefused":
            if getattr(out, "code", None) == "third_party_grant":
                raise _third_party_grant_refusal(self.name, out)
            try:
                raise _install_refused(self.name, out.code)
            except Unavailable as exc:
                if exc.reason == "migration_failed" and call.facts.get("creates_roles") is False:
                    raise Unavailable(
                        self.name,
                        "access_denied",
                        "the installing role cannot create roles",
                    ) from None
                raise
        return out

    def _installed(self) -> tuple[str | None, str] | None:
        """After a COMMIT of unknown outcome: the installed Truss's installation id and release id
        from a status read on a new connection (the old one was closed), or None when Truss is
        absent or the read fails."""
        assert self._connections is not None
        call = self._connections.installer("migrate")
        if call is None:
            return None
        try:
            with call as open_call:
                status = open_call.unwrap(
                    open_call.assembly.status_in_transaction(open_call.tx), _error
                )
        except ArrasError:
            return None
        if not status.installed:
            return None
        return status.installation_id, status.release_id

    def install_roles(self) -> tuple[str, str]:
        """The installation's owner and registrar role names, read by the administrator's connection
        (Truss's administrator-only `admin_install_recovery`): the names the install result gave once,
        for a host that lost them (a restart, a deploy job that installed and exited). No person's call
        gives them."""
        if self._connections is None:
            raise Unavailable(self.name, "not_configured", "no connection source")
        call = self._connections.installer("install_roles")
        if call is None:
            raise Unavailable(self.name, "not_configured", "no installing connection")
        try:
            with call as open_call:
                out = open_call.unwrap(
                    open_call.assembly.admin_install_recovery_in_transaction(open_call.tx), _error
                )
        except ImportError:
            raise Unavailable(
                self.name, "not_configured", "the truss extra is not installed"
            ) from None
        if type(out).__name__ == "AdminInstallRecovery":
            return out.owner_role, out.registrar_role
        reason = {
            "profile": "unsupported_version",
            "installation": "not_configured",
            "observation": "busy",
            "unauthorized": "access_denied",
        }.get(getattr(out, "reason", ""), "unreachable")
        raise Unavailable(self.name, reason, "the install roles were not given")  # type: ignore[arg-type]

    def configure_access(
        self, modules: tuple[str, ...] | None = None, *, timeout: float | None = None
    ) -> None:
        """Hands the host's reader and writer roles for `modules` (all it supplied, by default) to
        Truss, one module at a time, each in its own locked transaction, in the order given. It
        stops at the first refusal with `migration_failed` (or the mapped reason) naming that
        module; modules before it stay configured. A module must be registered first: Truss
        refuses the grant for one it has not accepted. An unknown module name is a `ValueError`."""
        names = tuple(self._access) if modules is None else tuple(modules)
        unknown = [n for n in names if n not in self._access]
        if unknown:
            raise ValueError(f"no module access was supplied for {unknown[0]!r}")
        with telemetry.operation("arras.backend.configure_access", backend=self.name):
            for module in names:
                self._configure_one(module, timeout)

    def _configure_one(self, module: str, timeout: float | None) -> None:
        access = self._access[module]
        try:
            from truss import ModuleAccessGrant, ModuleAuditGrant

            grant = ModuleAccessGrant(
                access.document_id, module, access.reader_role, access.writer_role
            )
            with self._open("configure_access", timeout) as call:
                try:
                    out = call.unwrap(
                        call.assembly.configure_module_access_in_transaction(call.tx, (grant,)),
                        _error,
                    )
                    if type(out).__name__ == "ModuleAccessBatchRefused":
                        # indexed codes only (duplicate_selection, unknown_module, unknown_role,
                        # unsafe_role); one grant is sent, so the index is always 0
                        codes = ", ".join(e.code for e in out.errors)
                        raise Unavailable(self.name, "migration_failed", codes)
                    if access.auditor_role is not None:
                        audit = call.unwrap(
                            call.assembly.grant_module_audit_access_in_transaction(
                                call.tx,
                                ModuleAuditGrant(
                                    document_id=access.document_id,
                                    module_id=module,
                                    auditor_role=access.auditor_role,
                                ),
                            ),
                            _error,
                        )
                        if type(audit).__name__ != "AuditAccessUpdated":
                            raise Unavailable(
                                self.name,
                                "migration_failed",
                                f"audit access refused ({getattr(audit, 'reason', 'unknown')})",
                            )
                except Unavailable as exc:
                    raise Unavailable(
                        self.name,
                        exc.reason,
                        f"module access for {module!r} was refused: {exc.detail}",
                    ) from None
        except ImportError:
            raise Unavailable(
                self.name, "not_configured", "the truss extra is not installed"
            ) from None
        except CommitUnknown:
            raise Unavailable(
                self.name, "migration_failed", f"module access for {module!r}: outcome unknown"
            ) from None
