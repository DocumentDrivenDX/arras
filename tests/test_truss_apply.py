# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
# ruff: noqa: F811
"""The Truss adapter's `apply` (TR-07)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from arras.actions import Create, Delete, Link, Plan, Precondition, Ref, Unlink, Update
from arras.adapters.truss import CommitUnknown, Connections, TrussBackend
from arras.errors import (
    Conflict,
    Invalid,
    PreconditionFailed,
    Refused,
    Unavailable,
    Unsupported,
)
from arras.results import Validation
from arras.types import Statement
from test_truss_harness import MODULE_TEXT, _world, cluster  # noqa: F401
from truss_harness import TrussHarness

# -- the plan against a real Truss

UC, SOL = "catalog.UseCase", "catalog.Solution"


def uc(key: str) -> Ref:
    return Ref(UC, key)


def sol(key: str) -> Ref:
    return Ref(SOL, key)


def basic(cluster: Any) -> Any:
    return _world(cluster, "basic")


def rows(h: Any, sql: str) -> list[dict[str, Any]]:
    return list(
        h.backend().query(h.principal("carol"), "catalog", Statement(sql, {}), limit=100).rows
    )


def run(h: Any, plan: Plan, who: str = "alice", **kw: Any) -> Any:
    return h.backend().apply(h.principal(who), plan, idempotency_key=kw.pop("key", None), **kw)


def pre(id: str, op: str, **args: Any) -> Precondition:
    return Precondition(id, f"{id} failed", op, args)


def whole(h: Any, key: str, record: str = "Solution") -> dict[str, Any]:
    sql = f"SELECT x.* FROM catalog.{record} x WHERE x.code = '{key}' ORDER BY x.code LIMIT 100"
    [row] = rows(h, sql)
    return row


def linked(h: Any, use_case: str) -> list[str]:
    sql = f"SELECT s.code FROM catalog.Solution s WHERE HAS_RELATED(s.addresses, KEY('{use_case}')) ORDER BY s.code LIMIT 100"
    return [r["code"] for r in rows(h, sql)]


@pytest.mark.truss
def test_a_delete_removes_the_objects_relationships(cluster: Any) -> None:
    h = basic(cluster)
    got = run(h, Plan("catalog.RetireUseCase", (), (Delete(uc("uc-1")),)))
    assert (got.deleted, got.unlinked, got.refs[0].version) == (1, 0, 2)
    assert linked(h, "uc-1") == []
    assert whole(h, "sol-1")["code"] == "sol-1"  # the solution stays


@pytest.mark.truss
def test_updates_of_one_ref_bump_the_version_once_and_each_counts(cluster: Any) -> None:
    h = basic(cluster)
    plan = Plan(
        "catalog.X",
        (),
        (Update(sol("sol-1"), {"name": "A"}), Update(sol("sol-1"), {"coverageLevel": "full"})),
    )
    got = run(h, plan, "bob")
    assert (got.updated, [(r.key, r.version) for r in got.refs]) == (2, [("sol-1", 2)])
    row = whole(h, "sol-1")
    assert (row["_version"], row["name"], row["coverageLevel"]) == (2, "A", "full")


@pytest.mark.truss
def test_an_update_after_a_create_in_one_plan_is_part_of_the_create(cluster: Any) -> None:
    h = basic(cluster)
    plan = Plan(
        "catalog.X", (), (Create(uc("uc-9"), {"name": "N"}), Update(uc("uc-9"), {"name": "M"}))
    )
    got = run(h, plan)
    assert (got.created, got.updated, [(r.key, r.version) for r in got.refs]) == (
        1,
        1,
        [("uc-9", 1)],
    )
    assert whole(h, "uc-9", "UseCase")["name"] == "M"


@pytest.mark.truss
def test_an_update_that_changes_nothing_is_not_counted_and_keeps_its_version(cluster: Any) -> None:
    h = basic(cluster)
    got = run(h, Plan("catalog.X", (), (Update(sol("sol-1"), {"name": "Pipeline extractor"}),)))
    assert (got.updated, [(r.key, r.version) for r in got.refs]) == (0, [("sol-1", 1)])
    assert got.token and got.group


@pytest.mark.truss
def test_a_link_and_an_unlink_inside_one_plan(cluster: Any) -> None:
    h = basic(cluster)
    plan = Plan(
        "catalog.X",
        (),
        (
            Create(sol("sol-2"), {"name": "S"}),
            Link("addresses", sol("sol-2"), uc("uc-2")),
            Link("addresses", sol("sol-2"), uc("uc-1")),
            Unlink("addresses", sol("sol-2"), uc("uc-1")),
        ),
    )
    got = run(h, plan)
    assert (got.created, got.linked, got.unlinked) == (1, 2, 1)
    assert linked(h, "uc-2") == ["sol-2"] and linked(h, "uc-1") == ["sol-1"]


@pytest.mark.truss
def test_an_object_made_and_deleted_in_one_plan_takes_its_edges_with_it(cluster: Any) -> None:
    h = basic(cluster)
    plan = Plan(
        "catalog.X",
        (),
        (
            Create(sol("sol-2"), {"name": "S"}),
            Link("addresses", sol("sol-2"), uc("uc-2")),
            Delete(sol("sol-2")),
        ),
    )
    got = run(h, plan)
    assert (got.created, got.linked, got.deleted, got.unlinked) == (1, 1, 1, 0)
    assert linked(h, "uc-2") == []
    assert [
        r["code"]
        for r in rows(h, "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 100")
    ] == ["sol-1"]


@pytest.mark.truss
def test_an_existing_relationship_is_unlinked_and_a_missing_one_is_a_failed_precondition(
    cluster: Any,
) -> None:
    h = basic(cluster)
    got = run(h, Plan("catalog.X", (), (Unlink("addresses", sol("sol-1"), uc("uc-1")),)))
    assert (got.unlinked, linked(h, "uc-1")) == (1, [])
    with pytest.raises(PreconditionFailed) as raised:
        run(h, Plan("catalog.X", (), (Unlink("addresses", sol("sol-1"), uc("uc-1")),)))
    assert [f.id for f in raised.value.failures] == ["_unlink"]


@pytest.mark.truss
def test_a_missing_ref_is_a_failed_precondition_after_the_declared_ones(cluster: Any) -> None:
    h = basic(cluster)
    plan = Plan(
        "catalog.X",
        (pre("p1", "exists", ref=uc("nope")),),
        (Update(sol("nope"), {"name": "A"}),),
    )
    with pytest.raises(PreconditionFailed) as raised:
        run(h, plan)
    assert [f.id for f in raised.value.failures] == ["p1"]
    only = Plan("catalog.X", (), (Update(sol("nope"), {"name": "A"}),))
    with pytest.raises(PreconditionFailed) as raised:
        run(h, only)
    assert [(f.id, f.reason) for f in raised.value.failures] == [
        ("_ref", "catalog.Solution nope does not exist")
    ]
    with pytest.raises(Refused):  # authority comes first: a reader learns nothing of the plan
        run(h, only, "carol")


@pytest.mark.truss
@pytest.mark.parametrize(
    ("op", "args", "holds"),
    [
        ("exists", {"ref": uc("uc-1")}, True),
        ("exists", {"ref": uc("nope")}, False),
        ("absent", {"type": UC, "key": "nope"}, True),
        ("absent", {"type": UC, "key": "uc-1"}, False),
        (
            "property_equals",
            {"ref": sol("sol-1"), "property": "name", "value": "Pipeline extractor"},
            True,
        ),
        ("property_equals", {"ref": sol("sol-1"), "property": "name", "value": "other"}, False),
        (
            "property_equals",
            {"ref": sol("sol-1"), "property": "coverageLevel", "value": "full"},
            False,
        ),
        ("property_equals", {"ref": sol("nope"), "property": "name", "value": "x"}, False),
        ("no_relationship", {"relationship": "addresses", "source": sol("sol-1")}, False),
        ("no_relationship", {"relationship": "addresses", "source": sol("nope")}, True),
        (
            "no_relationship",
            {"relationship": "addresses", "source": sol("sol-1"), "target": uc("uc-2")},
            True,
        ),
        (
            "no_relationship",
            {"relationship": "addresses", "source": sol("sol-1"), "target": uc("uc-1")},
            False,
        ),
        (
            "no_relationship",
            {"relationship": "addressedBy", "source": uc("uc-1"), "target": sol("sol-1")},
            False,
        ),
        ("no_relationship", {"relationship": "addressedBy", "source": uc("uc-2")}, True),
        ("count", {"relationship": "addresses", "source": sol("sol-1"), "cmp": "=", "n": 1}, True),
        ("count", {"relationship": "addresses", "source": sol("sol-1"), "cmp": ">", "n": 1}, False),
        ("count", {"relationship": "addresses", "source": sol("sol-1"), "cmp": ">=", "n": 1}, True),
        ("count", {"relationship": "addresses", "source": sol("sol-1"), "cmp": "<", "n": 1}, False),
        ("count", {"relationship": "addresses", "source": sol("sol-1"), "cmp": "<", "n": 2}, True),
        ("count", {"relationship": "addresses", "source": sol("sol-1"), "cmp": "<=", "n": 1}, True),
        ("count", {"relationship": "addresses", "source": sol("sol-1"), "cmp": "<", "n": 0}, False),
        ("count", {"relationship": "addressedBy", "source": uc("uc-1"), "cmp": "=", "n": 1}, True),
        ("count", {"relationship": "addressedBy", "source": uc("uc-2"), "cmp": "=", "n": 0}, True),
        ("count", {"relationship": "addresses", "source": sol("nope"), "cmp": "=", "n": 0}, True),
        ("count", {"relationship": "addresses", "source": sol("nope"), "cmp": ">", "n": 0}, False),
    ],
)
def test_each_precondition_kind_holds_as_the_memory_adapter_holds_it(
    cluster: Any,
    op: str,
    args: dict[str, Any],
    holds: bool,
) -> None:
    h = basic(cluster)
    plan = Plan("catalog.X", (pre("p", op, **args),), (Create(uc("uc-9"), {"name": "N"}),))
    got = run(h, plan, dry_run=True)
    assert (got.ok, [f.id for f in got.failures]) == (holds, [] if holds else ["p"])


@pytest.mark.truss
def test_a_count_compared_with_not_equal_is_unsupported(cluster: Any) -> None:
    h = basic(cluster)
    args = {"relationship": "addresses", "source": sol("sol-1"), "cmp": "!=", "n": 1}
    plan = Plan("catalog.X", (pre("p", "count", **args),), (Create(uc("uc-9"), {"name": "N"}),))
    with pytest.raises(Unsupported):
        run(h, plan)


@pytest.mark.truss
def test_an_absent_precondition_holds_for_a_deleted_key_as_it_does_in_memory(cluster: Any) -> None:
    h = basic(cluster)
    run(h, Plan("catalog.RetireUseCase", (), (Delete(uc("uc-2")),)))
    fresh = Plan(
        "catalog.X",
        (pre("fresh", "absent", type=UC, key="uc-2"),),
        (Update(sol("sol-1"), {"name": "A"}),),
    )
    assert run(h, fresh).updated == 1
    create = Plan(
        "catalog.X",
        (pre("fresh", "absent", type=UC, key="uc-2"),),
        (Create(uc("uc-2"), {"name": "N"}),),
    )
    with pytest.raises(Conflict) as raised:
        run(h, create)
    assert raised.value.reason == "deleted"
    live = Plan(
        "catalog.X",
        (pre("fresh", "absent", type=UC, key="uc-1"),),
        (Create(uc("uc-1"), {"name": "N"}),),
    )
    with pytest.raises(PreconditionFailed) as failed:
        run(h, live)
    assert [f.id for f in failed.value.failures] == ["fresh"]


@pytest.mark.truss
def test_a_keyed_retry_of_a_plan_with_a_retired_key_replays(cluster: Any) -> None:
    """The first call leaves the retired key's `absent` condition out; the retry leaves it out too."""
    h = basic(cluster)
    run(h, Plan("catalog.RetireUseCase", (), (Delete(uc("uc-2")),)))
    plan = Plan(
        "catalog.X",
        (pre("fresh", "absent", type=UC, key="uc-2"),),
        (Update(sol("sol-1"), {"name": "A"}),),
    )
    first = run(h, plan, key="k")
    assert (first.replayed, first.updated) == (False, 1)
    again = run(h, plan, key="k")
    assert again.replayed is True
    assert (again.token, again.group) == (first.token, first.group)
    assert whole(h, "sol-1")["_version"] == 2  # applied once


@pytest.mark.truss
def test_a_failed_group_leaves_no_request_so_the_key_applies_once_the_plan_can(
    cluster: Any,
) -> None:
    h = basic(cluster)
    plan = Plan(
        "catalog.X", (pre("p", "exists", ref=uc("uc-9")),), (Update(sol("sol-1"), {"name": "A"}),)
    )
    with pytest.raises(PreconditionFailed):
        run(h, plan, key="k")
    run(h, Plan("catalog.Y", (), (Create(uc("uc-9"), {"name": "N"}),)))
    got = run(h, plan, key="k")
    assert (got.replayed, got.updated) == (False, 1)  # the failed attempt left no record of the key
    assert whole(h, "sol-1")["name"] == "A" and whole(h, "sol-1")["_version"] == 2


@pytest.mark.truss
def test_a_dry_run_over_a_committed_request_names_the_replay(cluster: Any) -> None:
    h = basic(cluster)
    plan = Plan("catalog.X", (), (Create(uc("uc-9"), {"name": "N"}),))
    first = run(h, plan, key="k")
    checked = run(h, plan, key="k", dry_run=True)
    assert isinstance(checked, Validation) and checked.ok
    assert (
        checked.replay is not None
        and checked.replay.replayed
        and checked.replay.token == first.token
    )
    other = Plan("catalog.X", (), (Create(uc("uc-8"), {"name": "N"}),))
    clash = run(h, other, key="k", dry_run=True)
    assert [f.id for f in clash.failures] == ["conflict:idempotency_key_reused"]
    assert checked.freshness is None


@pytest.mark.truss
def test_a_keyed_retry_of_a_delete_cannot_be_rebuilt_and_conflicts(cluster: Any) -> None:
    """A recorded limit: the retry looks the key up again, finds nothing, and so presents other input."""
    h = basic(cluster)
    plan = Plan("catalog.RetireUseCase", (), (Delete(uc("uc-2")),))
    assert run(h, plan, key="k").deleted == 1
    with pytest.raises(Conflict) as raised:
        run(h, plan, key="k")
    assert raised.value.reason == "idempotency_key_reused"


@pytest.mark.truss
def test_a_keyed_retry_of_an_unlink_cannot_be_rebuilt_and_conflicts(cluster: Any) -> None:
    """A recorded limit: the original named the stored edge, the retry names a ghost edge."""
    h = basic(cluster)
    plan = Plan("catalog.X", (), (Unlink("addresses", sol("sol-1"), uc("uc-1")),))
    assert run(h, plan, key="k").unlinked == 1
    with pytest.raises(Conflict) as raised:
        run(h, plan, key="k")
    assert raised.value.reason == "idempotency_key_reused"


class LostCommit(Connections):
    """A connection layer whose first write loses the answer to COMMIT: the commit lands first
    (`landed`) or does not (not `landed`), then the call reports an unknown outcome."""

    def __init__(self, *args: Any, landed: bool, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.landed = landed
        self.armed = True

    def _settle(self, conn: Any, host: Any, call: Any) -> None:
        if self.armed and not (call.read_only or call.rollback):
            self.armed = False
            host.detach()
            if self.landed:
                conn.commit()
            else:
                conn.rollback()
            conn.close()
            raise CommitUnknown(self.backend)
        super()._settle(conn, host, call)


@pytest.mark.truss
@pytest.mark.parametrize("landed", [True, False])
def test_a_lost_commit_is_recovered_by_presenting_the_same_request(
    cluster: Any, landed: bool
) -> None:
    h = basic(cluster)
    world = h.world
    backend = TrussBackend(
        "truss",
        LostCommit("truss", world.connection_source, landed=landed),
    )
    plan = Plan("catalog.X", (), (Create(uc("uc-9"), {"name": "N"}),))
    got: Any = backend.apply(h.principal("alice"), plan, idempotency_key="k")
    assert (got.created, got.replayed) == (1, False)  # this invocation did it
    assert [
        r["code"]
        for r in rows(
            h,
            "SELECT u.code FROM catalog.UseCase u WHERE u.code = 'uc-9' ORDER BY u.code LIMIT 100",
        )
    ] == ["uc-9"]
    again: Any = backend.apply(h.principal("alice"), plan, idempotency_key="k")
    assert (again.replayed, again.token, again.group) == (True, got.token, got.group)


@pytest.mark.truss
def test_a_keyless_lost_commit_is_recovered_without_a_key(cluster: Any) -> None:
    h = basic(cluster)
    backend = TrussBackend("truss", LostCommit("truss", h.world.connection_source, landed=True))
    plan = Plan("catalog.X", (), (Create(uc("uc-9"), {"name": "N"}),))
    got: Any = backend.apply(h.principal("alice"), plan, idempotency_key=None)
    assert got.created == 1 and got.token
    assert (
        len(
            rows(
                h,
                "SELECT u.code FROM catalog.UseCase u WHERE u.code = 'uc-9' ORDER BY u.code LIMIT 100",
            )
        )
        == 1
    )


@pytest.mark.truss
def test_two_lost_commits_are_unavailable(cluster: Any) -> None:
    h = basic(cluster)

    class Twice(LostCommit):
        def _settle(self, conn: Any, host: Any, call: Any) -> None:
            self.armed = True
            super()._settle(conn, host, call)

    backend = TrussBackend("truss", Twice("truss", h.world.connection_source, landed=False))
    plan = Plan("catalog.X", (), (Create(uc("uc-9"), {"name": "N"}),))
    with pytest.raises(Unavailable) as raised:
        backend.apply(h.principal("alice"), plan, idempotency_key="k")
    assert raised.value.detail == "outcome unknown"
    assert (
        rows(
            h,
            "SELECT u.code FROM catalog.UseCase u WHERE u.code = 'uc-9' ORDER BY u.code LIMIT 100",
        )
        == []
    )
    assert h.backend().apply(h.principal("alice"), plan, idempotency_key="k").replayed is False


@pytest.mark.truss
def test_a_write_runs_as_the_person_and_a_non_member_is_refused_before_anything_is_planned(
    cluster: Any,
) -> None:
    h = basic(cluster)
    seen: list[str] = []

    @contextmanager
    def watching(principal: Any) -> Iterator[Any]:
        with h.world.connection_source(principal) as conn:
            conn.execute("select 1")
            seen.append(conn.execute("select session_user").fetchone()[0])
            conn.rollback()
            yield conn

    backend = TrussBackend("truss", Connections("truss", watching))
    plan = Plan("catalog.X", (), (Create(uc("uc-9"), {"name": "N"}),))
    backend.apply(h.principal("bob"), plan, idempotency_key=None)
    assert set(seen) == {"bob"}
    assert whole(h, "uc-9", "UseCase")["_created_by"] == "bob"
    with pytest.raises(Refused):
        backend.apply(h.principal("dave"), plan, idempotency_key=None)


@pytest.mark.truss
def test_an_update_after_a_delete_in_one_plan_is_a_missing_ref(cluster: Any) -> None:
    h = basic(cluster)
    plan = Plan("catalog.X", (), (Delete(uc("uc-2")), Update(uc("uc-2"), {"name": "A"})))
    with pytest.raises(PreconditionFailed) as raised:
        run(h, plan)
    assert [f.id for f in raised.value.failures] == ["_ref"]
    assert len(rows(h, "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100")) == 2


# -- batches against a real Truss (TR-08)


def batch(h: Any, plans: list[Plan], who: str = "alice", **kw: Any) -> Any:
    kw.setdefault("atomic", True)
    kw.setdefault("idempotency_key", None)
    return h.backend().apply_batch(h.principal(who), plans, **kw)


@pytest.mark.truss
def test_an_atomic_batch_gives_a_later_item_the_version_after_an_earlier_one(cluster: Any) -> None:
    h = basic(cluster)
    plans = [
        Plan("catalog.X", (), (Create(uc("uc-9"), {"name": "N"}),)),
        Plan(
            "catalog.X",
            (),
            (Update(uc("uc-9"), {"name": "M"}), Link("addresses", sol("sol-1"), uc("uc-9"))),
        ),
    ]
    got = batch(h, plans, idempotency_key="b-1")
    assert [(i.receipt.created, i.receipt.updated, i.receipt.linked) for i in got.items] == [
        (1, 0, 0),
        (0, 1, 1),
    ]
    assert [i.receipt.refs[0].version for i in got.items] == [1, 2]
    assert (
        len({i.receipt.token for i in got.items}) == 1
        and len({i.receipt.group for i in got.items}) == 1
    )
    assert linked(h, "uc-9") == ["sol-1"]
    again = batch(h, plans, idempotency_key="b-1")
    assert all(i.receipt.replayed for i in again.items) and again.token == got.token


@pytest.mark.truss
def test_a_failed_atomic_batch_writes_nothing_and_a_refused_independent_item_does_not_stop_the_rest(
    cluster: Any,
) -> None:
    h = basic(cluster)
    dup = Plan("catalog.X", (), (Create(uc("uc-1"), {"name": "again"}),))
    with pytest.raises(Conflict) as raised:
        batch(h, [Plan("catalog.X", (), (Create(uc("uc-8"), {"name": "N"}),)), dup])
    assert raised.value.reason == "exists" and "item 1" in raised.value.__notes__
    assert rows(h, "SELECT u.code FROM catalog.UseCase u WHERE u.code = 'uc-8' LIMIT 100") == []
    got = batch(
        h,
        [Plan("catalog.X", (), (Create(uc("uc-8"), {"name": "N"}),)), dup],
        atomic=False,
    )
    assert (got.succeeded, got.failed) == (1, 1) and isinstance(got.items[1].refusal, Conflict)
    assert len(rows(h, "SELECT u.code FROM catalog.UseCase u WHERE u.code = 'uc-8' LIMIT 100")) == 1


@pytest.mark.truss
def test_a_later_items_condition_on_what_an_earlier_item_updated_sees_the_update(
    cluster: Any,
) -> None:
    # Truss judges conditions against the state before the group; the planner decides this one from
    # the planned update, so the group fails as it does on the memory adapter and writes nothing.
    h = basic(cluster)
    plans = [
        Plan("catalog.X", (), (Update(uc("uc-1"), {"name": "Renamed"}),)),
        Plan(
            "catalog.X",
            (
                pre(
                    "still-old",
                    "property_equals",
                    ref=uc("uc-1"),
                    property="name",
                    value="Pipeline mapping",
                ),
            ),
            (Update(uc("uc-2"), {"name": "Other"}),),
        ),
    ]
    with pytest.raises(PreconditionFailed) as raised:
        batch(h, plans)
    assert [f.id for f in raised.value.failures] == ["still-old"]
    assert "item 1" in raised.value.__notes__
    names = rows(h, "SELECT u.code, u.name FROM catalog.UseCase u ORDER BY u.code LIMIT 100")
    assert [r["name"] for r in names] == ["Pipeline mapping", "Runbook review"]
    plans[1] = Plan(
        "catalog.X",
        (pre("renamed", "property_equals", ref=uc("uc-1"), property="name", value="Renamed"),),
        (Update(uc("uc-2"), {"name": "Other"}),),
    )
    assert batch(h, plans).items[1].receipt.updated == 1


def _multiplicity_text() -> str:
    import json

    doc = json.loads(MODULE_TEXT)
    for rel in doc["modules"][0]["relationships"]:
        rel["sourceMultiplicity"] = {"min": 0, "max": 1}
        rel["targetMultiplicity"] = {"min": 0, "max": 1}
    return json.dumps(doc)


@pytest.mark.truss
def test_linking_past_a_maximum_multiplicity_is_invalid_not_busy(cluster: Any) -> None:
    # Truss's `dependencies` code also carries a multiplicity violation, found when the group
    # finishes; the adapter tells it by the operation's kind (R18.16)
    from arras.umf import parse_module

    text = _multiplicity_text()
    h = TrussHarness(cluster)
    h.install(parse_module(text), text.encode())
    h.grant("alice", {"catalog": ["read", "write", "schema"]}, True)
    seed = Plan(
        "catalog.X",
        (),
        (
            Create(uc("u1"), {"name": "One"}),
            Create(uc("u2"), {"name": "Two"}),
            Create(sol("s1"), {"name": "S"}),
            Link("addresses", sol("s1"), uc("u1")),
        ),
    )
    run(h, seed)
    with pytest.raises(Invalid) as raised:
        run(h, Plan("catalog.X", (), (Link("addresses", sol("s1"), uc("u2")),)))
    assert [v.code for v in raised.value.violations] == ["multiplicity"]
    assert raised.value.violations[0].path == "effects[0]"


@pytest.mark.truss
def test_a_write_a_key_lookup_and_an_import_need_no_bun_and_start_no_process(
    cluster: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Truss 0.0.44 derives a key in PostgreSQL and prepares a module in an embedded V8, so nothing
    here starts a process. A `bun` on PATH that records any run and then fails stands for an unusable
    one, and an empty PATH for none; no subprocess may start either way. A create, a keyed
    precondition, an update, a link (a key lookup of each end), a delete and an import run under both."""
    import subprocess

    def no_process(*a: Any, **k: Any) -> Any:
        raise AssertionError(f"a process was started: {a!r}")

    monkeypatch.setattr(subprocess, "Popen", no_process)
    h = basic(cluster)
    ran = tmp_path / "ran"
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "bun").write_text(f"#!/bin/sh\necho run >> {ran}\nexit 1\n")
    (fake / "bun").chmod(0o755)
    monkeypatch.delenv("BUN_INSTALL", raising=False)
    for n, path in enumerate((str(fake), str(tmp_path / "empty"))):
        monkeypatch.setenv("PATH", path)  # an unusable bun first, then none at all
        k, key = f"uc-9{n}", f"k-no-bun-{n}"
        plan = Plan(
            "catalog.X",
            (pre("fresh", "absent", type=UC, key=k),),
            (
                Create(uc(k), {"name": "N"}),
                Update(sol("sol-1"), {"name": f"A{n}"}),
                Link("addresses", sol("sol-1"), uc(k)),
            ),
        )
        got = run(h, plan, key=key)
        assert (got.created, got.updated, got.linked) == (1, 1, 1)
        assert run(h, plan, key=key).refs == got.refs  # the keyed retry replays
        run(h, Plan("catalog.RetireUseCase", (), (Delete(uc(k)),)))
        loaded = h.backend().import_records(
            h.principal("alice"),
            "catalog",
            [{"type": "UseCase", "key": f"uc-1{n}", "properties": {"name": "I"}}],
            load_id=f"L-no-bun-{n}",
            initiated_by="alice",
        )
        assert (loaded.created, loaded.skipped) == (1, 0)
        assert whole(h, f"uc-1{n}", "UseCase")["name"] == "I"
    assert not ran.exists()


@pytest.mark.truss
def test_a_group_takes_more_than_128_preconditions_and_a_failing_one_is_named(
    cluster: Any,
) -> None:
    """Truss 0.0.44 admits 3,072 conditions for a group of 1,024 operations; the adapter's own bound
    was 128."""
    h = basic(cluster)
    holds = tuple(pre(f"p{i}", "exists", ref=uc("uc-1")) for i in range(300))
    got = run(h, Plan("catalog.X", holds, (Create(uc("uc-9"), {"name": "N"}),)))
    assert got.created == 1
    failing = (*holds, pre("ghost", "exists", ref=uc("nope")))
    with pytest.raises(PreconditionFailed) as raised:
        run(h, Plan("catalog.X", failing, (Create(uc("uc-8"), {"name": "N"}),)))
    assert [f.id for f in raised.value.failures] == ["ghost"]
