# SPDX-License-Identifier: MIT OR Apache-2.0
"""`changes` and `loads` of the Truss adapter (CONTRACT-001, Audit reads; CONTRACT-004): the metadata
Truss keeps of what its writers committed, read as the person.

What Truss gives, and what this module makes of it (plan B8):

- Access is Truss's own audit grant (`ModuleAuditGrant`, configured by an administrator), separate from
  reader and writer membership: a person with no grant for the module, or none across every owner a
  group touched, is `Refused`. The pages are read in a read-only call as the person, so Truss answers
  access on every call and nothing here caches it.
- A mutation group is a page of its own: Truss lists whole groups, newest *observed* first, at a fixed
  committed frontier, and its `observed_at` is when Truss saw the group, never a commit time or order.
  `Change.at` is that observation and `Change.group` is the source epoch and writer transaction id,
  which is the id a `Receipt` of the same group carries. A page of `limit` groups is read with one more,
  to say whether there is a next page, and the cursor is Truss's own typed cursor (it names the frontier
  and the filters) wrapped with a digest of the filters it was made for.
- Truss states no key, property or version: an op says what changed and of which type, with `key` and
  `version` absent (`None`) and the native entity id as `id`. The type is named from the module the
  person reads, and is the native type id (`#2`) for a person who reads none.
- Imports are groups too (their origin names `import_records`); a change is a group an action made, so
  a group whose asserted action is not a module action is left out, and `loads` lists the imports.
- `loads` is one Truss invocation summary per import call. Calls of one `import_records` share its
  load id, so consecutive summaries of one load id and person are one `Load` with their counts added.
  A summary Truss calls partial (some chunks are not yet visible) makes the load `partial`: its counts
  are of the chunks seen and are never a statement about the whole load. Truss 0.0.45's module-scoped
  discovery does not list an invocation that imported only relationships (measured), nor a literal
  empty load (it has no module scope and is given only to the registrar's disclosure path), so a
  load's counts are of its listed invocations.
- `by` is the person's role name as Truss recorded it; it is filtered here, with `group`, by reading on.
  `key` is refused: Truss's key filter needs the key's definition pin, which its public reads do not
  give this adapter.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from arras.adapters.truss.cache import CatalogCache
from arras.adapters.truss.connection import Call, Connections
from arras.adapters.truss.registry import Registry, kind_of, mapped
from arras.adapters.truss.wire import Wire
from arras.errors import ArrasError, Invalid, Refused, Unavailable, Unsupported, Violation
from arras.inputs import parse_timestamp
from arras.results import Change, ChangesPage, Load, LoadsPage
from arras.types import Freshness, Position, Principal

PAGE_EVENTS = 1024  # the most events one group may have for Truss to list it (its maximum)
SCAN = 500  # groups or invocations read on for one page when a filter is applied here
_GROUP = re.compile(r"[0-9a-fA-F-]{36}:[0-9]+")
_ACTION = re.compile(r"[^.\s]+\.[^.\s]+")
_CREATES = ("create", "create_object", "create_edge")
_DELETES = ("delete", "delete_object", "delete_edge")


@dataclass
class _Walk:
    """What one walk of Truss's pages found: the items, the cursor after the last of them and whether
    there is more (`more`), or that the scan bound ended it (`cut`)."""

    items: list[Any]
    after: Any = None
    more: bool = False
    cut: bool = False
    frontier: str = "none"


def _signature(*parts: object) -> str:
    text = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _encode(kind: str, signature: str, module: str, cursor: Any) -> str:
    body = {"k": kind, "s": signature, "m": module, "c": asdict(cursor)}
    raw = json.dumps(body, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode(
    text: str, kind: str, signature: str | None, build: Callable[[dict[str, Any]], Any]
) -> tuple[str, Any]:
    """The module and Truss cursor a page's `after` names; `Invalid(cursor)` for anything this
    adapter did not issue for these filters."""
    bad = Invalid([Violation("after", "cursor", "not a cursor of this statement")])
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        body = json.loads(raw)
        if body["k"] != kind or (signature is not None and body["s"] != signature):
            raise bad
        fields = {k: v for k, v in body["c"].items() if k != "profile"}
        return str(body["m"]), build(fields)
    except ArrasError:
        raise
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise bad from None


def _time(value: str | None) -> datetime:
    parsed = parse_timestamp(value) if value else None
    return parsed or datetime.now(UTC)


def _rfc3339(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _refusal(backend: str, operation: str, reason: str, *, cursor: bool) -> ArrasError:
    """The error for Truss's typed `LoadAuditUnavailable`."""
    if reason in ("unauthorized", "incomplete_scope"):
        return Refused(backend, operation, "no_access")
    if reason == "resource":
        return Unavailable(backend, "resource", "a Truss bound on an audit page")
    if reason == "unsupported_profile":
        return Unavailable(backend, "unsupported_version", "the audit profile is not available")
    if cursor:
        return Invalid([Violation("after", "cursor", "not a cursor of this statement")])
    return Unavailable(backend, "busy", "the audit read could not be observed")


class Auditor:
    def __init__(
        self,
        backend: str,
        connections: Connections,
        registry: Registry,
        cache: CatalogCache,
        documents: Mapping[str, str] | None = None,
        wire: Wire | None = None,
    ) -> None:
        self.name = backend
        self.connections = connections
        self.registry = registry
        self.cache = cache
        self.documents = dict(documents or {})  # module -> Truss document id the host configured
        self.wire = wire or Wire()

    # -- scope

    def _scope(self, call: Call, module: str) -> tuple[str, Mapping[int, str], Mapping[int, str]]:
        """The document id of `module` for this call, and the names of its types and relationships by
        Truss's ids, from the catalog the person reads (none, for a person who reads nothing)."""
        catalog = self.registry.call_catalog(call)
        entry = None
        if catalog is not None:
            entry = next((e for e in catalog.modules if e["moduleId"] == module), None)
        document = (
            (entry["documentId"] if entry is not None else None)
            or self.cache.document_of(module)
            or self.documents.get(module)
        )
        if document is None:
            raise Refused(self.name, call.operation, "no_access")
        types: dict[int, str] = {}
        relationships: dict[int, str] = {}
        if entry is not None:
            for t in entry.get("types", ()):
                if t.get("kind") == "record":
                    types[int(t["typeId"])] = f"{module}.{t['recordId']}"
            for r in entry.get("relationships", ()):
                relationships[int(r["relationshipId"])] = str(r["name"])
        return str(document), types, relationships

    def _modules(self, principal: Principal) -> list[str]:
        """The modules a group id is looked for in when no module is named: those this adapter has
        served or was configured with."""
        names = {m.name for m in self.cache.seen()} | set(self.documents)
        return sorted(names)

    # -- changes

    def changes(
        self,
        principal: Principal,
        *,
        module: str | None,
        type: str | None,  # noqa: A002
        key: str | None,
        by: str | None,
        action: str | None,
        group: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        after: str | None,
    ) -> ChangesPage:
        if not principal.token:
            raise Refused(self.name, "changes", "token_expired")
        if key is not None:
            raise Unsupported(
                "changes of a key",
                ["a module, a type, a person, an action, a group or a time range"],
            )
        signature = _signature(module, type, by, action, group, since, until)
        resume: Any = None
        if after is not None:
            named, resume = _decode(
                after, "changes", signature, lambda f: self.wire.audit_cursor("changes", f)
            )
            module = module or named
        modules = [module] if module is not None else self._modules(principal)
        refused: Refused | None = None
        last: ChangesPage | None = None
        for name in modules:
            try:
                page = self._changes_of(
                    principal,
                    name,
                    dict(type=type, by=by, action=action, group=group, since=since, until=until),
                    limit,
                    resume,
                    signature,
                )
            except Refused as exc:
                if module is not None:
                    raise
                refused = exc  # another module may be one the person audits
                continue
            if page.items or module is not None:
                return page
            last = page
        if last is not None:
            return last
        if refused is not None:
            raise refused
        return ChangesPage((), None, False, self._fresh("none"))

    def _changes_of(
        self,
        principal: Principal,
        module: str,
        asked: Mapping[str, Any],
        limit: int,
        resume: Any,
        signature: str,
    ) -> ChangesPage:
        with self.connections.read(principal, "changes") as call:
            document, types, relationships = self._scope(call, module)
            filters: dict[str, str] = {"documentId": document, "moduleId": module}
            if asked["action"] is not None:
                filters["assertedAction"] = str(asked["action"])
            if asked["since"] is not None:
                filters["observedAtFrom"] = _rfc3339(asked["since"])
            if asked["until"] is not None:
                filters["observedAtUntil"] = _rfc3339(asked["until"])
            if asked["type"] is not None:
                wanted = _id_of(types, str(asked["type"]))
                if wanted is None:  # not a type of the module this person reads: nothing matches
                    return ChangesPage((), None, False, self._fresh("none"))
                filters["entityType"] = str(wanted)
            by, group = asked["by"], asked["group"]
            if group is not None and not _GROUP.fullmatch(str(group)):
                return ChangesPage((), None, False, self._fresh("none"))
            names = {"types": types, "relationships": relationships}

            def fetch(cursor: Any) -> Any:
                return call.unwrap(
                    call.assembly.page_mutation_group_audit_in_transaction(
                        call.tx, filters=filters, cursor=cursor, maximum_events=PAGE_EVENTS
                    ),
                    mapped,
                )

            def project(page: Any, epoch: str) -> Change | None:
                if not _ACTION.fullmatch(page.asserted_action or ""):
                    return None  # an import, or a group no action made
                who = page.native_actor_name or page.native_actor
                if by is not None and who != by:
                    return None
                if group is not None and f"{epoch}:{page.writer_xid}" != group:
                    return None
                return _change(self.name, module, page, epoch, who, names)

            walked = self._walk(
                call, "changes", "MutationGroupAuditPage", fetch, resume, limit, project
            )
        items = tuple(walked.items)
        nxt = (
            _encode("changes", signature, module, walked.after)
            if (walked.more or walked.cut) and walked.after is not None
            else None
        )
        return ChangesPage(items, nxt, walked.cut, self._fresh(walked.frontier))

    # -- loads

    def loads(
        self, principal: Principal, module: str, *, limit: int, after: str | None
    ) -> LoadsPage:
        if not principal.token:
            raise Refused(self.name, "loads", "token_expired")
        signature = _signature(module)
        resume: Any = None
        if after is not None:
            _, resume = _decode(
                after, "loads", signature, lambda f: self.wire.audit_cursor("loads", f)
            )
        with self.connections.read(principal, "loads") as call:
            document, _, _ = self._scope(call, module)
            filters = {"documentId": document, "moduleId": module}

            def fetch(cursor: Any) -> Any:
                return call.unwrap(
                    call.assembly.page_import_load_audit_in_transaction(
                        call.tx, filters=filters, cursor=cursor, maximum_entries=128
                    ),
                    mapped,
                )

            walked = self._merge_loads(call, module, fetch, resume, limit)
        nxt = (
            _encode("loads", signature, module, walked.after)
            if walked.more and walked.after is not None
            else None
        )
        return LoadsPage(tuple(walked.items), nxt, walked.cut, self._fresh(walked.frontier))

    def _merge_loads(
        self, call: Call, module: str, fetch: Callable[[Any], Any], resume: Any, limit: int
    ) -> _Walk:
        """Invocation summaries, newest first, merged by load id and person into loads: `limit` of
        them, and whether another follows. The cursor is the one after the last summary the last load
        took in."""
        walked = _Walk([])
        current: Load | None = None
        cursor, taken, scanned = resume, resume, 0
        while True:
            out = fetch(cursor)
            kind = kind_of(out)
            if kind == "LoadAuditListingEnd":
                break
            if kind == "LoadAuditUnavailable":
                raise _refusal(self.name, "loads", out.reason, cursor=resume is not None)
            if kind != "LoadAuditInvocationSummary":
                raise Unavailable(self.name, "unreachable", f"truss {kind}")
            walked.frontier = out.next_page_cursor.frontier_xid if out.next_page_cursor else "none"
            scanned += 1
            piece = _load(module, out)
            if current is not None and _same(current, piece):
                current = _add(current, piece)
            else:
                if current is not None:
                    walked.items.append(current)
                    if len(walked.items) == limit:
                        walked.more = True
                        walked.after = taken
                        return walked
                current = piece
            taken = out.next_page_cursor
            if taken is None:
                break
            cursor = taken
            if scanned >= SCAN:
                walked.cut = True
                break
        if current is not None:
            walked.items.append(current)
        walked.after = taken
        return walked

    # -- the walk of mutation groups

    def _walk(
        self,
        call: Call,
        operation: str,
        page_kind: str,
        fetch: Callable[[Any], Any],
        resume: Any,
        limit: int,
        project: Callable[[Any, str], Any],
    ) -> _Walk:
        """Pages from `resume` until `limit` items `project` keeps and one more (so a next page is
        known), or Truss has no more, or the scan bound is reached (`cut`)."""
        walked = _Walk([])
        cursor, scanned = resume, 0
        while True:
            out = fetch(cursor)
            kind = kind_of(out)
            if kind == "MutationGroupAuditListingEnd":
                return walked
            if kind == "LoadAuditUnavailable":
                raise _refusal(self.name, operation, out.reason, cursor=resume is not None)
            if kind != page_kind:
                raise Unavailable(self.name, "unreachable", f"truss {kind}")
            nxt = out.next_page_cursor
            if nxt is None:
                raise Unavailable(self.name, "unreachable", "Truss gave no source epoch")
            walked.frontier = nxt.frontier_xid
            scanned += 1
            item = project(out, nxt.source_epoch)
            if item is not None:
                if len(walked.items) == limit:
                    walked.more = True
                    return walked
                walked.items.append(item)
                walked.after = nxt
            cursor = nxt
            if scanned >= SCAN:
                walked.cut = True
                walked.after = nxt
                return walked

    def _fresh(self, frontier: str) -> Freshness:
        return Freshness(
            self.name, Position(f"audit-frontier:{frontier}", datetime.now(UTC)), "latest"
        )


def _id_of(names: Mapping[int, str], wanted: str) -> int | None:
    return next((i for i, n in names.items() if n == wanted), None)


def _kind(entity_kind: str, operation: str) -> str:
    """The op kind of a Truss event: create and delete, or link and unlink for an edge, else an update."""
    edge = entity_kind == "edge"
    if operation in _CREATES:
        return "link" if edge else "create"
    if operation in _DELETES:
        return "unlink" if edge else "delete"
    return "update"


def _change(
    backend: str, module: str, page: Any, epoch: str, who: str, names: Mapping[str, Any]
) -> Change:
    """One group as the contract's change: its operations in order, one op per entity touched."""
    ops: dict[tuple[str, str, str], dict[str, Any]] = {}
    for e in page.entries:
        at = (e.operation_index, e.entity_kind, e.entity_id)
        kind = _kind(e.entity_kind, e.operation)
        held = ops.get(at)
        if held is not None:  # an update is a property and a metadata event of one operation
            if kind != "update":
                held["kind"] = kind
            continue
        ops[at] = _op(e, kind, names)
    return Change(
        f"{epoch}:{page.writer_xid}",
        _time(page.observed_at),
        who,
        page.asserted_action,
        module,
        tuple(ops.values()),
        backend,
    )


def _op(entry: Any, kind: str, names: Mapping[str, Any]) -> dict[str, Any]:
    tid = int(entry.entity_type)
    if entry.entity_kind == "edge":
        label = names["relationships"].get(tid, f"#{tid}")
        return {
            "kind": kind,
            "relationship": label,
            "source": None,
            "target": None,
            "id": entry.entity_id,
        }
    return {
        "kind": kind,
        "type": names["types"].get(tid, f"#{tid}"),
        "key": None,
        "version": None,
        "id": entry.entity_id,
    }


def _load(module: str, summary: Any) -> Load:
    return Load(
        summary.load_id,
        summary.native_actor_name,
        _time(summary.observed_at_until),
        module,
        int(summary.created_count),
        int(summary.skipped_count),
        int(summary.rejected_count),
        partial=summary.state != "complete",
    )


def _same(a: Load, b: Load) -> bool:
    return a.load_id == b.load_id and a.initiated_by == b.initiated_by


def _add(a: Load, b: Load) -> Load:
    return Load(
        a.load_id,
        a.initiated_by,
        max(a.at, b.at),
        a.module,
        a.created + b.created,
        a.skipped + b.skipped,
        a.rejected + b.rejected,
        partial=a.partial or b.partial,
    )
