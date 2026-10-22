# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""CONTRACT-010, section C: the search read, as `Ontology.search` and as `_search`."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

import pytest

from arras import Conflict, Invalid, NotYetCurrent, Unavailable
from arras.devhost import seed_demo
from arras.fakes import MemoryStore
from arras.sandbox import Sandbox
from arras.searchplan import EntityBudget
from test_console import Client
from test_telemetry import _exporter

EXAMPLE = Path(__file__).parent.parent / "examples" / "catalog"


@pytest.fixture
def box() -> Sandbox:
    return seed_demo(Sandbox().seed())  # 12 use cases and 10 solutions


@pytest.fixture
def carol(box: Sandbox):
    return box.arras.session(box.people["carol"])


def root_import(box: Sandbox, records: list[dict[str, Any]]) -> None:
    box.arras.session(box.people["root"]).import_records("catalog", records, load_id="more")
    box.replica.feed()


def spy_queries(monkeypatch) -> list[Any]:
    """Every `MemoryStore.query`, with whether another was running at the same time."""
    calls: list[Any] = []
    real = MemoryStore.query
    lock = threading.Lock()
    running = [0]

    def spy(self, principal, module, statement, *, limit, text=None):
        rq = self._statement(principal, module, statement, text)  # what the fake was asked
        with lock:
            running[0] += 1
            calls.append((self.name, rq, limit, running[0]))
        try:
            return real(self, principal, module, statement, limit=limit, text=text)
        finally:
            with lock:
                running[0] -= 1

    monkeypatch.setattr(MemoryStore, "query", spy)
    return calls


# -- ranked hits across types (US-065-AC1) -------------------------------------------------------


def test_hits_of_every_type_are_ranked_with_label_excerpt_and_freshness(carol) -> None:
    """@covers US-065-AC1, US-065-AC3: ranked across types, each with type, label and a marked
    excerpt, and the freshness of the backend that answered."""
    page = carol.search("catalog", "pipeline")
    assert [(h.type, h.key) for h in page.hits] == [  # equal scores: type order, then key
        ("UseCase", "uc-pipeline"),
        ("UseCase", "uc-pipeline-review"),
        ("Solution", "sol-1"),
        ("Solution", "sol-pipeline-risk"),
    ]
    first = page.hits[0]
    assert first.label == "Pipeline mapping" and first.score == 6
    # cut from `code`: the title uses `name`, so the excerpt does not repeat it
    assert [(s.text, s.mark) for s in first.excerpt] == [("uc-", False), ("pipeline", True)]
    assert first.matched == ("name", "code")
    assert [f.backend for f in page.freshness] == ["memory"]
    assert page.freshness[0].consistency == "latest" and page.freshness[0].as_of.value
    assert page.not_searched == () and page.truncated is False
    assert page.text == "pipeline"


def test_the_excerpt_is_null_when_the_title_uses_every_matched_property(carol) -> None:
    """The title of a use case is its name: a match only in the name shows no second copy of it."""
    page = carol.search("catalog", "mapping")
    hit = next(h for h in page.hits if h.key == "uc-pipeline")
    assert hit.matched == ("name",) and hit.label == "Pipeline mapping"
    assert hit.excerpt is None


def test_the_text_is_folded_and_every_word_must_match(carol) -> None:
    a = carol.search("catalog", "  PIPELINE   Review ")
    assert a.text == "pipeline review"
    assert [h.key for h in a.hits] == ["uc-pipeline-review"]  # the others have no "review"
    assert carol.search("catalog", "pipeline zzzz").hits == ()


def test_hits_with_equal_scores_are_ordered_by_type_then_key(carol) -> None:
    page = carol.search("catalog", "review", limit=50)
    keys = [(h.score, h.type, h.key) for h in page.hits]
    assert keys == sorted(keys, key=lambda k: (-k[0], ["UseCase", "Solution"].index(k[1]), k[2]))
    assert len(page.hits) >= 3


def test_the_entity_is_the_row_the_search_read(carol, monkeypatch) -> None:
    calls = spy_queries(monkeypatch)
    page = carol.search("catalog", "pipeline")
    assert len(calls) == 2  # one read per searched type, no more
    hit = page.hits[0]
    assert hit.row["name"] == "Pipeline mapping" and hit.row["_created_by"] == "alice"
    assert hit.row["addressedBy"] == ["sol-1"]


# -- types, counts, limit (US-066) ---------------------------------------------------------------


def test_counts_are_per_searched_type_and_a_type_with_none_says_zero(carol) -> None:
    """@covers US-066-AC3, US-065-AC4: the number of hits of each type, zero included."""
    page = carol.search("catalog", "capacity")
    assert [(c.type, c.count, c.at_least) for c in page.counts] == [
        ("UseCase", 1, False),
        ("Solution", 1, False),
    ]
    none = carol.search("catalog", "zzzz")
    assert none.hits == () and [(c.type, c.count) for c in none.counts] == [
        ("UseCase", 0),
        ("Solution", 0),
    ]


def test_types_narrow_the_search_and_an_unknown_type_is_a_bad_query(carol) -> None:
    """@covers US-066-AC4: only hits of the chosen types."""
    page = carol.search("catalog", "pipeline", types=["Solution"])
    assert {h.type for h in page.hits} == {"Solution"}
    assert [c.type for c in page.counts] == ["Solution"]
    assert carol.search("catalog", "pipeline", types=["Solution", "Solution"]).counts == page.counts
    for bad in (["Nope"], ["catalog.Solution"], ["solution"]):
        with pytest.raises(Invalid) as e:
            carol.search("catalog", "pipeline", types=bad)
        assert e.value.violations[0].path == "types"


def test_text_and_limit_are_bounded(carol) -> None:
    for bad in ("", "x", "a b c d e f g", "y" * 201):
        with pytest.raises(Invalid):
            carol.search("catalog", bad)
    for limit in (0, 51, -1, True, "5"):
        with pytest.raises(Invalid) as e:
            carol.search("catalog", "pipeline", limit=limit)
        assert e.value.violations[0].path == "limit"
    with pytest.raises(Invalid):
        carol.search("catalog", "pipeline", consistency="eventual")


def test_hits_are_cut_to_the_limit_and_the_page_says_truncated(carol) -> None:
    page = carol.search("catalog", "review", limit=2)
    assert len(page.hits) == 2 and page.truncated is True
    assert carol.search("catalog", "review", limit=50).truncated is False


def test_a_type_that_reaches_its_candidate_cap_says_at_least(
    box: Sandbox, carol, monkeypatch
) -> None:
    root_import(
        box,
        [
            {
                "type": "UseCase",
                "key": f"uc-bulk-{i:03}",
                "properties": {"name": f"Bulk pipeline {i}"},
            }
            for i in range(60)
        ],
    )
    calls = spy_queries(monkeypatch)
    page = carol.search("catalog", "bulk pipeline", limit=50)
    uc = next(c for c in page.counts if c.type == "UseCase")
    assert (uc.count, uc.at_least) == (50, True) and page.truncated is True
    assert all(limit == 50 for _, _, limit, _ in calls)  # never more than 50 candidates a type
    assert len(page.hits) == 50


# -- reads: sequential, as the viewer, one revision --------------------------------------------


def test_the_per_type_reads_run_one_after_another_with_a_structured_text_match(
    carol, monkeypatch
) -> None:
    calls = spy_queries(monkeypatch)
    carol.search("catalog", "pipeline review")
    assert [rq.type for _, rq, _, _ in calls] == ["catalog.UseCase", "catalog.Solution"]
    assert all(running == 1 for _, _, _, running in calls)  # never two at once
    for _, rq, _, _ in calls:
        assert rq.text.words == ("pipeline", "review") and rq.text.properties == ("name", "code")
        assert rq.whole and rq.conds == () and not rq.aggregated and not rq.joins
        assert "pipeline" not in repr(rq.conds)  # the text is not in the SQL-shaped parts


def test_a_backend_answering_under_another_revision_is_a_conflict(
    box: Sandbox, carol, monkeypatch
) -> None:
    """@covers US-065-AC1: the whole search runs under one registry revision."""
    from arras.sandbox import catalog_document

    real = MemoryStore.query
    done = []

    def change_then_read(self, principal, module, statement, *, limit, text=None):
        if not done:
            done.append(1)
            doc = json.loads(catalog_document())
            doc["modules"][0]["extensions"]["umf.ddd"]["terms"] = [
                {"id": "t", "name": "t", "definition": "d"}
            ]
            self.register(
                box.people["root"],
                json.dumps(doc).encode(),
                _parsed(doc),
                unknown_endpoint="reject",
            )
        return real(self, principal, module, statement, limit=limit, text=text)

    def _parsed(doc):
        from dataclasses import replace

        from arras.umf import parse_module

        return replace(parse_module(json.dumps(doc)), placement=self_placement)

    self_placement = box.store.modules["catalog"].placement
    monkeypatch.setattr(MemoryStore, "query", change_then_read)
    with pytest.raises(Conflict) as e:
        carol.search("catalog", "pipeline")
    assert e.value.reason == "revision"


def test_a_revision_the_caller_began_under_that_is_no_longer_current_is_a_conflict(carol) -> None:
    mod = carol.describe("catalog")[0]
    assert carol.search("catalog", "pipeline", revision=mod.revision).hits
    from arras import Revision

    with pytest.raises(Conflict):
        carol.search("catalog", "pipeline", revision=Revision({"memory": 99}))


def test_a_candidate_the_backend_should_not_have_returned_is_dropped(carol, monkeypatch) -> None:
    """The library re-checks every candidate with the same fold, so a backend's differing case
    handling cannot show a non-match."""

    real = MemoryStore.query

    def lax(self, principal, module, statement, *, limit, text=None):
        return real(self, principal, module, statement, limit=limit, text=None)

    monkeypatch.setattr(MemoryStore, "query", lax)
    page = carol.search("catalog", "capacity")
    assert sorted(h.key for h in page.hits) == ["sol-capacity", "uc-capacity-check"]
    assert [c.count for c in page.counts] == [1, 1]


def test_at_least_waits_for_a_position_the_backend_has_not_reached(carol) -> None:
    with pytest.raises(NotYetCurrent):
        carol.search("catalog", "pipeline", at_least="fake:999999")


def test_bulk_reads_come_from_the_replica_and_say_so(box: Sandbox, carol) -> None:
    page = carol.search("catalog", "pipeline", consistency="bulk")
    assert [f.backend for f in page.freshness] == ["memory_replica"]
    assert page.freshness[0].consistency == "bulk" and page.hits


def test_a_viewer_who_may_not_read_the_module_gets_nothing(box: Sandbox) -> None:
    dave = box.arras.session(box.people["dave"])
    with pytest.raises(Invalid):
        dave.search("catalog", "pipeline")  # the same answer as a module that does not exist
    with pytest.raises(Invalid):
        dave.search("nope", "pipeline")


# -- what was not searched, and why (US-065-AC6) -------------------------------------------------


def test_a_type_whose_backend_declares_no_search_is_named_not_searched(box: Sandbox, carol) -> None:
    """@covers US-065-AC6: the type is `no_capability`, the others still answer, and it is not
    counted as having no hits."""
    box.store.declare_search("catalog.Solution", "none")
    page = carol.search("catalog", "pipeline")
    assert [(n.type, n.reason, n.backend) for n in page.not_searched] == [
        ("Solution", "no_capability", "memory")
    ]
    assert {h.type for h in page.hits} == {"UseCase"}
    assert [c.type for c in page.counts] == ["UseCase"]
    box.store.declare_search("catalog.Solution", None)
    assert carol.search("catalog", "pipeline").not_searched == ()


def test_a_backend_that_lists_no_matching_property_is_no_searchable_property(
    box: Sandbox, carol
) -> None:

    box.store.declare_search("catalog.Solution", "substring", searchable=("summary",))
    page = carol.search("catalog", "pipeline")
    assert [(n.type, n.reason) for n in page.not_searched] == [
        ("Solution", "no_searchable_property")
    ]


def test_a_type_with_an_empty_search_list_is_not_requested_by_default_but_named_when_asked() -> (
    None
):
    doc = json.loads((EXAMPLE / "catalog.umf.json").read_text())
    for el in doc["modules"][0]["elements"]:
        if el["id"] == "CoverageAssertion":
            el["extensions"]["arras.view"]["search"] = []
    box = Sandbox().load(json.dumps(doc))
    o = box.arras.session(box.people["carol"])
    assert "CoverageAssertion" not in [c.type for c in o.search("catalog", "full").counts]
    assert o.search("catalog", "full").not_searched == ()  # not requested, so not named
    page = o.search("catalog", "full", types=["CoverageAssertion", "Product"])
    assert [(n.type, n.reason) for n in page.not_searched] == [
        ("CoverageAssertion", "no_searchable_property")
    ]
    assert [c.type for c in page.counts] == ["Product"]


def test_a_backend_that_is_down_names_the_type_unavailable_not_empty(box: Sandbox, carol) -> None:
    """A replica that is down for a bulk search: every type it would serve is `unavailable`,
    naming the backend, and none is counted as having no hits."""
    box.replica.outage = "unreachable"
    page = carol.search("catalog", "pipeline", consistency="bulk")
    assert [(n.type, n.reason, n.backend) for n in page.not_searched] == [
        ("UseCase", "unavailable", "memory_replica"),
        ("Solution", "unavailable", "memory_replica"),
    ]
    assert page.hits == () and page.counts == ()
    assert carol.search("catalog", "pipeline").hits  # latest is the record store's


def test_one_type_failing_at_read_time_leaves_the_others_answering(carol, monkeypatch) -> None:
    real = MemoryStore.query

    def flaky(self, principal, module, statement, *, limit, text=None):
        if '"catalog"."Solution"' in statement.sql:
            raise Unavailable("memory", "unreachable")
        return real(self, principal, module, statement, limit=limit, text=text)

    monkeypatch.setattr(MemoryStore, "query", flaky)
    page = carol.search("catalog", "pipeline")
    assert [(n.type, n.reason, n.backend) for n in page.not_searched] == [
        ("Solution", "unavailable", "memory")
    ]
    assert {h.type for h in page.hits} == {"UseCase"}


def test_a_type_the_budget_cannot_afford_is_over_budget(carol) -> None:
    class OneRead:
        def __init__(self) -> None:
            self.reads = 0

        def try_reserve(self, n: int) -> bool:
            self.reads += 1
            return self.reads == 1

        def settle(self, reserved: int, actual: int) -> None:
            pass

    page = carol.search("catalog", "pipeline", budget=OneRead())
    assert [(n.type, n.reason) for n in page.not_searched] == [("Solution", "over_budget")]
    assert [c.type for c in page.counts] == ["UseCase"]
    full = EntityBudget(limit=1000)
    carol.search("catalog", "pipeline", budget=full)
    assert full.used <= 4  # settled to what the reads returned


def many_types(n: int) -> str:
    """A module of `n` types, each with a name to search."""
    doc = json.loads((EXAMPLE.parent.parent / "src/arras/conformance/module.umf.json").read_text())
    mod = doc["modules"][0]
    uc = next(e for e in mod["elements"] if e["id"] == "UseCase")
    fields = [e for e in mod["elements"] if e["id"].startswith("UseCase.")]
    elements: list[dict[str, Any]] = []
    for i in range(n):
        name = f"Kind{i:02}"
        rec = json.loads(json.dumps(uc).replace("UseCase", name))
        elements.append(rec)
        elements += [json.loads(json.dumps(f).replace("UseCase", name)) for f in fields]
    mod["elements"], mod["relationships"], mod["actions"] = elements, [], []
    return json.dumps(doc)


def test_at_most_twenty_types_are_searched_in_one_request() -> None:
    box = Sandbox().load(many_types(22))
    o = box.arras.session(box.people["carol"])
    page = o.search("catalog", "anything")
    assert len(page.counts) == 20
    assert [(n.type, n.reason) for n in page.not_searched] == [
        ("Kind20", "over_budget"),
        ("Kind21", "over_budget"),
    ]


# -- telemetry: the text is never recorded (CONTRACT-008) ------------------------------------------


def test_the_text_and_the_words_are_never_in_a_span_or_a_log(carol, caplog) -> None:
    secret = "zxqvolcano"
    caplog.set_level(logging.DEBUG)
    _exporter.clear()
    carol.search("catalog", f"{secret} pipeline")
    with pytest.raises(Invalid):
        carol.search("catalog", f"{secret} a b c d e f g")
    from test_telemetry import events

    sent = events(caplog)
    assert any(e.arras_event == "arras.search" for e in sent)
    everything = json.dumps(
        [{"event": e.arras_event, "attrs": e.arras_attrs, "message": e.message} for e in sent]
        + [dict(s.attributes or {}) | {"name": s.name} for s in _exporter.get_finished_spans()]
        + [r.getMessage() for r in caplog.records],
        default=str,
    )
    assert secret not in everything and "pipeline" not in everything.replace("catalog", "")


# -- the console's `_search` ---------------------------------------------------------------------


SEARCH = """query($t: String!, $types: [String!], $limit: Int, $cons: Consistency) {
  _search(text: $t, types: $types, limit: $limit, consistency: $cons) {
    text truncated
    hits { type key label score matched excerpt { text mark }
           entity { key type createdBy freshness { backend } ... on UseCase { name workArea } } }
    counts { type count atLeast }
    notSearched { type reason backend }
    freshness { backend asOf at consistency }
  } }"""


@pytest.fixture
def c() -> Client:
    client = Client()
    client.box = seed_demo(Sandbox().seed())
    client.h = client.box.arras
    client.app.h = client.h
    return client


def search(c: Client, text: str, user: str = "carol", **variables: Any):
    return c.call(
        "POST",
        "/graphql/catalog",
        {"query": SEARCH, "variables": {"t": text, **variables}},
        user=user,
    )


def errors(r: Any) -> list[tuple[str, str | None]]:
    return [(e["extensions"]["code"], e["extensions"].get("reason")) for e in r["errors"]]


def test_the_search_field_answers_ranked_hits_with_the_entity_from_the_same_row(
    c: Client, monkeypatch
) -> None:
    """@covers US-065-AC1, US-065-AC3: one search, hits with type, label and marked excerpt, and
    freshness."""
    calls = spy_queries(monkeypatch)
    status, r, _ = search(c, "pipeline")
    assert status == 200 and "errors" not in r, r
    s = r["data"]["_search"]
    assert [h["key"] for h in s["hits"]] == [
        "uc-pipeline",
        "uc-pipeline-review",
        "sol-1",
        "sol-pipeline-risk",
    ]
    top = s["hits"][0]
    assert top["excerpt"][0] == {"text": "uc-", "mark": False}
    assert {"text": "pipeline", "mark": True} in top["excerpt"]
    assert top["entity"]["name"] == "Pipeline mapping" and top["entity"]["createdBy"] == "alice"
    assert (
        top["entity"]["type"] == "catalog.UseCase"
        and top["entity"]["freshness"]["backend"] == "memory"
    )
    assert s["freshness"][0]["backend"] == "memory" and s["freshness"][0]["consistency"] == "LATEST"
    assert s["counts"] == [
        {"type": "UseCase", "count": 2, "atLeast": False},
        {"type": "Solution", "count": 2, "atLeast": False},
    ]
    assert len(calls) == 2  # selecting the entity's fields costs no further read
    assert r["extensions"]["revision"]["memory"] == 1


def test_types_narrow_and_consistency_chooses_the_replica(c: Client) -> None:
    _, r, _ = search(c, "pipeline", types=["Solution"], cons="BULK")
    s = r["data"]["_search"]
    assert {h["type"] for h in s["hits"]} == {"Solution"}
    assert (
        s["freshness"][0]["backend"] == "memory_replica"
        and s["freshness"][0]["consistency"] == "BULK"
    )


def test_a_search_is_refused_text_limit_and_type_with_their_codes(c: Client) -> None:
    for text in ("x", "a b c d e f g", "y" * 201):
        assert errors(search(c, text)[1]) == [("BAD_QUERY", None)]
    assert errors(search(c, "pipeline", types=["Nope"])[1]) == [("BAD_QUERY", None)]
    for limit in (0, 51):
        assert errors(search(c, "pipeline", limit=limit)[1]) == [("LIMIT_EXCEEDED", None)]
    assert search(c, "pipeline", limit=50)[1].get("errors") is None
    for r in (search(c, "needleword a b c d e f g")[1],):
        assert "needleword" not in json.dumps(r)  # the answer does not repeat the text


def test_a_search_that_searched_nothing_is_an_error_by_what_stopped_it(c: Client) -> None:
    """@covers US-065-AC6: UNSUPPORTED when no requested type is searchable, UNAVAILABLE when the
    backends are down, COST_EXCEEDED when the request had no budget left."""
    c.box.store.declare_search("catalog.UseCase", "none")
    c.box.store.declare_search("catalog.Solution", "none")
    r = search(c, "pipeline")[1]
    assert errors(r) == [("UNSUPPORTED", None)]
    c.box.store.declare_search("catalog.UseCase", None)
    c.box.store.declare_search("catalog.Solution", None)
    c.box.replica.outage = "unreachable"
    r = search(c, "pipeline", cons="BULK")[1]
    assert (
        errors(r) == [("UNAVAILABLE", "unreachable")]
        and r["errors"][0]["extensions"]["backend"] == "memory_replica"
    )
    c.box.replica.outage = None
    root_import(
        c.box,
        [
            {"type": "UseCase", "key": f"uc-fill-{i:03}", "properties": {"name": f"Fill {i}"}}
            for i in range(100)
        ],
    )
    spent = " ".join(f"a{i}: useCaseList(limit: 100) {{ items {{ key }} }}" for i in range(10))
    _, r, _ = c.call(
        "POST",
        "/graphql/catalog",
        {"query": "{ " + spent + ' _search(text: "pipeline") { text } }'},
        user="carol",
    )
    assert ("COST_EXCEEDED", None) in errors(r)


def test_a_type_that_is_not_searched_is_listed_while_the_others_answer(c: Client) -> None:
    c.box.store.declare_search("catalog.Solution", "none")
    s = search(c, "pipeline")[1]["data"]["_search"]
    assert s["notSearched"] == [
        {"type": "Solution", "reason": "no_capability", "backend": "memory"}
    ]
    assert {h["type"] for h in s["hits"]} == {"UseCase"}


def test_the_search_is_the_viewers_own_and_an_unreadable_module_is_not_found(c: Client) -> None:
    status, r, _ = search(c, "pipeline", user="dave")
    assert status == 404
    assert search(c, "pipeline", user="carol")[0] == 200


def test_the_search_names_cannot_collide_with_a_modules_own(c: Client) -> None:
    q = '{ __type(name: "Query") { fields { name } } s: __type(name: "_SearchPage") { fields { name } } }'
    _, r, _ = c.call("POST", "/graphql/catalog", {"query": q}, user="carol")
    names = [f["name"] for f in r["data"]["__type"]["fields"]]
    assert "_search" in names and "useCase" in names
    assert {f["name"] for f in r["data"]["s"]["fields"]} == {
        "text",
        "hits",
        "counts",
        "notSearched",
        "truncated",
        "freshness",
    }


def test_a_revision_change_during_a_search_is_revision_changed(c: Client, monkeypatch) -> None:
    from dataclasses import replace

    from arras.sandbox import catalog_document
    from arras.umf import parse_module

    real = MemoryStore.query
    done: list[int] = []

    def change(self, principal, module, statement, *, limit, text=None):
        if not done:
            done.append(1)
            doc = json.loads(catalog_document())
            doc["modules"][0]["extensions"]["umf.ddd"]["terms"] = [
                {"id": "t", "name": "t", "definition": "d"}
            ]
            mod = replace(
                parse_module(json.dumps(doc)), placement=self.modules["catalog"].placement
            )
            self.register(
                c.box.people["root"], json.dumps(doc).encode(), mod, unknown_endpoint="reject"
            )
        return real(self, principal, module, statement, limit=limit, text=text)

    monkeypatch.setattr(MemoryStore, "query", change)
    assert errors(search(c, "pipeline")[1]) == [("REVISION_CHANGED", None)]


# -- the capability and the resolved query ------------------------------------------------------


def test_capabilities_state_search_and_the_searchable_properties_per_backend(c: Client) -> None:
    """@covers US-065-AC6: `EntityTypeInfo.capabilities` gains `search` and `searchable`."""
    q = "{ modules { entityTypes { name capabilities } } }"
    c.box.store.declare_search("catalog.Solution", "none")
    _, r, _ = c.call("POST", "/graphql", {"query": q}, user="carol")
    caps = {t["name"]: t["capabilities"] for t in r["data"]["modules"][0]["entityTypes"]}
    assert caps["catalog.UseCase"]["memory"]["search"] == "substring"
    assert caps["catalog.UseCase"]["memory"]["searchable"] == ["code", "name", "workArea"]
    assert caps["catalog.UseCase"]["memory_replica"]["search"] == "substring"
    assert caps["catalog.Solution"]["memory"]["search"] == "none"
    assert caps["catalog.Solution"]["memory"]["searchable"] == []


def test_the_backend_refuses_text_it_cannot_match(box: Sandbox, carol) -> None:
    """The text match travels beside the statement; the backend holds it to its own `search` and
    `searchable` declaration."""
    from arras import Statement, Unsupported
    from arras.searchplan import TextMatch

    sql = Statement("SELECT u.* FROM catalog.UseCase u ORDER BY u.code LIMIT 50")
    ask = lambda text: box.store.query(carol.principal, "catalog", sql, limit=50, text=text)  # noqa: E731
    assert [r["code"] for r in ask(TextMatch(("pipeline",), ("name",))).rows]
    assert len(ask(None).rows) >= 2  # no text: no capability needed
    with pytest.raises(Unsupported):  # a property it does not list as searchable
        ask(TextMatch(("a",), ("nope",)))
    box.store.declare_search("catalog.UseCase", "substring", searchable=("code",))
    with pytest.raises(Unsupported):
        ask(TextMatch(("a",), ("name",)))
    box.store.declare_search("catalog.UseCase", "none")
    with pytest.raises(Unsupported):
        ask(TextMatch(("a",), ("code",)))


def test_the_interface_refuses_a_text_read_of_a_type_whose_backend_declares_none(
    box: Sandbox, carol
) -> None:
    from arras import Unsupported
    from arras.searchplan import TextMatch

    box.store.declare_search("catalog.Solution", "none")
    sql = "SELECT s.* FROM catalog.Solution s ORDER BY s.code LIMIT 50"
    with pytest.raises(Unsupported):
        carol.query("catalog", sql, text=TextMatch(("pipeline",), ("name",)))
    assert carol.query("catalog", sql).rows  # an ordinary read is unaffected
    ok = carol.query(
        "catalog",
        "SELECT u.* FROM catalog.UseCase u ORDER BY u.code LIMIT 50",
        text=TextMatch(("pipeline",), ("name",)),
    )
    assert [r["code"] for r in ok.rows] == ["uc-pipeline", "uc-pipeline-review"]
    assert [c.name for c in ok.columns][:3] == ["code", "name", "workArea"]


def test_text_is_never_carried_in_sql(carol) -> None:
    """There is no SQL for a text match: the memory adapter's Weft subset serves no `LIKE`."""
    from arras import Unsupported

    for sql in (
        "SELECT u.* FROM catalog.UseCase u WHERE u.name LIKE '%pipeline%'",
        "SELECT u.* FROM catalog.UseCase u WHERE u.name CONTAINS 'pipeline'",
    ):
        with pytest.raises((Unsupported, Invalid)):
            carol.query("catalog", sql + " ORDER BY u.code LIMIT 50")
