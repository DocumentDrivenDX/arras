# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
# ruff: noqa: F811
"""`changes` and `loads` over Truss's audit pages (TR-11, plan B8).

The always-on tests drive the adapter against a scripted assembly (Truss's results named as Truss names
them); the Truss-marked tests run the two journal corpus cases' behavior and the audit grant's
separation from reading and writing against a real Truss on PostgreSQL 18.6.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from arras.actions import Create, Delete, Link, Plan, Ref, Unlink, Update
from arras.adapters.truss import Connections, TrussBackend
from arras.adapters.truss.wire import Wire
from arras.errors import Invalid, Refused, Unavailable, Unsupported
from arras.types import Principal
from test_truss_harness import _world, cluster  # noqa: F401
from test_truss_registry import ALICE, ReaderCatalog, Rig, entry, ok

EPOCH = "2aef00d0-9b28-4c30-9d48-ca40c8b985ba"  # a source epoch, as Truss names one
AUDITOR = Principal("aud", "aud-token")
MODULES = {
    **entry(),
    "types": [{"kind": "record", "typeId": 2, "recordId": "UseCase"}],
    "relationships": [{"relationshipId": 1, "name": "addresses"}],
}


@dataclass(frozen=True)
class Cursor:
    frontier_xid: str
    source_epoch: str
    after: int


class AuditWire(Wire):
    def audit_cursor(self, kind: str, fields: dict[str, Any]) -> Any:
        return Cursor(**fields)


@dataclass(frozen=True)
class MutationGroupAuditPage:
    asserted_action: str | None
    writer_xid: str
    entries: tuple[Any, ...]
    next_page_cursor: Any
    native_actor_name: str | None = "alice"
    native_actor: str = "18463"
    observed_at: str = "2026-10-21T16:51:28.333305Z"


@dataclass(frozen=True)
class MutationGroupAuditListingEnd:
    pass


@dataclass(frozen=True)
class LoadAuditUnavailable:
    reason: str


@dataclass(frozen=True)
class LoadAuditInvocationSummary:
    load_id: str
    native_actor_name: str
    observed_at_until: str
    created_count: str
    skipped_count: str
    rejected_count: str
    state: str
    next_page_cursor: Any


@dataclass(frozen=True)
class LoadAuditListingEnd:
    pass


def op(index: str, kind: str, entity: str, type_id: str, operation: str) -> Any:
    return SimpleNamespace(
        operation_index=index,
        entity_kind=kind,
        entity_id=entity,
        entity_type=type_id,
        operation=operation,
        observed_at="2026-10-21T16:51:28.4Z",
    )


class AuditAssembly:
    """A newest-first list of audit answers, each with the cursor after it."""

    def __init__(self, base: Any) -> None:
        self.base = base
        self.groups: list[Any] = []
        self.invocations: list[Any] = []
        self.refusal: str | None = None
        self.calls: list[tuple[dict[str, str], Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base, name)

    def _page(self, items: list[Any], end: Any, filters: Any, cursor: Any, **extra: Any) -> Any:
        self.calls.append((dict(filters), cursor))
        if self.refusal:
            return ok(LoadAuditUnavailable(self.refusal))
        start = 0 if cursor is None else cursor.after
        if start >= len(items):
            return ok(end())
        return ok(items[start](Cursor("700", EPOCH, start + 1)))

    def page_mutation_group_audit_in_transaction(
        self, tx: Any, *, filters: Any, cursor: Any = None, maximum_events: int
    ) -> Any:
        assert maximum_events == 1024
        return self._page(self.groups, MutationGroupAuditListingEnd, filters, cursor)

    def page_import_load_audit_in_transaction(
        self, tx: Any, *, filters: Any, cursor: Any = None, maximum_entries: int
    ) -> Any:
        return self._page(self.invocations, LoadAuditListingEnd, filters, cursor)


def group(action: str | None, xid: str, who: str = "alice", *entries: Any) -> Any:
    def make(cursor: Any) -> Any:
        return MutationGroupAuditPage(action, xid, tuple(entries), cursor, native_actor_name=who)

    return make


def invocation(load_id: str, created: int, *, who: str = "alice", state: str = "complete") -> Any:
    def make(cursor: Any) -> Any:
        return LoadAuditInvocationSummary(
            load_id, who, "2026-10-21T16:51:28.333305Z", str(created), "0", "0", state, cursor
        )

    return make


class Audited:
    def __init__(self) -> None:
        self.rig = Rig()
        self.rig.assembly.catalog = ok(ReaderCatalog(3, (MODULES,)))
        self.audit = AuditAssembly(self.rig.assembly)
        self.rig.assembly = self.audit  # type: ignore[assignment]
        self.backend = TrussBackend(
            "truss",
            Connections("truss", self.rig.source, toolkit=self.rig.toolkit()),
            AuditWire(),
        )

    def changes(self, **kw: Any) -> Any:
        who = kw.pop("who", ALICE)
        args: dict[str, Any] = dict(
            module="catalog",
            type=None,
            key=None,
            by=None,
            action=None,
            group=None,
            since=None,
            until=None,
            limit=10,
            after=None,
        )
        args.update(kw)
        return self.backend.changes(who, **args)

    def loads(self, **kw: Any) -> Any:
        return self.backend.loads(
            ALICE, "catalog", limit=kw.pop("limit", 10), after=kw.pop("after", None)
        )


def audited() -> Audited:
    return Audited()


# -- before any connection


class Forbidden:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the audit read opened a connection ({name})")


def kwargs() -> dict[str, Any]:
    return dict(
        module="catalog",
        type=None,
        key=None,
        by=None,
        action=None,
        group=None,
        since=None,
        until=None,
        limit=10,
        after=None,
    )


def test_an_audit_read_with_no_token_is_refused_before_any_connection() -> None:
    backend = TrussBackend("truss", Forbidden())  # type: ignore[arg-type]
    nobody = Principal("alice", "")
    with pytest.raises(Refused) as c:
        backend.changes(nobody, **kwargs())
    assert c.value.reason == "token_expired"
    with pytest.raises(Refused) as ld:
        backend.loads(nobody, "catalog", limit=10, after=None)
    assert ld.value.reason == "token_expired"


def test_a_key_is_refused_before_any_connection_because_truss_cannot_filter_by_it() -> None:
    backend = TrussBackend("truss", Forbidden())  # type: ignore[arg-type]
    with pytest.raises(Unsupported) as c:
        backend.changes(ALICE, **{**kwargs(), "type": "catalog.UseCase", "key": "uc-1"})
    assert c.value.construct == "changes of a key"


def test_describe_declares_an_audit_and_a_backend_with_no_connections_is_not_configured() -> None:
    backend = TrussBackend("truss")
    assert backend.describe().audit is True
    with pytest.raises(Unavailable) as c:
        backend.changes(ALICE, **kwargs())
    assert c.value.reason == "not_configured"
    with pytest.raises(Unavailable):
        backend.loads(ALICE, "catalog", limit=1, after=None)


# -- changes


def test_a_group_is_a_change_named_like_its_receipt_with_its_actor_action_and_ops() -> None:
    a = audited()
    a.audit.groups = [
        group(
            "catalog.AddSolution",
            "774",
            "alice",
            op("0", "object", "1", "2", "create"),
            op("1", "edge", "3", "1", "create"),
            op("2", "object", "1", "2", "property"),
            op("2", "object", "1", "2", "metadata"),
        )
    ]
    page = a.changes()
    [change] = page.items
    assert change.group == f"{EPOCH}:774"  # a receipt's group: the source epoch and the writer xid
    assert (change.by, change.action, change.module, change.backend) == (
        "alice",
        "catalog.AddSolution",
        "catalog",
        "truss",
    )
    assert change.at == datetime(2026, 10, 21, 16, 51, 28, 333305, tzinfo=UTC)
    assert [dict(o) for o in change.ops] == [
        {"kind": "create", "type": "catalog.UseCase", "key": None, "version": None, "id": "1"},
        {"kind": "link", "relationship": "addresses", "source": None, "target": None, "id": "3"},
        {"kind": "update", "type": "catalog.UseCase", "key": None, "version": None, "id": "1"},
    ]  # an op is an operation of the group: the third is its own, an update of the first's object
    assert (page.next_cursor, page.truncated, page.freshness.backend) == (None, False, "truss")
    assert page.freshness.as_of.value == "audit-frontier:700"


def test_an_update_is_one_op_of_its_property_and_metadata_events_and_a_delete_is_kept() -> None:
    a = audited()
    a.audit.groups = [
        group(
            "catalog.X",
            "1",
            "alice",
            op("0", "object", "1", "2", "property"),
            op("0", "object", "1", "2", "metadata"),
            op("1", "object", "2", "2", "delete"),
            op("2", "edge", "3", "1", "delete"),
            op("3", "object", "9", "7", "create"),  # a type this person reads nothing of
        )
    ]
    ops = [(o["kind"], o.get("type") or o.get("relationship")) for o in a.changes().items[0].ops]
    assert ops == [
        ("update", "catalog.UseCase"),
        ("delete", "catalog.UseCase"),
        ("unlink", "addresses"),
        ("create", "#7"),
    ]


def test_a_group_no_action_made_is_not_a_change() -> None:
    a = audited()
    a.audit.groups = [
        group("import_records", "5"),
        group(None, "4"),
        group("catalog.Add", "3"),
    ]
    assert [c.group for c in a.changes().items] == [f"{EPOCH}:3"]


def test_a_page_of_limit_groups_has_a_cursor_only_when_more_follow() -> None:
    a = audited()
    a.audit.groups = [group("catalog.A", str(i)) for i in (3, 2, 1)]
    first = a.changes(limit=2)
    assert [c.group for c in first.items] == [f"{EPOCH}:3", f"{EPOCH}:2"]
    assert first.next_cursor is not None
    last = a.changes(limit=2, after=first.next_cursor)
    assert [c.group for c in last.items] == [f"{EPOCH}:1"] and last.next_cursor is None
    exact = a.changes(limit=3)
    assert len(exact.items) == 3 and exact.next_cursor is None  # not a page that says "more"


def test_a_cursor_that_this_adapter_did_not_issue_for_these_filters_is_invalid() -> None:
    a = audited()
    a.audit.groups = [group("catalog.A", str(i)) for i in (3, 2, 1)]
    cursor = a.changes(limit=1).next_cursor
    for bad in ("nonsense", "e30", cursor[:-3] if cursor else "", "-1"):
        with pytest.raises(Invalid) as raised:
            a.changes(after=bad)
        assert raised.value.violations[0].code == "cursor"
    with pytest.raises(Invalid):  # made for other filters
        a.changes(limit=1, action="catalog.A", after=cursor)
    loads_cursor = a.audit.invocations = [invocation("L1", 1), invocation("L2", 1)]
    assert loads_cursor
    with pytest.raises(Invalid):  # and a loads cursor is no changes cursor
        a.changes(after=a.loads(limit=1).next_cursor)


def test_filters_are_sent_to_truss_where_it_has_them() -> None:
    a = audited()
    a.audit.groups = [group("catalog.A", "1")]
    a.changes(
        action="catalog.A",
        type="catalog.UseCase",
        since=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        until=datetime(2026, 1, 3, tzinfo=UTC),
    )
    [(filters, cursor)] = a.audit.calls[:1]
    assert filters == {
        "documentId": "sandbox",
        "moduleId": "catalog",
        "assertedAction": "catalog.A",
        "entityType": "2",
        "observedAtFrom": "2026-01-02T03:04:05.000000Z",
        "observedAtUntil": "2026-01-03T00:00:00.000000Z",
    }
    assert cursor is None


def test_a_person_and_a_group_are_matched_here_by_reading_on() -> None:
    a = audited()
    a.audit.groups = [group("catalog.A", "9", "bob"), group("catalog.A", "8", "alice")]
    assert [c.group for c in a.changes(by="alice").items] == [f"{EPOCH}:8"]
    assert [c.group for c in a.changes(group=f"{EPOCH}:9").items] == [f"{EPOCH}:9"]
    assert a.changes(group=f"{EPOCH}:77").items == ()
    assert a.changes(group="not a group").items == ()  # nothing is that: an empty page


def test_the_scan_bound_cuts_a_page_and_gives_a_cursor_to_go_on() -> None:
    import arras.adapters.truss.audit as audit

    a = audited()
    a.audit.groups = [group("catalog.A", str(i), "bob") for i in range(audit.SCAN + 3)] + [
        group("catalog.A", "0", "alice")
    ]
    cut = a.changes(by="alice")
    assert cut.items == () and cut.truncated is True and cut.next_cursor is not None
    more = a.changes(by="alice", after=cut.next_cursor)
    assert [c.by for c in more.items] == ["alice"] and more.truncated is False


def test_an_unknown_type_of_the_module_matches_nothing() -> None:
    a = audited()
    a.audit.groups = [group("catalog.A", "1")]
    assert a.changes(type="catalog.Nope").items == ()
    assert a.audit.calls == []  # Truss is not asked


def test_a_group_alone_is_looked_for_in_the_modules_this_adapter_knows() -> None:
    a = audited()
    a.audit.groups = [group("catalog.A", "4")]
    a.backend.catalog(ALICE)  # serves the module
    page = a.changes(module=None, group=f"{EPOCH}:4")
    assert [c.group for c in page.items] == [f"{EPOCH}:4"]


@pytest.mark.parametrize(
    ("reason", "expected", "detail"),
    [
        ("unauthorized", Refused, "no_access"),
        ("incomplete_scope", Refused, "no_access"),
        ("resource", Unavailable, "resource"),
        ("unsupported_profile", Unavailable, "unsupported_version"),
        ("observation", Unavailable, "busy"),
    ],
)
def test_truss_refusals_of_an_audit_page_are_mapped_by_their_reason(
    reason: str, expected: type, detail: str
) -> None:
    a = audited()
    a.audit.refusal = reason
    with pytest.raises(expected) as raised:
        a.changes()
    assert detail in (getattr(raised.value, "reason", None), getattr(raised.value, "detail", None))
    with pytest.raises(expected):
        a.loads()


def test_a_refused_continuation_is_an_invalid_cursor_not_busy() -> None:
    a = audited()
    a.audit.groups = [group("catalog.A", str(i)) for i in (3, 2, 1)]
    cursor = a.changes(limit=1).next_cursor
    a.audit.refusal = "observation"
    with pytest.raises(Invalid):
        a.changes(limit=1, after=cursor)


def test_a_page_with_no_cursor_gives_no_source_epoch_and_is_unavailable() -> None:
    a = audited()
    a.audit.groups = [lambda cursor: MutationGroupAuditPage("catalog.A", "1", (), None)]
    with pytest.raises(Unavailable) as raised:
        a.changes()
    assert raised.value.reason == "unreachable"


def test_an_auditor_who_reads_nothing_names_the_module_from_the_hosts_configuration() -> None:
    a = audited()
    a.audit.base.catalog = ok(ReaderCatalog(3, ()))  # reads nothing
    a.audit.groups = [group("catalog.A", "1")]
    with pytest.raises(Refused):  # no document is known for the module
        a.changes()
    from arras.adapters.truss.audit import Auditor

    known = Auditor(
        "truss",
        a.backend.connections,  # type: ignore[arg-type]
        a.backend._registry,  # type: ignore[arg-type]
        a.backend.cache,
        {"catalog": "sandbox"},
        AuditWire(),
    )
    page = known.changes(ALICE, **{**kwargs(), "module": "catalog"})
    assert page.items[0].group == f"{EPOCH}:1"
    assert page.items[0].ops == ()


# -- loads


def test_consecutive_invocations_of_one_load_are_one_load_with_their_counts_added() -> None:
    a = audited()
    a.audit.invocations = [
        invocation("L2", 3),
        invocation("L2", 100),  # the same load's entities, then its edges
        invocation("L1", 1),
    ]
    page = a.loads()
    assert [(ld.load_id, ld.created, ld.initiated_by, ld.module) for ld in page.items] == [
        ("L2", 103, "alice", "catalog"),
        ("L1", 1, "alice", "catalog"),
    ]
    assert not any(ld.partial for ld in page.items) and page.next_cursor is None


def test_a_summary_truss_calls_partial_makes_a_partial_load_never_a_whole_one() -> None:
    a = audited()
    a.audit.invocations = [invocation("L2", 1, state="partial"), invocation("L1", 5)]
    page = a.loads()
    assert [(ld.load_id, ld.partial) for ld in page.items] == [("L2", True), ("L1", False)]
    merged = audited()
    merged.audit.invocations = [invocation("L", 1, state="partial"), invocation("L", 1)]
    [only] = merged.loads().items
    assert (only.created, only.partial) == (2, True)


def test_two_loads_of_one_id_by_different_people_are_two_loads() -> None:
    a = audited()
    a.audit.invocations = [invocation("L", 1, who="bob"), invocation("L", 1)]
    assert [ld.initiated_by for ld in a.loads().items] == ["bob", "alice"]


def test_loads_page_with_a_cursor_after_the_last_invocation_the_last_load_took() -> None:
    a = audited()
    a.audit.invocations = [
        invocation("L3", 1),
        invocation("L3", 1),
        invocation("L2", 1),
        invocation("L1", 1),
    ]
    first = a.loads(limit=1)
    assert [(ld.load_id, ld.created) for ld in first.items] == [("L3", 2)]
    assert first.next_cursor is not None
    second = a.loads(limit=1, after=first.next_cursor)
    assert [ld.load_id for ld in second.items] == ["L2"]
    third = a.loads(limit=1, after=second.next_cursor)
    assert [ld.load_id for ld in third.items] == ["L1"] and third.next_cursor is None


def test_a_loads_cursor_of_another_module_or_a_forgery_is_invalid() -> None:
    a = audited()
    a.audit.invocations = [invocation("L2", 1), invocation("L1", 1)]
    with pytest.raises(Invalid):
        a.loads(after="garbage")


# -- against a real Truss


def grants(h: Any) -> None:
    h.grant("aud", {"catalog": ["journal"]}, False)  # an auditor who reads and writes nothing


def uc(key: str) -> Ref:
    return Ref("catalog.UseCase", key)


def sol(key: str) -> Ref:
    return Ref("catalog.Solution", key)


def apply(h: Any, who: str, plan: Plan, key: str | None = None) -> Any:
    return h.backend().apply(h.principal(who), plan, idempotency_key=key)


def real_changes(h: Any, who: str, **kw: Any) -> Any:
    args = {**kwargs(), **kw}
    return h.backend().changes(h.principal(who), **args)


@pytest.mark.truss
def test_the_changes_of_a_module_are_its_groups_as_their_receipts_name_them(cluster: Any) -> None:
    h = _world(cluster, "journal")
    first = apply(
        h, "alice", Plan("catalog.AddUseCase", (), (Create(uc("a"), {"name": "A"}),)), "k1"
    )
    second = apply(
        h,
        "bob",
        Plan(
            "catalog.AddSolution",
            (),
            (
                Create(sol("s"), {"name": "S"}),
                Link("addresses", sol("s"), uc("a")),
                Update(uc("a"), {"name": "B"}),
            ),
        ),
        "k2",
    )
    page = real_changes(h, "alice")
    assert [c.group for c in page.items] == [second.group, first.group]
    assert [c.by for c in page.items] == ["bob", "alice"]
    newest = page.items[0]
    assert [(o["kind"], o.get("type") or o.get("relationship")) for o in newest.ops] == [
        ("create", "catalog.Solution"),
        ("link", "addresses"),
        ("update", "catalog.UseCase"),
    ]
    assert all(o.get("key") is None and o.get("version") is None for o in newest.ops if "key" in o)
    assert newest.at <= datetime.now(UTC)
    # a delete and an unlink are groups too
    gone = apply(
        h,
        "alice",
        Plan("catalog.Retire", (), (Unlink("addresses", sol("s"), uc("a")), Delete(sol("s")))),
    )
    top = real_changes(h, "alice", limit=1)
    assert [c.group for c in top.items] == [gone.group] and top.next_cursor is not None
    assert [(o["kind"]) for o in top.items[0].ops] == ["unlink", "delete"]


@pytest.mark.truss
def test_pages_continue_by_cursor_and_the_cursor_ends_with_the_listing(cluster: Any) -> None:
    h = _world(cluster, "journal")
    made = [
        apply(h, "alice", Plan("catalog.AddUseCase", (), (Create(uc(f"c{i}"), {"name": "N"}),)))
        for i in range(4)
    ]
    seen: list[str] = []
    after = None
    for _ in range(10):
        page = real_changes(h, "alice", limit=2, after=after)
        seen += [c.group for c in page.items]
        after = page.next_cursor
        if after is None:
            break
    assert seen == [m.group for m in reversed(made)]  # newest first, none twice, none missed
    # a group written after the first page does not enter the pages already being read
    first = real_changes(h, "alice", limit=1)
    apply(h, "alice", Plan("catalog.AddUseCase", (), (Create(uc("late"), {"name": "N"}),)))
    rest = real_changes(h, "alice", limit=10, after=first.next_cursor)
    assert [c.group for c in rest.items] == [m.group for m in reversed(made)][1:]


@pytest.mark.truss
def test_changes_by_person_action_group_type_and_time(cluster: Any) -> None:
    h = _world(cluster, "journal")
    a = apply(h, "alice", Plan("catalog.AddUseCase", (), (Create(uc("a"), {"name": "N"}),)))
    b = apply(h, "bob", Plan("catalog.AddSolution", (), (Create(sol("s"), {"name": "S"}),)))
    assert [c.group for c in real_changes(h, "alice", by="bob").items] == [b.group]
    assert [c.group for c in real_changes(h, "alice", action="catalog.AddUseCase").items] == [
        a.group
    ]
    assert [c.group for c in real_changes(h, "alice", module=None, group=a.group).items] == [
        a.group
    ]
    assert [c.group for c in real_changes(h, "alice", type="catalog.Solution").items] == [b.group]
    middle = real_changes(h, "alice").items[0].at
    assert [c.group for c in real_changes(h, "alice", until=middle).items][-1:] == [a.group]
    future = datetime(2100, 1, 1, tzinfo=UTC)
    assert real_changes(h, "alice", since=future).items == ()


@pytest.mark.truss
def test_an_import_is_a_load_and_no_change_and_loads_page_newest_first(cluster: Any) -> None:
    h = _world(cluster, "journal")
    h.backend().import_records(
        h.principal("alice"),
        "catalog",
        [{"type": "UseCase", "key": "i1", "properties": {"name": "I"}}],
        load_id="L9",
        initiated_by="alice",
    )
    assert real_changes(h, "alice").items == ()
    page = h.backend().loads(h.principal("alice"), "catalog", limit=1, after=None)
    assert [(ld.load_id, ld.initiated_by, ld.created, ld.partial) for ld in page.items] == [
        ("L9", "alice", 1, False)
    ]
    rest = h.backend().loads(h.principal("alice"), "catalog", limit=5, after=page.next_cursor)
    assert [ld.load_id for ld in rest.items] == ["seed"] and rest.next_cursor is None


@pytest.mark.truss
def test_a_load_of_several_calls_is_one_load_with_the_counts_of_its_listed_calls(
    cluster: Any,
) -> None:
    import arras.adapters.truss.load as load

    h = _world(cluster, "journal")
    n = load.BATCH + 5
    records = [
        {"type": "UseCase", "key": f"m{i:04d}", "properties": {"name": "M"}} for i in range(n)
    ]
    records.append({"relationship": "addresses", "source": "sol-1", "target": "m0001"})
    h.backend().import_records(
        h.principal("alice"), "catalog", records, load_id="big", initiated_by="alice"
    )
    page = h.backend().loads(h.principal("alice"), "catalog", limit=1, after=None)
    [big] = page.items
    # Truss 0.0.44's module-scoped discovery lists the invocations that imported entities; the one
    # that imported only the relationship is not listed (a pinned limit, truss-requirements R20), so
    # the counts are of the entities of the two calls that made them
    assert (big.load_id, big.created, big.skipped, big.partial) == ("big", n, 0, False)


@pytest.mark.truss
def test_reading_and_writing_do_not_authorize_an_audit_and_an_auditor_reads_no_data(
    cluster: Any,
) -> None:
    from arras.errors import Invalid as NoModule

    h = _world(cluster, "journal")
    grants(h)
    apply(h, "alice", Plan("catalog.AddUseCase", (), (Create(uc("a"), {"name": "N"}),)))
    for who in ("carol", "bob", "dave"):  # a reader, a writer and a stranger
        with pytest.raises(Refused):
            real_changes(h, who)
        with pytest.raises(Refused):
            h.backend().loads(h.principal(who), "catalog", limit=5, after=None)
    seen = real_changes(h, "aud")  # the auditor lists the group and reads no catalog
    assert [c.action for c in seen.items] == ["catalog.AddUseCase"]
    assert seen.items[0].ops[0]["type"].startswith("#")  # a type this person cannot name
    assert h.backend().loads(h.principal("aud"), "catalog", limit=5, after=None).items
    sql = "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 10"
    from arras.types import Statement

    with pytest.raises((Refused, NoModule, Unavailable)):
        h.backend().query(h.principal("aud"), "catalog", Statement(sql, {}), limit=10)


@pytest.mark.truss
def test_a_revoked_auditor_is_refused_on_the_very_next_call_page_or_cursor(cluster: Any) -> None:
    h = _world(cluster, "journal")
    grants(h)
    for i in range(3):
        apply(h, "alice", Plan("catalog.AddUseCase", (), (Create(uc(f"c{i}"), {"name": "N"}),)))
    first = real_changes(h, "aud", limit=1)
    assert first.next_cursor is not None
    h.world.cluster.su.execute('REVOKE "catalog_auditor" FROM "aud"')
    with pytest.raises(Refused):
        real_changes(h, "aud", limit=1, after=first.next_cursor)  # a cursor grants nothing
    with pytest.raises(Refused):
        real_changes(h, "aud")
    with pytest.raises(Refused):
        h.backend().loads(h.principal("aud"), "catalog", limit=5, after=None)


@pytest.mark.truss
def test_a_key_filter_is_unsupported_and_a_dry_run_leaves_no_change(cluster: Any) -> None:
    h = _world(cluster, "journal")
    with pytest.raises(Unsupported):
        real_changes(h, "alice", type="catalog.UseCase", key="uc-1")
    before = real_changes(h, "alice").items
    h.backend().apply(
        h.principal("alice"),
        Plan("catalog.AddUseCase", (), (Create(uc("dry"), {"name": "N"}),)),
        idempotency_key=None,
        dry_run=True,
    )
    assert real_changes(h, "alice").items == before
