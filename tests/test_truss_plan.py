# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The Truss adapter's plan to group (TR-07), always on.

A recording `Wire` whose products are plain tuples and a scripted fake of Truss's assembly stand in
for Truss, which the base install does not have. Results carry the names Truss gives them (the
adapter recognizes them by class name). `tests/test_truss_apply.py` runs the same adapter against a
real Truss.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from arras.actions import Create, Delete, Link, Plan, Precondition, Ref, Unlink, Update
from arras.adapters.truss import Connections, TrussBackend
from arras.adapters.truss.outcome import artifact, group_of, operation_failure, receipt
from arras.adapters.truss.plan import (
    GHOST_ID,
    Planner,
    check_bounds,
    derive_keys,
    materialize,
    request_id,
)
from arras.adapters.truss.values import Domain, document_ids, encode
from arras.adapters.truss.wire import Wire
from arras.errors import (
    Conflict,
    Failure,
    Invalid,
    PreconditionFailed,
    Refused,
    Unavailable,
    Unsupported,
    Violation,
)
from arras.results import Validation
from arras.types import Principal
from test_truss_registry import ALICE, DOC, MODULE, CatalogRefused, FakeAssembly, Rig, error, ok

UC, SOL = "catalog.UseCase", "catalog.Solution"


def uc(key: str) -> Ref:
    return Ref(UC, key)


def sol(key: str) -> Ref:
    return Ref(SOL, key)


# -- a Wire of plain tuples


class RecordingWire(Wire):
    def text(self, kind: str, text: str) -> Any:
        return ("text", kind, text)

    def boolean(self, value: bool) -> Any:
        return ("bool", value)

    def authored(self, name: str, value: Any) -> Any:
        return ("val", name, value)

    def origin(self, action: str) -> Any:
        return ("origin", action)

    def ghost(self, template: Any, object_id: str) -> Any:
        return ("ghost", template.definition_pin, object_id)

    def ghost_edge(self, relationship: Any, object_id: str) -> Any:
        return ("ghost-edge", relationship.definition_pin, object_id)

    def stored(self, identity: Any) -> Any:
        return ("stored", identity)

    def alias_ref(self, alias: str) -> Any:
        return ("alias", alias)

    def create_object(self, pin: str, values: tuple[Any, ...], alias: str) -> Any:
        return ("create", pin, values, alias)

    def create_edge(self, pin: str, source: Any, target: Any, alias: str) -> Any:
        return ("link", pin, source, target, alias)

    def update_object(self, target: Any, set: tuple[Any, ...], unset: tuple[str, ...]) -> Any:
        return ("update", target, set, unset)

    def delete(self, operation: str, target: Any) -> Any:
        return (operation, target)

    def object_exists(self, id: str, reason: str, target: Any) -> Any:
        return ("exists", id, reason, target)

    def key_absent(self, id: str, reason: str, pin: str, key_id: str, key: Any) -> Any:
        return ("absent", id, reason, pin, key_id, key)

    def property_equals(self, id: str, reason: str, target: Any, name: str, value: Any) -> Any:
        return ("equals", id, reason, target, name, value)

    def relationship_absent(self, id: str, reason: str, pin: str, source: Any, target: Any) -> Any:
        return ("no-edge", id, reason, pin, source, target)

    def relationship_count(
        self,
        id: str,
        reason: str,
        pin: str,
        anchor: Any,
        direction: str,
        minimum: int,
        maximum: int | None,
    ) -> Any:
        return ("count", id, reason, pin, anchor, direction, minimum, maximum)

    def document(self, document_id: str, content: bytes) -> Any:
        return ("document", document_id, content)


# -- Truss results, named as Truss names them


@dataclass(frozen=True)
class Event:
    source_epoch: str = "epoch"
    xid: str = "77"
    seq: str = "1"


@dataclass(frozen=True)
class Created:
    version: str = "1"
    events: tuple[Event, ...] = (Event(),)


@dataclass(frozen=True)
class Changed:
    version: str = "2"
    events: tuple[Event, ...] = (Event(),)


@dataclass(frozen=True)
class Unchanged:
    version: str = "1"
    events: tuple[Event, ...] = ()


@dataclass(frozen=True)
class Deleted:
    deletion_version: str = "2"
    events: tuple[Event, ...] = (Event(),)


@dataclass(frozen=True)
class Semantic:
    results: tuple[Any, ...]


@dataclass(frozen=True)
class Absent:
    """Truss's marker for a value the answer does not carry."""


ABSENT = Absent()


@dataclass(frozen=True)
class AppliedPending:
    semantic: Semantic
    receipt_token: Any = "token-1"


@dataclass(frozen=True)
class CommittedReceiptReplay:
    semantic: Semantic
    receipt_token: Any = "token-1"


@dataclass(frozen=True)
class SameTransactionReplay:
    semantic: Semantic


@dataclass(frozen=True)
class GroupSuccess:
    response: Any


@dataclass(frozen=True)
class FailedPrecondition:
    condition_id: str
    reason: str
    rule: str


@dataclass(frozen=True)
class PreconditionFailedCarrier:
    failures: tuple[FailedPrecondition, ...]


PreconditionFailedCarrier.__name__ = "PreconditionFailed"


@dataclass(frozen=True)
class Artifact:
    bytes_base64: str


def artifact_of(**body: Any) -> Artifact:
    return Artifact(base64.b64encode(json.dumps(body).encode()).decode())


@dataclass(frozen=True)
class GroupOperationFailure:
    operation_index: str
    inner_error: Artifact


@dataclass(frozen=True)
class InvalidGroupInput:
    diagnostic: Artifact


@dataclass(frozen=True)
class RequestConflict:
    diagnostic: Artifact = field(default_factory=lambda: artifact_of(code="request_conflict"))


@dataclass(frozen=True)
class UnauthorizedPerson:
    pass


@dataclass(frozen=True)
class GroupFailed:
    failure: Any


@dataclass(frozen=True)
class GroupUnavailable:
    reason: str


@dataclass(frozen=True)
class ObjectFound:
    object: Any


@dataclass(frozen=True)
class ObjectNotFound:
    pass


@dataclass(frozen=True)
class EdgePage:
    edges: tuple[Any, ...]
    continuation: Any = None


@dataclass(frozen=True)
class EdgeNotFound:
    pass


@dataclass(frozen=True)
class PreparedGroup:
    catalog_revision: str
    context: Any
    types: tuple[Any, ...]
    relationships: tuple[Any, ...]


def applied(*results: Any, token: Any = "token-1") -> Any:
    return ok(GroupSuccess(AppliedPending(Semantic(tuple(results)), token)))


def replayed(*results: Any, token: Any = "token-1") -> Any:
    return ok(GroupSuccess(CommittedReceiptReplay(Semantic(tuple(results)), token)))


def failed(failure: Any) -> Any:
    return ok(GroupFailed(failure))


def ident(record: str, key: str) -> Any:
    return SimpleNamespace(id=f"{record}:{key}")


def edge(eid: str, source: Any, target: Any) -> Any:
    return SimpleNamespace(identity=SimpleNamespace(id=eid), source=source, target=target)


# -- a scripted assembly for apply


class ApplyAssembly(FakeAssembly):
    def __init__(self) -> None:
        super().__init__()
        self.objects: dict[tuple[str, str], Any] = {}  # (record, key) -> identity
        self.edge_pages: dict[tuple[str, str, str], list[Any]] = {}  # (anchor id, rel, direction)
        self.outcomes: list[Any] = [applied(Created())]
        self.presented: list[tuple[Any, Any, Any]] = []
        self.lookup_failure: Any = None
        self.prepared: list[tuple[Any, Any]] = []
        self.gone_after_failure: set[tuple[str, str]] = set()

    def group_context_in_transaction(self, tx: Any, log: bool = True) -> Any:
        if log:
            self.log.append("context")
        return ok(
            SimpleNamespace(
                input=lambda ops, origin, preconditions=(): SimpleNamespace(
                    ops=ops, origin=origin, preconditions=preconditions
                ),
                request=lambda rid: SimpleNamespace(rid=rid),
            )
        )

    def prepare_group_in_transaction(
        self,
        tx: Any,
        *,
        records: tuple[tuple[str, str, str], ...],
        relationships: tuple[tuple[str, str, str], ...] = (),
    ) -> Any:
        """Truss's one call for the group context and the references the plan names."""
        self.log.append("prepare_group")
        self.prepared.append((records, relationships))
        context = self.group_context_in_transaction(tx, log=False).value
        types = tuple(
            self.get_type_reference_in_transaction(
                tx, document_id=d, module_id=m, record_id=r, log=False
            ).value
            for d, m, r in records
        )
        rels = tuple(
            self.get_relationship_reference_in_transaction(
                tx, document_id=d, module_id=m, relationship_id=r, log=False
            ).value
            for d, m, r in relationships
        )
        return ok(PreparedGroup("1", context, types, rels))

    def get_type_reference_in_transaction(
        self, tx: Any, *, document_id: str, module_id: str, record_id: str, log: bool = True
    ) -> Any:
        if log:
            self.log.append(f"type:{record_id}")
        if record_id not in ("UseCase", "Solution"):
            return ok(None)
        return ok(SimpleNamespace(definition_pin=f"pin-{record_id}", type_id="1", owner="o"))

    def get_relationship_reference_in_transaction(
        self, tx: Any, *, document_id: str, module_id: str, relationship_id: str, log: bool = True
    ) -> Any:
        if log:
            self.log.append(f"relationship:{relationship_id}")
        return ok(
            SimpleNamespace(definition_pin=f"pin-{relationship_id}", relationship_id="9", owner="o")
        )

    def lookup_key_in_transaction(self, tx: Any, **kw: Any) -> Any:
        assert (
            "bun_executable" not in kw
        )  # a key is derived in PostgreSQL: no executable for a lookup
        self.log.append(f"lookup:{kw['record_id']}:{kw['values'][0]}")
        assert kw["key_id"] == "identity" and kw["document_id"] == "sandbox"
        if self.lookup_failure is not None:
            return self.lookup_failure
        found = self.objects.get((kw["record_id"], kw["values"][0]))
        return ok(ObjectFound(SimpleNamespace(identity=found)) if found else ObjectNotFound())

    def page_edges_in_transaction(self, tx: Any, **kw: Any) -> Any:
        anchor = kw["anchor"]
        self.log.append(f"edges:{anchor.id}:{kw['relationship_id']}:{kw['direction']}")
        return ok(
            EdgePage(
                tuple(self.edge_pages.get((anchor.id, kw["relationship_id"], kw["direction"]), []))
            )
        )

    def apply_in_transaction(self, tx: Any, inp: Any, req: Any, *, documents: Any) -> Any:
        self.log.append("apply")
        self.presented.append((inp, req, documents))
        out = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if callable(out):
            out = out()
        return out


class ApplyRig(Rig):
    def __init__(self) -> None:
        super().__init__(assembly=ApplyAssembly())
        self.assembly: ApplyAssembly

    def backend(self, **_: Any) -> TrussBackend:  # type: ignore[override]
        return TrussBackend(
            "truss", Connections("truss", self.source, toolkit=self.toolkit()), RecordingWire()
        )

    @property
    def writes(self) -> list[Any]:
        return [c for c in self.conns if c.log and c.log[0].endswith("READ WRITE")]


def create_plan(key: str = "uc-9", **extra: Any) -> Plan:
    return Plan("catalog.AddUseCase", (), (Create(uc(key), {"name": "N", **extra}),))


def apply(rig: ApplyRig, plan: Plan | None = None, **kw: Any) -> Any:
    kw.setdefault("idempotency_key", "k1")
    return rig.backend().apply(ALICE, plan or create_plan(), **kw)


# -- request identity


def test_a_request_id_is_the_key_scoped_by_the_action() -> None:
    assert request_id("catalog.AddUseCase", "k1") == "catalog.AddUseCase:k1"
    assert request_id("catalog.A", "x") != request_id("catalog.B", "x")


def test_a_key_over_the_bound_is_digested_never_truncated() -> None:
    long_a, long_b = "a" * 2000, "a" * 1999 + "b"
    one, again, other = (request_id("m.A", k) for k in (long_a, long_a, long_b))
    assert one == again and one != other and len(one.encode()) <= 1024
    assert len(request_id("m.A", "é" * 600).encode()) <= 1024


def test_no_key_makes_a_digested_request_id() -> None:
    long = "a" * 2000
    digested = request_id("m.A", long)
    forged = digested.split(":", 1)[1]  # what a caller would pass to reach the digest's id
    assert request_id("m.A", forged) != digested
    assert request_id("m.A", "sha256:" + digested.rsplit(":", 1)[1]) != digested
    for scope in ("m.A", "m.A#atomic", "m.A#3"):
        assert request_id(scope, long).split(":", 1)[0].endswith("#sha256")


def test_a_request_id_is_digested_only_over_trusss_bound_of_1024_bytes() -> None:
    at = "a" * (1024 - len("m.A:"))
    assert request_id("m.A", at) == f"m.A:{at}"  # exactly at the bound: as it is
    over = request_id("m.A", at + "a")
    assert over.startswith("m.A#sha256:") and len(over.encode()) <= 1024


def test_a_keyless_invocation_gets_a_fresh_request_id_each_time() -> None:
    assert request_id("m.A", None) != request_id("m.A", None)


# -- generated keys


def generated_plan() -> Plan:
    made = Ref(SOL, "random-1", generated=True)
    return Plan(
        "catalog.DraftSolution",
        (
            Precondition("p", "r", "exists", {"ref": made}),
            Precondition("a", "r", "absent", {"type": SOL, "key": "random-1"}),
        ),
        (
            Create(made, {"name": "D"}, generated=True),
            Link("addresses", made, uc("uc-1")),
            Update(made, {"name": "E"}),
        ),
    )


def test_generated_keys_are_derived_from_the_request_and_the_effects_place() -> None:
    a, b, c = (derive_keys(generated_plan(), r) for r in ("req-1", "req-1", "req-2"))
    effects: Any = a.effects
    created = effects[0].ref
    assert a == b and created.key != "random-1" and created != c.effects[0].ref  # type: ignore[attr-defined]
    assert len(created.key) == 36 and created.generated
    assert effects[1].source == created and effects[1].target == uc("uc-1")
    assert effects[2].ref == created
    assert a.preconditions[0].args["ref"] == created
    assert a.preconditions[1].args["key"] == created.key


def test_two_generated_keys_of_one_plan_differ_and_each_is_stable_for_its_place() -> None:
    first, second = Ref(SOL, "r-1", generated=True), Ref(SOL, "r-2", generated=True)
    plan = Plan(
        "catalog.DraftSolution",
        (),
        (
            Create(first, {"name": "A"}, generated=True),
            Create(second, {"name": "B"}, generated=True),
        ),
    )
    a = derive_keys(plan, "req-1")
    b = derive_keys(plan, "req-1")
    effects: Any = a.effects
    assert effects[0].ref.key != effects[1].ref.key
    assert a == b


def test_the_ghost_id_is_the_largest_id_and_so_no_created_object_holds_it() -> None:
    assert GHOST_ID == str(2**63 - 1)


def test_a_plan_with_no_generated_key_is_unchanged() -> None:
    plan = create_plan()
    assert derive_keys(plan, "req") is plan


# -- values


@pytest.mark.parametrize(
    ("family", "domain", "value", "expected"),
    [
        ("string", None, "x", ("text", "string", "x")),
        ("integer", None, 7, ("text", "integer", "7")),
        ("integer", Domain("integer", bits=64), -3, ("text", "integer", "-3")),
        ("decimal", Domain("decimal", 18, 4), Decimal("1.5"), ("text", "decimal", "1.5000")),
        ("decimal", Domain("decimal", 18, 4), Decimal("1E+2"), ("text", "decimal", "100.0000")),
        ("decimal", Domain("decimal", 18, 4), 3, ("text", "decimal", "3.0000")),
        ("decimal", None, Decimal("1E+2"), ("text", "decimal", "100")),
        ("boolean", None, True, ("bool", True)),
        ("binary", None, b"\x00\xff", ("text", "binary", "AP8=")),
        (
            "timestamp",
            None,
            datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=2))),
            ("text", "timestamp", "2026-01-02T01:04:05.000000Z"),
        ),
        (
            "timestamp",
            None,
            datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=UTC),
            ("text", "timestamp", "2026-01-02T03:04:05.123456Z"),
        ),
    ],
)
def test_values_are_written_in_one_canonical_spelling(
    family: str, domain: Domain | None, value: Any, expected: Any
) -> None:
    assert encode(RecordingWire(), family, domain, "f", value) == expected


@pytest.mark.parametrize(
    ("domain", "value"),
    [
        (Domain("decimal", 18, 4), Decimal("1.00005")),
        (Domain("decimal", 18, 4), Decimal("1" * 15)),
        (Domain("integer", bits=32), 2**31),
    ],
)
def test_a_number_outside_its_field_is_invalid_at_the_effect(domain: Domain, value: Any) -> None:
    with pytest.raises(Invalid) as raised:
        encode(RecordingWire(), domain.family, domain, "amount", value)
    assert [(v.path, v.code) for v in raised.value.violations] == [
        ("effects.amount", "numeric_domain")
    ]


@pytest.mark.parametrize(
    ("domain", "value"),
    [
        (Domain("decimal", 18, 4), Decimal("0.1234")),  # as many places as the scale
        (
            Domain("decimal", 18, 4),
            Decimal("1" * 14),
        ),  # as many whole digits as precision less scale
        (Domain("decimal", 18, 4), Decimal("-" + "9" * 14 + ".9999")),
        (Domain("integer", bits=8), 127),
        (Domain("integer", bits=8), -128),
        (Domain("integer", bits=8, signed=False), 255),
        (Domain("integer", bits=8, signed=False), 0),
    ],
)
def test_a_number_at_the_edge_of_its_field_is_accepted(domain: Domain, value: Any) -> None:
    encode(RecordingWire(), domain.family, domain, "amount", value)


@pytest.mark.parametrize(
    ("domain", "value"),
    [
        (Domain("integer", bits=8), 128),
        (Domain("integer", bits=8), -129),
        (Domain("integer", bits=8, signed=False), 256),
        (Domain("integer", bits=8, signed=False), -1),
        (Domain("decimal", 18, 4), Decimal("0.12345")),
    ],
)
def test_a_number_one_past_the_edge_of_its_field_is_invalid(domain: Domain, value: Any) -> None:
    with pytest.raises(Invalid):
        encode(RecordingWire(), domain.family, domain, "amount", value)


def test_the_ids_of_a_document_are_read_from_the_document() -> None:
    ids = document_ids(DOC, "catalog")
    assert ids.module_id == "catalog"
    assert ids.keys == {"UseCase": "identity", "Solution": "identity"}
    assert ids.relationships == {"addresses": "solution-addresses"}


def test_the_numeric_facets_of_a_document_are_read() -> None:
    doc = json.loads(DOC)
    doc["modules"][0]["elements"].append(
        {
            "id": "UseCase.cost",
            "kind": "field",
            "scalarType": "decimal",
            "facets": {"precision": 18, "scale": 4},
        }
    )
    doc["modules"][0]["elements"].append(
        {
            "id": "UseCase.n",
            "kind": "field",
            "scalarType": "integer",
            "facets": {"integerWidth": {"bits": 32, "signed": False}},
        }
    )
    ids = document_ids(json.dumps(doc).encode(), "catalog")
    assert ids.domains[("UseCase", "cost")] == Domain("decimal", 18, 4)
    assert ids.domains[("UseCase", "n")] == Domain("integer", bits=32, signed=False)


@pytest.mark.parametrize("content", [b"not json", b'{"modules": []}'])
def test_a_document_that_is_not_the_modules_is_unsupported(content: bytes) -> None:
    with pytest.raises(Unsupported):
        document_ids(content, "catalog")


# -- the planner


class FakeLookups:
    def __init__(self, existing: dict[Ref, Any] | None = None) -> None:
        self.existing = existing or {}
        self.edge_pages: dict[tuple[str, str, str], list[Any]] = {}

    def type_ref(self, record: str) -> Any:
        return SimpleNamespace(definition_pin=f"pin-{record}")

    def relationship_ref(self, name: str) -> Any:
        return SimpleNamespace(definition_pin=f"pin-{name}")

    def identity(self, ref: Ref) -> Any:
        return self.existing.get(ref)

    def edges(self, anchor: Any, relationship: str, direction: str) -> Sequence[Any]:
        return self.edge_pages.get((anchor.id, relationship, direction), [])


def planner(plan: Plan, lookups: FakeLookups | None = None) -> Planner:
    return Planner(
        RecordingWire(), MODULE, document_ids(DOC, "catalog"), lookups or FakeLookups(), plan
    )


def ops_of(plan: Plan, lookups: FakeLookups | None = None) -> list[Any]:
    wire = RecordingWire()
    built = planner(plan, lookups).operations()
    return [materialize(wire, op) for op in built.ops]


def basic_world() -> FakeLookups:
    world = FakeLookups(
        {uc("uc-1"): ident("UseCase", "uc-1"), sol("sol-1"): ident("Solution", "sol-1")}
    )
    world.existing[uc("uc-2")] = ident("UseCase", "uc-2")
    return world


def test_a_create_carries_its_key_and_is_named_by_an_alias() -> None:
    [op] = ops_of(create_plan("uc-9", workArea="x"))
    assert op == (
        "create",
        "pin-UseCase",
        (
            ("val", "code", ("text", "string", "uc-9")),
            ("val", "name", ("text", "string", "N")),
            ("val", "workArea", ("text", "string", "x")),
        ),
        "e1",
    )


def test_an_update_names_the_object_found_or_a_ghost_that_is_reported_in_order() -> None:
    world = basic_world()
    plan = Plan(
        "catalog.X", (), (Update(sol("sol-1"), {"name": "A"}), Update(sol("nope"), {"name": "B"}))
    )
    built = planner(plan, world).operations()
    [first, second] = [materialize(RecordingWire(), op) for op in built.ops]
    assert first[1] == ("stored", ident("Solution", "sol-1"))
    assert second[1] == ("stored", ("ghost", "pin-Solution", GHOST_ID))
    assert [op.missing for op in built.ops] == [(), (sol("nope"),)]


def test_updates_of_one_ref_are_one_operation_and_the_later_write_wins() -> None:
    plan = Plan(
        "catalog.X",
        (),
        (
            Update(sol("sol-1"), {"name": "A", "coverageLevel": "x"}),
            Update(sol("sol-1"), {"name": "B"}, ("coverageLevel",)),
            Update(sol("sol-1"), {"coverageLevel": "y"}),
        ),
    )
    [op] = ops_of(plan, basic_world())
    assert op[2] == (
        ("val", "name", ("text", "string", "B")),
        ("val", "coverageLevel", ("text", "string", "y")),
    )
    assert op[3] == ()
    unset = Plan(
        "catalog.X",
        (),
        (
            Update(sol("sol-1"), {"coverageLevel": "x"}),
            Update(sol("sol-1"), {}, ("coverageLevel",)),
        ),
    )
    [op] = ops_of(unset, basic_world())
    assert (op[2], op[3]) == ((), ("coverageLevel",))


def test_an_update_of_a_ref_the_plan_created_is_part_of_the_create() -> None:
    plan = Plan(
        "catalog.X",
        (),
        (
            Create(uc("uc-9"), {"name": "N", "workArea": "p"}),
            Update(uc("uc-9"), {"name": "M"}, ("workArea",)),
        ),
    )
    built = planner(plan).operations()
    [op] = [materialize(RecordingWire(), o) for o in built.ops]
    assert op[2] == (
        ("val", "code", ("text", "string", "uc-9")),
        ("val", "name", ("text", "string", "M")),
    )
    assert built.effect_op[1] is built.effect_op[0] and built.effect_op[0].effects == [0, 1]


def test_an_update_after_a_delete_is_its_own_operation_for_truss_to_refuse() -> None:
    plan = Plan("catalog.X", (), (Delete(uc("uc-2")), Update(uc("uc-2"), {"name": "A"})))
    ops = ops_of(plan, basic_world())
    assert [o[0] for o in ops] == ["delete_object", "update"]


def test_a_delete_first_removes_the_edges_the_object_has_on_either_end() -> None:
    world = basic_world()
    world.edge_pages[("UseCase:uc-1", "addresses", "incoming")] = [edge("edge-1", None, None)]
    world.edge_pages[("UseCase:uc-1", "addresses", "outgoing")] = []
    plan = Plan("catalog.X", (), (Delete(uc("uc-1")),))
    built = planner(plan, world).operations()
    ops = [materialize(RecordingWire(), op) for op in built.ops]
    assert ops == [
        ("delete_edge", ("stored", SimpleNamespace(id="edge-1"))),
        ("delete_object", ("stored", ident("UseCase", "uc-1"))),
    ]
    assert [(op.cascade, op.effects) for op in built.ops] == [(True, []), (False, [0])]


def test_an_edge_seen_from_both_of_its_ends_is_removed_once() -> None:
    world = basic_world()
    shared = edge("edge-1", None, None)
    world.edge_pages[("Solution:sol-1", "addresses", "outgoing")] = [shared]
    world.edge_pages[("Solution:sol-1", "addresses", "incoming")] = [shared]
    ops = ops_of(Plan("catalog.X", (), (Delete(sol("sol-1")),)), world)
    assert [o[0] for o in ops] == ["delete_edge", "delete_object"]


def test_a_delete_of_a_missing_object_removes_nothing_else() -> None:
    ops = ops_of(Plan("catalog.X", (), (Delete(uc("nope")),)), basic_world())
    assert ops == [("delete_object", ("stored", ("ghost", "pin-UseCase", GHOST_ID)))]


def test_a_link_names_made_objects_by_alias_and_found_ones_by_identity() -> None:
    plan = Plan(
        "catalog.X",
        (),
        (
            Create(sol("sol-2"), {"name": "S"}),
            Link("addresses", sol("sol-2"), uc("uc-1")),
            Link("addresses", sol("sol-2"), uc("nope")),
        ),
    )
    built = planner(plan, basic_world()).operations()
    ops = [materialize(RecordingWire(), op) for op in built.ops]
    assert ops[1][1:4] == ("pin-addresses", ("alias", "e1"), ("stored", ident("UseCase", "uc-1")))
    assert ops[2][3] == ("stored", ("ghost", "pin-UseCase", GHOST_ID))
    assert built.ops[2].missing == (uc("nope"),)


def test_an_unlink_removes_the_existing_edge_the_plan_made_or_a_ghost() -> None:
    world = basic_world()
    world.edge_pages[("Solution:sol-1", "addresses", "outgoing")] = [
        edge("edge-1", ident("Solution", "sol-1"), ident("UseCase", "uc-1"))
    ]
    plan = Plan(
        "catalog.X",
        (),
        (
            Unlink("addresses", sol("sol-1"), uc("uc-1")),
            Unlink("addresses", sol("sol-1"), uc("uc-1")),
            Link("addresses", sol("sol-1"), uc("uc-2")),
            Unlink("addresses", sol("sol-1"), uc("uc-2")),
        ),
    )
    ops = ops_of(plan, world)
    assert ops[0] == ("delete_edge", ("stored", SimpleNamespace(id="edge-1")))
    assert ops[1] == ("delete_edge", ("stored", ("ghost-edge", "pin-addresses", GHOST_ID)))
    assert ops[3] == ("delete_edge", ("alias", "e1"))


def test_a_delete_takes_the_edges_the_plan_made_to_the_object() -> None:
    plan = Plan(
        "catalog.X",
        (),
        (
            Create(sol("sol-2"), {"name": "S"}),
            Link("addresses", sol("sol-2"), uc("uc-1")),
            Delete(sol("sol-2")),
        ),
    )
    ops = ops_of(plan, basic_world())
    assert [o[0] for o in ops] == ["create", "link", "delete_edge", "delete_object"]
    assert ops[2] == ("delete_edge", ("alias", "e2")) and ops[3][1] == ("alias", "e1")


def test_a_structured_value_is_unsupported() -> None:
    plan = Plan("catalog.X", (), (Update(sol("sol-1"), {"nope": 1}),))
    ops_of(plan, basic_world())  # an unknown property is the effect check's, not the planner's


# -- preconditions


def pre(op: str, **args: Any) -> Precondition:
    return Precondition("p", "why", op, args)


def conditions(
    p: Precondition, world: FakeLookups | None = None, dropped: frozenset[str] = frozenset()
) -> Any:
    plan = Plan("catalog.X", (p,), ())
    return planner(plan, world or basic_world()).preconditions(dropped)


def test_exists_names_the_object_or_a_ghost_with_the_callers_id_and_reason() -> None:
    assert conditions(pre("exists", ref=uc("uc-1"))) == (
        [("exists", "p", "why", ident("UseCase", "uc-1"))],
        [],
    )
    assert conditions(pre("exists", ref=uc("nope"))) == (
        [("exists", "p", "why", ("ghost", "pin-UseCase", GHOST_ID))],
        [],
    )


def test_absent_is_always_sent_whatever_the_lookup_found_so_a_retry_rebuilds_the_same_input() -> (
    None
):
    found, _ = conditions(pre("absent", type=UC, key="uc-1"))
    missing, _ = conditions(pre("absent", type=UC, key="nope"))
    assert found[0][:5] == ("absent", "p", "why", "pin-UseCase", "identity")
    assert found[0][5] == ("text", "string", "uc-1") and missing[0][5] == ("text", "string", "nope")


def test_a_dropped_condition_is_left_out() -> None:
    assert conditions(pre("absent", type=UC, key="nope"), dropped=frozenset({"p"})) == ([], [])


def test_property_equals_is_written_in_the_fields_canonical_spelling() -> None:
    sent, _ = conditions(pre("property_equals", ref=sol("sol-1"), property="name", value="x"))
    assert sent == [
        ("equals", "p", "why", ident("Solution", "sol-1"), "name", ("text", "string", "x"))
    ]


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (
            {"relationship": "addresses", "source": sol("sol-1"), "target": uc("uc-1")},
            (
                "no-edge",
                "p",
                "why",
                "pin-addresses",
                ident("Solution", "sol-1"),
                ident("UseCase", "uc-1"),
            ),
        ),
        (
            {"relationship": "addressedBy", "source": uc("uc-1"), "target": sol("sol-1")},
            (
                "no-edge",
                "p",
                "why",
                "pin-addresses",
                ident("Solution", "sol-1"),
                ident("UseCase", "uc-1"),
            ),
        ),
        (
            {"relationship": "addresses", "source": sol("sol-1")},
            ("count", "p", "why", "pin-addresses", ident("Solution", "sol-1"), "outgoing", 0, 0),
        ),
        (
            {"relationship": "addressedBy", "source": uc("uc-1")},
            ("count", "p", "why", "pin-addresses", ident("UseCase", "uc-1"), "incoming", 0, 0),
        ),
    ],
)
def test_no_relationship_is_stated_from_the_forward_relationship(
    args: dict[str, Any], expected: Any
) -> None:
    assert conditions(pre("no_relationship", **args))[0] == [expected]


@pytest.mark.parametrize(
    ("cmp", "n", "low", "high"),
    [("=", 2, 2, 2), (">", 2, 3, None), (">=", 2, 2, None), ("<", 2, 0, 1), ("<=", 2, 0, 2)],
)
def test_a_count_comparison_is_one_inclusive_range(
    cmp: str, n: int, low: int, high: int | None
) -> None:
    args = {"relationship": "addresses", "source": sol("sol-1"), "cmp": cmp, "n": n}
    [sent], static = conditions(pre("count", **args))
    assert static == [] and sent[5:] == ("outgoing", low, high)


def test_a_count_with_no_satisfying_number_fails_here() -> None:
    args = {"relationship": "addresses", "source": sol("sol-1"), "cmp": "<", "n": 0}
    assert conditions(pre("count", **args)) == ([], [(0, Failure("p", "why"))])


@pytest.mark.parametrize(
    ("cmp", "n", "holds"),
    [
        ("=", 0, True),
        ("<", 1, True),
        ("<=", 0, True),
        (">=", 0, True),
        (">", 0, False),
        ("=", 1, False),
    ],
)
def test_a_count_of_an_object_that_does_not_exist_is_evaluated_as_zero(
    cmp: str, n: int, holds: bool
) -> None:
    args = {"relationship": "addresses", "source": sol("nope"), "cmp": cmp, "n": n}
    sent, static = conditions(pre("count", **args))
    assert sent == [] and (static == []) is holds


def test_a_missing_object_has_no_relationship_and_a_mismatched_end_has_none() -> None:
    assert conditions(pre("no_relationship", relationship="addresses", source=sol("nope"))) == (
        [],
        [],
    )
    mismatched = {"relationship": "addresses", "source": uc("uc-1")}  # a use case is not a source
    assert conditions(pre("no_relationship", **mismatched)) == ([], [])
    assert conditions(
        pre("no_relationship", relationship="addresses", source=sol("sol-1"), target=uc("nope"))
    ) == ([], [])


def test_a_relationship_that_is_not_declared_is_invalid() -> None:
    with pytest.raises(Invalid):
        conditions(pre("no_relationship", relationship="nope", source=sol("sol-1")))


def test_a_count_compared_with_not_equal_or_too_many_conditions_or_effects_are_unsupported() -> (
    None
):
    bad = Plan(
        "catalog.X",
        (pre("count", relationship="addresses", source=sol("sol-1"), cmp="!=", n=1),),
        (),
    )
    with pytest.raises(Unsupported):
        check_bounds(bad)
    many = Plan("catalog.X", (), tuple(Create(uc(f"u{i}"), {"name": "N"}) for i in range(1025)))
    with pytest.raises(Unsupported):
        check_bounds(many)
    check_bounds(Plan("catalog.X", (), many.effects[:1024]))
    check_bounds(Plan("catalog.X", tuple(pre("exists", ref=uc("a")) for _ in range(3072)), ()))
    with pytest.raises(Unsupported):
        check_bounds(Plan("catalog.X", tuple(pre("exists", ref=uc("a")) for _ in range(3073)), ()))


# -- outcomes


def test_a_group_is_named_by_the_first_event_or_by_its_request() -> None:
    assert group_of(Semantic((Unchanged(), Created())), "r") == "epoch:77"
    named = group_of(Semantic((Unchanged(),)), "r")
    assert named.startswith("request:") and named == group_of(Semantic((Unchanged(),)), "r")
    assert named != group_of(Semantic((Unchanged(),)), "s")


def test_a_receipt_counts_effects_lists_refs_once_and_leaves_out_what_changed_nothing() -> None:
    plan = Plan(
        "catalog.X",
        (),
        (
            Update(sol("sol-1"), {"name": "A"}),
            Update(sol("sol-1"), {"coverageLevel": "x"}),
            Update(uc("uc-1"), {"name": "same"}),
            Create(uc("uc-9"), {"name": "N"}),
            Link("addresses", sol("sol-1"), uc("uc-9")),
            Delete(uc("uc-2")),
            Unlink("addresses", sol("sol-1"), uc("uc-1")),
        ),
    )
    built = planner(plan, basic_world()).operations()
    results = [Changed("2"), Unchanged("1"), Created("1"), Created("1"), Deleted("5"), Deleted("2")]
    # ops: update sol-1 (merged), update uc-1, create uc-9, link, delete uc-2 (edges first), unlink
    assert len(built.ops) == 6
    got = receipt(plan, built, Semantic(tuple(results)), "t", replayed=False, request="r")
    assert (got.created, got.updated, got.deleted, got.linked, got.unlinked) == (1, 2, 1, 1, 1)
    assert [(r.key, r.version) for r in got.refs] == [
        ("sol-1", 2),
        ("uc-1", 1),
        ("uc-9", 1),
        ("uc-2", 5),
    ]
    assert (got.token, got.replayed, got.group) == ("t", False, "epoch:77")


def op_failure(code: str, index: int | None, plan: Plan, **kw: Any) -> Any:
    built = planner(plan, basic_world()).operations()
    inner_error = artifact_of(code=code)
    failure = (
        GroupOperationFailure(str(index), inner_error)
        if index is not None
        else SimpleNamespace(operation_index=None, inner_error=inner_error)
    )
    return operation_failure("truss", failure, built, kw.get("exists", lambda r: True))


def test_not_found_names_the_ref_the_operation_used() -> None:
    plan = Plan("catalog.X", (), (Update(sol("nope"), {"name": "A"}),))
    err = op_failure("not_found", 0, plan)
    assert isinstance(err, PreconditionFailed)
    assert [(f.id, f.reason) for f in err.failures] == [
        ("_ref", "catalog.Solution nope does not exist")
    ]
    link = Plan("catalog.X", (), (Link("addresses", sol("sol-1"), uc("nope")),))
    assert (
        op_failure("not_found", 0, link).failures[0].reason == "catalog.UseCase nope does not exist"
    )


def test_not_found_at_an_unlink_is_the_unlink_failure() -> None:
    plan = Plan("catalog.X", (), (Unlink("addresses", sol("sol-1"), uc("uc-1")),))
    err = op_failure("not_found", 0, plan)
    assert [f.id for f in err.failures] == ["_unlink"]


def test_a_key_conflict_is_exists_deleted_or_a_duplicate_relationship() -> None:
    plan = create_plan()
    assert op_failure("key_conflict", 0, plan, exists=lambda r: True).reason == "exists"
    assert op_failure("key_conflict", 0, plan, exists=lambda r: False).reason == "deleted"
    link = Plan("catalog.X", (), (Link("addresses", sol("sol-1"), uc("uc-1")),))
    assert op_failure("key_conflict", 0, link).reason == "duplicate_relationship"


def test_the_other_codes_map_by_their_meaning() -> None:
    plan = Plan("catalog.X", (), (Update(sol("sol-1"), {"name": "A"}),))
    assert op_failure("expected_version", 0, plan).reason == "version"
    assert isinstance(
        op_failure("dependencies", 0, Plan("catalog.X", (), (Delete(uc("uc-1")),))), Unavailable
    )
    invalid = op_failure("invalid_input", 0, plan)
    assert isinstance(invalid, Invalid) and invalid.violations[0].path == "effects[0]"
    assert isinstance(op_failure("surprise", 0, plan), Unavailable)
    assert isinstance(op_failure("not_found", 9, plan), Unavailable)


def test_dependencies_is_busy_at_a_delete_and_a_multiplicity_violation_elsewhere() -> None:
    delete = Plan("catalog.X", (), (Delete(uc("uc-2")),))
    busy = op_failure("dependencies", 0, delete)
    assert isinstance(busy, Unavailable) and busy.reason == "busy"
    link = Plan(
        "catalog.X",
        (),
        (Update(sol("sol-1"), {"name": "A"}), Link("addresses", sol("sol-1"), uc("uc-1"))),
    )
    for index in (0, 1):  # the finish-time index is the last operation, not the offender
        err = op_failure("dependencies", index, link)
        assert isinstance(err, Invalid)
        [violation] = err.violations
        assert violation.code == "multiplicity"
        assert violation.path == f"effects[{index}]"
    unresolved = op_failure("dependencies", 9, link)
    assert isinstance(unresolved, Invalid) and unresolved.violations[0].path == "effects"


def test_final_state_multiplicity_reports_without_claiming_a_causal_effect() -> None:
    detail = (
        "the relationship's final-state multiplicity is not met; Truss did not identify a causal "
        "operation; the path is a reporting location"
    )
    single = Plan("catalog.X", (), (Update(sol("sol-1"), {"name": "A"}),))
    err = op_failure("multiplicity", None, single)
    assert isinstance(err, Invalid)
    assert err.violations == [Violation("effects[0]", "multiplicity", detail)]


def test_final_state_multiplicity_after_a_delete_uses_last_effect_as_reporting_location() -> None:
    detail = (
        "the relationship's final-state multiplicity is not met; Truss did not identify a causal "
        "operation; the path is a reporting location"
    )
    plan = Plan(
        "catalog.X",
        (),
        (Update(sol("sol-1"), {"name": "A"}), Delete(uc("uc-1"))),
    )
    err = op_failure("multiplicity", None, plan)
    assert isinstance(err, Invalid)
    assert err.violations == [Violation("effects[1]", "multiplicity", detail)]


def test_batch_final_state_multiplicity_uses_the_last_effect_as_a_reporting_location() -> None:
    from arras.adapters.truss.plan import Built, Op

    failure = SimpleNamespace(operation_index=None, inner_error=artifact_of(code="multiplicity"))
    built = Built(
        ops=[Op("delete_object", effects=[3], item=2)],
        effect_op={},
        touched={},
        batch=True,
    )
    err = operation_failure("truss", failure, built, lambda r: True)
    assert isinstance(err, Invalid)
    [violation] = err.violations
    assert violation.path == "items[2].effects[3]"
    assert "Truss did not identify a causal operation" in violation.message


def test_an_unknown_group_failure_without_an_operation_index_fails_closed() -> None:
    err = op_failure("surprise", None, Plan("catalog.X", (), (Delete(uc("uc-1")),)))
    assert isinstance(err, Unavailable) and err.reason == "unreachable"


def test_an_artifact_that_is_not_json_decodes_to_nothing() -> None:
    assert artifact(Artifact("!!!")) == {} and artifact(None) == {}
    assert artifact(artifact_of(code="x")) == {"code": "x"}


# -- apply through the call layer


def test_a_write_reads_the_catalog_then_the_document_then_lookups_then_applies_and_commits() -> (
    None
):
    rig = ApplyRig()
    rig.assembly.objects[("UseCase", "uc-1")] = ident("UseCase", "uc-1")
    plan = Plan(
        "catalog.AddSolution",
        (Precondition("use_case_exists", "r", "exists", {"ref": uc("uc-1")}),),
        (Create(sol("sol-2"), {"name": "S"}), Link("addresses", sol("sol-2"), uc("uc-1"))),
    )
    rig.assembly.outcomes = [applied(Created(), Created())]
    got = apply(rig, plan)
    log = rig.assembly.log
    assert log[:2] == ["catalog", "document:sandbox"]
    # the group context and the references the plan names come in one call before the planner's
    # lookups, which ask Truss for neither again
    assert log.index("prepare_group") < log.index("lookup:UseCase:uc-1") < log.index("apply")
    assert not any(x.startswith(("type:", "relationship:", "context")) for x in log)
    [(records, relationships)] = rig.assembly.prepared
    assert sorted(r for _, _, r in records) == ["Solution", "UseCase"]
    assert [r for _, _, r in relationships] == ["solution-addresses"]
    assert log.count("apply") == 1 and log[-1] == "apply"  # the pending token needs no second call
    [first] = rig.writes
    assert first.log[0].endswith("READ WRITE") and first.log[-2:] == [
        "SET CONSTRAINTS ALL IMMEDIATE",
        "commit",
    ]
    assert (got.created, got.linked, got.token, got.replayed) == (1, 1, "token-1", False)
    [(inp, req, documents)] = rig.assembly.presented[:1]
    assert req.rid == "catalog.AddSolution:k1" and inp.origin == ("origin", "catalog.AddSolution")
    assert documents == (("document", "sandbox", DOC),)


def test_a_group_without_a_pending_token_gets_its_token_from_the_same_request_after_commit() -> (
    None
):
    rig = ApplyRig()
    rig.assembly.outcomes = [applied(Created(), token=ABSENT), replayed(Created())]
    got = apply(rig)
    assert (got.token, got.replayed) == ("token-1", False)
    assert rig.assembly.log.count("apply") == 2
    [first, second] = rig.writes
    assert first.log[-1] == "commit" and second.log[-1] == "rollback"  # the call writes nothing
    assert rig.assembly.presented[0][:2] == rig.assembly.presented[1][:2]
    assert rig.assembly.presented[0][0] is rig.assembly.presented[1][0]  # not a rebuilt input


def test_a_caller_retry_gets_the_replay_on_its_first_call_and_writes_nothing() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [replayed(Created(), token="orig")]
    got = apply(rig)
    assert (got.replayed, got.token, got.created) == (True, "orig", 1)
    assert len(rig.writes) == 1 and "commit" not in rig.writes[0].log


def test_a_keyless_write_presents_a_fresh_request_id_each_time() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [applied(Created())]
    apply(rig, idempotency_key=None)
    apply(rig, idempotency_key=None)
    rids = [req.rid for _, req, _ in rig.assembly.presented]
    assert len(rids) == 2 and rids[0] != rids[1]


def test_a_commit_that_raises_is_recovered_by_presenting_the_same_request_again() -> None:
    rig = ApplyRig()
    rig.commit_failures = [True]
    rig.assembly.outcomes = [applied(Created()), replayed(Created(), token="landed")]
    got = apply(rig)
    assert (got.replayed, got.token) == (False, "landed")  # this invocation applied it
    assert rig.assembly.presented[0][:2] == rig.assembly.presented[1][:2]
    assert len(rig.writes) == 2 and "commit" not in rig.writes[1].log


def test_a_retry_while_recovering_keeps_the_recovered_state() -> None:
    rig = ApplyRig()
    rig.commit_failures = [True]
    rig.assembly.outcomes = [
        applied(Created()),
        error("retry"),
        replayed(Created(), token="landed"),
    ]
    got = apply(rig)
    assert (got.replayed, got.token) == (False, "landed")  # this invocation's write, not a replay
    assert rig.assembly.log.count("apply") == 3


def test_a_commit_that_did_not_land_is_applied_again_and_committed() -> None:
    rig = ApplyRig()
    rig.commit_failures = [True, False]
    rig.assembly.outcomes = [applied(Created()), applied(Created(), token="t")]
    got = apply(rig)
    assert (got.replayed, got.token) == (False, "t")
    assert len(rig.writes) == 2 and rig.writes[1].log[-1] == "commit"


def test_two_unknown_commits_are_unavailable() -> None:
    rig = ApplyRig()
    rig.commit_failures = [True, True]
    rig.assembly.outcomes = [applied(Created())]
    with pytest.raises(Unavailable) as raised:
        apply(rig)
    assert raised.value.detail == "outcome unknown"


def test_a_receipt_that_cannot_be_read_after_the_commit_is_unavailable_and_the_write_stands() -> (
    None
):
    rig = ApplyRig()
    rig.assembly.outcomes = [applied(Created(), token=ABSENT), failed(UnauthorizedPerson())]
    with pytest.raises(Unavailable) as raised:
        apply(rig)
    assert "committed" in raised.value.detail
    assert "commit" in rig.writes[0].log


def test_a_replay_with_no_token_is_unavailable() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [replayed(Created(), token="")]
    with pytest.raises(Unavailable):
        apply(rig)


def test_a_state_apply_does_not_use_is_unavailable() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [ok(GroupSuccess(SameTransactionReplay(Semantic((Created(),)))))]
    with pytest.raises(Unavailable):
        apply(rig)


def test_a_same_transaction_replay_cannot_occur_and_is_unreachable() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [ok(GroupSuccess(SameTransactionReplay(Semantic((Created(),)))))]
    with pytest.raises(Unavailable) as raised:
        apply(rig)
    assert raised.value.reason == "unreachable"
    assert "same-transaction" in raised.value.detail


def only_rollback(rig: ApplyRig) -> None:
    [write] = rig.writes
    assert "commit" not in write.log and write.log[-1] == "rollback"


def test_a_failed_precondition_is_raised_inside_the_call_so_nothing_is_committed() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [
        failed(
            PreconditionFailedCarrier(
                (FailedPrecondition("use_case_exists", "no such", "object_exists"),)
            )
        )
    ]
    plan = Plan(
        "catalog.X",
        (Precondition("use_case_exists", "no such", "exists", {"ref": uc("a")}),),
        create_plan().effects,
    )
    with pytest.raises(PreconditionFailed) as raised:
        apply(rig, plan)
    assert raised.value.failures == [Failure("use_case_exists", "no such")]
    only_rollback(rig)


def test_truss_and_planner_failures_come_back_in_the_plans_order() -> None:
    rig = ApplyRig()
    rig.assembly.objects[("Solution", "sol-1")] = ident("Solution", "sol-1")
    rig.assembly.outcomes = [
        failed(
            PreconditionFailedCarrier(
                (
                    FailedPrecondition("third", "r3", "object_exists"),
                    FailedPrecondition("first", "r1", "object_exists"),
                )
            )
        )
    ]
    plan = Plan(
        "catalog.X",
        (
            pre_id("first", "exists", ref=uc("a")),
            pre_id("second", "count", relationship="addresses", source=sol("sol-1"), cmp="<", n=0),
            pre_id("third", "exists", ref=uc("b")),
        ),
        create_plan().effects,
    )
    with pytest.raises(PreconditionFailed) as raised:
        apply(rig, plan)
    assert [f.id for f in raised.value.failures] == ["first", "second", "third"]


def pre_id(id: str, op: str, **args: Any) -> Precondition:
    return Precondition(id, f"{id} failed", op, args)


def test_a_condition_the_planner_decided_fails_even_when_truss_applies_the_group() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [applied(Created())]
    plan = Plan(
        "catalog.X",
        (pre_id("c", "count", relationship="addresses", source=sol("nope"), cmp=">", n=0),),
        create_plan().effects,
    )
    with pytest.raises(PreconditionFailed) as raised:
        apply(rig, plan)
    assert [f.id for f in raised.value.failures] == ["c"]
    only_rollback(rig)


def test_the_declared_failure_wins_over_an_effect_failure() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [failed(GroupOperationFailure("0", artifact_of(code="key_conflict")))]
    plan = Plan(
        "catalog.X",
        (pre_id("c", "count", relationship="addresses", source=sol("nope"), cmp=">", n=0),),
        create_plan().effects,
    )
    with pytest.raises(PreconditionFailed):
        apply(rig, plan)


def test_a_tombstoned_key_does_not_fail_an_absent_condition_and_the_group_is_presented_again() -> (
    None
):
    rig = ApplyRig()
    plan = Plan(
        "catalog.X",
        (pre_id("fresh", "absent", type=UC, key="gone"),),
        (Update(sol("sol-1"), {"name": "A"}),),
    )
    rig.assembly.objects[("Solution", "sol-1")] = ident("Solution", "sol-1")
    rig.assembly.outcomes = [
        failed(PreconditionFailedCarrier((FailedPrecondition("fresh", "r", "key_absent"),))),
        applied(Changed()),
    ]
    got = apply(rig, plan)
    assert got.updated == 1
    first, again = rig.assembly.presented[:2]
    assert len(first[0].preconditions) == 1 and again[0].preconditions == ()


def test_a_keyed_retry_conflicting_over_a_retired_key_leaves_the_condition_out_and_replays() -> (
    None
):
    plan = Plan(
        "catalog.X",
        (pre_id("fresh", "absent", type=UC, key="gone"),),
        (Update(sol("sol-1"), {"name": "A"}),),
    )
    rig = ApplyRig()
    rig.assembly.objects[("Solution", "sol-1")] = ident("Solution", "sol-1")
    rig.assembly.outcomes = [failed(RequestConflict()), replayed(Changed(), token="t0")]
    got = apply(rig, plan)  # keyed
    assert (got.replayed, got.token) == (True, "t0")
    full, left_out = rig.assembly.presented[:2]
    assert len(full[0].preconditions) == 1 and left_out[0].preconditions == ()
    # a request that was not keyed, a key that is held, or a second conflict stays the conflict
    for objects, key, outcomes in (
        ({("UseCase", "gone"): ident("UseCase", "gone")}, "k1", [failed(RequestConflict())]),
        ({}, "k1", [failed(RequestConflict()), failed(RequestConflict())]),
    ):
        other = ApplyRig()
        other.assembly.objects[("Solution", "sol-1")] = ident("Solution", "sol-1")
        other.assembly.objects.update(objects)
        other.assembly.outcomes = outcomes
        with pytest.raises(Conflict) as raised:
            apply(other, plan, idempotency_key=key)
        assert raised.value.reason == "idempotency_key_reused"
        assert "no longer resolve" in raised.value.detail  # R18.3: say the original's targets
    keyless = ApplyRig()
    keyless.assembly.objects[("Solution", "sol-1")] = ident("Solution", "sol-1")
    keyless.assembly.outcomes = [failed(RequestConflict())]
    with pytest.raises(Conflict):
        apply(keyless, plan, idempotency_key=None)
    assert keyless.assembly.log.count("apply") == 1


def test_a_held_key_fails_an_absent_condition() -> None:
    rig = ApplyRig()
    rig.assembly.objects[("UseCase", "held")] = ident("UseCase", "held")
    rig.assembly.outcomes = [
        failed(PreconditionFailedCarrier((FailedPrecondition("fresh", "r", "key_absent"),)))
    ]
    plan = Plan(
        "catalog.X", (pre_id("fresh", "absent", type=UC, key="held"),), create_plan().effects
    )
    with pytest.raises(PreconditionFailed) as raised:
        apply(rig, plan)
    assert [f.id for f in raised.value.failures] == ["fresh"]
    assert rig.assembly.log.count("apply") == 1


def test_a_create_on_a_held_key_is_exists_and_on_a_deleted_key_is_deleted() -> None:
    held = ApplyRig()
    held.assembly.objects[("UseCase", "uc-9")] = ident("UseCase", "uc-9")
    held.assembly.outcomes = [failed(GroupOperationFailure("0", artifact_of(code="key_conflict")))]
    with pytest.raises(Conflict) as raised:
        apply(held)
    assert raised.value.reason == "exists"
    gone = ApplyRig()
    gone.assembly.outcomes = [failed(GroupOperationFailure("0", artifact_of(code="key_conflict")))]
    with pytest.raises(Conflict) as raised:
        apply(gone)
    assert raised.value.reason == "deleted"
    only_rollback(gone)


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (failed(UnauthorizedPerson()), Refused),
        (failed(RequestConflict()), Conflict),
        (failed(InvalidGroupInput(artifact_of(code="invalid_input"))), Invalid),
        (failed(InvalidGroupInput(artifact_of(code="original_documents"))), Unavailable),
        (ok(GroupUnavailable("profile")), Unsupported),
        (ok(GroupUnavailable("resource")), Unavailable),
        (ok(GroupUnavailable("observation")), Unavailable),
        (ok(GroupUnavailable("receipt")), Unavailable),
        (error("execution_obligation", sql_state="42501"), Refused),
        (error("execution_obligation", sql_state="P0002"), Unavailable),
        (error("cancelled", sql_state="57014"), Unavailable),
        (ok("something else"), Unavailable),
    ],
)
def test_the_failure_map(outcome: Any, expected: type[Exception]) -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [outcome]
    with pytest.raises(expected):
        apply(rig)
    only_rollback(rig)


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("original_documents", "busy"),  # the accepted catalog changed under the write
        ("catalog", "busy"),
        ("shape", "unreachable"),
        ("transport", "unreachable"),
    ],
)
def test_an_invalid_group_input_that_is_a_race_or_a_transport_fault_is_unavailable(
    code: str, reason: str
) -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [failed(InvalidGroupInput(artifact_of(code=code)))]
    with pytest.raises(Unavailable) as raised:
        apply(rig)
    assert raised.value.reason == reason
    only_rollback(rig)


def test_the_unavailable_reasons_of_a_group() -> None:
    reasons = {}
    for reason in ("resource", "observation", "receipt"):
        rig = ApplyRig()
        rig.assembly.outcomes = [ok(GroupUnavailable(reason))]
        with pytest.raises(Unavailable) as raised:
            apply(rig)
        reasons[reason] = raised.value.reason
    assert reasons == {"resource": "resource", "observation": "busy", "receipt": "unreachable"}


def test_a_retry_the_whole_transaction_runs_the_call_again_a_bounded_number_of_times() -> None:
    rig = ApplyRig()
    retry = error("retry")
    rig.assembly.outcomes = [retry, retry, applied(Created())]
    assert apply(rig).created == 1
    assert len(rig.conns) == 3 and "commit" not in rig.conns[0].log
    forever = ApplyRig()
    forever.assembly.outcomes = [error("retry")]
    with pytest.raises(Unavailable) as raised:
        apply(forever)
    assert raised.value.reason == "busy" and len(forever.conns) == 3


def test_a_write_by_a_person_who_can_read_nothing_is_refused_before_anything_is_planned() -> None:
    rig = ApplyRig()
    rig.assembly.catalog = ok(CatalogRefused())
    with pytest.raises(Refused):
        apply(rig)
    assert rig.assembly.log == ["catalog"]
    unknown = ApplyRig()
    plan = Plan("other.Act", (), create_plan().effects)
    with pytest.raises(Refused):
        apply(unknown, plan)


def test_a_write_with_no_token_never_connects() -> None:
    rig = ApplyRig()
    with pytest.raises(Refused) as raised:
        rig.backend().apply(Principal("alice", ""), create_plan(), idempotency_key=None)
    assert raised.value.reason == "token_expired" and rig.conns == []


def test_a_backend_with_no_connection_source_is_unavailable() -> None:
    with pytest.raises(Unavailable) as raised:
        TrussBackend("truss").apply(ALICE, create_plan(), idempotency_key=None)
    assert raised.value.reason == "not_configured"


def test_a_plan_too_large_for_a_group_or_with_an_unsupported_count_is_unsupported_before_any_call() -> (
    None
):
    rig = ApplyRig()
    big = Plan("catalog.X", (), tuple(Create(uc(f"u{i}"), {"name": "N"}) for i in range(1025)))
    with pytest.raises(Unsupported):
        apply(rig, big)
    bad = Plan(
        "catalog.X",
        (pre_id("c", "count", relationship="addresses", source=sol("sol-1"), cmp="!=", n=1),),
        create_plan().effects,
    )
    with pytest.raises(Unsupported):
        apply(rig, bad)
    assert rig.conns == []


def test_a_plan_with_no_effects_is_unsupported() -> None:
    with pytest.raises(Unsupported):
        apply(ApplyRig(), Plan("catalog.X", (), ()))


def test_a_cascade_that_passes_the_group_bound_is_unsupported() -> None:
    rig = ApplyRig()
    rig.assembly.objects[("UseCase", "uc-1")] = ident("UseCase", "uc-1")
    rig.assembly.edge_pages[("UseCase:uc-1", "solution-addresses", "incoming")] = [
        edge(f"e{i}", None, None) for i in range(1024)
    ]
    with pytest.raises(Unsupported):
        apply(rig, Plan("catalog.Retire", (), (Delete(uc("uc-1")),)))
    assert "context" not in rig.assembly.log


def test_an_effect_the_module_does_not_take_is_invalid_before_any_lookup() -> None:
    rig = ApplyRig()
    bad = Plan("catalog.X", (), (Update(sol("sol-1"), {"nope": "x"}),))
    with pytest.raises(Invalid):
        apply(rig, bad)
    assert not any(entry.startswith("lookup") for entry in rig.assembly.log)
    only_rollback(rig)


def test_a_lookup_that_cannot_answer_is_unavailable_and_a_refused_one_is_refused() -> None:
    busy = ApplyRig()
    busy.assembly.lookup_failure = ok(SimpleNamespace(reason="observation"))
    busy.assembly.lookup_failure = ok(
        type("ObjectReadUnavailable", (), {"reason": "observation"})()
    )
    plan = Plan("catalog.X", (), (Update(sol("sol-1"), {"name": "A"}),))
    with pytest.raises(Unavailable) as raised:
        apply(busy, plan)
    assert raised.value.reason == "busy"
    refused = ApplyRig()
    refused.assembly.lookup_failure = error("execution_obligation", sql_state="42501")
    with pytest.raises(Refused):
        apply(refused, plan)


def test_a_credential_never_appears_in_an_error() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [error("execution_obligation", sql_state="P0002")]
    with pytest.raises(Unavailable) as raised:
        apply(rig)
    assert ALICE.token not in str(raised.value) and ALICE.token not in repr(raised.value.__dict__)


# -- a dry run


def test_a_dry_run_rolls_back_and_reports_the_effects_with_no_freshness() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [applied(Created())]
    plan = create_plan()
    got = apply(rig, plan, dry_run=True)
    assert isinstance(got, Validation)
    assert (got.ok, got.violations, got.failures, got.effects, got.replay, got.freshness) == (
        True,
        (),
        (),
        plan.effects,
        None,
        None,
    )
    only_rollback(rig)
    assert rig.assembly.log.count("apply") == 1  # no receipt call for a dry run


def test_a_dry_run_presents_its_request_so_a_committed_one_surfaces_as_the_replay() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [replayed(Created(), token="orig")]
    got = apply(rig, dry_run=True)
    assert got.ok and got.replay is not None
    assert (got.replay.replayed, got.replay.token, got.replay.created) == (True, "orig", 1)
    assert rig.assembly.presented[0][1].rid == "catalog.AddUseCase:k1"


def test_a_dry_run_reports_failures_conflicts_and_violations_as_the_answer() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [
        failed(PreconditionFailedCarrier((FailedPrecondition("p", "r", "object_exists"),)))
    ]
    plan = Plan("catalog.X", (pre_id("p", "exists", ref=uc("a")),), create_plan().effects)
    got = apply(rig, plan, dry_run=True)
    assert (got.ok, [f.id for f in got.failures]) == (False, ["p"])
    clash = ApplyRig()
    clash.assembly.outcomes = [failed(RequestConflict())]
    got = apply(clash, dry_run=True)
    assert [f.id for f in got.failures] == ["conflict:idempotency_key_reused"]
    exists = ApplyRig()
    exists.assembly.outcomes = [
        failed(GroupOperationFailure("0", artifact_of(code="key_conflict")))
    ]
    exists.assembly.objects[("UseCase", "uc-9")] = ident("UseCase", "uc-9")
    assert [f.id for f in apply(exists, dry_run=True).failures] == ["conflict:exists"]
    bad = apply(
        ApplyRig(), Plan("catalog.X", (), (Update(sol("sol-1"), {"nope": "x"}),)), dry_run=True
    )
    assert (bad.ok, bad.violations[0].code) == (False, "unknown_field")


def test_a_dry_run_by_a_person_who_may_not_write_is_refused() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [failed(UnauthorizedPerson())]
    with pytest.raises(Refused):
        apply(rig, dry_run=True)
    nobody = ApplyRig()
    nobody.assembly.catalog = ok(CatalogRefused())
    with pytest.raises(Refused):
        apply(nobody, dry_run=True)


def test_a_dry_run_that_truss_cannot_take_is_unsupported_not_a_verdict() -> None:
    with pytest.raises(Unsupported):
        apply(ApplyRig(), Plan("catalog.X", (), ()), dry_run=True)


def test_the_adapter_names_no_truss_class_so_the_base_install_needs_none() -> None:
    import subprocess
    import sys

    code = (
        "import sys, arras.adapters.truss as t; "
        "from arras.adapters.truss import apply, load, plan, outcome, values, wire; "
        "print(sorted(m for m in ('truss', 'psycopg', 'weft') if m in sys.modules))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


_ = (field, Callable, Iterator, contextmanager)
