# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The Truss adapter's `apply_batch` (TR-08), always on: the scripted assembly of
`tests/test_truss_plan.py` stands in for Truss. `tests/test_truss_apply.py` runs the corpus batch
cases against a real Truss."""

from __future__ import annotations

from typing import Any

import pytest

from arras.actions import Create, Delete, Link, Plan, Unlink, Update
from arras.adapters.truss import TrussBackend
from arras.adapters.truss.plan import Planner, materialize
from arras.adapters.truss.values import document_ids
from arras.errors import (
    Conflict,
    Invalid,
    PreconditionFailed,
    Refused,
    Unavailable,
    Unsupported,
)
from arras.types import Principal
from test_truss_plan import (
    DOC,
    MODULE,
    ApplyRig,
    Changed,
    Created,
    Deleted,
    FailedPrecondition,
    FakeLookups,
    GroupOperationFailure,
    PreconditionFailedCarrier,
    RecordingWire,
    Unchanged,
    applied,
    artifact_of,
    create_plan,
    failed,
    ident,
    planner,
    pre_id,
    replayed,
    sol,
    uc,
)
from test_truss_registry import ALICE, error


def batch(rig: ApplyRig, plans: list[Plan], **kw: Any) -> Any:
    kw.setdefault("atomic", True)
    kw.setdefault("idempotency_key", "k")
    return rig.backend().apply_batch(ALICE, plans, **kw)


def many(start: int, stop: int) -> Plan:
    effects = tuple(create_plan(f"u{i}").effects[0] for i in range(start, stop))
    return Plan("catalog.AddUseCase", (), effects)


def creates(*keys: str) -> list[Plan]:
    return [create_plan(k) for k in keys]


# -- shape


def test_a_batch_of_no_items_or_too_many_or_two_actions_is_invalid_before_any_connection() -> None:
    rig = ApplyRig()
    for plans, code in (
        ([], "bound"),
        (creates(*[f"u{i}" for i in range(101)]), "bound"),
        ([create_plan("a"), Plan("catalog.Other", (), create_plan("b").effects)], "mixed_actions"),
    ):
        with pytest.raises(Invalid) as raised:
            batch(rig, plans)
        assert (
            raised.value.violations[0].code == code and raised.value.violations[0].path == "items"
        )
    assert rig.conns == []


def test_a_batch_with_no_token_never_connects() -> None:
    rig = ApplyRig()
    with pytest.raises(Refused) as raised:
        rig.backend().apply_batch(
            Principal("alice", ""), creates("a"), atomic=True, idempotency_key=None
        )
    assert raised.value.reason == "token_expired" and rig.conns == []


def test_an_atomic_batch_over_a_group_bound_is_unsupported_before_any_call() -> None:
    rig = ApplyRig()
    with pytest.raises(Unsupported):
        batch(rig, [many(0, 513), many(513, 1026)])
    plans = [
        Plan("catalog.X", tuple(pre_id(f"p{i}", "exists", ref=uc("a")) for i in range(1600)), ()),
        Plan("catalog.X", tuple(pre_id(f"q{i}", "exists", ref=uc("a")) for i in range(1600)), ()),
    ]
    with pytest.raises(Unsupported):
        batch(rig, plans)
    assert rig.conns == []


# -- atomic


def test_an_atomic_batch_is_one_group_one_request_one_commit_and_one_token() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [applied(Created(), Created())]
    got = batch(rig, creates("a", "b"))
    assert rig.assembly.log.count("apply") == 1 and rig.assembly.log.count("prepare_group") == 1
    [(inp, req, _)] = rig.assembly.presented
    assert req.rid == "catalog.AddUseCase#atomic:k"
    assert [op[0] for op in inp.ops] == ["create", "create"]
    assert [op[3] for op in inp.ops] == ["e1", "e2"]  # one alias counter for the group
    [first] = rig.writes
    assert first.log[-1] == "commit"
    assert got.atomic and (got.succeeded, got.failed, got.token) == (2, 0, "token-1")
    assert {i.receipt.token for i in got.items} == {"token-1"}
    assert len({i.receipt.group for i in got.items}) == 1
    assert [i.receipt.refs[0].key for i in got.items] == ["a", "b"]
    assert not any(i.receipt.replayed for i in got.items)


def test_a_keyed_repeat_of_an_atomic_batch_replays_every_item() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [replayed(Created(), Created(), token="orig")]
    got = batch(rig, creates("a", "b"))
    assert [i.receipt.replayed for i in got.items] == [True, True]
    assert got.token == "orig" and len(rig.writes) == 1 and "commit" not in rig.writes[0].log


def test_a_keyless_atomic_batch_gets_a_fresh_request_id() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [applied(Created())]
    batch(rig, creates("a"), idempotency_key=None)
    assert rig.assembly.presented[0][1].rid != "catalog.AddUseCase#atomic:None"


def test_an_unknown_commit_of_an_atomic_batch_is_recovered_by_the_same_request() -> None:
    rig = ApplyRig()
    rig.commit_failures = [True]
    rig.assembly.outcomes = [
        applied(Created(), Created()),
        replayed(Created(), Created(), token="landed"),
    ]
    got = batch(rig, creates("a", "b"))
    assert got.token == "landed" and not any(i.receipt.replayed for i in got.items)
    assert rig.assembly.presented[0][:2] == rig.assembly.presented[1][:2]


def test_a_failed_atomic_batch_commits_nothing_and_names_the_item() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [
        failed(
            GroupOperationFailure(
                "1",
                artifact_of(code="key_conflict"),
            )
        )
    ]
    rig.assembly.objects[("UseCase", "b")] = ident("UseCase", "b")
    with pytest.raises(Conflict) as raised:
        batch(rig, creates("a", "b", "c"))
    assert raised.value.reason == "exists" and "item 1" in raised.value.__notes__
    [write] = rig.writes
    assert "commit" not in write.log and write.log[-1] == "rollback"


def test_a_key_conflict_reported_at_a_runs_first_create_names_the_create_that_collided() -> None:
    """Truss 0.0.44 inserts independent creates as one statement and reports the first of them
    whichever collided, so the adapter reads the run again and names the create whose key exists."""
    rig = ApplyRig()
    rig.assembly.outcomes = [failed(GroupOperationFailure("0", artifact_of(code="key_conflict")))]
    rig.assembly.objects[("UseCase", "c")] = ident("UseCase", "c")
    with pytest.raises(Conflict) as raised:
        batch(rig, creates("a", "b", "c"))
    assert raised.value.reason == "exists"
    assert "catalog.UseCase" in str(raised.value) and "'c'" in str(raised.value)
    assert "item 2" in raised.value.__notes__


def test_a_key_conflict_with_no_create_holding_its_key_stands_at_the_reported_one() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [failed(GroupOperationFailure("1", artifact_of(code="key_conflict")))]
    with pytest.raises(Conflict) as raised:
        batch(rig, creates("a", "b", "c"))
    assert raised.value.reason == "deleted"
    assert "'b'" in str(raised.value) and "item 1" in raised.value.__notes__


def test_a_failing_effect_names_the_item_and_the_effect() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [failed(GroupOperationFailure("1", artifact_of(code="invalid_input")))]
    with pytest.raises(Invalid) as raised:
        batch(rig, creates("a", "b"))
    assert raised.value.violations[0].path == "items[1].effects[0]"
    assert "item 1" in raised.value.__notes__


def test_conditions_are_sent_by_item_and_told_back_under_the_callers_ids() -> None:
    rig = ApplyRig()
    plans = [
        Plan("catalog.X", (pre_id("fresh", "exists", ref=uc("a")),), create_plan("n1").effects),
        Plan("catalog.X", (pre_id("fresh", "exists", ref=uc("b")),), create_plan("n2").effects),
    ]
    rig.assembly.outcomes = [
        failed(
            PreconditionFailedCarrier(
                (
                    FailedPrecondition("1:fresh", "second", "object_exists"),
                    FailedPrecondition("0:fresh", "first", "object_exists"),
                )
            )
        )
    ]
    with pytest.raises(PreconditionFailed) as raised:
        batch(rig, plans)
    # one id twice in a group is refused by Truss, so the ids sent differ; only the first failing
    # item is told, as the memory adapter stops at it
    assert [(f.id, f.reason) for f in raised.value.failures] == [("fresh", "first")]
    assert "item 0" in raised.value.__notes__
    sent = [c[1] for c in rig.assembly.presented[0][0].preconditions]
    assert sent == ["0:fresh", "1:fresh"]


def test_a_later_items_absent_on_a_key_an_earlier_item_creates_fails_in_the_planner() -> None:
    rig = ApplyRig()
    plans = [
        create_plan("same"),
        Plan(
            "catalog.AddUseCase",
            (pre_id("fresh", "absent", type="catalog.UseCase", key="same"),),
            create_plan("same").effects,
        ),
    ]
    rig.assembly.outcomes = [applied(Created(), Created())]
    with pytest.raises(PreconditionFailed) as raised:
        batch(rig, plans)
    assert [f.id for f in raised.value.failures] == ["fresh"]
    assert "item 1" in raised.value.__notes__


def test_a_duplicate_create_in_one_batch_is_exists() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [failed(GroupOperationFailure("1", artifact_of(code="key_conflict")))]
    with pytest.raises(Conflict) as raised:
        batch(rig, creates("same", "same"))
    assert raised.value.reason == "exists"


def test_items_are_planned_as_one_group_with_a_version_each() -> None:
    plans = [
        Plan("catalog.X", (), (Create(uc("n"), {"name": "N"}),)),
        Plan(
            "catalog.X",
            (),
            (Update(uc("n"), {"name": "M"}), Link("addresses", sol("sol-1"), uc("n"))),
        ),
        Plan("catalog.X", (), (Update(uc("n"), {"name": "O"}),)),
    ]

    lookups = FakeLookups({sol("sol-1"): ident("Solution", "sol-1")})

    wire = RecordingWire()
    pl = Planner(wire, MODULE, document_ids(DOC, "catalog"), lookups, plans[0], items=plans)
    pl.operations()
    ops = [materialize(wire, o) for o in pl.ops]
    assert [o[0] for o in ops] == ["create", "update", "link", "update"]  # not merged across items
    assert ops[1][1] == ("alias", "e1") and ops[3][1] == ("alias", "e1")
    assert [o.item for o in pl.ops] == [0, 1, 1, 2]
    assert [len(b.effect_op) for b in pl.builts] == [1, 2, 1]
    assert all(b.ops is pl.ops and b.batch for b in pl.builts)


def test_per_item_receipts_count_their_own_effects_and_versions() -> None:
    rig = ApplyRig()
    rig.assembly.objects[("UseCase", "old")] = ident("UseCase", "old")
    plans = [
        Plan("catalog.X", (), (Create(uc("n"), {"name": "N"}),)),
        Plan("catalog.X", (), (Update(uc("n"), {"name": "M"}),)),
        Plan("catalog.X", (), (Update(uc("old"), {"name": "same"}), Delete(uc("n")))),
    ]
    results = (Created(), Changed(), Unchanged("4"), Deleted("3"))
    rig.assembly.outcomes = [applied(*results)]
    got = batch(rig, plans)
    [a, b, c] = [i.receipt for i in got.items]
    assert (a.created, a.refs[0].version) == (1, 1)
    assert (b.updated, b.refs[0].version) == (1, 2)
    assert c.updated == 0 and c.deleted == 1
    assert (
        len({r.group for r in (a, b, c)}) == 1
    )  # the group is named from the whole group's events


def test_generated_keys_differ_between_items_and_repeat_for_a_key() -> None:
    def drafts() -> list[Plan]:
        out = []
        for n in range(2):
            made = type(sol("g"))(sol("g").type, f"random-{n}", generated=True)
            out.append(
                Plan("catalog.DraftSolution", (), (Create(made, {"name": "D"}, generated=True),))
            )
        return out

    rig = ApplyRig()
    rig.assembly.outcomes = [applied(Created(), Created())]
    first = batch(rig, drafts())
    keys = [i.receipt.refs[0].key for i in first.items]
    assert keys[0] != keys[1]
    rig.assembly.outcomes = [replayed(Created(), Created())]
    again = batch(rig, drafts())
    assert [i.receipt.refs[0].key for i in again.items] == keys


# -- independent


def test_an_independent_batch_is_a_call_and_a_request_per_item() -> None:
    rig = ApplyRig()
    each = [applied(Created())]
    rig.assembly.outcomes = each + each
    got = batch(rig, creates("a", "b"), atomic=False)
    rids = [r.rid for _, r, _ in rig.assembly.presented]
    assert rids == ["catalog.AddUseCase#0:k", "catalog.AddUseCase#1:k"]
    assert len(rig.writes) == 2  # an item is one call, one group and one commit
    assert not got.atomic and (got.succeeded, got.failed) == (2, 0)
    assert got.token == got.items[1].receipt.token


def test_a_batch_item_never_shares_a_request_id_with_a_single_apply_of_a_key_like_it() -> None:
    # a caller's key may hold any text, `k#1` included: the item's index is in the action's part
    # of the id, which a key cannot reach (an action name holds no `#` and the key follows the
    # first `:`)
    rig = ApplyRig()
    each = [applied(Created())]
    rig.assembly.outcomes = each + each
    batch(rig, creates("a", "b"), atomic=False, idempotency_key="k")
    items = {r.rid for _, r, _ in rig.assembly.presented}
    single = ApplyRig()
    single.assembly.outcomes = each
    single.backend().apply(ALICE, create_plan("a"), idempotency_key="k#1")
    [(_, one, _)] = single.assembly.presented
    assert one.rid == "catalog.AddUseCase:k#1" and one.rid not in items
    atomic = ApplyRig()
    atomic.assembly.outcomes = [applied(Created())]
    batch(atomic, creates("a"), idempotency_key="k")
    assert atomic.assembly.presented[0][1].rid not in items | {"catalog.AddUseCase:k"}


def test_keyless_independent_items_have_fresh_request_ids() -> None:
    rig = ApplyRig()
    each = [applied(Created())]
    rig.assembly.outcomes = each + each
    batch(rig, creates("a", "b"), atomic=False, idempotency_key=None)
    rids = {r.rid for _, r, _ in rig.assembly.presented}
    assert len(rids) == 2


def test_an_over_long_key_keeps_the_items_distinct() -> None:
    rig = ApplyRig()
    each = [applied(Created())]
    rig.assembly.outcomes = each + each
    batch(rig, creates("a", "b"), atomic=False, idempotency_key="k" * 2000)
    rids = {r.rid for _, r, _ in rig.assembly.presented}
    assert len(rids) == 2 and all(len(r.encode()) <= 1024 for r in rids)


def refusing() -> Any:
    return failed(PreconditionFailedCarrier((FailedPrecondition("fresh", "held", "key_absent"),)))


def test_a_refused_item_is_reported_and_the_others_commit() -> None:
    rig = ApplyRig()
    plans = creates("a", "b", "c")
    plans[1] = Plan(
        "catalog.AddUseCase", (pre_id("fresh", "exists", ref=uc("x")),), plans[1].effects
    )
    rig.assembly.outcomes = [
        applied(Created()),
        refusing(),
        applied(Created()),
    ]
    got = batch(rig, plans, atomic=False)
    assert (got.succeeded, got.failed) == (2, 1)
    assert [type(i.refusal).__name__ for i in got.items] == [
        "NoneType",
        "PreconditionFailed",
        "NoneType",
    ]
    assert got.items[1].receipt is None and got.token == got.items[2].receipt.token


def test_stop_on_error_stops_at_the_first_refusal() -> None:
    rig = ApplyRig()
    plans = creates("a", "b", "c")
    plans[0] = Plan(
        "catalog.AddUseCase", (pre_id("fresh", "exists", ref=uc("x")),), plans[0].effects
    )
    rig.assembly.outcomes = [refusing()]
    got = batch(rig, plans, atomic=False, stop_on_error=True)
    assert len(got.items) == 1 and (got.succeeded, got.failed, got.token) == (0, 1, None)


@pytest.mark.parametrize(
    "outage", [Unavailable("truss", "unreachable"), Refused("truss", "apply", "no_access")]
)
def test_an_error_that_is_not_the_items_stops_the_whole_call(outage: Exception) -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [applied(Created())]
    backend = rig.backend()
    real = backend._applier.apply  # type: ignore[union-attr]
    calls: list[int] = []

    def flaky(*a: Any, **k: Any) -> Any:
        calls.append(1)
        if len(calls) == 2:
            raise outage
        return real(*a, **k)

    backend._applier.apply = flaky  # type: ignore[union-attr, method-assign]
    with pytest.raises(type(outage)):
        backend.apply_batch(ALICE, creates("a", "b", "c"), atomic=False, idempotency_key="k")
    assert len(calls) == 2


def test_an_unsupported_item_is_told_before_any_item_is_applied() -> None:
    rig = ApplyRig()
    plans = creates("a") + [
        Plan("catalog.AddUseCase", (), tuple(create_plan(f"u{i}").effects[0] for i in range(1025)))
    ]
    with pytest.raises(Unsupported):
        batch(rig, plans, atomic=False)
    assert rig.conns == []


def test_a_batch_with_no_connection_source_is_unavailable() -> None:

    with pytest.raises(Unavailable) as raised:
        TrussBackend("truss").apply_batch(ALICE, creates("a"), atomic=True, idempotency_key=None)
    assert raised.value.reason == "not_configured"


def test_a_retry_is_not_swallowed_into_an_item() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [error("retry")]
    with pytest.raises(Unavailable) as raised:
        batch(rig, creates("a"), atomic=True)
    assert raised.value.reason == "busy"
    _ = planner  # the planner helper is shared with the plan tests


# -- conditions on what an earlier item touched are decided in the planner, or refused


def gated(
    first: tuple[Any, ...], p: Any, world: FakeLookups | None = None
) -> tuple[list[Any], list[Any]]:
    """The conditions sent and decided for a second item carrying `p`, after a first item of `first`."""
    plans = [Plan("catalog.X", (), first), Plan("catalog.X", (p,), ())]
    lookups = world or FakeLookups(
        {
            sol("sol-1"): ident("Solution", "sol-1"),
            uc("uc-1"): ident("UseCase", "uc-1"),
            uc("uc-2"): ident("UseCase", "uc-2"),
        }
    )
    pl = Planner(
        RecordingWire(), MODULE, document_ids(DOC, "catalog"), lookups, plans[0], items=plans
    )
    pl.operations()
    return pl.preconditions(frozenset())


def cond(op: str, **args: Any) -> Any:
    return pre_id("c", op, **args)


@pytest.mark.parametrize(("value", "holds"), [("B", True), ("A", False)])
def test_property_equals_after_an_update_is_decided_from_the_planned_value(
    value: str, holds: bool
) -> None:
    sent, static = gated(
        (Update(uc("uc-1"), {"name": "B"}),),
        cond("property_equals", ref=uc("uc-1"), property="name", value=value),
    )
    assert sent == [] and (static == []) is holds
    assert holds or [f.id for _, f in static] == ["c"]


def test_property_equals_after_an_unset_or_a_create_compares_the_planned_values() -> None:
    args = {"ref": uc("uc-1"), "property": "name", "value": None}
    assert gated((Update(uc("uc-1"), {}, ("name",)),), cond("property_equals", **args)) == ([], [])
    created = (Create(uc("n"), {"name": "N"}),)
    ok = cond("property_equals", ref=uc("n"), property="name", value="N")
    assert gated(created, ok) == ([], [])
    other = cond("property_equals", ref=uc("n"), property="workArea", value="x")
    assert gated(created, other)[1][0][1].id == "c"


def test_property_equals_on_a_property_an_earlier_update_left_alone_is_sent() -> None:
    sent, static = gated(
        (Update(uc("uc-1"), {"name": "B"}),),
        cond("property_equals", ref=uc("uc-1"), property="workArea", value="x"),
    )
    assert static == [] and [c[0] for c in sent] == ["equals"]


def test_exists_after_a_create_passes_and_after_a_delete_fails() -> None:
    assert gated((Create(uc("n"), {"name": "N"}),), cond("exists", ref=uc("n"))) == ([], [])
    sent, static = gated((Delete(uc("uc-2")),), cond("exists", ref=uc("uc-2")))
    assert sent == [] and [f.id for _, f in static] == ["c"]


def test_absent_after_a_delete_passes_and_after_a_create_fails() -> None:
    assert gated((Delete(uc("uc-2")),), cond("absent", type="catalog.UseCase", key="uc-2")) == (
        [],
        [],
    )
    _, static = gated(
        (Create(uc("n"), {"name": "N"}),), cond("absent", type="catalog.UseCase", key="n")
    )
    assert [f.id for _, f in static] == ["c"]


def test_a_count_after_a_link_is_sent_with_the_shifted_range() -> None:
    link = (Link("addresses", sol("sol-1"), uc("uc-1")),)
    args = {"relationship": "addresses", "source": sol("sol-1"), "cmp": "=", "n": 3}
    [sent], static = gated(link, cond("count", **args))
    assert static == [] and sent[5:] == ("outgoing", 2, 2)
    [sent], _ = gated(link, cond("count", **{**args, "cmp": ">=", "n": 1}))
    assert sent[5:] == ("outgoing", 0, None)  # the low end is clamped at 0
    _, static = gated(link, cond("count", **{**args, "cmp": "=", "n": 0}))
    assert [f.id for _, f in static] == ["c"]  # the high end goes below 0
    # the inverse relationship counts at the other end
    inverse = {"relationship": "addressedBy", "source": uc("uc-1"), "cmp": "=", "n": 2}
    [sent], _ = gated(link, cond("count", **inverse))
    assert sent[5:] == ("incoming", 1, 1)


def test_a_count_after_an_unlink_shifts_up_and_after_a_link_and_unlink_not_at_all() -> None:
    args = {"relationship": "addresses", "source": sol("sol-1"), "cmp": "=", "n": 1}
    [sent], _ = gated((Unlink("addresses", sol("sol-1"), uc("uc-1")),), cond("count", **args))
    assert sent[5:] == ("outgoing", 2, 2)
    both = (
        Link("addresses", sol("sol-1"), uc("uc-2")),
        Unlink("addresses", sol("sol-1"), uc("uc-2")),
    )
    [sent], _ = gated(both, cond("count", **args))
    assert sent[5:] == ("outgoing", 1, 1)


def test_a_count_of_an_object_an_earlier_item_creates_is_decided_from_the_planned_edges() -> None:
    made = (Create(sol("s"), {"name": "S"}), Link("addresses", sol("s"), uc("uc-1")))
    args = {"relationship": "addresses", "source": sol("s")}
    assert gated(made, cond("count", **args, cmp="=", n=1)) == ([], [])
    _, static = gated(made, cond("count", **args, cmp="=", n=0))
    assert [f.id for _, f in static] == ["c"]


def test_no_relationship_with_a_target_after_a_link_fails_and_after_an_unlink_passes() -> None:
    args = {"relationship": "addresses", "source": sol("sol-1"), "target": uc("uc-1")}
    _, static = gated(
        (Link("addresses", sol("sol-1"), uc("uc-1")),), cond("no_relationship", **args)
    )
    assert [f.id for _, f in static] == ["c"]
    inverse = {"relationship": "addressedBy", "source": uc("uc-1"), "target": sol("sol-1")}
    _, static = gated(
        (Link("addresses", sol("sol-1"), uc("uc-1")),), cond("no_relationship", **inverse)
    )
    assert [f.id for _, f in static] == ["c"]
    gone = (Unlink("addresses", sol("sol-1"), uc("uc-1")),)
    assert gated(gone, cond("no_relationship", **args)) == ([], [])
    sent, static = gated(
        (Link("addresses", sol("sol-1"), uc("uc-2")),), cond("no_relationship", **args)
    )
    assert static == [] and [c[0] for c in sent] == ["no-edge"]


def test_no_relationship_without_a_target_is_a_shifted_exact_count() -> None:
    args = {"relationship": "addresses", "source": sol("sol-1")}
    [sent], _ = gated(
        (Unlink("addresses", sol("sol-1"), uc("uc-1")),), cond("no_relationship", **args)
    )
    assert sent[0] == "count" and sent[5:] == ("outgoing", 1, 1)
    _, static = gated(
        (Link("addresses", sol("sol-1"), uc("uc-1")),), cond("no_relationship", **args)
    )
    assert [f.id for _, f in static] == ["c"]  # the count would have to be below 0


@pytest.mark.parametrize("op", ["count", "no_relationship"])
def test_a_relationship_condition_after_a_cascading_delete_is_unsupported(op: str) -> None:
    args: dict[str, Any] = {"relationship": "addresses", "source": sol("sol-1")}
    if op == "count":
        args |= {"cmp": "=", "n": 0}
    with pytest.raises(Unsupported) as raised:
        gated((Delete(uc("uc-2")),), cond(op, **args))
    assert "a condition after a cascading delete in the same batch" in str(raised.value)


# -- a failed operation is reported as Truss gives it
#
# Truss judges the declared conditions first (truss-requirements R18.18): a group whose condition
# fails answers `PreconditionFailed`, so the adapter reads no state of its own to rank them. A
# `GroupOperationFailure` is the operation's own failure.


def test_an_operations_failure_is_reported_as_truss_gives_it() -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [failed(GroupOperationFailure("0", artifact_of(code="key_conflict")))]
    rig.assembly.objects[("UseCase", "a")] = ident("UseCase", "a")
    plan = Plan(
        "catalog.X",
        (pre_id("known", "exists", ref=uc("a")),),
        create_plan("a").effects,
    )
    with pytest.raises(Conflict) as raised:
        rig.backend().apply(ALICE, plan, idempotency_key=None)
    assert raised.value.reason == "exists"
