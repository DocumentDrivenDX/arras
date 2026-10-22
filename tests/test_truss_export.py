# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The Truss adapter's `export_records` (CONTRACT-003, Export): the module's graph as records, read as
the person through Weft a page at a time.

The unit tests are always on: a scripted fake of Truss's assembly behind the connection layer's
`Toolkit` seam, with results named as Truss names them. The Truss-marked tests run the export corpus
cases and the checks the corpus cannot make against a real Truss on PostgreSQL 18.6
(`uv run --extra truss --group truss-test pytest -m truss tests/test_truss_export.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

import arras.adapters.truss.export as export
from arras.conformance import run_corpus
from arras.errors import Invalid, Refused, Unavailable, Unsupported
from arras.exportcursor import cursor
from arras.types import Principal
from test_truss_harness import _world, cluster  # noqa: F401
from test_truss_query import (
    AT,
    QueryAbsent,
    QueryRelatedKeys,
    QueryRig,
    QueryRows,
    refused,
)
from test_truss_registry import ALICE, CatalogRefused, ReaderCatalog, ok
from truss_harness import TrussHarness

WHOLE = (
    "code",
    "name",
    "workArea",
    "_version",
    "_original_author",
    "_original_at",
    "addressedBy",
)


def rig(*answers: Any) -> QueryRig:
    r = QueryRig()
    r.assembly.answers = list(answers)
    return r


def use_cases(*rows: tuple[Any, ...]) -> list[Any]:
    """Truss's answers for a type: the keys, then each entity read whole by its key."""
    return [
        ok(QueryRows(("code",), tuple((r[0],) for r in rows))),
        *[ok(QueryRows(WHOLE, (r,))) for r in rows],
    ]


def solutions(*rows: tuple[Any, ...]) -> list[Any]:
    columns = ("code", "name", "coverageLevel", "addresses")
    return [
        ok(QueryRows(("code",), tuple((r[0],) for r in rows))),
        *[ok(QueryRows(columns, (r,))) for r in rows],
    ]


def edges(*rows: tuple[Any, ...]) -> Any:
    return ok(QueryRows(("src", "tgt"), rows))


def nothing(columns: tuple[str, ...] = ("code",)) -> Any:
    return ok(QueryRows(columns, ()))


def pages(
    r: QueryRig, *, limit: int = 500, after: str | None = None, who: Principal = ALICE
) -> Any:
    return r.backend().export_records(who, "catalog", limit=limit, after=after)


def sql_of(r: QueryRig) -> list[str]:
    return [c["sql"] for c in r.assembly.calls]


NO = QueryAbsent()


# -- the person and the module come first


def test_an_export_with_no_token_never_connects() -> None:
    r = rig(nothing())
    with pytest.raises(Refused) as raised:
        pages(r, who=Principal("anon", ""))
    assert (raised.value.reason, r.conns) == ("token_expired", [])


@pytest.mark.parametrize("catalog", [ok(CatalogRefused()), ok(ReaderCatalog(3, ()))])
def test_a_module_the_person_cannot_read_is_refused_never_an_empty_page(catalog: Any) -> None:
    r = rig(nothing())
    r.assembly.catalog = catalog
    with pytest.raises(Refused) as raised:
        pages(r)
    assert raised.value.reason == "no_access" and r.assembly.calls == []


@pytest.mark.parametrize("limit", [0, 501, -1])
def test_a_limit_outside_one_to_five_hundred_is_invalid_before_truss_is_queried(limit: int) -> None:
    r = rig(nothing())
    with pytest.raises(Invalid) as raised:
        pages(r, limit=limit)
    assert raised.value.violations[0].code == "bound" and r.assembly.calls == []


@pytest.mark.parametrize(
    "after", ["not-a-cursor", cursor((0, "catalog.Nope", "k")), cursor((1, "nope", "a", "b"))]
)
def test_a_cursor_that_is_not_of_this_export_is_invalid(after: str) -> None:
    r = rig(nothing())
    with pytest.raises(Invalid) as raised:
        pages(r, after=after)
    assert raised.value.violations[0].code == "cursor" and r.assembly.calls == []


# -- the records


def test_the_graph_is_entities_by_type_then_relationships_with_facts_only_where_they_exist() -> (
    None
):
    old = datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
    r = rig(
        *use_cases(
            ("uc-0", "Zero", NO, 1, None, None, QueryRelatedKeys(())),
            ("uc-7", "Old", "finance", 1, "ann", old, QueryRelatedKeys((("sol-1",),))),
        ),
        *solutions(("sol-1", "Ext", NO, QueryRelatedKeys((("uc-7",), ("uc-0",))))),
        edges(("sol-1", QueryRelatedKeys((("uc-7",), ("uc-0",)))), ("sol-2", NO)),
    )
    got = pages(r)
    assert [dict(x) for x in got.items] == [
        {"type": "UseCase", "key": "uc-0", "properties": {"name": "Zero"}},
        {
            "type": "UseCase",
            "key": "uc-7",
            "properties": {"name": "Old", "workArea": "finance"},
            "original_author": "ann",
            "original_at": "2020-01-02T03:04:05+00:00",
        },
        {"type": "Solution", "key": "sol-1", "properties": {"name": "Ext"}},
        {"relationship": "addresses", "source": "sol-1", "target": "uc-0"},
        {"relationship": "addresses", "source": "sol-1", "target": "uc-7"},
    ]
    assert got.next_cursor is None and got.omitted == ()
    assert (got.freshness.backend, got.freshness.as_of.value, got.freshness.as_of.at) == (
        "truss",
        "truss-read-position-v1:x",
        AT,
    )


def test_keys_are_listed_by_keyset_and_each_entity_read_whole_in_one_read_only_call() -> None:
    r = rig(
        *use_cases(("uc-1", "A", NO, 1, None, None, QueryRelatedKeys(()))),
        *solutions(),
        nothing(("src", "tgt")),
    )
    pages(r)
    whole = "SELECT u.* FROM catalog.UseCase u WHERE u.code = :key ORDER BY u.code LIMIT 1"
    assert sql_of(r) == [
        f"SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT {export.BATCH}",
        whole,
        f"SELECT u.code FROM catalog.Solution u ORDER BY u.code LIMIT {export.BATCH}",
        "SELECT s.code AS src, RELATED_KEYS(s.addresses, 100) AS tgt FROM catalog.Solution s "
        f"ORDER BY s.code LIMIT {export.BATCH}",
    ]
    assert r.assembly.calls[1]["parameters"] == {"key": "uc-1"}
    assert [c.get("read_profile") for c in r.assembly.calls] == [
        None,
        "complete-entity",
        None,
        None,
    ]
    assert len(r.conns) == 1 and r.conns[0].log[0].endswith("READ ONLY")


def test_a_page_stops_at_the_limit_and_its_cursor_resumes_after_the_last_record() -> None:
    first = rig(
        *use_cases(
            ("uc-1", "A", NO, 1, None, None, QueryRelatedKeys(())),
            ("uc-2", "B", NO, 1, None, None, QueryRelatedKeys(())),
            ("uc-3", "C", NO, 1, None, None, QueryRelatedKeys(())),
        )
    )
    got = pages(first, limit=2)
    assert [x["key"] for x in got.items] == ["uc-1", "uc-2"]
    assert got.next_cursor == cursor((0, "catalog.UseCase", "uc-2"))
    second = rig(*use_cases(), *solutions(), nothing(("src", "tgt")))
    pages(second, after=got.next_cursor)
    assert sql_of(second)[0] == (
        f"SELECT u.code FROM catalog.UseCase u WHERE u.code > :last ORDER BY u.code LIMIT {export.BATCH}"
    )
    assert second.assembly.calls[0]["parameters"] == {"last": "uc-2"}


def test_a_cursor_in_the_relationships_skips_the_entities_and_resumes_after_the_edge() -> None:
    r = rig(
        edges(("sol-1", QueryRelatedKeys((("uc-1",), ("uc-2",))))),
        edges(("sol-3", QueryRelatedKeys((("uc-1",),)))),
    )
    got = pages(r, after=cursor((1, "addresses", "sol-1", "uc-1")))
    head = "SELECT s.code AS src, RELATED_KEYS(s.addresses, 100) AS tgt FROM catalog.Solution s "
    assert sql_of(r) == [
        f"{head}WHERE s.code = :key ORDER BY s.code LIMIT 1",
        f"{head}WHERE s.code > :last ORDER BY s.code LIMIT {export.BATCH}",
    ]
    assert [c["parameters"] for c in r.assembly.calls] == [{"key": "sol-1"}, {"last": "sol-1"}]
    assert not any(">=" in sql for sql in sql_of(r))
    assert [(x["source"], x["target"]) for x in got.items] == [("sol-1", "uc-2"), ("sol-3", "uc-1")]


def test_a_page_boundary_inside_the_edges_of_one_source_resumes_with_the_rest_of_them() -> None:
    first = rig(
        *use_cases(),
        *solutions(),
        edges(
            ("sol-1", QueryRelatedKeys((("uc-2",), ("uc-1",)))),
            ("sol-3", QueryRelatedKeys((("uc-1",),))),
        ),
    )
    one = pages(first, limit=2)
    assert [(x["source"], x["target"]) for x in one.items] == [("sol-1", "uc-1"), ("sol-1", "uc-2")]
    assert one.next_cursor == cursor((1, "addresses", "sol-1", "uc-2"))
    second = rig(
        edges(("sol-1", QueryRelatedKeys((("uc-2",), ("uc-1",), ("uc-3",))))),
        edges(("sol-3", QueryRelatedKeys((("uc-1",),)))),
    )
    two = pages(second, limit=2, after=one.next_cursor)
    assert [(x["source"], x["target"]) for x in two.items] == [("sol-1", "uc-3"), ("sol-3", "uc-1")]
    assert two.next_cursor is None
    assert not any(">=" in sql for sql in sql_of(first) + sql_of(second))


def test_a_source_with_more_related_keys_than_truss_gives_is_unsupported_never_cut() -> None:
    r = rig(
        *use_cases(),
        *solutions(),
        edges(("sol-1", QueryRelatedKeys((("uc-1",),), truncated=True))),
    )
    with pytest.raises(Unsupported):
        pages(r)


def test_a_relationship_whose_source_type_is_in_another_module_is_unsupported_and_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    from arras.adapters.truss.registry import Registry

    real = Registry.module_info

    def foreign(self: Any, call: Any, head: int, entry: Any) -> Any:
        info = real(self, call, head, entry)
        assert info is not None
        rel = info.relationships[0]
        return replace(info, relationships=(replace(rel, source=("other.Thing",)),))

    monkeypatch.setattr(Registry, "module_info", foreign)
    r = rig(*use_cases(), *solutions(), edges())
    with pytest.raises(Unsupported) as raised:
        pages(r)
    assert "other.Thing" in str(raised.value) and r.assembly.calls == []


def test_a_whole_entity_with_more_related_keys_than_truss_gives_is_unsupported() -> None:
    with pytest.raises(Unsupported):
        pages(rig(use_cases(("uc-1",))[0], refused("limits")))


def test_a_type_is_read_in_batches_by_the_last_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export, "BATCH", 2)

    def row(key: str) -> tuple[Any, ...]:
        return (key, "n", NO, 1, None, None, QueryRelatedKeys(()))

    keys = ok(QueryRows(("code",), (("uc-1",), ("uc-2",))))
    r = rig(
        keys,
        *use_cases(row("uc-1"))[1:],
        *use_cases(row("uc-2"))[1:],
        *use_cases(row("uc-3")),
        *solutions(),
        nothing(("src", "tgt")),
    )
    got = pages(r)
    assert [x["key"] for x in got.items] == ["uc-1", "uc-2", "uc-3"]
    assert sql_of(r)[3] == (
        "SELECT u.code FROM catalog.UseCase u WHERE u.code > :last ORDER BY u.code LIMIT 2"
    )
    assert r.assembly.calls[3]["parameters"] == {"last": "uc-2"}


def test_a_page_with_no_position_is_unavailable() -> None:
    r = rig(
        ok(QueryRows(("code",), (), as_of=None)),
        ok(QueryRows(("code",), (), as_of=None)),
        ok(QueryRows(("src", "tgt"), (), as_of=None)),
    )
    with pytest.raises(Unavailable):
        pages(r)


def test_a_backend_with_no_connections_is_not_configured() -> None:
    from arras.adapters.truss import TrussBackend

    with pytest.raises(Unavailable) as raised:
        TrussBackend("truss").export_records(ALICE, "catalog", limit=1, after=None)
    assert raised.value.reason == "not_configured"


# -- against a real Truss


@pytest.mark.truss
def test_the_export_corpus_cases_pass_with_no_limit(cluster: Any) -> None:  # noqa: F811
    report = run_corpus(
        lambda: TrussHarness(cluster),
        only=[
            "export.canonical-order-and-absent-properties",
            "export.refused-without-read-never-empty",
            "export.pages-resume-after-the-last-record",
        ],
    )
    assert report.passed, [(r.case, r.message) for r in report.failed]
    assert [r.status for r in report.results] == ["passed"] * 3


@pytest.mark.truss
def test_the_whole_graph_is_the_pages_in_order_and_what_the_person_wrote_is_in_it(
    cluster: Any,  # noqa: F811
) -> None:
    h = _world(cluster, "basic")
    who = h.principal("carol")
    whole = h.backend().export_records(who, "catalog", limit=500, after=None)
    assert whole.next_cursor is None
    seen: list[Any] = []
    after = None
    while True:
        page = h.backend().export_records(who, "catalog", limit=1, after=after)
        seen += list(page.items)
        after = page.next_cursor
        if after is None:
            break
    assert seen == list(whole.items) and len(seen) >= 3
    kinds = ["type" in x for x in seen]
    assert kinds == sorted(kinds, reverse=True)  # every entity before any relationship


@pytest.mark.truss
def test_a_person_with_no_role_on_the_module_is_refused_not_given_nothing(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster, "basic")
    with pytest.raises(Refused):
        h.backend().export_records(h.principal("dave"), "catalog", limit=10, after=None)


@pytest.mark.truss
def test_pages_that_break_inside_the_relationships_are_the_whole_export(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster, "basic")
    h.seed("alice", [{"relationship": "addresses", "source": "sol-1", "target": "uc-2"}])
    who = h.principal("carol")
    whole = h.backend().export_records(who, "catalog", limit=500, after=None)
    assert whole.next_cursor is None
    seen: list[Any] = []
    after = None
    firsts: list[Any] = []
    while True:
        page = h.backend().export_records(who, "catalog", limit=4, after=after)
        firsts.append(page)
        seen += list(page.items)
        after = page.next_cursor
        if after is None:
            break
    assert seen == list(whole.items)
    assert "relationship" in firsts[0].items[-1]  # the first boundary is inside the edges
    assert len(firsts) > 1 and any("relationship" in x for x in firsts[1].items)
