# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The audit reads through the operator surface, with the store's clock in the test's hands
(CONTRACT-001, Audit reads; CONTRACT-009): time filters, their boundaries, cursors and paging,
newest first, and the journal grant."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from arras.sandbox import Sandbox
from test_operate import Client

SEEDED = datetime(2026, 1, 1, tzinfo=UTC)
T = [datetime(2026, 3, d, tzinfo=UTC) for d in (1, 2, 3)]  # t0 < t1 < t2


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


@pytest.fixture
def world() -> tuple[Client, list[str], list[str]]:
    """The sandbox seeded at `SEEDED`; then bob adds a use case at each of t0, t1, t2 and root
    imports a load at each. Returns the client, bob's groups and the load ids, oldest first."""
    box = Sandbox()
    clock = Clock(SEEDED)
    box.store.clock = clock
    box.seed()
    bob = box.arras.session(box.people["bob"])
    root = box.arras.session(box.people["root"])
    groups, loads = [], []
    for i, t in enumerate(T):
        clock.at = t
        r = bob.invoke("catalog.AddUseCase", {"code": f"uc-t{i}", "name": "T"})
        groups.append(r.group)
        rec = {"type": "catalog.UseCase", "key": f"uc-l{i}", "properties": {"name": "L"}}
        root.import_records("catalog", [rec], load_id=f"L{i}")
        loads.append(f"L{i}")
    return Client(box), groups, loads


def changes(c: Client, **body: Any) -> tuple[int, Any]:
    status, page, _ = c.post("/audit/changes", {"module": "catalog", **body})
    return status, page


def groups_of(page: Any) -> list[str]:
    return [x["group"] for x in page["items"]]


def test_since_and_until_are_inclusive_bounds(world) -> None:
    c, g, _ = world
    iso = [t.isoformat() for t in T]
    assert groups_of(changes(c, by="bob", since=iso[1])[1]) == [g[2], g[1]]
    assert groups_of(changes(c, by="bob", until=iso[1])[1]) == [g[1], g[0]]
    assert groups_of(changes(c, by="bob", since=iso[1], until=iso[1])[1]) == [g[1]]
    assert groups_of(changes(c, by="bob", since=iso[0], until=iso[2])[1]) == g[::-1]
    # the same instant written with another offset is the same bound
    assert groups_of(changes(c, by="bob", since="2026-03-02T05:30:00+05:30")[1]) == [g[2], g[1]]
    # one microsecond past a change leaves it out
    assert groups_of(changes(c, by="bob", since="2026-03-02T00:00:00.000001Z")[1]) == [g[2]]
    assert groups_of(changes(c, by="bob", until="2026-03-01T23:59:59.999999Z")[1]) == [g[0]]
    assert changes(c, by="bob", since=iso[2], until=iso[0])[1]["items"] == []
    # every change carries the store's time for it
    _, page = changes(c, by="bob")
    assert [x["at"] for x in page["items"]] == [t.isoformat() for t in T[::-1]]


def test_a_time_filter_applies_to_the_seeded_changes_too(world) -> None:
    c, g, _ = world
    _, all_ = changes(c, limit=100)
    assert len(all_["items"]) == 6  # three seeded, three of bob's
    _, old = changes(c, until="2026-02-01T00:00:00Z")
    assert {x["by"] for x in old["items"]} == {"alice"} and len(old["items"]) == 3
    assert groups_of(all_)[:3] == g[::-1]  # newest first


@pytest.mark.parametrize("after", ["-1", "abc", "1.5", "-0x1"])
def test_a_cursor_that_was_not_issued_is_400(world, after: str) -> None:
    c, _, _ = world
    status, e = changes(c, after=after)
    assert status == 400 and e["error"]["type"] == "Invalid"
    assert e["error"]["violations"][0]["path"] == "after"
    status, _, _ = c.post("/audit/loads", {"module": "catalog", "after": after})
    assert status == 400


@pytest.mark.parametrize("limit", [0, 101, -1, "5", True, 1.5, None])
def test_a_limit_out_of_range_or_of_another_type_is_400(world, limit: Any) -> None:
    c, _, _ = world
    assert changes(c, limit=limit)[0] == 400
    assert c.post("/audit/loads", {"module": "catalog", "limit": limit})[0] == 400


def _walk(c: Client, path: str, size: int, **body: Any) -> tuple[list[str], int]:
    """Every item, a page at a time: (the ids in order, the pages read). Each page but the last
    is full and names the next; the last names none."""
    out: list[str] = []
    after = None
    pages = 0
    while True:
        status, page, _ = c.post(
            path,
            {"module": "catalog", "limit": size, **({"after": after} if after else {}), **body},
        )
        assert status == 200
        pages += 1
        ids = [x.get("group") or x.get("load_id") for x in page["items"]]
        out += ids
        after = page["nextCursor"]
        if after is None:
            return out, pages
        assert len(ids) == size and pages < 50


@pytest.mark.parametrize("size", [1, 2, 3, 5, 6, 7, 100])
def test_paging_reads_every_change_once_newest_first(world, size: int) -> None:
    c, _, _ = world
    _, whole = changes(c, limit=100)
    every = groups_of(whole)
    assert len(every) == 6 and whole["nextCursor"] is None
    got, pages = _walk(c, "/audit/changes", size)
    assert got == every
    assert pages == max(1, -(-6 // size))  # no empty page after a full last one


@pytest.mark.parametrize("size", [1, 2, 4, 100])
def test_loads_are_newest_first_and_page_the_same_way(world, size: int) -> None:
    c, _, loads = world
    status, page, _ = c.post("/audit/loads", {"module": "catalog", "limit": 100})
    assert status == 200
    assert [x["load_id"] for x in page["items"]] == loads[::-1]
    assert [x["at"] for x in page["items"]] == [t.isoformat() for t in T[::-1]]
    assert {x["initiated_by"] for x in page["items"]} == {"root"}
    got, pages = _walk(c, "/audit/loads", size)
    assert got == loads[::-1] and pages == -(-3 // size)


def test_a_cursor_past_the_end_is_an_empty_last_page(world) -> None:
    c, _, _ = world
    status, page = changes(c, after="6")
    assert status == 200 and page["items"] == [] and page["nextCursor"] is None


def test_the_journal_grant_decides_both_reads(world) -> None:
    c, _, _ = world
    for path in ("/audit/changes", "/audit/loads"):
        status, e, _ = c.post(path, {"module": "catalog"}, user="carol")  # reads, no journal
        assert status == 403 and e["error"]["reason"] == "no_access", path
        assert c.post(path, {"module": "catalog"}, user="alice")[0] == 200, path
        assert c.post(path, {"module": "catalog"}, user="dave")[0] == 404, (
            path
        )  # unreadable: unknown


def test_audit_routes_accept_a_provider() -> None:
    """`provider` in the POST body picks which provider's journal is read; the same rules as the
    library: the record store by default, a placed provider by name, any other name a 422."""
    from types import SimpleNamespace

    from test_operator_library import two_providers

    h, o, _, _ = two_providers()
    o.invoke("catalog.AddUseCase", {"code": "v1", "name": "V"})
    on_vault = o.invoke("catalog.AddSolution", {"code": "s1", "name": "S", "useCase": "v1"})
    c = Client(SimpleNamespace(arras=h, principal=lambda name: o.principal))  # type: ignore[arg-type]

    status, page = changes(c)
    assert status == 200 and {x["backend"] for x in page["items"]} == {"primary"}
    status, page = changes(c, provider="vault")
    assert status == 200 and groups_of(page) == [on_vault.group]
    status, page = changes(c, provider="vault", type="catalog.Solution", key="s1")
    assert status == 200 and groups_of(page) == [on_vault.group]
    status, page, _ = c.post("/audit/loads", {"module": "catalog", "provider": "vault"})
    assert status == 200 and [x["load_id"] for x in page["items"]] == ["V1"]
    for path, body in (
        ("/audit/changes", {"module": "catalog", "provider": "mirror"}),
        ("/audit/loads", {"module": "catalog", "provider": "nowhere"}),
    ):
        status, err, _ = c.post(path, body)
        assert status == 404, err  # unknown_type, as for an unknown module
        assert err["error"]["violations"][0]["path"] == "provider"
    status, err, _ = c.post("/audit/changes", {"group": on_vault.group, "provider": "vault"})
    assert status == 400 and err["error"]["violations"][0]["code"] == "scope"
    status, _, _ = c.post("/audit/changes", {"module": "catalog", "provider": 7})
    assert status == 400
