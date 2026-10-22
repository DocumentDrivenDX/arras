# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Where a module lives is the host's decision: named backends, roles and placement (CONTRACT-002).

The backends here are named "primary", "mirror" and "upstream": the names are the host's, and
nothing in Arras knows them."""

import json
from typing import Any

import pytest

from arras import (
    Arras,
    Conflict,
    Invalid,
    NotYetCurrent,
    Placement,
    Principal,
    Revision,
    Unavailable,
    Unsupported,
)
from arras.conformance import run_corpus
from arras.conformance.fakes import MemoryReplicaHarness, MemoryStoreHarness
from arras.fakes import FakeAccess, MemoryReplica, MemoryStore
from arras.results import (
    BackendInfo,
    BackendStatus,
    BatchReceipt,
    ItemResult,
    Receipt,
    Validation,
)
from arras.serialize import jsonable
from arras.testing import example_module

ADD = "catalog.AddUseCase"
SQL = "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100"


class Upstream:
    """A backend that only provides: it applies the actions bound to it and serves no read.

    It stands for another system whose results reach a reader later. It records what it applied."""

    def __init__(self, name: str = "upstream") -> None:
        self.name = name
        self.applied: list[tuple[str, list[str], bool]] = []

    def describe(self) -> BackendInfo:
        return BackendInfo(self.name, ("provider",), {})

    def catalog(self, principal: Principal) -> dict[str, Any]:
        return {}

    def status(self) -> BackendStatus:
        return BackendStatus(True)

    def query(self, *a: Any, **k: Any) -> Any:
        raise AssertionError("a provider-only backend serves no read")

    def reached(self, principal: Principal, token: str) -> bool:
        raise AssertionError("a provider-only backend places no token")

    def attach(self, *a: Any, **k: Any) -> Any:
        raise AssertionError("a provider-only backend holds no module")

    def _receipt(self, plan: Any) -> Receipt:
        n = len(self.applied)
        return Receipt(plan.action, (), 0, 0, 0, 0, 0, f"{self.name}:{n}", group=f"g{n}")

    def apply(
        self, principal: Principal, plan: Any, *, idempotency_key: str | None, dry_run: bool = False
    ) -> Receipt | Validation:
        self.applied.append((plan.action, [e.ref.key for e in plan.effects], dry_run))
        if dry_run:
            return Validation(True, (), (), (), None, None)
        return self._receipt(plan)

    def apply_batch(
        self, principal: Principal, plans: Any, *, atomic: bool, idempotency_key: Any, **kw: Any
    ) -> BatchReceipt:
        items = tuple(ItemResult(i, self._receipt_for(p, principal)) for i, p in enumerate(plans))
        return BatchReceipt(
            plans[0].action,
            atomic,
            items,
            len(items),
            0,
            items[-1].receipt.token if items[-1].receipt else None,
        )

    def _receipt_for(self, plan: Any, principal: Principal) -> Receipt:
        r = self.apply(principal, plan, idempotency_key=None)
        assert isinstance(r, Receipt)
        return r


def document(module: str = "catalog") -> str:
    return example_module().replace('"catalog"', json.dumps(module))


class Stack:
    """A record store "primary", a replica "mirror" and a provider-only "upstream"."""

    def __init__(self, placement: Placement | None, *, register: bool = True, **kw: Any) -> None:
        self.access = FakeAccess()
        self.primary = MemoryStore(self.access, "primary")
        self.mirror = MemoryReplica(self.primary, self.access, "mirror")
        self.upstream = Upstream()
        self.root = self.access.grant("root", "catalog", "read", "write", "schema", admin=True)
        self.alice = self.access.grant("alice", "catalog", "read", "write")
        self.backends = {"primary": self.primary, "mirror": self.mirror, "upstream": self.upstream}
        self.h = Arras.start(
            self.backends,
            admin=self.root,
            placement={"catalog": placement} if placement else None,
            **kw,
        )
        self.o = self.h.session(self.alice)
        self.admin = self.h.session(self.root)
        if register:
            self.admin.registry().register(document())


def codes(e: pytest.ExceptionInfo[Invalid]) -> set[str]:
    return {v.code for v in e.value.violations}


def test_modules_have_their_own_record_stores() -> None:
    access = FakeAccess()
    alpha = MemoryStore(access, "alpha")
    beta = MemoryStore(access, "beta")
    root = access.grant("root", "*", "read", "write", "schema", admin=True)
    alice = access.grant("alice", "catalog", "read", "write")
    access.grant("alice", "ledger", "read", "write")
    h = Arras.start(
        {"alpha": alpha, "beta": beta},
        admin=root,
        placement={"catalog": Placement("alpha"), "ledger": Placement("beta")},
    )
    reg = h.session(root).registry()
    reg.register(document("catalog"))
    reg.register(document("ledger"))
    assert alpha.modules.keys() == {"catalog"} and beta.modules.keys() == {"ledger"}
    o = h.session(alice)
    o.invoke("catalog.AddUseCase", {"code": "c1", "name": "C", "workArea": "x"})
    o.invoke("ledger.AddUseCase", {"code": "l1", "name": "L", "workArea": "x"})
    assert (alpha.count("catalog.UseCase"), beta.count("catalog.UseCase")) == (1, 0)
    assert (alpha.count("ledger.UseCase"), beta.count("ledger.UseCase")) == (0, 1)
    for module, backend in (("catalog", "alpha"), ("ledger", "beta")):
        ans = o.query(module, f"SELECT u.code FROM {module}.UseCase u ORDER BY u.code LIMIT 100")
        assert ans.freshness.backend == backend
        assert ans.revision == Revision({backend: 1})
    placed = {m.name: m.placement.record for m in o.describe()}
    assert placed == {"catalog": "alpha", "ledger": "beta"}


def test_replicas_are_tried_in_order() -> None:
    access = FakeAccess()
    primary = MemoryStore(access, "primary")
    first = MemoryReplica(primary, access, "first")
    second = MemoryReplica(primary, access, "second")
    root = access.grant("root", "catalog", "read", "write", "schema", admin=True)
    alice = access.grant("alice", "catalog", "read", "write")
    h = Arras.start(
        {"primary": primary, "first": first, "second": second},
        admin=root,
        default_placement=Placement("primary", ("first", "second")),
    )
    h.session(root).registry().register(document())
    o = h.session(alice)
    o.invoke(ADD, {"code": "a", "name": "A", "workArea": "x"})
    first.feed()
    second.feed()
    assert o.query("catalog", SQL, consistency="bulk").freshness.backend == "first"
    first.modules.clear()  # the first holds no types, so it does not serve this read
    assert o.query("catalog", SQL, consistency="bulk").freshness.backend == "second"
    first.modules.update(second.modules)
    first.available = False  # a down replica raises; the next one is not quietly asked
    with pytest.raises(Unavailable) as e:
        o.query("catalog", SQL, consistency="bulk")
    assert e.value.backend == "first"
    primary.available = False  # and the record store does not stand in either
    with pytest.raises(Unavailable) as e:
        o.query("catalog", SQL, consistency="bulk")
    assert e.value.backend == "first"


def test_module_without_placement_is_refused() -> None:
    s = Stack(None, register=False)
    with pytest.raises(Invalid) as e:
        s.admin.registry().register(document())
    assert codes(e) == {"invalid_placement"}
    with pytest.raises(Invalid) as e:
        s.admin.registry().attach(document())
    assert codes(e) == {"invalid_placement"}
    # a backend that holds the module does not make it served: the host placed it nowhere
    placed = Stack(Placement("primary", ("mirror",)))
    bare = Arras.start(placed.backends, admin=placed.root)
    assert bare.session(placed.alice).describe() == []
    assert bare.session(placed.alice).modules() == []
    with pytest.raises(Invalid):
        bare.session(placed.alice).query("catalog", SQL)
    with pytest.raises(Invalid):
        bare.session(placed.alice).invoke(ADD, {"code": "a", "name": "A", "workArea": "x"})


@pytest.mark.parametrize(
    "placement",
    [
        Placement("nowhere"),  # a record store that is not configured
        Placement("primary", ("nowhere",)),  # a replica that is not configured
        Placement("primary", providers={ADD: "nowhere"}),  # a provider that is not configured
        Placement("primary", ("mirror", "mirror")),  # a reader named twice
        Placement("primary", ("primary",)),  # the record store named again as a replica
        Placement("primary", ("upstream",)),  # a replica that is not a reader
        Placement("upstream"),  # a record store that is not a reader
        Placement("primary", providers={ADD: "mirror"}),  # a provider that cannot provide
    ],
    ids=[
        "record-unconfigured",
        "replica-unconfigured",
        "provider-unconfigured",
        "reader-twice",
        "record-as-replica",
        "replica-not-a-reader",
        "record-not-a-reader",
        "provider-cannot-provide",
    ],
)
def test_placement_names_must_be_configured_and_of_the_right_kind(placement: Placement) -> None:
    s = Stack(placement, register=False)
    with pytest.raises(Invalid) as e:
        s.admin.registry().register(document())
    assert "invalid_placement" in codes(e)
    with pytest.raises(Invalid) as e:
        s.admin.registry().attach(document())
    assert "invalid_placement" in codes(e)
    assert s.primary.modules == {}  # nothing was registered


def test_revision_is_keyed_by_backend() -> None:
    s = Stack(Placement("primary", ("mirror",)))
    [m] = s.o.describe()
    assert m.revision == Revision({"primary": 1})
    assert m.revision["primary"] == 1 and m.revision["mirror"] is None
    assert dict(m.revision.by_backend) == {"primary": 1}
    assert jsonable(m.revision) == {"primary": 1}
    assert Revision.from_wire({"primary": 1, "mirror": None})["primary"] == 1
    for bad in ({"primary": 1.5}, {"primary": True}, {"": 1}, {"primary": [1]}):
        with pytest.raises(ValueError):
            Revision.from_wire(bad)
    s.mirror.feed()
    assert s.o.query("catalog", SQL, consistency="bulk").revision["primary"] == 1


def test_expected_revision_checks_only_the_backends_named() -> None:
    s = Stack(Placement("primary", ("mirror",)))
    inputs = {"code": "a", "name": "A", "workArea": "x"}
    assert s.o.validate(ADD, inputs, expected_revision={"primary": 1}).ok
    s.o.invoke(ADD, {**inputs, "code": "b"}, expected_revision={"primary": 1})  # the rest unchecked
    s.o.invoke(ADD, {**inputs, "code": "c"}, expected_revision=Revision({"primary": 1}))
    s.o.invoke(ADD, {**inputs, "code": "d"}, expected_revision={"primary": 1, "mirror": None})
    s.o.invoke(ADD, {**inputs, "code": "e"}, expected_revision={})
    for stale in ({"primary": 2}, {"primary": None}, {"mirror": 1}, {"upstream": 1}):
        with pytest.raises(Conflict):
            s.o.invoke(ADD, {**inputs, "code": "z"}, expected_revision=stale)
        with pytest.raises(Conflict):
            s.o.validate(ADD, {**inputs, "code": "z"}, expected_revision=stale)
        with pytest.raises(Conflict):
            s.o.invoke_batch(ADD, [{**inputs, "code": "z"}], expected_revision=stale)
    with pytest.raises(Invalid) as e:
        s.o.invoke(ADD, inputs, expected_revision={"primary": 1.5})
    assert codes(e) == {"type"}
    assert s.primary.count("catalog.UseCase") == 4  # nothing was applied under a stale revision


def test_memory_adapter_passes_the_corpus() -> None:
    for harness in (MemoryStoreHarness, MemoryReplicaHarness):
        report = run_corpus(harness)
        assert report.passed and report.results
        assert [r.message for r in report.failed] == []


def test_action_is_routed_to_its_provider() -> None:
    s = Stack(Placement("primary", ("mirror",), {ADD: "upstream"}))
    inputs = {"code": "a", "name": "A", "workArea": "x"}
    r = s.o.invoke(ADD, inputs)
    assert r.token == "upstream:1"  # the provider's own position
    assert s.upstream.applied == [(ADD, ["a"], False)]
    assert s.primary.count("catalog.UseCase") == 0  # not run on the record store
    v = s.o.validate(ADD, {**inputs, "code": "b"})
    assert v.ok and s.upstream.applied[-1][2] is True  # a dry run goes to the same provider
    b = s.o.invoke_batch(ADD, [{**inputs, "code": "c"}, {**inputs, "code": "d"}])
    assert b.succeeded == 2 and [i.receipt.token for i in b.items if i.receipt] == [
        "upstream:3",
        "upstream:4",
    ]
    assert s.primary.count("catalog.UseCase") == 0
    # an action the placement does not bind runs on the record store
    s.admin.import_records(
        "catalog",
        [{"type": "UseCase", "key": "u", "properties": {"name": "U", "workArea": "x"}}],
        load_id="L",
    )
    other = s.o.invoke("catalog.AddSolution", {"code": "s", "name": "S", "useCase": "u"})
    assert other.token.startswith("fake:") and s.primary.count("catalog.Solution") == 1
    assert len(s.upstream.applied) == 4  # nothing else reached it


def test_latest_is_served_only_by_the_record_store() -> None:
    s = Stack(Placement("primary", ("mirror",), {ADD: "upstream"}))
    s.o.invoke("catalog.AddUseCase", {"code": "a", "name": "A", "workArea": "x"})
    s.primary.import_records(
        s.root,
        "catalog",
        [{"type": "UseCase", "key": "u1", "properties": {"name": "U", "workArea": "x"}}],
        load_id="L",
        initiated_by="root",
    )
    s.mirror.feed()
    assert (
        s.o.query("catalog", SQL).freshness.backend == "primary"
    )  # a fed replica does not take `latest`
    assert s.o.query("catalog", SQL, consistency="bulk").freshness.backend == "mirror"
    s.primary.available = False
    with pytest.raises(Unavailable) as e:
        s.o.query("catalog", SQL)
    assert e.value.backend == "primary"
    assert s.o.query("catalog", SQL, consistency="bulk").freshness.backend == "mirror"
    s.primary.available = True
    s.mirror.available = False
    assert (
        s.o.query("catalog", SQL).freshness.backend == "primary"
    )  # and a replica's outage does not touch it


def test_provider_only_backend_runs_actions() -> None:
    s = Stack(Placement("primary", ("mirror",), {ADD: "upstream"}), wait_bound=0.0)
    info = s.upstream.describe()
    assert info.provides and not info.reads and info.roles == ("provider",)
    assert s.h.status()["upstream"].available
    r = s.o.invoke(ADD, {"code": "a", "name": "A", "workArea": "x"})
    assert isinstance(r, Receipt) and s.upstream.applied
    # it is not a reader: describe and reads name the module's readers only
    [m] = s.o.describe()
    assert set(m.status) == {"primary", "mirror"}
    assert set(m.entity_types[0].capabilities) == {"primary", "mirror"}
    # a reader that cannot place the provider's position does not reach it
    with pytest.raises(NotYetCurrent) as e:
        s.o.query("catalog", SQL, at_least=r.token)
    assert (e.value.token, e.value.backend) == (r.token, "primary")
    # a provider-only backend cannot hold a module's record
    bad = Stack(Placement("upstream"), register=False)
    with pytest.raises(Invalid) as e2:
        bad.admin.registry().register(document())
    assert "invalid_placement" in codes(e2)


def test_reader_only_backend_cannot_be_a_provider() -> None:
    s = Stack(Placement("primary", ("mirror",)))
    reader_only = MemoryReplica(s.primary, s.access, "mirror").describe()
    assert reader_only.reads and not reader_only.provides
    # refused when the host places it so ...
    bound = Stack(Placement("primary", ("mirror",), {ADD: "mirror"}), register=False)
    with pytest.raises(Invalid) as e:
        bound.admin.registry().register(document())
    assert "invalid_placement" in codes(e)
    # ... and Unsupported at invoke if a host reconfigures a registered module to bind it
    s.h.placements["catalog"] = Placement("primary", ("mirror",), {ADD: "mirror"})
    with pytest.raises(Unsupported) as u:
        s.o.invoke(ADD, {"code": "a", "name": "A", "workArea": "x"})
    assert u.value.supported == ["mirror does not apply actions"]
    with pytest.raises(Unsupported):
        s.o.validate(ADD, {"code": "a", "name": "A", "workArea": "x"})
    assert s.primary.count("catalog.UseCase") == 0
