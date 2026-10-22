# SPDX-License-Identifier: MIT OR Apache-2.0
"""A plan as a Truss group (CONTRACT-003, plan TR-07): pure planning, no Truss class named.

The planner turns the resolved `Plan` into the group's operations and preconditions. It reads what
exists through `Lookups` (the one call's lookups, cached) and builds Truss's own types through a
`Wire`, so it runs the same against a recording `Wire` in the always-on tests and the real one.

Where Truss and the memory adapter differ, the planner makes Truss behave as Arras promises:

- A create carries the key as a value (a plan's properties exclude it); a ref made earlier in the
  plan is named by an alias; a ref that does not exist is named by a ghost identity, so a missing
  target is reported by Truss in order (authority first, then conditions, then effects) rather than
  failing the whole group as invalid input.
- Truss bumps a version once per update operation and Arras once per touched ref per plan: updates
  of one ref are merged into one operation (into the create's values when the plan created the ref).
- Truss refuses to delete an object that has relationships and Arras removes them: the delete is
  preceded by a `delete_edge` for each edge it has, found by paging the object's relationships, and
  by one for each edge the plan itself made.
- Truss expresses a count as one inclusive range, so `!=` is `Unsupported`; a condition on an
  object or an edge that does not exist is evaluated here (an absent source has no relationships).
- `KeyAbsent` is sent for every `absent` precondition. A key a deleted object held fails it though
  an `absent` precondition holds there, so after a follow-up lookup that condition is left out and
  the group presented again. A keyed retry presents the full input, which Truss answers as a
  conflicting request (its probe runs before the conditions), so the applier leaves out the same
  conditions on the retry and both calls present the same input. `expected_version` is never sent:
  no plan holds a version, the lookup locks the row until the transaction ends, and a version taken
  at lookup changes the input a keyed retry rebuilds, which Truss answers as a conflicting request.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any, Protocol

from arras.actions import (
    Create,
    Delete,
    Link,
    Plan,
    Precondition,
    Ref,
    Unlink,
    Update,
)
from arras.adapters.truss.values import Domain, Ids, encode
from arras.adapters.truss.wire import Wire
from arras.errors import Failure, Invalid, Unsupported, Violation
from arras.model import EntityTypeInfo, ModuleInfo, RelationshipInfo

GHOST_ID = "9223372036854775807"  # a valid id (the largest) that no object holds
MAX_OPERATIONS = 1024  # Truss's bound on a group (1,025 is `resource`); Arras's is 1,000 effects
MAX_PRECONDITIONS = 3072  # Truss's bound on a group's conditions (1,024 operations, 3 each)
MAX_BATCH = 100  # Arras's bound on the items of a batch
REQUEST_BYTES = 1024  # Truss's bound on a request id
_NAMESPACE = uuid.UUID("5f0f3c3e-9a52-4f5e-9d8e-3c0f0f1e7a11")


class Lookups(Protocol):
    """What the planner reads of Truss in the call: references and the objects that exist."""

    def type_ref(self, record: str) -> Any: ...

    def relationship_ref(self, name: str) -> Any: ...

    def identity(self, ref: Ref) -> Any | None:
        """The identity of the object `ref` names, or None when no such object exists."""
        ...

    def edges(self, anchor: Any, relationship: str, direction: str) -> Sequence[Any]:
        """Every edge of `relationship` at `anchor` in `direction`."""
        ...


# -- request identity


def request_id(action: str, key: str | None) -> str:
    """The request id of an invocation: the idempotency key scoped by the action, shortened by a digest
    (never truncated) when it would pass Truss's bound; a fresh one for a keyless invocation.

    A key may hold any text, so what scopes it is what a key cannot reach: `action` is the part
    before the first `:`. A single apply scopes by `module.Action`, an atomic batch by
    `module.Action#atomic` and an independent batch's item by `module.Action#<index>`, and an
    action's name holds no `#`, so no key makes one scope's id another's. A digested id marks its
    scope `#sha256`, a scope no plain id has (a plain id's scope is the action, `#atomic` or `#<index>`),
    so no key makes a digested id either."""
    if key is None:
        return str(uuid.uuid4())
    text = f"{action}:{key}"
    if len(text.encode()) <= REQUEST_BYTES:
        return text
    return f"{action}#sha256:{hashlib.sha256(key.encode()).hexdigest()}"[:REQUEST_BYTES]


def derive_keys(plan: Plan, request: str) -> Plan:
    """The plan with each generated key replaced by one derived from the request id and the effect's
    place, everywhere the key appears. The resolver made them at random, so a retry under the same
    idempotency key would otherwise present Truss different input."""
    renamed: dict[Ref, Ref] = {}
    for i, effect in enumerate(plan.effects):
        if isinstance(effect, Create) and effect.generated:
            key = str(uuid.uuid5(_NAMESPACE, f"{request}#{i}"))
            renamed[effect.ref] = Ref(effect.ref.type, key, generated=True)
    if not renamed:
        return plan

    def ref(r: Ref) -> Ref:
        return renamed.get(r, r)

    def args(a: Mapping[str, Any]) -> dict[str, Any]:
        out = {k: ref(v) if isinstance(v, Ref) else v for k, v in a.items()}
        if "type" in out and "key" in out:
            moved = renamed.get(Ref(str(out["type"]), str(out["key"])))
            if moved is not None:
                out["key"] = moved.key
        return out

    effects: list[Any] = []
    for e in plan.effects:
        if isinstance(e, Create):
            effects.append(replace(e, ref=ref(e.ref)))
        elif isinstance(e, Update | Delete):
            effects.append(replace(e, ref=ref(e.ref)))
        else:
            effects.append(replace(e, source=ref(e.source), target=ref(e.target)))
    pres = tuple(replace(p, args=args(p.args)) for p in plan.preconditions)
    return replace(plan, effects=tuple(effects), preconditions=pres)


# -- operations


@dataclass
class Op:
    """One group operation, still open to merging updates, with what a failure needs to be told."""

    kind: str  # create_object | update_object | delete_object | create_edge | delete_edge
    effects: list[int] = field(default_factory=list[int])
    refs: tuple[Ref, ...] = ()
    missing: tuple[Ref, ...] = ()  # the refs named by a ghost
    pin: str = ""
    values: dict[str, Any] = field(default_factory=dict[str, Any])
    unset: list[str] = field(default_factory=list[str])
    target: Any = None
    source: Any = None
    alias: str = ""
    relationship: str = ""
    cascade: bool = False  # made by a delete, counted nowhere
    ghost: bool = False  # names an edge that is not there (an unlink of a missing relationship)
    item: int = 0  # the batch item whose effect made it


@dataclass
class Built:
    ops: list[Op]
    effect_op: dict[int, Op]
    touched: dict[Ref, Op]  # first touch order; the op that last touched the ref
    batch: bool = False  # one item of an atomic batch: `ops` is the whole group's


def canonical(module: ModuleInfo, name: str) -> tuple[RelationshipInfo, bool] | None:
    for r in module.relationships:
        if name == r.name:
            return r, False
        if name == r.inverse:
            return r, True
    return None


def _local(ref: Ref) -> str:
    return ref.type.split(".", 1)[1]


@dataclass
class _Before:
    """What the items before one item left, as far as a condition of that item can tell: the memory
    adapter judges item k against this state, Truss against the state before the group."""

    made: dict[Ref, dict[str, Any]] = field(default_factory=dict[Ref, dict[str, Any]])
    deleted: set[Ref] = field(default_factory=set[Ref])
    written: dict[Ref, dict[str, Any]] = field(  # pre-existing objects: what was set (None: unset)
        default_factory=dict[Ref, dict[str, Any]]
    )
    deleted_types: set[str] = field(default_factory=set[str])
    added: set[tuple[str, Ref, Ref]] = field(default_factory=set[tuple[str, Ref, Ref]])
    removed: set[tuple[str, Ref, Ref]] = field(default_factory=set[tuple[str, Ref, Ref]])


class Planner:
    def __init__(
        self,
        wire: Wire,
        module: ModuleInfo,
        ids: Ids,
        lookups: Lookups,
        plan: Plan,
        *,
        items: Sequence[Plan] | None = None,
    ) -> None:
        """`items` are the plans of an atomic batch (one group, `plan` is the first); a lone plan
        is a group of its own. A batch's conditions are sent as `<item>:<id>`, since Truss takes one
        id once in a group, and told back under the caller's own id."""
        self.wire = wire
        self.module = module
        self.ids = ids
        self.lookups = lookups
        self.plan = plan
        self.batch = items is not None
        self.items: Sequence[Plan] = items if items is not None else (plan,)
        self.item = 0
        self.builts: list[Built] = []
        self.ops: list[Op] = []
        self.made: dict[Ref, int] = {}  # the first item that creates each ref
        self.pres: list[tuple[str, int, Precondition]] = [
            (f"{n}:{p.id}" if self.batch else p.id, n, p)
            for n, item in enumerate(self.items)
            for p in item.preconditions
        ]
        self.types = {t.name: t for t in module.entity_types}

    # -- pieces

    def _etype(self, ref: Ref) -> EntityTypeInfo:
        t = self.types.get(ref.type)
        if t is None:
            raise Invalid([Violation("effects", "unknown_type", f"no type {ref.type}")])
        return t

    def _value(self, ref: Ref, name: str, value: Any) -> Any:
        prop = self._etype(ref).property(name)
        if prop is not None and (not prop.scalar or prop.cardinality == "many"):
            raise Unsupported(
                "a structured or repeated value", ["scalar values Truss 0.0.45 groups take"]
            )
        family = prop.type if prop is not None else ""
        domain: Domain | None = self.ids.domains.get((_local(ref), name))
        return encode(self.wire, family, domain, name, value)

    def _object(self, ref: Ref) -> tuple[Any, bool]:
        """The identity named for `ref` and whether it is a ghost."""
        found = self.lookups.identity(ref)
        if found is not None:
            return found, False
        template = self.lookups.type_ref(_local(ref))
        return self.wire.ghost(template, GHOST_ID), True

    # -- operations

    def operations(self) -> Built:
        """The group's operations, one effect at a time. For a batch the group's operations are in
        item order and `builts` holds each item's view of them (the first is returned)."""
        self.ops: list[Op] = []
        self.effect_op: dict[int, Op] = {}
        self.touched: dict[Ref, Op] = {}
        self.created: dict[Ref, Op] = {}  # made by the plan and still there
        self.updated: dict[Ref, Op] = {}
        self.new_edges: dict[tuple[str, Ref, Ref], Op] = {}  # edges the plan made and not removed
        self.removed: set[str] = set()  # ids of existing edges the plan removes
        self.aliases = 0
        self.builts = []
        for n, item in enumerate(self.items):
            self.item = n
            self.effect_op = {}
            self.touched = {}
            for i, e in enumerate(item.effects):
                if isinstance(e, Create):
                    op = self._create(i, e)
                elif isinstance(e, Update):
                    op = self._update(i, e)
                elif isinstance(e, Delete):
                    op = self._delete(i, e)
                elif isinstance(e, Link):
                    op = self._link(i, e)
                else:
                    op = self._unlink(i, e)
                self.effect_op[i] = op
            self.builts.append(Built(self.ops, self.effect_op, self.touched, self.batch))
        return self.builts[0]

    def _alias(self) -> str:
        self.aliases += 1
        return f"e{self.aliases}"

    def _reference(self, ref: Ref) -> tuple[Any, bool]:
        """How an operation names `ref`: by alias when the plan made it, else by identity (a ghost
        when no object holds the key)."""
        if ref in self.created:
            return self.wire.alias_ref(self.created[ref].alias), False
        ident, ghost = self._object(ref)
        return self.wire.stored(ident), ghost

    def _add(self, op: Op) -> Op:
        op.item = self.item
        self.ops.append(op)
        return op

    def _create(self, i: int, e: Create) -> Op:
        t = self._etype(e.ref)
        values = {t.key: self.wire.text("string", e.ref.key)}
        for k, v in e.properties.items():
            values[k] = self._value(e.ref, k, v)
        pin = self.lookups.type_ref(t.local_name).definition_pin
        op = self._add(
            Op("create_object", [i], (e.ref,), pin=pin, values=values, alias=self._alias())
        )
        self.created[e.ref] = op
        self.made.setdefault(e.ref, self.item)
        self.touched[e.ref] = op
        return op

    def _update(self, i: int, e: Update) -> Op:
        values = {k: self._value(e.ref, k, v) for k, v in e.set.items()}
        op = self.created.get(e.ref) or self.updated.get(e.ref)
        if op is not None and op.item != self.item:
            op = None  # one version per item: an earlier item's operation is not merged into
        if op is None:
            target, ghost = self._reference(e.ref)
            missing = (e.ref,) if ghost else ()
            op = self._add(Op("update_object", [i], (e.ref,), missing=missing, target=target))
            self.updated[e.ref] = op
        else:
            op.effects.append(i)
        _merge(op, values, e.unset)
        self.touched[e.ref] = op
        return op

    def _delete(self, i: int, e: Delete) -> Op:
        target, ghost = self._reference(e.ref)
        if not ghost and e.ref not in self.created:
            for edge in self._incident(self._object(e.ref)[0], e.ref):
                if edge.identity.id not in self.removed:
                    self.removed.add(edge.identity.id)
                    self._add(
                        Op(
                            "delete_edge",
                            refs=(e.ref,),
                            target=self.wire.stored(edge.identity),
                            cascade=True,
                        )
                    )
        for triple in [k for k in self.new_edges if e.ref in (k[1], k[2])]:
            made = self.new_edges.pop(triple)
            self._add(
                Op(
                    "delete_edge",
                    refs=(e.ref,),
                    target=self.wire.alias_ref(made.alias),
                    cascade=True,
                )
            )
        missing = (e.ref,) if ghost else ()
        op = self._add(Op("delete_object", [i], (e.ref,), missing=missing, target=target))
        self.created.pop(e.ref, None)
        self.updated.pop(e.ref, None)
        self.touched[e.ref] = op
        return op

    def _link(self, i: int, e: Link) -> Op:
        source, target = self._reference(e.source), self._reference(e.target)
        missing = tuple(r for r, end in ((e.source, source), (e.target, target)) if end[1])
        op = self._add(
            Op(
                "create_edge",
                [i],
                (e.source, e.target),
                missing=missing,
                pin=self.lookups.relationship_ref(e.relationship).definition_pin,
                source=source[0],
                target=target[0],
                alias=self._alias(),
                relationship=e.relationship,
            )
        )
        self.new_edges[(e.relationship, e.source, e.target)] = op
        return op

    def _unlink(self, i: int, e: Unlink) -> Op:
        made = self.new_edges.pop((e.relationship, e.source, e.target), None)
        ghost = False
        if made is not None:
            target = self.wire.alias_ref(made.alias)
        else:
            target, ghost = self._existing_edge(e)
        return self._add(
            Op(
                "delete_edge",
                [i],
                (e.source, e.target),
                target=target,
                relationship=e.relationship,
                ghost=ghost,
            )
        )

    def _incident(self, identity: Any, ref: Ref) -> list[Any]:
        """Every edge of every relationship the type takes part in, that touches the object."""
        out: dict[str, Any] = {}
        name = ref.type
        for rel in self.module.relationships:
            for direction, ends in (("outgoing", rel.source), ("incoming", rel.target)):
                if name in ends:
                    for edge in self.lookups.edges(identity, rel.name, direction):
                        out.setdefault(edge.identity.id, edge)
        return list(out.values())

    def _existing_edge(self, e: Unlink) -> tuple[Any, bool]:
        """The reference to the existing edge an unlink removes and whether it is a ghost; an edge
        that is not there is named by a ghost edge, so Truss reports it as `not_found`."""
        wire = self.wire
        rel = self.lookups.relationship_ref(e.relationship)
        if e.source not in self.created and e.target not in self.created:
            source = self.lookups.identity(e.source)
            target = self.lookups.identity(e.target)
            if source is not None and target is not None:
                for edge in self.lookups.edges(source, e.relationship, "outgoing"):
                    if edge.target.id == target.id and edge.identity.id not in self.removed:
                        self.removed.add(edge.identity.id)
                        return wire.stored(edge.identity), False
        return wire.stored(wire.ghost_edge(rel, GHOST_ID)), True

    # -- preconditions

    def preconditions(self, dropped: frozenset[str]) -> tuple[list[Any], list[tuple[int, Failure]]]:
        """The group's conditions, in plan order, without the `absent` ones named in `dropped`, and
        the failures decided here: (plan index, failure)."""
        sent: list[Any] = []
        static: list[tuple[int, Failure]] = []
        for i, (cid, item, p) in enumerate(self.pres):
            if cid in dropped:
                continue
            built = self._condition(cid, item, p)
            if built is None:
                continue
            if isinstance(built, Failure):
                static.append((i, built))
            else:
                sent.append(built)
        return sent, static

    def _before(self, item: int) -> _Before:
        """The state the items before `item` leave, from their effects and operations."""
        b = _Before()
        for plan in self.items[:item]:
            for e in plan.effects:
                if isinstance(e, Create):
                    b.made[e.ref] = dict(e.properties)
                    b.deleted.discard(e.ref)
                elif isinstance(e, Update):
                    props = b.made[e.ref] if e.ref in b.made else b.written.setdefault(e.ref, {})
                    props.update(e.set)
                    for name in e.unset:  # as `_merge` does: an unset follows the sets
                        if e.ref in b.made:
                            props.pop(name, None)
                        else:
                            props[name] = None
                elif isinstance(e, Delete):
                    b.made.pop(e.ref, None)
                    b.written.pop(e.ref, None)
                    b.deleted.add(e.ref)
                    b.deleted_types.add(e.ref.type)
        for op in self.ops:
            if op.item >= item or not op.relationship or op.cascade:
                continue
            found = canonical(self.module, op.relationship)
            if found is None or len(op.refs) != 2:
                continue
            rel, inverse = found
            a, c = op.refs
            triple = (rel.name, c, a) if inverse else (rel.name, a, c)
            if op.kind == "create_edge":
                if triple in b.removed:
                    b.removed.discard(triple)
                else:
                    b.added.add(triple)
            elif op.kind == "delete_edge":
                if triple in b.added:
                    b.added.discard(triple)
                else:
                    b.removed.add(triple)
        return b

    def _condition(self, cid: str, item: int, p: Precondition) -> Any | Failure | None:
        """The condition `p` of `item`, sent under `cid`. Truss judges every condition against the
        state before the group, the memory adapter against the state the earlier items left, so a
        condition on what an earlier item touched is never sent unchanged: it is decided here from the
        planned operations, or refused as `Unsupported` when it cannot be."""
        wire, a = self.wire, p.args
        before = self._before(item)
        if p.op == "exists":
            ref: Ref = a["ref"]
            if ref in before.made:
                return None
            if ref in before.deleted:
                return Failure(p.id, p.reason)
            ident, _ = self._object(ref)
            return wire.object_exists(cid, p.reason, ident)
        if p.op == "absent":
            key = Ref(str(a["type"]), str(a["key"]))
            if key in before.made:
                return Failure(p.id, p.reason)
            if key in before.deleted:
                return None  # the entity is gone, though Truss's key check fails on the retired key
            local = key.type.split(".", 1)[1]
            return wire.key_absent(
                cid,
                p.reason,
                self.lookups.type_ref(local).definition_pin,
                self._key_id(local),
                wire.text("string", str(a["key"])),
            )
        if p.op == "property_equals":
            ref = a["ref"]
            prop: str = a["property"]
            if ref in before.deleted:
                return Failure(p.id, p.reason)
            props = before.made.get(ref)
            if props is None and prop in before.written.get(ref, {}):
                props = before.written[ref]
            if props is not None:  # the raw values, as the memory adapter compares them
                return None if props.get(prop) == a["value"] else Failure(p.id, p.reason)
            ident, _ = self._object(ref)
            return wire.property_equals(
                cid, p.reason, ident, prop, self._value(ref, prop, a["value"])
            )
        return self._relation(cid, item, before, p)

    def _key_id(self, record: str) -> str:
        key = self.ids.keys.get(record)
        if key is None:
            raise Unsupported(f"{record} has no key Truss can look up", ["a record with a key"])
        return key

    def _relation(
        self, cid: str, item: int, before: _Before, p: Precondition
    ) -> Any | Failure | None:
        """`no_relationship` and `count`, from the point of view of the forward relationship. A
        missing object, or one of a type the relationship does not join, has no relationships. The
        edges the earlier items added and removed shift what Truss would count in the state before
        the group; a delete of an object the relationship joins (it cascades) cannot be tracked."""
        wire, a = self.wire, p.args
        found = canonical(self.module, str(a["relationship"]))
        if found is None:
            raise Invalid(
                [
                    Violation(
                        "preconditions",
                        "unknown_type",
                        f"{a['relationship']} is not a relationship",
                    )
                ]
            )
        rel, inverse = found
        if before.deleted_types & {*rel.source, *rel.target}:
            raise Unsupported(
                "a condition after a cascading delete in the same batch",
                ["conditions before the delete, or a batch without it"],
            )
        pin = self.lookups.relationship_ref(rel.name).definition_pin
        anchor: Ref = a["source"]
        target: Ref | None = a.get("target")
        direction = "incoming" if inverse else "outgoing"
        ends = rel.target if inverse else rel.source
        if p.op == "no_relationship" and target is not None:
            src, tgt = (target, anchor) if inverse else (anchor, target)
            if (rel.name, src, tgt) in before.added:
                return Failure(p.id, p.reason)
            if (rel.name, src, tgt) in before.removed:
                return None
            s, t = self.lookups.identity(src), self.lookups.identity(tgt)
            if s is None or t is None or src.type not in rel.source or tgt.type not in rel.target:
                return None  # no such edge can exist
            return wire.relationship_absent(cid, p.reason, pin, s, t)
        low, high = _range(str(a["cmp"]), int(a["n"])) if p.op == "count" else (0, 0)
        if high is not None and high < low:
            return Failure(p.id, p.reason)  # no count satisfies it
        end = 2 if inverse else 1  # the anchor's end of a (relationship, source, target) triple
        added = sum(1 for t in before.added if t[0] == rel.name and t[end] == anchor)
        removed = sum(1 for t in before.removed if t[0] == rel.name and t[end] == anchor)
        ident = self.lookups.identity(anchor)
        if anchor in before.made or ident is None or anchor.type not in ends:
            # there is no state before the group to shift: what the earlier items left is the count
            post = added - removed if anchor in before.made else 0
            holds = low <= post and (high is None or post <= high)
            return None if holds else Failure(p.id, p.reason)
        shift = removed - added  # the count before the group is the count now plus this
        low, high = max(0, low + shift), None if high is None else high + shift
        if high is not None and high < 0:
            return Failure(p.id, p.reason)
        return wire.relationship_count(cid, p.reason, pin, ident, direction, low, high)


def _merge(op: Op, values: Mapping[str, Any], unset: Sequence[str]) -> None:
    """Apply an update to an open operation: the later write of a property wins, and a property is
    never both set and unset (Truss refuses that as invalid input)."""
    for name, value in values.items():
        op.values[name] = value
        if name in op.unset:
            op.unset.remove(name)
    for name in unset:
        op.values.pop(name, None)
        if name not in op.unset and op.kind == "update_object":
            op.unset.append(name)


def _range(cmp: str, n: int) -> tuple[int, int | None]:
    """The inclusive range a comparison states; `!=` is not a range Truss states."""
    match cmp:
        case "=":
            return n, n
        case ">":
            return n + 1, None
        case ">=":
            return n, None
        case "<":
            return 0, n - 1
        case "<=":
            return 0, n
        case _:
            pass
    raise Unsupported(f"a count compared with {cmp}", ["=", "<", "<=", ">", ">="])


def check_bounds(plan: Plan) -> None:
    """`Unsupported` for a plan Truss's bounds cannot hold, before any call."""
    if len(plan.effects) > MAX_OPERATIONS:
        raise Unsupported(
            f"a plan of {len(plan.effects)} effects",
            [f"at most {MAX_OPERATIONS} effects in one Truss group"],
        )
    if len(plan.preconditions) > MAX_PRECONDITIONS:
        raise Unsupported(
            f"{len(plan.preconditions)} preconditions",
            [f"at most {MAX_PRECONDITIONS} preconditions in one Truss group"],
        )
    for p in plan.preconditions:
        if p.op == "count" and p.args.get("cmp") not in ("=", "<", "<=", ">", ">="):
            raise Unsupported(
                f"a count compared with {p.args.get('cmp')}", ["=", "<", "<=", ">", ">="]
            )
        if p.op == "count" and not isinstance(p.args.get("n"), int | Decimal):
            raise Invalid([Violation("preconditions", "type", "a count compares with a number")])


def materialize(wire: Wire, op: Op) -> Any:
    """The group operation `op` has become, once every later update has been merged into it."""
    if op.kind == "create_object":
        values = tuple(wire.authored(name, value) for name, value in op.values.items())
        return wire.create_object(op.pin, values, op.alias)
    if op.kind == "update_object":
        values = tuple(wire.authored(name, value) for name, value in op.values.items())
        return wire.update_object(op.target, values, tuple(op.unset))
    if op.kind == "create_edge":
        return wire.create_edge(op.pin, op.source, op.target, op.alias)
    return wire.delete(op.kind, op.target)
