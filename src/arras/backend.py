# SPDX-License-Identifier: MIT OR Apache-2.0
"""What a backend implements so Arras can serve the interface from it (CONTRACT-004).

Every call is made for the caller's `Principal`, over that person's own token; the backend's own
controls decide. A backend answers with an empty result, `Refused` or `Unavailable`, and never
turns an outage into either of the others.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from arras.actions import Plan
from arras.model import ModuleInfo
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


class Backend(Protocol):
    """The operations every backend has, and a reader's: it serves reads. A backend that also applies
    actions is a `Provider` and says so in `describe().roles`."""

    def describe(self) -> BackendInfo: ...

    def catalog(self, principal: Principal) -> Mapping[str, ModuleInfo]:
        """The modules this backend holds and the principal may read, with their revision."""
        ...

    def status(self) -> BackendStatus: ...

    def query(
        self,
        principal: Principal,
        module: str,
        statement: Statement,
        *,
        limit: int,
        text: TextMatch | None = None,
    ) -> Answer:
        """Compile `statement` with Weft against the named module's types and run it as the
        principal, read-only, returning at most `limit` rows. `Invalid` (`unknown_type`) for a
        module the principal may not read or this backend does not hold, before anything that
        depends on a type; `Unsupported` for what Weft or the declared profiles refuse and for a
        statement that reads outside `module`. `text`, when given, narrows the statement's rows to
        those that match it (CONTRACT-010); a type the backend does not declare `substring` search
        for, or a property it does not list as searchable, is `Unsupported`. A token's wait (`at_least`) is Arras's: it asks
        `reached(principal, token)` and chooses the backend from the module's placement."""
        ...

    def reached(self, principal: Principal, token: str) -> bool:
        """Whether this backend's data, as `principal` reads it, includes the position a
        receipt's token names. `Invalid` for a token that is malformed or was never issued,
        `Unavailable` when the backend cannot determine it, `Refused` for a call without a
        token or for a person the backend refuses; `False` is the only answer that invites a
        wait."""
        ...

    def attach(self, principal: Principal, module: ModuleInfo) -> RegistryResult:
        """Record a module's types for discovery, without changing the record store."""
        ...


class Provider(Backend, Protocol):
    """A backend that accepts changes: it applies actions, imports records, takes catalogs."""

    def apply(
        self,
        principal: Principal,
        plan: Plan,
        *,
        idempotency_key: str | None,
        dry_run: bool = False,
    ) -> Receipt | Validation: ...

    def apply_batch(
        self,
        principal: Principal,
        plans: Sequence[Plan],
        *,
        atomic: bool,
        idempotency_key: str | None,
        stop_on_error: bool = False,
    ) -> BatchReceipt: ...

    def import_records(
        self,
        principal: Principal,
        module: str,
        records: Sequence[Mapping[str, object]],
        *,
        load_id: str,
        initiated_by: str,
    ) -> ImportResult: ...

    def export_records(
        self, principal: Principal, module: str, *, limit: int, after: str | None
    ) -> RecordsPage:
        """The module's graph as records of the shapes `import_records` takes, a page at a time, in
        an order that is the same each time: entities, then relationship instances. Read as the
        person under the module's `read` grant (CONTRACT-003, Export)."""
        ...

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
        """The committed groups of the journal that match, newest first, read as the person
        under the backend's own journal grant (CONTRACT-004)."""
        ...

    def loads(
        self, principal: Principal, module: str, *, limit: int, after: str | None
    ) -> LoadsPage: ...

    def register(
        self,
        principal: Principal,
        document: bytes,
        module: ModuleInfo,
        *,
        unknown_endpoint: str,
        expected_revision: Revision | None = None,
    ) -> RegistryResult:
        """Accept the document as a revision under the person's `schema` grant; a stated
        `expected_revision` is checked in the same serialized step (CONTRACT-004)."""
        ...

    def validate_register(
        self,
        principal: Principal,
        document: bytes,
        module: ModuleInfo,
        *,
        unknown_endpoint: str,
    ) -> RegistrationCheck:
        """The dry run of `register`: the same grant, checked first, and the same rules,
        reported and not applied (CONTRACT-004)."""
        ...

    def document(self, principal: Principal, module: str) -> RegisteredDocument:
        """The module's UMF document exactly as it was registered, at the revision the authority
        holds, read as the person under the module's `read` grant (CONTRACT-004). A module the
        authority does not hold is `Invalid`; a person without the grant is `Refused`."""
        ...


@runtime_checkable
class Migrates(Protocol):
    """What a backend with a store to install adds (the Truss adapter): `Arras.migrate` calls it
    on each backend that has it. Install-or-verify on the backend's installing connection, with no
    person; `timeout` (seconds, None waits) bounds the wait for the install lock. A failure raises
    `Unavailable`. It is not part of `Backend`: the memory backends and the replica have no store
    to install."""

    def migrate(self, *, timeout: float | None = None) -> MigrationResult: ...
