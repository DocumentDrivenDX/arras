# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from arras import Invalid, Principal, Refused, Unavailable, Unsupported
from arras.actions import (
    ActionInfo,
    AliasKey,
    EffectDecl,
    Generate,
    Input,
    InputSpec,
    Item,
    Literal_,
    PreconditionDecl,
    resolve,
)
from arras.errors import Conflict, PreconditionFailed
from arras.fakes import FakeAccess, MemoryReplica, MemoryStore
from arras.fakes_weft import ENTITY, WEFT
from arras.results import Receipt, Validation, WeftSupport
from arras.types import Statement
from arras.umf import parse_module

EXAMPLE = Path(__file__).parents[1] / "docs/helix/02-design/contracts/examples/catalog.umf.json"
DOC = EXAMPLE.read_bytes()
MODULE = parse_module(DOC)


class Clock:
    def __init__(self) -> None:
        self.t = datetime(2026, 10, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.t += timedelta(seconds=1)
        return self.t


class World:
    def __init__(self) -> None:
        self.clock = Clock()
        self.access = FakeAccess()
        self.auth = MemoryStore(self.access, clock=self.clock)
        self.replica = MemoryReplica(self.auth, self.access, clock=self.clock)
        self.alice = self.access.grant("alice", "catalog", "read", "write", "schema", admin=True)
        self.reader = self.access.grant("carol", "catalog", "read")
        self.auth.register(self.alice, DOC, MODULE, unknown_endpoint="reject")
        self.replica.attach(self.alice, self.auth.modules["catalog"])

    def run(self, backend, p: Principal, sql: str, params=None, limit=50, module="catalog"):
        return backend.query(p, module, Statement(sql, params or {}), limit=limit)

    def act(self, a: ActionInfo, inputs, p=None, key=None, dry_run=False) -> Any:
        plan = resolve(a, inputs, MODULE, new_key=iter(f"g{i}" for i in range(99)).__next__)
        return self.auth.apply(p or self.alice, plan, idempotency_key=key, dry_run=dry_run)


ADD = ActionInfo(
    "catalog.AddSolution",
    "",
    (InputSpec("code", "string", "scalar", "one"), InputSpec("uc", "UseCase", "ref", "one")),
    (PreconditionDecl("uc", "no such use case", "exists", {"ref": Input("uc")}),),
    (
        EffectDecl(
            "create",
            alias="s",
            type="Solution",
            key=Input("code"),
            properties={"name": Literal_("n")},
        ),
        EffectDecl("link", type="addresses", source=AliasKey("s"), target=Input("uc")),
    ),
)
ADD_UC = ActionInfo(
    "catalog.AddUseCase",
    "",
    (InputSpec("code", "string", "scalar", "one"),),
    (),
    (EffectDecl("create", type="UseCase", key=Input("code"), properties={"name": Literal_("u")}),),
)


@pytest.fixture
def w() -> World:
    w = World()
    w.act(ADD_UC, {"code": "uc-1"})
    return w


def test_apply_commits_one_unit_and_reads_see_it(w: World) -> None:
    r = w.act(ADD, {"code": "s-1", "uc": "uc-1"})
    assert isinstance(r, Receipt) and (r.created, r.linked, r.replayed) == (1, 1, False)
    assert r.refs[0].key == "s-1" and r.refs[0].version == 1
    ans = w.run(
        w.auth,
        w.reader,
        "SELECT s.*, RELATED_KEYS(s.addresses, 100) AS addresses FROM catalog.Solution s WHERE s.code = 's-1' ORDER BY s.code LIMIT 100",
    )
    row = ans.rows[0]
    assert row["addresses"] == ["uc-1"] and row["_version"] == 1
    assert row["_created_by"] == "alice" and row["_original_author"] is None
    assert ans.as_of.value == r.token


def test_failed_precondition_changes_nothing_and_lists_every_failure(w: World) -> None:
    with pytest.raises(PreconditionFailed) as e:
        w.act(ADD, {"code": "s-1", "uc": "missing"})
    assert [f.id for f in e.value.failures] == ["uc"]
    assert (
        w.run(
            w.auth, w.reader, "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 100"
        ).rows
        == ()
    )


def test_conflicts_roll_the_whole_unit_back(w: World) -> None:
    w.act(ADD, {"code": "s-1", "uc": "uc-1"})
    before = w.auth.state.seq
    with pytest.raises(Conflict) as e:
        w.act(ADD, {"code": "s-1", "uc": "uc-1"})
    assert e.value.reason == "exists" and w.auth.state.seq == before


def test_idempotency_replays_and_refuses_other_inputs(w: World) -> None:
    first = w.act(ADD, {"code": "s-1", "uc": "uc-1"}, key="k1")
    again = w.act(ADD, {"code": "s-1", "uc": "uc-1"}, key="k1")
    assert again.replayed and again.token == first.token and again.refs == first.refs
    with pytest.raises(Conflict) as e:
        w.act(ADD, {"code": "s-2", "uc": "uc-1"}, key="k1")
    assert e.value.reason == "idempotency_key_reused"


def test_generated_keys_do_not_break_a_retry() -> None:
    w = World()
    gen = ActionInfo(
        "catalog.NewUC",
        "",
        (InputSpec("n", "string", "scalar", "one"),),
        (),
        (EffectDecl("create", type="UseCase", key=Generate(), properties={"name": Input("n")}),),
    )
    a = w.act(gen, {"n": "x"}, key="k")
    b = w.act(gen, {"n": "x"}, key="k")  # a different generated key, the same inputs
    assert b.replayed and b.refs == a.refs


def test_validate_writes_nothing_and_reports(w: World) -> None:
    seq = w.auth.state.seq
    v = w.act(ADD, {"code": "s-1", "uc": "uc-1"}, dry_run=True)
    assert isinstance(v, Validation) and v.ok and len(v.effects) == 2
    assert w.auth.state.seq == seq and w.auth.count("catalog.Solution") == 0
    v = w.act(ADD, {"code": "s-1", "uc": "nope"}, dry_run=True)
    assert not v.ok and v.failures[0].id == "uc"
    w.act(ADD, {"code": "s-1", "uc": "uc-1"}, key="k")
    v = w.act(ADD, {"code": "s-1", "uc": "uc-1"}, key="k", dry_run=True)
    assert v.replay is not None and v.replay.replayed is False


def test_deleted_keys_stay_deleted(w: World) -> None:
    w.act(ADD, {"code": "s-1", "uc": "uc-1"})
    drop = ActionInfo(
        "catalog.Drop",
        "",
        (InputSpec("s", "Solution", "ref", "one"),),
        (),
        (EffectDecl("delete", ref_type="Solution", key=Input("s")),),
    )
    w.act(drop, {"s": "s-1"})
    assert (
        w.run(
            w.auth,
            w.reader,
            "SELECT u.*, RELATED_KEYS(u.addressedBy, 100) AS addressedBy FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
        ).rows[0]["addressedBy"]
        == []
    )
    with pytest.raises(Conflict) as e:
        w.act(ADD, {"code": "s-1", "uc": "uc-1"})
    assert e.value.reason == "deleted"


def test_queries_page_filter_and_count(w: World) -> None:
    for i in range(5):
        w.act(ADD, {"code": f"s-{i}", "uc": "uc-1"})
    page = "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 2"
    after = "SELECT s.code FROM catalog.Solution s WHERE s.code > :last ORDER BY s.code LIMIT 2"
    p1 = w.run(w.auth, w.reader, page)
    assert [r["code"] for r in p1.rows] == ["s-0", "s-1"] and not p1.truncated
    p2 = w.run(w.auth, w.reader, after, {"last": p1.rows[-1]["code"]})
    assert [r["code"] for r in p2.rows] == ["s-2", "s-3"]
    p3 = w.run(w.auth, w.reader, after, {"last": p2.rows[-1]["code"]})
    assert [r["code"] for r in p3.rows] == ["s-4"]
    capped = w.run(
        w.auth, w.reader, "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 100", limit=2
    )
    assert [r["code"] for r in capped.rows] == ["s-0", "s-1"] and capped.truncated  # the cap cut it
    assert not w.run(
        w.auth, w.reader, "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 100", limit=5
    ).truncated
    by_uc = w.run(
        w.auth,
        w.reader,
        "SELECT s.code FROM catalog.Solution s WHERE HAS_RELATED(s.addresses, KEY('uc-1')) ORDER BY s.code LIMIT 100",
    )
    assert len(by_uc.rows) == 5
    inv = w.run(
        w.auth,
        w.reader,
        "SELECT u.code FROM catalog.UseCase u WHERE HAS_RELATED(u.addressedBy, KEY(:s)) ORDER BY u.code LIMIT 100",
        {"s": "s-3"},
    )
    assert [r["code"] for r in inv.rows] == ["uc-1"]
    n = w.run(
        w.auth,
        w.reader,
        "SELECT s.name, COUNT(*) FROM catalog.Solution s GROUP BY s.name ORDER BY s.name LIMIT 100",
    )
    assert n.rows == ({"name": "n", "count": 5},)
    assert (
        w.run(
            w.auth,
            w.reader,
            "SELECT s.code FROM catalog.Solution s WHERE s.code = 'zz' ORDER BY s.code LIMIT 100",
        ).rows
        == ()
    )
    for sql in (  # the memory adapter bounds its own work: a LIMIT; and DESC is outside the subset
        "SELECT s.code FROM catalog.Solution s ORDER BY s.name",
        "SELECT s.code FROM catalog.Solution s ORDER BY s.code DESC",
    ):
        with pytest.raises(Unsupported):
            w.run(w.auth, w.reader, sql)
    # a comparison on a non-key column is no page: the general profile serves it, a backend
    # declaring only the named profiles refuses it
    off_key = "SELECT s.code FROM catalog.Solution s WHERE s.name > 'a' ORDER BY s.code LIMIT 100"
    assert len(w.run(w.auth, w.reader, off_key).rows) == 5
    w.auth.weft = WeftSupport(WEFT.version, tuple(p for p in WEFT.profiles if p != "general"))
    with pytest.raises(Unsupported):
        w.run(w.auth, w.reader, off_key)


def test_access_refusals_and_outage_are_distinct(w: World) -> None:
    sql = "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 100"
    with pytest.raises(Refused):
        w.run(w.auth, Principal("alice", ""), sql)
    with pytest.raises(Refused):
        w.run(w.auth, Principal("mallory", "token-alice"), sql)  # another person's token
    w.access.expire("token-carol")
    with pytest.raises(Refused):
        w.run(w.auth, w.reader, sql)
    nobody = w.access.grant("nobody", "other", "read")
    with pytest.raises(Invalid) as e:  # no grant: to this person the module does not exist
        w.run(w.auth, nobody, sql)
    assert e.value.violations[0].code == "unknown_type"
    with pytest.raises(Refused):
        w.act(ADD, {"code": "s", "uc": "uc-1"}, p=w.access.grant("carol2", "catalog", "read"))
    w.auth.available = False
    with pytest.raises(Unavailable) as e:
        w.run(w.auth, w.alice, sql)
    assert e.value.reason == "unreachable" and not w.auth.status().available


def test_register_is_idempotent_and_guarded(w: World) -> None:
    rev = w.auth.modules["catalog"].revision
    r = w.auth.register(w.alice, DOC, MODULE, unknown_endpoint="reject")
    assert not r.changed and r.revision == rev
    with pytest.raises(Refused):
        w.auth.register(w.reader, DOC, MODULE, unknown_endpoint="reject")


def test_import_is_identity_based_and_attributed(w: World) -> None:
    recs = [
        {
            "type": "UseCase",
            "key": "uc-9",
            "properties": {"name": "old"},
            "original_author": "ann",
            "original_at": datetime(2020, 1, 1, tzinfo=UTC),
        },
        {"type": "UseCase", "key": "uc-1", "properties": {"name": "dup"}},
        {"type": "Nope", "key": "x", "properties": {}},
        {"relationship": "addresses", "source": "ghost", "target": "uc-9"},
    ]
    r = w.auth.import_records(w.alice, "catalog", recs, load_id="L1", initiated_by="alice")
    assert (r.created, r.skipped, len(r.rejected)) == (1, 1, 2)
    seq = w.auth.state.seq
    again = w.auth.import_records(w.alice, "catalog", recs, load_id="L1", initiated_by="alice")
    assert again.created == 0 and w.auth.state.seq == seq  # a repeat changes nothing
    row = w.run(
        w.auth,
        w.reader,
        "SELECT u.*, RELATED_KEYS(u.addressedBy, 100) AS addressedBy FROM catalog.UseCase u WHERE u.code = 'uc-9' ORDER BY u.code LIMIT 100",
    ).rows[0]
    assert (row["_created_by"], row["_original_author"], row["_load_id"]) == ("alice", "ann", "L1")


def test_batch_atomic_and_independent(w: World) -> None:
    ok = resolve(ADD, {"code": "b-1", "uc": "uc-1"}, MODULE)
    bad = resolve(ADD, {"code": "b-2", "uc": "nope"}, MODULE)
    ok2 = resolve(ADD, {"code": "b-3", "uc": "uc-1"}, MODULE)
    with pytest.raises(PreconditionFailed):
        w.auth.apply_batch(w.alice, [ok, bad], atomic=True, idempotency_key=None)
    assert w.auth.count("catalog.Solution") == 0
    r = w.auth.apply_batch(w.alice, [ok, bad, ok2], atomic=False, idempotency_key="b")
    assert (r.succeeded, r.failed) == (2, 1) and r.items[1].refusal is not None
    r = w.auth.apply_batch(w.alice, [ok, bad, ok2], atomic=False, idempotency_key="b")
    assert [i.receipt.replayed for i in r.items if i.receipt] == [True, True]
    r = w.auth.apply_batch(
        w.alice, [bad, ok], atomic=False, idempotency_key=None, stop_on_error=True
    )
    assert len(r.items) == 1


def test_replica_serves_bulk_and_states_its_position(w: World) -> None:
    r = w.act(ADD, {"code": "s-1", "uc": "uc-1"})
    sql = "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 100"
    with pytest.raises(Unavailable):  # not fed yet: it states no position, so it answers nothing
        w.run(w.replica, w.reader, sql)
    assert not w.replica.reached(w.reader, r.token)
    never = w.replica.status()
    assert never.available and never.position is None and never.lag is None
    w.replica.feed()
    ans = w.run(w.replica, w.reader, sql)
    assert [x["code"] for x in ans.rows] == ["s-1"] and ans.as_of.value == r.token
    assert w.replica.reached(w.reader, r.token) and w.replica.status().lag == 0.0
    assert w.replica.describe().roles == ("reader",)
    assert not w.replica.describe().capabilities["catalog.Solution"].mutable
    assert w.auth.describe().capabilities["catalog.Solution"].mutable
    for op in (
        w.replica.apply,
        w.replica.apply_batch,
        w.replica.import_records,
        w.replica.register,
    ):
        with pytest.raises(Unsupported):
            op()  # a replica takes changes only through its feed
    w.replica.available = False
    with pytest.raises(Unavailable):
        w.run(w.replica, w.reader, sql)


def test_foreach_over_the_fake(w: World) -> None:
    bulk = ActionInfo(
        "catalog.Bulk",
        "",
        (InputSpec("xs", "string", "scalar", "many"),),
        (),
        (
            EffectDecl(
                "foreach",
                over="xs",
                body=(
                    EffectDecl(
                        "create", type="UseCase", key=Item(), properties={"name": Literal_("u")}
                    ),
                ),
            ),
        ),
    )
    r = w.act(bulk, {"xs": ["a", "b", "c"]})
    assert r.created == 3 and len(r.refs) == 3


def test_conformance_to_the_protocols() -> None:
    from arras.backend import Backend, Provider

    w = World()
    _a: Provider = w.auth
    _b: Backend = w.replica
    assert _a and _b


def test_update_unlink_and_every_precondition(w: World) -> None:
    w.act(ADD, {"code": "s-1", "uc": "uc-1"})
    fix = ActionInfo(
        "catalog.Fix",
        "",
        (
            InputSpec("s", "Solution", "ref", "one"),
            InputSpec("u", "UseCase", "ref", "one"),
            InputSpec("lvl", "string", "scalar", "one"),
        ),
        (
            PreconditionDecl(
                "linked",
                "not linked",
                "count",
                {"relationship": "addresses", "source": Input("s"), "cmp": "=", "n": 1},
            ),
            PreconditionDecl(
                "named",
                "wrong name",
                "property_equals",
                {"ref": Input("s"), "property": "name", "value": Literal_("n")},
            ),
            PreconditionDecl(
                "fresh", "taken", "absent", {"type": "Solution", "key": Literal_("s-9")}
            ),
        ),
        (
            EffectDecl(
                "update",
                ref_type="Solution",
                key=Input("s"),
                properties={"coverageLevel": Input("lvl")},
            ),
            EffectDecl("unlink", type="addresses", source=Input("s"), target=Input("u")),
        ),
    )
    r = w.act(fix, {"s": "s-1", "u": "uc-1", "lvl": "full"})
    assert (r.updated, r.unlinked) == (1, 1) and r.refs[0].version == 2
    row = w.run(
        w.auth,
        w.reader,
        "SELECT s.*, RELATED_KEYS(s.addresses, 100) AS addresses FROM catalog.Solution s ORDER BY s.code LIMIT 100",
    ).rows[0]
    assert (
        row["coverageLevel"] == "full" and row["addresses"] == [] and row["_updated_by"] == "alice"
    )
    with pytest.raises(PreconditionFailed) as e:  # the link is gone now; the others still hold
        w.act(fix, {"s": "s-1", "u": "uc-1", "lvl": "x"})
    assert [f.id for f in e.value.failures] == ["linked"]
    nolink = ActionInfo(
        "catalog.NoLink",
        "",
        (InputSpec("s", "Solution", "ref", "one"),),
        (
            PreconditionDecl(
                "none",
                "linked",
                "no_relationship",
                {"relationship": "addresses", "source": Input("s")},
            ),
        ),
        (
            EffectDecl(
                "update",
                ref_type="Solution",
                key=Input("s"),
                properties={"coverageLevel": Literal_("z")},
            ),
        ),
    )
    assert w.act(nolink, {"s": "s-1"}).updated == 1


def test_two_updates_in_one_action_bump_the_version_once(w: World) -> None:
    w.act(ADD, {"code": "s-1", "uc": "uc-1"})
    twice = ActionInfo(
        "catalog.Twice",
        "",
        (InputSpec("s", "Solution", "ref", "one"),),
        (),
        tuple(
            EffectDecl(
                "update",
                ref_type="Solution",
                key=Input("s"),
                properties={"coverageLevel": Literal_(str(i))},
            )
            for i in range(2)
        ),
    )
    assert w.act(twice, {"s": "s-1"}).refs[0].version == 2


def test_delete_reports_a_version_and_one_clock_reading(w: World) -> None:
    r = w.act(ADD, {"code": "s-1", "uc": "uc-1"})
    row = w.run(
        w.auth,
        w.reader,
        "SELECT s.*, RELATED_KEYS(s.addresses, 100) AS addresses FROM catalog.Solution s ORDER BY s.code LIMIT 100",
    ).rows[0]
    assert row["_created_at"] == w.auth.state.at  # one reading for the group and the position
    drop = ActionInfo(
        "catalog.Drop",
        "",
        (InputSpec("s", "Solution", "ref", "one"),),
        (),
        (EffectDecl("delete", ref_type="Solution", key=Input("s")),),
    )
    d = w.act(drop, {"s": "s-1"})
    assert d.refs[0].version == 2 and d.token != r.token


def test_keys_are_per_type_not_global(w: World) -> None:
    # a Solution whose key equals a UseCase's key; deleting one must not touch the other's link
    w.act(ADD_UC, {"code": "x"})
    w.act(ADD, {"code": "x", "uc": "x"})  # Solution x addresses UseCase x
    drop = ActionInfo(
        "catalog.DropUC",
        "",
        (InputSpec("u", "UseCase", "ref", "one"),),
        (),
        (EffectDecl("delete", ref_type="UseCase", key=Input("u")),),
    )
    w.act(ADD, {"code": "y", "uc": "uc-1"})
    w.act(drop, {"u": "x"})
    ys = w.run(
        w.auth,
        w.reader,
        "SELECT s.*, RELATED_KEYS(s.addresses, 100) AS addresses FROM catalog.Solution s WHERE s.code = 'y' ORDER BY s.code LIMIT 100",
    ).rows[0]
    assert ys["addresses"] == ["uc-1"]
    xs = w.run(
        w.auth,
        w.reader,
        "SELECT s.*, RELATED_KEYS(s.addresses, 100) AS addresses FROM catalog.Solution s WHERE s.code = 'x' ORDER BY s.code LIMIT 100",
    ).rows[0]
    assert xs["addresses"] == []  # its own link went with the deleted use case


def test_no_token_is_refused_even_when_down(w: World) -> None:
    w.auth.available = False
    with pytest.raises(Refused):
        w.run(
            w.auth,
            Principal("alice", ""),
            "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 100",
        )
    with pytest.raises(Unavailable):
        w.run(w.auth, w.alice, "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 100")
    w.auth.outage = "access_denied"
    with pytest.raises(Unavailable) as e:
        w.run(w.auth, w.alice, "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 100")
    assert e.value.reason == "access_denied" and w.auth.status().reason == "access_denied"


def test_attach_is_for_replicas_and_administrators(w: World) -> None:
    with pytest.raises(Unsupported):
        w.auth.attach(w.alice, MODULE)
    with pytest.raises(Refused):
        w.replica.attach(w.reader, MODULE)


def test_effects_are_checked_against_the_types(w: World) -> None:
    from arras.actions import Create, Link, Plan, Ref, Update

    uc = Ref("catalog.UseCase", "uc-1")

    def plan(*effects) -> Plan:
        return Plan("catalog.Hand", (), tuple(effects), "d")

    bad = [
        Create(Ref("catalog.Solution", "s"), {"bogus": 1}),  # undeclared, and `name` is missing
        Update(uc, {"code": "other"}),
        Update(uc, {}, ("name",)),
        Link("addresses", uc, uc),
        Link("nope", uc, uc),
        Create(Ref("catalog.Nope", "n"), {}),
    ]
    for e in bad:
        with pytest.raises(Invalid):
            w.auth.apply(w.alice, plan(e), idempotency_key=None)
        v: Any = w.auth.apply(w.alice, plan(e), idempotency_key=None, dry_run=True)
        assert not v.ok and v.violations


def test_values_are_not_shared_with_callers_or_between_backends(w: World) -> None:
    from arras.actions import Create, Plan, Ref

    tags = ["a"]
    w.auth.apply(
        w.alice,
        Plan(
            "catalog.H",
            (),
            (Create(Ref("catalog.UseCase", "t"), {"name": "n", "tags": tags}),),
            "d",
        ),
        idempotency_key=None,
    ) if False else None
    w.act(ADD_UC, {"code": "k"})
    row = w.run(
        w.auth,
        w.reader,
        "SELECT u.*, RELATED_KEYS(u.addressedBy, 100) AS addressedBy FROM catalog.UseCase u WHERE u.code = 'k' ORDER BY u.code LIMIT 100",
    ).rows[0]
    row["addressedBy"].append("zzz")
    again = w.run(
        w.auth,
        w.reader,
        "SELECT u.*, RELATED_KEYS(u.addressedBy, 100) AS addressedBy FROM catalog.UseCase u WHERE u.code = 'k' ORDER BY u.code LIMIT 100",
    ).rows[0]
    assert again["addressedBy"] == []
    w.replica.feed()
    w.act(ADD, {"code": "s-new", "uc": "k"})
    assert (
        w.run(
            w.replica, w.reader, "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 100"
        ).rows
        == ()
    )


def test_dry_run_records_no_idempotency_key(w: World) -> None:
    v = w.act(ADD, {"code": "s-1", "uc": "uc-1"}, key="k", dry_run=True)
    assert v.ok
    assert w.act(ADD, {"code": "s-1", "uc": "uc-1"}, key="k").replayed is False  # type: ignore


def test_validate_reports_a_reused_key_and_a_replay(w: World) -> None:
    w.act(ADD, {"code": "s-1", "uc": "uc-1"}, key="k")
    v = w.act(ADD, {"code": "s-2", "uc": "uc-1"}, key="k", dry_run=True)
    assert not v.ok and v.failures[0].id == "conflict:idempotency_key_reused"
    v = w.act(ADD, {"code": "s-1", "uc": "uc-1"}, key="k", dry_run=True)
    assert v.ok and v.replay is not None  # the invoke would answer with the replay


def test_a_plan_built_by_hand_is_hashed_by_the_adapter(w: World) -> None:
    from arras.actions import Create, Plan, Ref

    one = Plan("catalog.H", (), (Create(Ref("catalog.UseCase", "a"), {"name": "n"}),))
    two = Plan("catalog.H", (), (Create(Ref("catalog.UseCase", "b"), {"name": "n"}),))
    w.auth.apply(w.alice, one, idempotency_key="k")
    assert w.auth.apply(w.alice, one, idempotency_key="k").replayed  # type: ignore
    with pytest.raises(Conflict):
        w.auth.apply(w.alice, two, idempotency_key="k")


def test_atomic_batches(w: World) -> None:
    ok = resolve(ADD, {"code": "b-1", "uc": "uc-1"}, MODULE)
    ok2 = resolve(ADD, {"code": "b-3", "uc": "uc-1"}, MODULE)
    bad = resolve(ADD, {"code": "b-2", "uc": "nope"}, MODULE)
    with pytest.raises(PreconditionFailed) as e:
        w.auth.apply_batch(w.alice, [ok, ok2, bad], atomic=True, idempotency_key=None)
    assert "item 2" in e.value.__notes__ and w.auth.count("catalog.Solution") == 0
    seq = w.auth.state.seq
    r = w.auth.apply_batch(w.alice, [ok, ok2], atomic=True, idempotency_key="k")
    assert w.auth.state.seq == seq + 1 and len({i.receipt.token for i in r.items if i.receipt}) == 1
    again = w.auth.apply_batch(w.alice, [ok, ok2], atomic=True, idempotency_key="k")
    assert (
        all(i.receipt and i.receipt.replayed for i in again.items) and w.auth.state.seq == seq + 1
    )
    other = resolve(ADD, {"code": "b-9", "uc": "uc-1"}, MODULE)
    with pytest.raises(Conflict):
        w.auth.apply_batch(w.alice, [other], atomic=True, idempotency_key="k")


def test_a_batch_item_and_a_single_apply_never_share_a_journal_entry(w: World) -> None:
    a = resolve(ADD, {"code": "s-1", "uc": "uc-1"}, MODULE)
    b = resolve(ADD, {"code": "s-2", "uc": "uc-1"}, MODULE)
    c = resolve(ADD, {"code": "s-3", "uc": "uc-1"}, MODULE)
    one = w.auth.apply(w.alice, a, idempotency_key="k#1")
    assert isinstance(one, Receipt) and not one.replayed
    r = w.auth.apply_batch(w.alice, [b, c], atomic=False, idempotency_key="k")
    assert all(i.receipt and not i.receipt.replayed and i.refusal is None for i in r.items)
    # the reverse order: a batch first, then a single apply keyed like its item
    d = resolve(ADD, {"code": "s-4", "uc": "uc-1"}, MODULE)
    e = resolve(ADD, {"code": "s-5", "uc": "uc-1"}, MODULE)
    f = resolve(ADD, {"code": "s-6", "uc": "uc-1"}, MODULE)
    r = w.auth.apply_batch(w.alice, [d, e], atomic=False, idempotency_key="m")
    assert all(i.receipt and not i.receipt.replayed for i in r.items)
    single = w.auth.apply(w.alice, f, idempotency_key="m#1")
    assert isinstance(single, Receipt) and not single.replayed
    # an item still replays within its own batch
    again = w.auth.apply_batch(w.alice, [d, e], atomic=False, idempotency_key="m")
    assert all(i.receipt and i.receipt.replayed for i in again.items)


def test_an_atomic_batch_and_a_single_invoke_with_one_key_are_separate_requests(
    w: World,
) -> None:
    a = resolve(ADD, {"code": "t-1", "uc": "uc-1"}, MODULE)
    b = resolve(ADD, {"code": "t-2", "uc": "uc-1"}, MODULE)
    c = resolve(ADD, {"code": "t-3", "uc": "uc-1"}, MODULE)
    batch = w.auth.apply_batch(w.alice, [a, b], atomic=True, idempotency_key="k")
    assert all(i.receipt and not i.receipt.replayed for i in batch.items)
    single = w.auth.apply(w.alice, c, idempotency_key="k")
    assert isinstance(single, Receipt) and not single.replayed
    # and the other way round
    d = resolve(ADD, {"code": "t-4", "uc": "uc-1"}, MODULE)
    e = resolve(ADD, {"code": "t-5", "uc": "uc-1"}, MODULE)
    f = resolve(ADD, {"code": "t-6", "uc": "uc-1"}, MODULE)
    single = w.auth.apply(w.alice, f, idempotency_key="n")
    assert isinstance(single, Receipt) and not single.replayed
    batch = w.auth.apply_batch(w.alice, [d, e], atomic=True, idempotency_key="n")
    assert all(i.receipt and not i.receipt.replayed for i in batch.items)


def test_batch_shape_and_access(w: World) -> None:
    ok = resolve(ADD, {"code": "b-1", "uc": "uc-1"}, MODULE)
    uc = resolve(ADD_UC, {"code": "z"}, MODULE)
    for plans in ([], [ok, uc], [ok] * 101):
        with pytest.raises(Invalid):
            w.auth.apply_batch(w.alice, plans, atomic=False, idempotency_key=None)
    with pytest.raises(Refused):
        w.auth.apply_batch(w.reader, [ok], atomic=False, idempotency_key=None)
    from arras.actions import Plan

    nomod = w.access.grant("alice", "nomod", "read", "write")
    with pytest.raises(Invalid):  # an action of a module the backend does not hold
        w.auth.apply_batch(nomod, [Plan("nomod.A", (), ())], atomic=False, idempotency_key=None)


def test_import_is_admin_only_attributed_and_validated(w: World) -> None:
    rec = [{"type": "UseCase", "key": "uc-9", "properties": {"name": "x"}}]
    plain = w.access.grant("wendy", "catalog", "read", "write")
    with pytest.raises(Refused):
        w.auth.import_records(plain, "catalog", rec, load_id="L", initiated_by="wendy")
    with pytest.raises(Invalid):  # there is no author a caller can assert
        w.auth.import_records(w.alice, "catalog", rec, load_id="L", initiated_by="someone-else")
    odd = [
        {"nothing": 1},
        {"type": "UseCase", "key": "uc-8", "properties": {}},  # no required name
        {"type": "UseCase", "key": "bad key!", "properties": {"name": "x"}},
        {"type": "UseCase", "properties": {"name": "x"}},  # no key
        {"type": "UseCase", "key": "uc-7", "properties": {"name": "x", "zzz": 1}},
    ]
    r = w.auth.import_records(w.alice, "catalog", odd, load_id="L", initiated_by="alice")
    assert r.created == 0 and len(r.rejected) == 5


def test_import_relationships_by_type_and_inverse(w: World) -> None:
    w.act(ADD_UC, {"code": "x"})
    recs = [
        {"type": "Solution", "key": "x", "properties": {"name": "n"}},
        {"relationship": "addresses", "source": "x", "target": "x"},
        {"relationship": "addressedBy", "source": "uc-1", "target": "x"},  # via the inverse name
        {"relationship": "addresses", "source": "uc-1", "target": "x"},  # wrong end types
    ]
    r = w.auth.import_records(w.alice, "catalog", recs, load_id="L", initiated_by="alice")
    assert (r.created, len(r.rejected)) == (3, 1)
    assert w.run(
        w.auth,
        w.reader,
        "SELECT u.*, RELATED_KEYS(u.addressedBy, 100) AS addressedBy FROM catalog.UseCase u WHERE u.code='uc-1' ORDER BY u.code LIMIT 100",
    ).rows[0]["addressedBy"] == ["x"]


def test_import_does_not_resurrect_a_deleted_entity(w: World) -> None:
    w.act(ADD, {"code": "s-1", "uc": "uc-1"})
    drop = ActionInfo(
        "catalog.Drop",
        "",
        (InputSpec("s", "Solution", "ref", "one"),),
        (),
        (EffectDecl("delete", ref_type="Solution", key=Input("s")),),
    )
    w.act(drop, {"s": "s-1"})
    rec = [{"type": "Solution", "key": "s-1", "properties": {"name": "n"}}]
    r = w.auth.import_records(w.alice, "catalog", rec, load_id="L", initiated_by="alice")
    assert (r.created, r.skipped) == (0, 1)


def test_related_keys_are_bounded_by_the_statement(w: World) -> None:
    recs = [
        {"type": "Solution", "key": f"s{i:03}", "properties": {"name": "n"}} for i in range(101)
    ]
    recs += [
        {"relationship": "addresses", "source": f"s{i:03}", "target": "uc-1"} for i in range(101)
    ]
    w.auth.import_records(w.alice, "catalog", recs, load_id="L", initiated_by="alice")
    ans = w.run(
        w.auth,
        w.reader,
        "SELECT u.*, RELATED_KEYS(u.addressedBy, 100) AS addressedBy FROM catalog.UseCase u WHERE u.code = 'uc-1' ORDER BY u.code LIMIT 100",
    )
    assert len(ans.rows[0]["addressedBy"]) == 100  # the statement's own bound
    more = "SELECT u.code, RELATED_KEYS(u.addressedBy, 101) AS addressedBy FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
    assert len(w.run(w.auth, w.reader, more).rows[0]["addressedBy"]) == 101
    plain = w.run(
        w.auth,
        w.reader,
        "SELECT u.* FROM catalog.UseCase u WHERE u.code = 'uc-1' ORDER BY u.code LIMIT 100",
    )
    assert "addressedBy" not in plain.rows[0]  # alias.* carries declared fields and facts only
    assert "addressedBy" not in {c.name for c in plain.columns} and "_version" in plain.rows[0]


def test_count_bound_and_ordering(w: World) -> None:
    recs = [
        {"type": "UseCase", "key": f"u{i}", "properties": {"name": str(i)}} for i in range(1001)
    ]
    w.auth.import_records(w.alice, "catalog", recs, load_id="L", initiated_by="alice")
    count = "SELECT u.name, COUNT(*) FROM catalog.UseCase u GROUP BY u.name ORDER BY u.name"
    capped = w.run(w.auth, w.reader, count + " LIMIT 1000", limit=100)  # more than the cap: said
    assert len(capped.rows) == 100 and capped.truncated
    ordered = w.run(w.auth, w.reader, count + " LIMIT 3", limit=100)
    assert [r["name"] for r in ordered.rows] == ["0", "1", "10"] and not ordered.truncated


def test_counts_sort_by_value(w: World) -> None:
    for n in ("10", "9", "100"):
        w.act(ADD_UC, {"code": f"c{n}"})
    ans = w.run(
        w.auth,
        w.reader,
        "SELECT u.code, COUNT(*) FROM catalog.UseCase u GROUP BY u.code ORDER BY u.code LIMIT 100",
    )
    assert [r["code"] for r in ans.rows] == sorted(r["code"] for r in ans.rows)


def test_a_narrower_declaration_makes_unsupported_expressible(w: World) -> None:
    """A fake that declares fewer Weft profiles refuses the rest from `query`."""
    count = (
        "SELECT s.name, COUNT(*) FROM catalog.Solution s GROUP BY s.name ORDER BY s.name LIMIT 100"
    )
    w.auth.weft = WeftSupport(WEFT.version, (ENTITY,))
    assert w.auth.describe().weft == WeftSupport(WEFT.version, (ENTITY,))
    with pytest.raises(Unsupported):
        w.run(w.auth, w.reader, count)
    with pytest.raises(Unsupported):  # RELATED_KEYS needs the related-entity profile
        w.run(
            w.auth,
            w.reader,
            "SELECT s.code, RELATED_KEYS(s.addresses, 5) FROM catalog.Solution s ORDER BY s.code LIMIT 100",
        )
    w.run(w.auth, w.reader, "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 100")
    w.auth.weft = None  # a backend that hosts no Weft serves no statement
    with pytest.raises(Unsupported):
        w.run(w.auth, w.reader, "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 100")


def test_query_checks_the_named_module_before_anything_else(w: World) -> None:
    sql = "SELECT s.code FROM catalog.Solution s WHERE HAS_RELATED(s.addresses, KEY(:k)) ORDER BY s.code LIMIT 100"
    assert w.auth.describe().weft == WEFT
    # a module the principal may not read is one the backend does not hold: never Refused
    nobody = w.access.grant("nobody", "other", "read")
    with pytest.raises(Invalid) as e:
        w.run(w.auth, nobody, "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 100")
    assert [(v.path, v.code) for v in e.value.violations] == [("module", "unknown_type")]
    w.auth.weft = WeftSupport(WEFT.version, (ENTITY,))  # unknown_type before a profile refusal
    with pytest.raises(Invalid) as e:
        w.run(
            w.auth,
            nobody,
            "SELECT s.name, COUNT(*) FROM catalog.Solution s GROUP BY s.name ORDER BY s.name LIMIT 100",
        )
    assert e.value.violations[0].code == "unknown_type"
    w.auth.weft = WEFT
    with pytest.raises(Invalid) as e:  # a module this backend does not hold
        w.run(
            w.auth,
            w.reader,
            "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 100",
            module="nomodule",
        )
    assert e.value.violations[0].code == "unknown_type"
    with pytest.raises(Unsupported) as u:  # a statement reading outside the named module
        w.run(w.auth, w.reader, "SELECT t.code FROM other.Thing t ORDER BY t.code LIMIT 100")
    assert "outside module catalog" in u.value.construct
    with pytest.raises(Invalid) as e:  # a statement fault is not unknown_type
        w.run(w.auth, w.reader, sql, {})
    assert e.value.violations[0].code == "missing_param"
    with pytest.raises(Unsupported):
        w.run(w.auth, w.reader, "SELECT s.code FROM catalog.Solution s WHERE s.a = 1 OR s.a = 2")
    with pytest.raises(Refused):
        w.run(w.auth, Principal("carol", ""), sql, {"k": "x"})
    w.auth.available = False
    with pytest.raises(Unavailable):
        w.run(w.auth, w.reader, sql, {"k": "x"})


def test_reached_and_status_on_replicas(w: World) -> None:
    r = w.act(ADD, {"code": "s-1", "uc": "uc-1"})
    for bad in ("garbage", "fake:x", ":1"):  # not position tokens: invalid, not "no"
        with pytest.raises(Invalid):
            w.replica.reached(w.reader, bad)
        with pytest.raises(Invalid):
            w.auth.reached(w.reader, bad)
    assert not w.replica.reached(w.reader, r.token)  # before its first feed
    assert w.auth.reached(w.reader, r.token)
    w.replica.outage = "unreachable"
    with pytest.raises(Unavailable):
        w.replica.reached(w.reader, r.token)
    assert w.replica.status().available is False and w.replica.status().reason == "unreachable"


def test_unknown_modules_are_invalid_not_crashes(w: World) -> None:
    from arras.actions import Plan

    w.replica.modules.clear()
    with pytest.raises(Invalid):
        w.replica.module("catalog")
    nomod = w.access.grant("alice", "nomod", "read", "write")
    with pytest.raises(Invalid):
        w.auth.apply(nomod, Plan("nomod.A", (), ()), idempotency_key=None)


def test_registering_validates_endpoints_and_policy(w: World) -> None:
    import json

    doc = json.loads(DOC.decode().replace('"catalog"', '"other"'))
    doc["modules"][0]["relationships"][0]["target"][0] = {"module": "gone", "element": "Thing"}
    other = parse_module(json.dumps(doc))
    wr = w.access.grant("alice", "other", "read", "write", "schema")
    with pytest.raises(Invalid):
        w.auth.register(wr, b"", other, unknown_endpoint="reject")
    assert w.auth.register(wr, b"", other, unknown_endpoint="provisional").changed
    with pytest.raises(Invalid):
        w.auth.register(wr, b"", other, unknown_endpoint="whatever")


def test_reached_is_asked_for_a_person(w: World) -> None:
    r = w.act(ADD, {"code": "s-1", "uc": "uc-1"})
    for b in (w.auth, w.replica):
        with pytest.raises(Refused) as e:
            b.reached(Principal("carol", ""), r.token)  # no token: refused before the outage
        assert e.value.reason == "token_expired"
        with pytest.raises(Refused):
            b.reached(Principal("carol", "stale"), r.token)
    nobody = w.access.grants.pop("carol")  # authenticated, but holds nothing here
    with pytest.raises(Refused):
        w.auth.reached(w.reader, r.token)
    w.access.grants["carol"] = nobody
    w.auth.outage = "unreachable"
    with pytest.raises(Unavailable):
        w.auth.reached(w.reader, r.token)
    with pytest.raises(Refused):
        w.auth.reached(Principal("carol", ""), r.token)


def test_a_replica_that_was_never_fed_has_reached_nothing(w: World) -> None:
    r = w.act(ADD, {"code": "s-1", "uc": "uc-1"})
    assert not w.replica.reached(w.reader, r.token) and not w.replica.reached(w.reader, "fake:0")
    w.replica.feed()
    assert w.replica.reached(w.reader, "fake:0") and w.replica.reached(w.reader, r.token)
