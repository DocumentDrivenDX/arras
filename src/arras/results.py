# SPDX-License-Identifier: MIT OR Apache-2.0
"""What operations return: receipts, validations, import and registry results."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from arras.actions import Effect, Ref
from arras.errors import ArrasError, Failure, Violation
from arras.model import Capabilities, ModuleInfo
from arras.types import Column, Freshness, Position, Revision

Reason = Literal[
    "not_configured", "unreachable", "access_denied", "migration_failed", "unsupported_version"
]


@dataclass(frozen=True)
class MigrationResult:
    """What `Arras.migrate` reports (CONTRACT-005). `ran` is true only when this call installed
    the store; `revision` is the store's release id ("none" when no backend migrates). Truss reports
    the owner and registrar role names once, from the install, so they are set only when `ran` and
    the host persists them."""

    ran: bool
    revision: str
    owner_role: str | None = None
    registrar_role: str | None = None


@dataclass(frozen=True)
class RefVersion:
    type: str
    key: str
    version: int


@dataclass(frozen=True)
class Receipt:
    action: str
    refs: tuple[RefVersion, ...]
    created: int
    updated: int
    deleted: int
    linked: int
    unlinked: int
    token: str
    replayed: bool = False
    group: str = ""  # the atomic group the change committed in (opaque)


@dataclass(frozen=True)
class ItemResult:
    index: int
    receipt: Receipt | None = None
    refusal: ArrasError | None = None


@dataclass(frozen=True)
class BatchReceipt:
    action: str
    atomic: bool
    items: tuple[ItemResult, ...]
    succeeded: int
    failed: int
    token: str | None


@dataclass(frozen=True)
class Validation:
    ok: bool
    violations: tuple[Violation, ...]
    failures: tuple[Failure, ...]
    effects: tuple[Effect, ...]
    replay: Receipt | None
    freshness: Freshness | None


@dataclass(frozen=True)
class Rejection:
    kind: str
    identity: str
    reason: str


@dataclass(frozen=True)
class ImportResult:
    created: int
    skipped: int
    rejected: tuple[Rejection, ...]


@dataclass(frozen=True)
class RegistryResult:
    module: str
    revision: Revision
    changed: bool
    report: tuple[str, ...] = ()


@dataclass(frozen=True)
class RegistrationCheck:
    """What a record store says of registering a document, applying nothing (CONTRACT-004,
    `validate_register`): the module's current revision (none if it holds none), whether the
    derived rows would change, every reason it would refuse, and the module as held."""

    revision: Revision | None
    changed: bool
    violations: tuple[Violation, ...] = ()
    report: tuple[str, ...] = ()
    current: ModuleInfo | None = None


@dataclass(frozen=True)
class SchemaChange:
    """One element a registration would add, change or retire, named module-qualified."""

    kind: Literal["added", "changed", "retired"]
    element: Literal["type", "property", "relationship", "action"]
    name: str
    detail: str = ""


@dataclass(frozen=True)
class SchemaPlan:
    """The answer to validating a registration (CONTRACT-002): what it would change and what would
    refuse it. Nothing is applied."""

    module: str
    ok: bool
    violations: tuple[Violation, ...]
    changed: bool
    revision: Revision | None
    changes: tuple[SchemaChange, ...] = ()
    report: tuple[str, ...] = ()


DocumentFormat = Literal["json", "yaml"]


@dataclass(frozen=True)
class RegisteredDocument:
    """A module's UMF document as the authority holds it (CONTRACT-001, Registry reads): `text` is
    the document exactly as it was registered at `revision`, never a re-serialization."""

    module: str
    revision: Revision
    text: str
    format: DocumentFormat


def document_format(raw: bytes) -> DocumentFormat:
    """JSON when the first significant character opens an object or array, else YAML."""
    head = raw.lstrip(b"\xef\xbb\xbf \t\r\n")[:1]
    return "json" if head in (b"{", b"[") else "yaml"


def document_text(raw: bytes) -> str:
    """The registered bytes as text, losslessly: UTF-8 (a byte-order mark is kept as U+FEFF), or
    the UTF-16/32 encoding JSON allows when the bytes are not UTF-8."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(json.detect_encoding(raw))


Role = Literal["reader", "provider"]


@dataclass(frozen=True)
class WeftSupport:
    """The Weft SQL version and the named read profiles a backend has qualified (CONTRACT-004).
    Descriptive for clients: Arras routes by the module's placement and what `query` accepts,
    never by these names."""

    version: str
    profiles: tuple[str, ...] = ()


@dataclass(frozen=True)
class BackendInfo:
    name: str
    roles: tuple[Role, ...]  # what it does: "reader" serves reads, "provider" applies actions
    capabilities: dict[str, Capabilities] = field(default_factory=dict[str, Capabilities])
    weft: WeftSupport | None = None  # a backend that hosts no Weft declares none
    audit: bool = (
        True  # False: it keeps no group-scoped journal, so `changes` and `loads` are Unsupported
    )

    @property
    def reads(self) -> bool:
        return "reader" in self.roles

    @property
    def provides(self) -> bool:
        return "provider" in self.roles


@dataclass(frozen=True)
class BackendStatus:
    available: bool
    reason: Reason | None = None
    detail: str = ""
    position: Position | None = None
    lag: float | None = None  # seconds behind the authority, for a replica


@dataclass(frozen=True)
class Answer:
    """What an adapter returns for `query`; Arras adds the consistency and the revision."""

    columns: tuple[Column, ...]
    rows: tuple[dict[str, Any], ...]
    truncated: bool
    as_of: Position


__all__ = ["Ref"]


@dataclass(frozen=True)
class Change:
    """One atomic group the authority committed (CONTRACT-001, Audit reads). It never holds the
    action's input values."""

    group: str
    at: datetime
    by: str
    action: str
    module: str
    ops: tuple[Mapping[str, Any], ...]
    backend: str


@dataclass(frozen=True)
class Load:
    """One run of `import_records`, kept by the provider."""

    load_id: str
    initiated_by: str
    at: datetime
    module: str
    created: int
    skipped: int
    rejected: int
    # a backend whose journal can show a load only in part (some chunks not yet visible) says so: the
    # counts are then of what it showed and are never a statement about the whole load
    partial: bool = False


@dataclass(frozen=True)
class ChangesPage:
    items: tuple[Change, ...]
    next_cursor: str | None
    truncated: bool
    freshness: Freshness


@dataclass(frozen=True)
class RecordsPage:
    """A page of an export (CONTRACT-003, Export): entity records, then relationship records, in the
    shapes `import_records` takes, in a stable order. `omitted` names the types the viewer could not
    be given; a page with any is not the whole graph."""

    items: tuple[Mapping[str, Any], ...]
    next_cursor: str | None
    omitted: tuple[str, ...]
    freshness: Freshness


@dataclass(frozen=True)
class LoadsPage:
    items: tuple[Load, ...]
    next_cursor: str | None
    truncated: bool
    freshness: Freshness
