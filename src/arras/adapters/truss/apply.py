# SPDX-License-Identifier: MIT OR Apache-2.0
"""`apply` of the Truss adapter (CONTRACT-003, CONTRACT-004, plan TR-07): a plan as one Truss group,
applied as the person.

One write call per attempt, on the person's own connection (never a service identity):

1. the person's catalog and the module's accepted document, read in the call (Truss binds a write to
   the document's exact bytes; the catalog cache grants nothing);
2. the effects checked against the module, then the planner's lookups (a key lookup locks the
   row until the transaction ends);
3. `apply_in_transaction` with a request id: the idempotency key scoped by the action, or a fresh
   id for a keyless invocation. A failure is raised inside the call, so the call rolls back and a
   failed group leaves no row, no journal row and no request record;
4. commit. Truss's first answer holds no receipt token: the token is read by presenting the same
   input and request once more, in a second call, after the commit (D1). That repeat is also the
   recovery from a commit whose outcome is unknown: Truss answers it with the original's results
   when the commit landed, and applies it when it did not. A write that committed but whose token
   cannot be read is `Unavailable`; the write stands and a keyed caller retries with its key.

A dry run is the same call rolled back; a keyed one presents its request, so a request already
committed surfaces as the replay.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from arras import telemetry
from arras.actions import Create, Link, Plan, Ref, Unlink, check_effects
from arras.adapters.truss.connection import Call, CommitUnknown, Connections
from arras.adapters.truss.outcome import (
    Retry,
    artifact,
    attributed,
    invalid_input,
    mapper,
    merge_failures,
    operation_failure,
    receipt,
    unavailable_group,
)
from arras.adapters.truss.plan import (
    MAX_BATCH,
    MAX_OPERATIONS,
    MAX_PRECONDITIONS,
    Built,
    Planner,
    canonical,
    check_bounds,
    derive_keys,
    materialize,
    request_id,
)
from arras.adapters.truss.registry import Registry, kind_of
from arras.adapters.truss.values import Ids, document_ids
from arras.adapters.truss.wire import Wire
from arras.errors import (
    ArrasError,
    Conflict,
    Failure,
    Invalid,
    PreconditionFailed,
    Refused,
    Unavailable,
    Unsupported,
    Violation,
)
from arras.model import ModuleInfo
from arras.results import BatchReceipt, ItemResult, Receipt, Validation
from arras.types import Principal

ATTEMPTS = 3  # runs of a call Truss asks to be restarted
PAGE = 1000  # Truss's page size for edges
# Truss answers a replay only for the input it was first given. The adapter rebuilds a retry's input
# from what exists, so a request Truss holds is either one for other input or one whose original
# targets (a deleted object, an unlinked edge) no longer resolve as they did (truss-requirements R18.3).
_HELD_FOR_OTHER_INPUT = (
    "Truss holds that request for other input, or the original's targets no longer resolve"
)


def needed(plans: Sequence[Plan], module: ModuleInfo) -> tuple[list[str], list[str]]:
    """The record types (local names) and forward relationship names the plans' effects and
    preconditions name, in first-use order: what the planner would ask Truss for one by one."""
    records: dict[str, None] = {}
    rels: dict[str, None] = {}

    def record(ref: object) -> None:
        if isinstance(ref, Ref):
            records.setdefault(ref.type.split(".", 1)[1], None)

    def relationship(name: object) -> None:
        found = canonical(module, str(name))
        if found is not None:
            rels.setdefault(found[0].name, None)

    for plan in plans:
        for e in plan.effects:
            if isinstance(e, Link | Unlink):
                relationship(e.relationship)
                record(e.source)
                record(e.target)
            else:
                record(e.ref)
        for p in plan.preconditions:
            record(p.args.get("ref"))
            if p.op == "absent" and "type" in p.args:
                records.setdefault(str(p.args["type"]).split(".", 1)[1], None)
            if "relationship" in p.args:
                relationship(p.args["relationship"])
            for v in p.args.values():
                record(v)
    return list(records), list(rels)


class CallLookups:
    """The planner's reads of Truss in one call: references, key lookups and edges, each cached."""

    def __init__(
        self, backend: str, call: Call, document_id: str, ids: Ids, generated: frozenset[Ref]
    ) -> None:
        self.backend = backend
        self.call = call
        self.document_id = document_id
        self.ids = ids
        self.generated = generated  # refs made for this invocation: none exists yet
        self._types: dict[str, Any] = {}
        self._relationships: dict[str, Any] = {}
        self._found: dict[Ref, Any | None] = {}

    def _read(self, outcome: Any) -> Any:
        return self.call.unwrap(outcome, mapper)

    def type_ref(self, record: str) -> Any:
        if record not in self._types:
            found = self._read(
                self.call.assembly.get_type_reference_in_transaction(
                    self.call.tx,
                    document_id=self.document_id,
                    module_id=self.ids.module_id,
                    record_id=record,
                )
            )
            if found is None:
                raise Invalid([Violation("effects", "unknown_type", f"no type {record}")])
            self._types[record] = found
        return self._types[record]

    def relationship_ref(self, name: str) -> Any:
        if name not in self._relationships:
            rid = self.ids.relationships.get(name)
            found = (
                None
                if rid is None
                else self._read(
                    self.call.assembly.get_relationship_reference_in_transaction(
                        self.call.tx,
                        document_id=self.document_id,
                        module_id=self.ids.module_id,
                        relationship_id=rid,
                    )
                )
            )
            if found is None:
                raise Invalid(
                    [Violation("effects", "unknown_type", f"{name} is not a relationship")]
                )
            self._relationships[name] = found
        return self._relationships[name]

    def seed(self, types: Mapping[str, Any], relationships: Mapping[str, Any]) -> None:
        """References `prepare_group_in_transaction` gave with the group context, so the planner
        asks Truss for none of them again."""
        self._types.update(types)
        self._relationships.update(relationships)

    def identity(self, ref: Ref) -> Any | None:
        if ref in self.generated:
            return None
        if ref not in self._found:
            found = self._lookup(ref)
            self._found[ref] = None if found is None else found.identity
        return self._found[ref]

    def exists_now(self, ref: Ref) -> bool:
        """Whether an object holds the key now: not cached, for a failure's follow-up."""
        return self._lookup(ref) is not None

    def _lookup(self, ref: Ref) -> Any | None:
        record = ref.type.split(".", 1)[1]
        key_id = self.ids.keys.get(record)
        if key_id is None:
            raise Unsupported(f"{record} has no key Truss can look up", ["a record with a key"])
        out = self._read(
            self.call.assembly.lookup_key_in_transaction(
                self.call.tx,
                document_id=self.document_id,
                module_id=self.ids.module_id,
                record_id=record,
                key_id=key_id,
                values=(ref.key,),
            )
        )
        kind = kind_of(out)
        if kind == "ObjectFound":
            return out.object
        if kind == "ObjectNotFound":
            return None
        if kind == "ObjectReadInvalid":
            raise Invalid([Violation(f"key.{ref.key}", "invalid", "Truss refused the key")])
        raise unavailable_group(self.backend, getattr(out, "reason", "observation"))

    def edges(self, anchor: Any, relationship: str, direction: str) -> Sequence[Any]:
        rid = self.ids.relationships.get(relationship)
        if rid is None:
            return []
        out: list[Any] = []
        cursor: Any = None
        while True:
            page = self._read(
                self.call.assembly.page_edges_in_transaction(
                    self.call.tx,
                    document_id=self.document_id,
                    module_id=self.ids.module_id,
                    relationship_id=rid,
                    anchor=anchor,
                    direction=direction,
                    limit=PAGE,
                    continuation=cursor,
                )
            )
            if kind_of(page) != "EdgePage":
                if kind_of(page) in ("EdgeNotFound",):
                    return out
                raise unavailable_group(self.backend, getattr(page, "reason", "observation"))
            out.extend(page.edges)
            cursor = page.continuation
            if cursor is None:
                return out


@dataclass
class Sent:
    """What a first apply presented, kept so the same input and request can be presented again."""

    inp: Any
    req: Any
    documents: tuple[Any, ...]
    built: Built
    request: str
    builts: tuple[Built, ...] = ()  # each item of an atomic batch, over the group's operations


@dataclass(frozen=True)
class Done:
    kind: str  # `applied` (this attempt's group) or `replay` (Truss's record of an earlier commit)
    semantic: Any
    token: str | None
    sent: Sent


def _assume_exists(ref: Ref) -> bool:
    return True


@dataclass
class _Group:
    built: Built
    static: list[tuple[int, Failure]]
    order: dict[str, int]
    exists_now: Callable[[Ref], bool]
    names: dict[str, str] = field(default_factory=dict[str, str])  # an id sent -> the caller's
    owner: tuple[int, ...] = ()  # the batch item of each condition

    def failed(self, carried: Sequence[Any]) -> PreconditionFailed:
        failures = merge_failures(
            carried, self.static, self.order, names=self.names, owner=self.owner
        )
        err = PreconditionFailed(failures)
        if self.built.batch and self.owner:
            err.add_note(f"item {self._item(carried)}")
        return err

    def _item(self, carried: Sequence[Any]) -> int:
        rows = [self.order.get(f.condition_id, len(self.order)) for f in carried]
        rows.extend(i for i, _ in self.static)
        low = min(rows, default=0)
        return self.owner[low] if low < len(self.owner) else 0


class Applier:
    def __init__(
        self, backend: str, connections: Connections, registry: Registry, wire: Wire | None = None
    ) -> None:
        self.name = backend
        self.connections = connections
        self.registry = registry
        self.wire = wire or Wire()

    # -- entry

    def apply(
        self,
        principal: Principal,
        plan: Plan,
        *,
        idempotency_key: str | None,
        dry_run: bool = False,
        scope: str | None = None,
    ) -> Receipt | Validation:
        """`scope` names the request id's action part (`request_id`): an independent batch's item
        sets it to the action and its index, and every other call leaves it the action."""
        if not principal.token:
            raise Refused(
                self.name, "apply", "token_expired"
            )  # before anything else, as the layer does
        check_bounds(plan)
        if scope is None:  # an independent batch's item leaves the flag its batch set
            telemetry.annotate(recovered=False)
        request = request_id(scope or plan.action, idempotency_key)
        derived = derive_keys(plan, request)
        for _ in range(ATTEMPTS):
            try:
                return self._once(
                    principal, plan, derived, request, dry_run, idempotency_key is not None
                )
            except Retry:
                continue
        raise Unavailable(self.name, "busy", "Truss asked for the write to be run again")

    def _once(
        self,
        principal: Principal,
        plan: Plan,
        derived: Plan,
        request: str,
        dry: bool,
        keyed: bool,
    ) -> Receipt | Validation:
        module = plan.action.split(".", 1)[0]
        sent: list[Sent] = []
        recovered = False
        try:
            with self.connections.write(principal, "apply") as call:
                call.rollback = dry
                done = self._first(call, [derived], request, module, sent, keyed)
                if done.kind == "replay":
                    call.rollback = True  # nothing was written
        except CommitUnknown:
            if not sent:
                raise
            # the invocation core is observing says a lost commit was recovered (a flag, never the
            # request id or the key)
            telemetry.annotate(recovered=True)
            done = self._recover(principal, sent[0])
            recovered = True
        except (PreconditionFailed, Conflict, Invalid) as exc:
            if dry:
                return self._verdict(plan, exc)
            raise
        if dry:
            replay = (
                receipt(
                    plan,
                    done.sent.built,
                    done.semantic,
                    done.token or "",
                    replayed=True,
                    request=request,
                )
                if done.kind == "replay"
                else None
            )
            return Validation(True, (), (), plan.effects, replay, None)
        replayed = done.kind == "replay" and not recovered
        token = done.token if done.token is not None else self._token(principal, done.sent)
        return receipt(
            plan, done.sent.built, done.semantic, token, replayed=replayed, request=request
        )

    # -- a batch

    def apply_batch(
        self,
        principal: Principal,
        plans: Sequence[Plan],
        *,
        atomic: bool,
        idempotency_key: str | None,
        stop_on_error: bool = False,
    ) -> BatchReceipt:
        """An atomic batch is one group under one request id, committed once and named by one token.
        An independent batch is the host's orchestration (Truss has none): each item is its own call,
        group and request id (`module.Action#index:key`), so a refused item leaves the rest to commit
        and a keyed repeat replays the committed ones."""
        if not 1 <= len(plans) <= MAX_BATCH:
            raise Invalid([Violation("items", "bound", f"a batch holds 1 to {MAX_BATCH} items")])
        action = plans[0].action
        if any(p.action != action for p in plans):
            raise Invalid([Violation("items", "mixed_actions", "a batch is one action")])
        if not principal.token:
            raise Refused(self.name, "apply", "token_expired")
        for plan in plans:  # every item is told before any is applied
            check_bounds(plan)
        telemetry.annotate(recovered=False)  # a recovery in any item raises it, nothing lowers it
        if atomic:
            effects = sum(len(p.effects) for p in plans)
            conditions = sum(len(p.preconditions) for p in plans)
            if effects > MAX_OPERATIONS or conditions > MAX_PRECONDITIONS:
                raise Unsupported(
                    f"an atomic batch of {effects} effects and {conditions} preconditions",
                    [f"at most {MAX_OPERATIONS} operations and {MAX_PRECONDITIONS} preconditions"],
                )
            return self._atomic(principal, plans, idempotency_key)
        items: list[ItemResult] = []
        for i, plan in enumerate(plans):
            try:
                got = self.apply(
                    principal, plan, idempotency_key=idempotency_key, scope=f"{action}#{i}"
                )
                assert isinstance(got, Receipt)
                items.append(ItemResult(i, got))
            except (PreconditionFailed, Conflict, Invalid) as exc:
                items.append(ItemResult(i, refusal=exc))
                if stop_on_error:
                    break
        ok = [it.receipt for it in items if it.receipt is not None]
        return BatchReceipt(
            action, False, tuple(items), len(ok), len(items) - len(ok), ok[-1].token if ok else None
        )

    def _atomic(
        self, principal: Principal, plans: Sequence[Plan], idempotency_key: str | None
    ) -> BatchReceipt:
        action = plans[0].action
        request = request_id(f"{action}#atomic", idempotency_key)
        # an item's generated keys are named by the request and the item, so two items never share one
        derived = [derive_keys(p, f"{request}@{i}") for i, p in enumerate(plans)]
        for _ in range(ATTEMPTS):
            try:
                return self._once_atomic(
                    principal, plans, derived, request, idempotency_key is not None
                )
            except Retry:
                continue
        raise Unavailable(self.name, "busy", "Truss asked for the write to be run again")

    def _once_atomic(
        self,
        principal: Principal,
        plans: Sequence[Plan],
        derived: Sequence[Plan],
        request: str,
        keyed: bool,
    ) -> BatchReceipt:
        action = plans[0].action
        sent: list[Sent] = []
        recovered = False
        try:
            with self.connections.write(principal, "apply") as call:
                done = self._first(
                    call, derived, request, action.split(".", 1)[0], sent, keyed, batch=True
                )
                if done.kind == "replay":
                    call.rollback = True  # nothing was written
        except CommitUnknown:
            if not sent:
                raise
            # the invocation core is observing says a lost commit was recovered (a flag, never the
            # request id or the key)
            telemetry.annotate(recovered=True)
            done = self._recover(principal, sent[0])
            recovered = True
        replayed = done.kind == "replay" and not recovered
        token = done.token if done.token is not None else self._token(principal, done.sent)
        items = tuple(
            ItemResult(
                i,
                receipt(
                    plan,
                    done.sent.builts[i],
                    done.semantic,
                    token,
                    replayed=replayed,
                    request=request,
                ),
            )
            for i, plan in enumerate(plans)
        )
        return BatchReceipt(action, True, items, len(items), 0, token)

    @staticmethod
    def _verdict(plan: Plan, exc: ArrasError) -> Validation:
        failures: tuple[Failure, ...] = ()
        violations: tuple[Violation, ...] = ()
        if isinstance(exc, PreconditionFailed):
            failures = tuple(exc.failures)
        elif isinstance(exc, Conflict):
            failures = (Failure(f"conflict:{exc.reason}", exc.detail),)
        elif isinstance(exc, Invalid):
            violations = tuple(exc.violations)
        return Validation(False, violations, failures, plan.effects, None, None)

    # -- the first call

    def _prepare(
        self, call: Call, plans: Sequence[Plan], module: str, batch: bool
    ) -> tuple[CallLookups, Planner, Built, Any, tuple[Any, ...], tuple[Any, ...]]:
        """The module as held in the call, the planner's lookups, the group's operations and the
        group context."""
        held = self.registry.held_module(call, module)
        if held is None:
            raise Refused(self.name, "apply", "no_access")
        for plan in plans:
            if not plan.effects:
                raise Unsupported("a plan with no effects", ["a plan of at least one effect"])
            check_effects(list(plan.effects), held.info)
        ids = document_ids(held.content, module)
        generated = frozenset(
            e.ref for plan in plans for e in plan.effects if isinstance(e, Create) and e.generated
        )
        lookups = CallLookups(self.name, call, held.document_id, ids, generated)
        prepared = self._prepared(call, held, ids, plans, lookups)
        planner = Planner(
            self.wire, held.info, ids, lookups, plans[0], items=plans if batch else None
        )
        built = planner.operations()
        if len(built.ops) > MAX_OPERATIONS:
            raise Unsupported(
                f"a plan that makes {len(built.ops)} operations",
                [f"at most {MAX_OPERATIONS} operations in one Truss group"],
            )
        context = (
            prepared.context
            if prepared is not None
            else call.unwrap(call.assembly.group_context_in_transaction(call.tx), mapper)
        )
        documents = (self.wire.document(held.document_id, held.content),)
        operations = tuple(materialize(self.wire, op) for op in built.ops)
        return lookups, planner, built, context, documents, operations

    def _prepared(
        self, call: Call, held: Any, ids: Ids, plans: Sequence[Plan], lookups: CallLookups
    ) -> Any | None:
        """The group context with the type and relationship references the plans name, in the one
        call Truss gives for them (`prepare_group_in_transaction`); the references seed the planner's
        lookups. None when Truss answers anything but the prepared group (a refusal is told by the
        calls it replaces, as they always told it), and the planner then asks for each as before."""
        records, rels = needed(plans, held.info)
        if not records:
            return None
        out = call.unwrap(
            call.assembly.prepare_group_in_transaction(
                call.tx,
                records=tuple((held.document_id, ids.module_id, r) for r in records),
                relationships=tuple(
                    (held.document_id, ids.module_id, ids.relationships[r])
                    for r in rels
                    if r in ids.relationships
                ),
            ),
            mapper,
        )
        if kind_of(out) != "PreparedGroup":
            return None
        named = [r for r in rels if r in ids.relationships]
        lookups.seed(
            {r: t for r, t in zip(records, out.types, strict=True) if t is not None},
            {r: t for r, t in zip(named, out.relationships, strict=True) if t is not None},
        )
        return out

    def _first(
        self,
        call: Call,
        plans: Sequence[Plan],
        request: str,
        module: str,
        sent: list[Sent],
        keyed: bool,
        *,
        batch: bool = False,
    ) -> Done:
        """The first call of a write: `plans` is one plan, or the items of an atomic batch."""
        lookups, planner, built, context, documents, operations = self._prepare(
            call, plans, module, batch
        )
        order = {cid: i for i, (cid, _, _) in enumerate(planner.pres)}
        names = {cid: p.id for cid, _, p in planner.pres}
        owner = tuple(item for _, item, _ in planner.pres)
        absent = {
            cid: Ref(str(p.args["type"]), str(p.args["key"]))
            for cid, _, p in planner.pres
            if p.op == "absent"
        }
        dropped: frozenset[str] = frozenset()
        while True:
            conditions, static = planner.preconditions(dropped)
            if len(conditions) > MAX_PRECONDITIONS:
                raise Unsupported(
                    f"{len(conditions)} preconditions",
                    [f"at most {MAX_PRECONDITIONS} in a group"],
                )
            inp = context.input(
                operations, self.wire.origin(plans[0].action), preconditions=tuple(conditions)
            )
            req = context.request(request)
            group = _Group(
                built,
                static,
                order,
                lookups.exists_now,
                names,
                owner if batch else (),
            )
            presented = Sent(inp, req, documents, built, request, tuple(planner.builts))
            got = self._classify(
                self._present(call, inp, req, documents), group, presented, conflict_to_caller=keyed
            )
            if isinstance(got, Done):
                if got.kind == "applied":
                    sent.append(presented)
                return got
            if kind_of(got) == "RequestConflict":
                # Truss holds this request for other input. A keyed retry of a plan whose `absent`
                # condition was left out on the first call (a retired key, below) presents the full
                # input and so conflicts: Truss's probe runs before the conditions. Left out here
                # again, exactly those conditions, the retry presents what the first call committed.
                # Deleted keys stay deleted and a create on a tombstoned key never commits, so the
                # original can only have left them out. A plan with an absent condition on a key
                # that never existed as well as one on a retired key cannot be rebuilt (the probe
                # cannot tell which was left out): it stays the conflict.
                retired = {cid for cid, ref in absent.items() if not lookups.exists_now(ref)}
                if retired - dropped:
                    dropped = dropped | retired
                    continue
                raise Conflict("idempotency_key_reused", _HELD_FOR_OTHER_INPUT)
            # `KeyAbsent` also fails for a key a deleted object held; an `absent` precondition holds
            # for it (the create that follows is the Conflict(deleted)), so such a condition is left
            # out and the group presented again, in the same transaction
            tombstoned = {
                f.condition_id
                for f in got.failures
                if f.rule == "key_absent"
                and f.condition_id in absent
                and not lookups.exists_now(absent[f.condition_id])
            }
            if tombstoned - dropped:
                dropped = dropped | tombstoned
                continue
            raise group.failed(got.failures)

    def _present(self, call: Call, inp: Any, req: Any, documents: tuple[Any, ...]) -> Any:
        return call.unwrap(
            call.assembly.apply_in_transaction(call.tx, inp, req, documents=documents),
            mapper,
        )

    def _classify(
        self, out: Any, group: _Group, sent: Sent, *, conflict_to_caller: bool = False
    ) -> Done | Any:
        """The result of presenting a group: `Done`, the `PreconditionFailed` carrier (for the
        caller to settle), the `RequestConflict` failure when `conflict_to_caller` (the first call of
        a keyed request settles it), or the error."""
        kind = kind_of(out)
        if kind == "GroupSuccess":
            response = out.response
            if kind_of(response) == "AppliedPending":
                if group.static:
                    raise group.failed(())
                pending = response.receipt_token
                return Done(
                    "applied",
                    response.semantic,
                    pending if isinstance(pending, str) and pending else None,
                    sent,
                )
            if kind_of(response) == "CommittedReceiptReplay":
                token = response.receipt_token
                if not isinstance(token, str) or not token:
                    raise Unavailable(self.name, "unreachable", "Truss gave no receipt token")
                return Done("replay", response.semantic, token, sent)
            if kind_of(response) == "SameTransactionReplay":
                # Truss answers this only when the stored receipt's writer is the current
                # transaction. A failed presentation leaves no receipt (the request_receipt insert
                # is inside the block that answers `failed`), and the adapter presents a request
                # twice in one transaction only after a failed presentation, so it cannot occur.
                raise Unavailable(
                    self.name, "unreachable", "Truss answered with a same-transaction replay"
                )
            raise Unavailable(self.name, "unreachable", "Truss answered with an unexpected state")
        if kind == "GroupUnavailable":
            raise unavailable_group(self.name, out.reason)
        if kind != "GroupFailed":
            raise Unavailable(self.name, "unreachable", "Truss answered with an unexpected result")
        failure = out.failure
        fk = kind_of(failure)
        if fk == "UnauthorizedPerson":
            raise Refused(self.name, "apply", "no_access")
        if fk == "RequestConflict":
            if conflict_to_caller:
                return failure
            raise Conflict("idempotency_key_reused", _HELD_FOR_OTHER_INPUT)
        if fk == "PreconditionFailed":
            return failure
        if group.static:  # conditions are checked before effects
            raise group.failed(())
        if fk == "GroupOperationFailure":
            raise self._operation_error(group, failure)
        if fk == "InvalidGroupInput":
            raise invalid_input(self.name, failure)
        raise Unavailable(self.name, "unreachable", f"truss {fk}")

    def _operation_error(self, group: _Group, failure: Any) -> ArrasError:
        err = operation_failure(self.name, failure, group.built, group.exists_now)
        if group.built.batch and not getattr(err, "__notes__", None):  # a conflict names its own
            op = attributed(failure, group.built, artifact(failure.inner_error).get("code"))
            if op is not None:
                err.add_note(f"item {op.item}")
        return err

    # -- the receipt

    def _again(self, principal: Principal, sent: Sent, *, rollback: bool) -> Done:
        """Present the same input and request in a new call."""
        with self.connections.write(principal, "apply") as call:
            call.rollback = rollback
            group = _Group(sent.built, [], {}, _assume_exists)
            got = self._classify(
                self._present(call, sent.inp, sent.req, sent.documents), group, sent
            )
            if not isinstance(got, Done):
                raise PreconditionFailed(merge_failures(got.failures, [], {}))
            if got.kind == "replay":
                call.rollback = True
            return got

    def _token(self, principal: Principal, sent: Sent) -> str:
        """The receipt token of a committed group: Truss answers the same input and request with the
        committed receipt. The write stands whatever this returns."""
        last: ArrasError | None = None
        for _ in range(2):
            try:
                done = self._again(principal, sent, rollback=True)
            except ArrasError as exc:
                last = exc
                continue
            if done.kind == "replay" and done.token:
                return done.token
        telemetry.annotate(
            committed=True
        )  # the write stands; the event must not read as one that never landed
        detail = "the write committed and its receipt could not be read"
        if isinstance(last, Unavailable):
            detail += f" ({last.reason})"
        raise Unavailable(self.name, "unreachable", detail)

    def _recover(self, principal: Principal, sent: Sent) -> Done:
        """A commit whose outcome is not known: Truss answers the same request with the original's
        results when it committed, and applies it when it did not (committed here, once more: a second
        unknown outcome is `Unavailable`)."""
        for _ in range(ATTEMPTS):
            try:
                return self._again(principal, sent, rollback=False)
            except Retry:
                continue
        raise Unavailable(self.name, "busy", "Truss asked for the write to be run again")
