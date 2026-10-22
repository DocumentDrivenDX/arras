# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The library additions the operator surface needs: receipt groups and `expected_revision`
(CONTRACT-003), the refusal reason (CONTRACT-001) and the audit reads (CONTRACT-001)."""

from datetime import UTC, datetime
from typing import Any

import pytest

from arras import (
    Arras,
    Conflict,
    Invalid,
    Placement,
    PreconditionFailed,
    Receipt,
    Refused,
)
from arras.fakes import FakeAccess, MemoryReplica, MemoryStore
from arras.results import Change, ChangesPage, Load, LoadsPage, Validation
from arras.sandbox import Sandbox
from arras.testing import example_module
from arras.types import Freshness, Position, Revision
from test_placement import Upstream


@pytest.fixture
def box() -> Sandbox:
    return Sandbox().seed()


def alice(box: Sandbox):
    return box.arras.session(box.people["alice"])


ADD = ("catalog.AddUseCase", {"code": "uc-x", "name": "X", "workArea": "finance"})


def test_a_receipt_names_its_group(box: Sandbox) -> None:
    r = alice(box).invoke(ADD[0], dict(ADD[1]))
    assert isinstance(r, Receipt) and r.group
    again = alice(box).invoke(
        ADD[0], {"code": "uc-y", "name": "Y", "workArea": "finance"}, idempotency_key="k1"
    )
    replay = alice(box).invoke(
        ADD[0], {"code": "uc-y", "name": "Y", "workArea": "finance"}, idempotency_key="k1"
    )
    assert replay.replayed and replay.group == again.group != r.group


def test_an_atomic_batch_is_one_group_and_an_independent_one_is_many(box: Sandbox) -> None:
    items = [{"code": f"uc-{i}", "name": "N", "workArea": "finance"} for i in range(3)]
    atomic = alice(box).invoke_batch("catalog.AddUseCase", items, atomic=True)
    assert len({i.receipt.group for i in atomic.items if i.receipt}) == 1
    more = [{"code": f"uc-z{i}", "name": "N", "workArea": "finance"} for i in range(3)]
    loose = alice(box).invoke_batch("catalog.AddUseCase", more)
    assert len({i.receipt.group for i in loose.items if i.receipt}) == 3


def test_a_stale_expected_revision_applies_nothing(box: Sandbox) -> None:
    o = alice(box)
    current = o.describe("catalog")[0].revision
    bad = Revision({"memory": int(current["memory"] or 0) + 7})
    with pytest.raises(Conflict) as e:
        o.invoke(ADD[0], dict(ADD[1]), expected_revision=bad)
    assert e.value.reason == "revision"
    rows = o.query(
        "catalog",
        "SELECT x.* FROM catalog.UseCase x WHERE x.code = 'uc-x' ORDER BY x.code LIMIT 100",
    )
    assert len(rows.rows) == 0
    ok = o.invoke(ADD[0], dict(ADD[1]), expected_revision=current)
    assert ok.refs


def test_expected_revision_accepts_the_wire_form_and_guards_validate_and_batch(
    box: Sandbox,
) -> None:
    o = alice(box)
    current = o.describe("catalog")[0].revision
    wire = {"memory": current["memory"]}
    assert o.validate(ADD[0], dict(ADD[1]), expected_revision=wire).ok
    stale = {"memory": int(current["memory"] or 0) + 1}
    with pytest.raises(Conflict):
        o.validate(ADD[0], dict(ADD[1]), expected_revision=stale)
    with pytest.raises(Conflict):
        o.invoke_batch(ADD[0], [dict(ADD[1])], expected_revision=stale)


def test_a_refusal_says_whether_to_sign_in_or_ask_for_access(box: Sandbox) -> None:
    from arras import Refused
    from arras.serialize import error_body

    carol = box.arras.session(box.people["carol"])  # reads, cannot write
    with pytest.raises(Refused) as no_access:
        carol.invoke(ADD[0], dict(ADD[1]))
    assert no_access.value.reason == "no_access"
    assert error_body(no_access.value)["reason"] == "no_access"
    box.access.expire(box.people["alice"].token)
    with pytest.raises(Refused) as expired:
        alice(box).invoke(ADD[0], dict(ADD[1]))
    assert expired.value.reason == "token_expired"
    from arras.types import Principal

    with pytest.raises(Refused) as none:
        box.arras.session(Principal("alice", "")).describe()
    assert none.value.reason == "token_expired"


# -- audit reads (CONTRACT-001) ----------------------------------------------------------------


def test_a_committed_change_is_read_back_with_person_action_ops_and_group(box: Sandbox) -> None:
    o = alice(box)
    secret = {"code": "uc-x", "name": "NAME-VALUE-7Q", "workArea": "AREA-VALUE-9Z"}
    r = o.invoke(ADD[0], secret)
    page = o.changes("catalog", type="catalog.UseCase", key="uc-x")
    [c] = page.items
    assert (c.by, c.action, c.module, c.backend) == (
        "alice",
        "catalog.AddUseCase",
        "catalog",
        "memory",
    )
    assert c.group == r.group
    assert {"kind": "create", "type": "catalog.UseCase", "key": "uc-x", "version": 1} in c.ops
    # the action's values are not part of the record: no input value, and ops name only what
    # was touched (CONTRACT-001, Audit reads)
    assert "NAME-VALUE-7Q" not in repr(c) and "AREA-VALUE-9Z" not in repr(c)
    allowed = {"kind", "type", "key", "version", "relationship", "source", "target"}
    assert c.ops and all(set(op) <= allowed for op in c.ops)
    o.invoke("catalog.AddSolution", {"code": "sol-q", "name": "NAME-VALUE-8R", "useCase": "uc-x"})
    [s] = o.changes("catalog", type="catalog.Solution", key="sol-q").items
    assert "NAME-VALUE-8R" not in repr(s) and all(set(op) <= allowed for op in s.ops)
    assert {op["kind"] for op in s.ops} == {"create", "link"}


def test_validate_refused_and_failed_changes_leave_no_record(box: Sandbox) -> None:
    o = alice(box)
    before = len(o.changes("catalog").items)
    assert o.validate(ADD[0], dict(ADD[1])).ok
    with pytest.raises(PreconditionFailed):
        o.invoke(ADD[0], {"code": "uc-pipeline", "name": "dup", "workArea": "finance"})  # exists
    with pytest.raises(Refused):
        box.arras.session(box.people["carol"]).invoke(ADD[0], dict(ADD[1]))
    assert len(o.changes("catalog").items) == before


def test_changes_filter_page_and_come_newest_first(box: Sandbox) -> None:
    o = alice(box)
    bob = box.arras.session(box.people["bob"])
    for i in range(3):
        o.invoke(ADD[0], {"code": f"uc-n{i}", "name": "N", "workArea": "finance"})
    bob.invoke("catalog.AddUseCase", {"code": "uc-w", "name": "W", "workArea": "finance"})
    first = o.changes("catalog", limit=2)
    assert first.next_cursor and len(first.items) == 2
    assert first.items[0].by == "bob"  # newest first
    second = o.changes("catalog", limit=2, after=first.next_cursor)
    assert second.items[0].group != first.items[0].group
    assert {c.by for c in o.changes("catalog", by="bob").items} == {"bob"}
    g = first.items[0].group
    assert [c.group for c in o.changes(group=g).items] == [g]
    assert o.changes("catalog", action="catalog.NoSuch").items == ()


def test_changes_need_a_scope_a_valid_limit_and_the_journal_grant(box: Sandbox) -> None:
    from arras import Invalid, Refused

    o = alice(box)
    with pytest.raises(Invalid):
        o.changes()  # a module, a type with a key, or a group
    with pytest.raises(Invalid):
        o.changes("catalog", limit=101)
    with pytest.raises(Invalid):
        o.changes("catalog", key="uc-x")  # a key names a type
    with pytest.raises(Refused) as e:
        box.arras.session(box.people["carol"]).changes("catalog")
    assert e.value.reason == "no_access"


def test_a_batch_is_one_change_and_an_import_is_one_load(box: Sandbox) -> None:
    o = alice(box)
    items = [{"code": f"uc-b{i}", "name": "N", "workArea": "finance"} for i in range(3)]
    o.invoke_batch("catalog.AddUseCase", items, atomic=True)
    newest = o.changes("catalog", limit=1).items[0]
    assert sum(1 for op in newest.ops if op["kind"] == "create") == 3
    root = box.arras.session(box.people["root"])
    recs = [
        {
            "type": "catalog.UseCase",
            "key": "uc-i",
            "properties": {"name": "I", "workArea": "finance"},
        }
    ]
    root.import_records("catalog", recs, load_id="L1")
    loads = o.loads("catalog")
    [ld] = loads.items
    assert (ld.load_id, ld.initiated_by, ld.module) == ("L1", "root", "catalog")
    assert ld.created + ld.skipped + ld.rejected >= 1


def test_a_group_is_found_on_whichever_provider_committed_it() -> None:
    """A group id names a change on one backend; the lookup asks each provider in turn, so a
    group committed on the second is found as readily as one on the first (CONTRACT-001)."""
    import json

    from arras import Arras, Placement
    from arras.fakes import FakeAccess, MemoryStore
    from arras.testing import example_module

    access = FakeAccess()
    primary, vault = MemoryStore(access, "primary"), MemoryStore(access, "vault")
    root = access.grant("root", "*", "read", "write", "schema", admin=True)
    alice_p = access.grant("alice", "*", "read", "write", "journal")
    h = Arras.start(
        {"primary": primary, "vault": vault},
        admin=root,
        placement={"catalog": Placement("primary"), "store": Placement("vault")},
    )
    doc = json.loads(example_module())
    mod = doc["modules"][0]
    h.session(root).registry().register(json.dumps(doc))
    mod["id"] = mod["namespace"] = "store"
    text = json.dumps(doc).replace('"module": "catalog"', '"module": "store"')
    h.session(root).registry().register(text)
    o = h.session(alice_p)
    o.invoke("catalog.AddUseCase", {"code": "a", "name": "A"})
    o.invoke("store.AddUseCase", {"code": "b", "name": "B"})
    second = o.invoke("store.AddUseCase", {"code": "c", "name": "C"})
    assert second.group not in {c.group for c in o.changes("catalog").items}  # vault's alone
    [found] = o.changes(group=second.group).items
    assert (found.module, found.backend, found.group) == ("store", "vault", second.group)


# -- audit reads name the provider (CONTRACT-001): one journal per provider, none merged

ADD_UC = "catalog.AddSolution"  # the action bound to `vault`


class Vault(Upstream):
    """A provider-only backend that keeps a journal of what it applies and the loads it ran."""

    def __init__(self) -> None:
        super().__init__("vault")
        self.journal: list[Change] = []
        self.load_log: list[Load] = [Load("V1", "vera", T0, "catalog", 1, 0, 0)]

    def apply(self, principal: Any, plan: Any, *, idempotency_key: Any, dry_run: bool = False):
        if dry_run:
            return Validation(True, (), (), (), None, None)
        out = self._receipt(plan)
        self.applied.append((plan.action, [], False))
        ops = tuple({"kind": type(e).__name__.lower()} for e in plan.effects)
        self.journal.append(
            Change(out.group or "", T0, principal.user, plan.action, "catalog", ops, "vault")
        )
        return out

    def changes(self, principal: Any, *, module: Any, group: Any, limit: int, **kw: Any):
        items = tuple(c for c in self.journal if group in (None, c.group))
        return ChangesPage(
            items, None, False, Freshness("vault", Position("vault:0", T0), "latest")
        )

    def loads(self, principal: Any, module: str, *, limit: int, after: Any):
        return LoadsPage(
            tuple(self.load_log), None, False, Freshness("vault", Position("vault:0", T0), "latest")
        )


T0 = datetime(2026, 3, 1, tzinfo=UTC)


def two_providers():
    """The record store `primary` applies most actions; `vault` applies AddSolution and keeps its own journal."""
    access = FakeAccess()
    primary, vault = MemoryStore(access, "primary"), Vault()
    mirror = MemoryReplica(primary, access, "mirror")
    root = access.grant("root", "*", "read", "write", "schema", admin=True)
    alice_p = access.grant("alice", "*", "read", "write", "journal")
    h = Arras.start(
        {"primary": primary, "vault": vault, "mirror": mirror},
        admin=root,
        placement={"catalog": Placement("primary", ("mirror",), {ADD_UC: "vault"})},
    )
    h.session(root).registry().register(example_module())
    return h, h.session(alice_p), h.session(root), vault


def test_changes_can_name_the_provider_whose_journal_is_read() -> None:
    _, o, _, _ = two_providers()
    on_primary = o.invoke("catalog.AddUseCase", {"code": "v1", "name": "V"})
    on_vault = o.invoke(ADD_UC, {"code": "s1", "name": "S", "useCase": "v1"})
    default = o.changes("catalog")  # the record store's own journal
    assert [c.group for c in default.items] == [on_primary.group]
    assert {c.backend for c in default.items} == {"primary"}
    vault = o.changes("catalog", provider="vault")
    assert [(c.group, c.backend, c.by) for c in vault.items] == [(on_vault.group, "vault", "alice")]
    assert [c.group for c in o.changes("catalog", provider="primary").items] == [on_primary.group]
    # a type with its key names the module too, and the provider is read within it
    keyed = o.changes(type="catalog.Solution", key="s1", provider="vault")
    assert [c.group for c in keyed.items] == [on_vault.group]


def test_loads_can_name_the_provider() -> None:
    _, o, root, _ = two_providers()
    rec = {"type": "catalog.UseCase", "key": "uc-i", "properties": {"name": "I"}}
    root.import_records("catalog", [rec], load_id="P1")
    assert [ld.load_id for ld in o.loads("catalog").items] == ["P1"]
    assert [ld.load_id for ld in o.loads("catalog", provider="primary").items] == ["P1"]
    assert [ld.load_id for ld in o.loads("catalog", provider="vault").items] == ["V1"]


def test_a_provider_outside_the_placement_is_refused() -> None:
    _, o, _, _ = two_providers()
    # a replica, a name nothing configures and a type that is no name: all the same refusal
    for bad in ("mirror", "nowhere", 7):
        for read in (
            lambda b: o.changes("catalog", provider=b),
            lambda b: o.loads("catalog", provider=b),
        ):
            with pytest.raises(Invalid) as e:
                read(bad)
            assert {(v.path, v.code) for v in e.value.violations} == {("provider", "unknown_type")}


def test_a_provider_without_a_module_is_refused() -> None:
    _, o, _, _ = two_providers()
    o.invoke("catalog.AddUseCase", {"code": "v1", "name": "V"})
    g = o.invoke(ADD_UC, {"code": "s1", "name": "S", "useCase": "v1"}).group
    with pytest.raises(Invalid) as e:
        o.changes(group=g, provider="vault")
    assert {(v.path, v.code) for v in e.value.violations} == {("provider", "scope")}
    assert [c.group for c in o.changes(group=g).items] == [g]  # still found without it
