# SPDX-License-Identifier: MIT OR Apache-2.0
"""`import_records` of the Truss adapter (CONTRACT-003, CONTRACT-004, plan TR-09, B8): a load as the person.

The administrative gate is Truss's own, asked cheaply: only a registrar may import (CONTRACT-005), and
Truss's advisory registrar status says whether the person is one, so a person who is not is refused
(CONTRACT-005) before any record is read; the person's writer role is Truss's check at each record.
Truss imports for any writer and validates less than Arras does, so the adapter checks each record
first, as the memory adapter does: a type, a key, the declared and required properties and a number's
domain. A record that fails is a `Rejection` and is never sent.

A load takes Truss's explicit batched route. The entities of the whole load go first, then its
relationships (an edge needs the identities of its ends, so the entities' calls commit before the
relationships are built). Each phase is sent in calls of at most `BATCH` records (Truss's batched
profile takes 1,024, but a call's time grows faster than its records), and every call is one transaction of the person: all its records are built in one
native call (`build_import_records_in_transaction`), imported in chunks of `CHUNK` (Truss's own
containment: each record has a subtransaction of its own, so a record Truss rejects does not undo the
others) and settled together, committed when the call ends. A load is therefore not atomic: a failure
leaves the earlier calls stored, and repeating the load is safe because a record already held is
skipped. Both the outer outcome and the inner semantic result are narrowed. A COMMIT whose outcome is
unknown is not replayed (Truss has no token for an import, and a replay would count a created record as
skipped): it is `Unavailable` and the caller repeats the load. An error that ends a later call carries a
note of what the earlier calls confirmed.

A literally empty load is sent as an empty load and Truss settles it (`empty_load_settlement`); a load
whose every record the adapter rejected sends nothing. Truss keeps a load, including one that created
nothing, and `initiated_by` is the session person (it is the origin's `x-initiated-by` and is checked
here).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from arras.actions import KEY_VALUE, Ref
from arras.adapters.truss.apply import CallLookups
from arras.adapters.truss.connection import Call, Connections, failure_error
from arras.adapters.truss.outcome import mapper
from arras.adapters.truss.plan import canonical
from arras.adapters.truss.registry import Registry, kind_of
from arras.adapters.truss.values import Ids, document_ids, encode, timestamp
from arras.adapters.truss.wire import Wire
from arras.errors import ArrasError, Invalid, Refused, Unavailable, Violation
from arras.inputs import parse_timestamp
from arras.model import EntityTypeInfo, ModuleInfo
from arras.results import ImportResult, Rejection
from arras.types import Principal

# Records in one call and one commit. Truss's batched profile takes up to 1,024 original records in
# chunks of 1 to 128, but the time of a call is not linear in its records: Truss gives each record a
# subtransaction of its own, and measured on a quiet local PostgreSQL 18.6, 1,024 records cost 49 s in
# one transaction (the operation bound is 60 s), 22 s in two of 512, 16 s in four of 256 and 14 s in
# eight of 128 (plan B8). So a call is one chunk of 128, which keeps the statements of the batched
# route (9 for a chunk: 3 to build, 6 to import and authorize its report) and the time per record
# flat, and a bigger load is more calls, each committed.
BATCH = 128
CHUNK = 128
LOAD_ID_BYTES = 4096


@dataclass
class _Chunk:
    """What one call decided; kept only once its commit lands."""

    created: int = 0
    skipped: int = 0
    rejected: list[Rejection] = field(default_factory=list[Rejection])
    known: dict[Ref, Any] = field(default_factory=dict[Ref, Any])


@dataclass
class _Sent:
    """A record ready to send, and what to say of its outcome."""

    record: Any
    kind: str
    identity: str
    ref: Ref | None = None  # an entity record's own ref


def _identity_present(value: Any) -> bool:
    return value is not None and kind_of(value) != "Absent"


def _original_at(value: object) -> str | None:
    """The original time as Truss takes it: an ISO 8601 timestamp that names its offset."""
    if value is None:
        return None
    if isinstance(value, str):
        value = parse_timestamp(value)  # RFC 3339 text, as an exported file writes it
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("original_at: not an ISO timestamp with an offset")
    return timestamp(value)


class Importer:
    def __init__(
        self, backend: str, connections: Connections, registry: Registry, wire: Wire | None = None
    ) -> None:
        self.name = backend
        self.connections = connections
        self.registry = registry
        self.wire = wire or Wire()

    # -- entry

    def import_records(
        self,
        principal: Principal,
        module: str,
        records: Sequence[Mapping[str, object]],
        *,
        load_id: str,
        initiated_by: str,
    ) -> ImportResult:
        if not principal.token:
            raise Refused(self.name, "import_records", "token_expired")
        entities = [r for r in records if "type" in r]
        relations = [r for r in records if "type" not in r]
        chunks = [entities[i : i + BATCH] for i in range(0, len(entities), BATCH)]
        chunks += [relations[i : i + BATCH] for i in range(0, len(relations), BATCH)]
        known: dict[Ref, Any] = {}
        created = skipped = 0
        rejected: list[Rejection] = []
        for done, chunk in enumerate(chunks or [[]]):  # an empty load still reaches Truss
            try:
                got = self._chunk(
                    principal, module, chunk, load_id, initiated_by, known, empty=not records
                )
            except ArrasError as exc:
                if done:  # what the calls before this one confirmed stays stored
                    exc.add_note(
                        f"{created} created and {skipped} skipped by {done} confirmed call(s)"
                    )
                raise
            created, skipped = created + got.created, skipped + got.skipped
            rejected += got.rejected
            known.update(got.known)
        return ImportResult(created, skipped, tuple(rejected))

    def _chunk(
        self,
        principal: Principal,
        module: str,
        records: Sequence[Mapping[str, object]],
        load_id: str,
        initiated_by: str,
        known: Mapping[Ref, Any],
        *,
        empty: bool,
    ) -> _Chunk:
        out = _Chunk()
        with self.connections.write(principal, "import_records") as call:
            self.registry.require_registrar(call, "import_records")
            if initiated_by != principal.user:
                raise Invalid(
                    [Violation("initiated_by", "attribution", "a load is the caller's own")]
                )
            size = len(load_id.encode())
            if not 1 <= size <= LOAD_ID_BYTES or "\x00" in load_id:
                raise Invalid(
                    [Violation("load_id", "bound", f"a load id is 1 to {LOAD_ID_BYTES} bytes")]
                )
            held = self.registry.held_module(call, module)
            if held is None:
                raise Refused(self.name, "import_records", "no_access")
            ids = document_ids(held.content, module)
            lookups = CallLookups(self.name, call, held.document_id, ids, frozenset())
            sent: list[_Sent] = []
            for r in records:
                if "type" in r:
                    got = self._entity(held.info, held.document_id, ids, r)
                else:
                    got = self._relation(held.info, held.document_id, ids, lookups, known, r)
                if isinstance(got, Rejection):
                    out.rejected.append(got)
                else:
                    sent.append(got)
            if sent or empty:
                self._send(call, held, sent, load_id, initiated_by, out)
        return out

    def _send(
        self,
        call: Call,
        held: Any,
        sent: Sequence[_Sent],
        load_id: str,
        initiated_by: str,
        out: _Chunk,
    ) -> None:
        """Build the call's records in one native call, import them in Truss's chunks and read
        the outcomes. The outer outcome of each Truss call is narrowed by `unwrap`, the inner
        result by class."""
        built = call.unwrap(
            call.assembly.build_import_records_in_transaction(
                call.tx, tuple(s.record for s in sent)
            ),
            mapper,
        )
        if kind_of(built) != "BuiltImportRecords":
            raise Unavailable(self.name, "unreachable", f"truss {kind_of(built)}")
        given = built.context.input(
            built.records,
            load_id=load_id,
            asserted_origin=self.wire.import_origin(initiated_by),
            chunk_size=CHUNK,
        )
        executed = call.assembly.import_batched_in_transaction(
            call.tx, given, documents=(self.wire.document(held.document_id, held.content),)
        )
        self._outcomes(call, executed, sent, out)

    # -- records

    def _entity(
        self,
        module: ModuleInfo,
        document_id: str,
        ids: Ids,
        r: Mapping[str, object],
    ) -> _Sent | Rejection:
        key = str(r.get("key", ""))
        ref = Ref(f"{module.name}.{r['type']}", key)
        t: EntityTypeInfo | None = module.entity_type(str(r["type"]))
        if t is None or not KEY_VALUE.fullmatch(key):
            return Rejection("entity", str(ref), "unknown type or not a key")
        given = cast(Mapping[str, Any], r.get("properties") or {})
        props = {k: v for k, v in given.items() if v is not None}
        missing = [
            p.name for p in t.properties if p.required and p.name != t.key and p.name not in props
        ]
        extra = sorted(set(given) - {p.name for p in t.properties})
        if missing or extra:
            return Rejection("entity", str(ref), f"missing {missing}, undeclared {extra}")
        local = t.local_name
        values: list[Any] = []
        try:
            for name, value in {**props, t.key: key}.items():
                prop = t.property(name)
                assert prop is not None
                if not prop.scalar or prop.cardinality == "many":
                    return Rejection("entity", str(ref), f"{name} is not a scalar value")
                values.append(
                    self.wire.authored(
                        name,
                        encode(self.wire, prop.type, ids.domains.get((local, name)), name, value),
                    )
                )
        except Invalid as exc:
            return Rejection("entity", str(ref), exc.violations[0].message)
        author = r.get("original_author")
        try:
            original_at = _original_at(r.get("original_at"))
        except ValueError as exc:
            return Rejection("entity", str(ref), str(exc))
        source = self.wire.import_source(None if author is None else str(author), original_at)
        record = self.wire.object_draft(document_id, ids.module_id, local, tuple(values), source)
        return _Sent(record, "entity", str(ref), ref)

    def _relation(
        self,
        module: ModuleInfo,
        document_id: str,
        ids: Ids,
        lookups: CallLookups,
        known: Mapping[Ref, Any],
        r: Mapping[str, object],
    ) -> _Sent | Rejection:
        name, s, t = str(r.get("relationship")), str(r.get("source")), str(r.get("target"))
        ident = f"{name}/{s}/{t}"
        found = canonical(module, name)
        rid = None if found is None else ids.relationships.get(found[0].name)
        if found is None or rid is None:
            return Rejection("record", ident, "neither an entity nor a relationship")
        rel, inverse = found
        if inverse:
            s, t = t, s
        src = self._endpoint(lookups, known, rel.source, s)
        tgt = self._endpoint(lookups, known, rel.target, t)
        if src is None or tgt is None:
            return Rejection("relationship", ident, "an endpoint is missing or of the wrong type")
        record = self.wire.edge_draft(document_id, ids.module_id, rid, src, tgt)
        return _Sent(record, "relationship", ident)

    @staticmethod
    def _endpoint(
        lookups: CallLookups, known: Mapping[Ref, Any], types: Sequence[str], key: str
    ) -> Any | None:
        """The identity of the first type's object that holds the key: this load's own, else Truss's
        (a key lookup, cached in the call)."""
        for qualified in types:
            ref = Ref(qualified, key)
            identity = known.get(ref)
            if identity is None:
                identity = lookups.identity(ref)
            if identity is not None:
                return identity
        return None

    # -- the answer

    def _outcomes(self, call: Call, executed: Any, sent: Sequence[_Sent], out: _Chunk) -> None:
        """`executed` is Truss's `BatchedImportExecutionResult`: the tagged import result, and for a
        zero-record load how Truss settled it. Neither is taken for success unread."""
        if kind_of(executed) != "BatchedImportExecutionResult":
            raise Unavailable(self.name, "unreachable", f"truss {kind_of(executed)}")
        settled = executed.empty_load_settlement
        if settled is not None and settled.disposition != "pending":
            # a caller-owned load is pending; any other disposition is Truss saying it settled the
            # load itself, which this call never asked, so nothing may be inferred of the outcome
            call.quarantined = settled.disposition in ("commit_unknown", "transaction_unresolved")
            raise Unavailable(self.name, "unreachable", f"truss empty load {settled.disposition}")
        result = executed.result
        kind = kind_of(result)
        if kind == "ImportExecutionFailed":
            failure = result.error
            if getattr(failure, "code", None) in ("transaction_unusable", "commit_unknown"):
                call.quarantined = True
            if getattr(failure, "sql_state", None) == "54000":
                raise Unavailable(self.name, "resource", "a Truss bound on a transaction's writes")
            raise failure_error(self.name, "import_records", failure)
        if kind == "ImportResourceLimited":
            raise Unavailable(self.name, "resource", "a Truss bound on an import")
        if kind == "ImportInvalid":
            raise Invalid([Violation("records", "invalid", "Truss refused the import's shape")])
        if kind != "ImportReported":
            raise Unavailable(self.name, "unreachable", f"truss {kind}")
        outcomes = sorted(result.report.outcomes, key=lambda o: int(o.input_index))
        if len(outcomes) != len(sent):
            raise Unavailable(self.name, "unreachable", "truss reported another count of records")
        for item, o in zip(sent, outcomes, strict=True):
            self._record(item, o, out)

    def _record(self, item: _Sent, o: Any, out: _Chunk) -> None:
        what = kind_of(o)
        if what == "ImportCreated":
            out.created += 1
            if item.ref is not None:
                out.known[item.ref] = o.identity
        elif what == "ImportSkipped":
            out.skipped += 1
            if item.ref is not None and _identity_present(getattr(o, "identity", None)):
                out.known[item.ref] = o.identity
        elif what == "ImportRejected":
            if o.code == "unauthorized":
                raise Refused(self.name, "import_records", "no_access")
            out.rejected.append(
                Rejection(item.kind, item.identity, f"Truss rejected the record: {o.code}")
            )
        else:
            raise Unavailable(self.name, "unreachable", "truss could not tell a record's outcome")
