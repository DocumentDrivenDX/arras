# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Exporting a graph as records, and loading it back (CONTRACT-003, Export; ADR-028)."""

import base64
import json
from pathlib import Path

import pytest

from arras import graphfile
from arras.devhost import build
from arras.errors import Invalid, Refused
from arras.fakes import FakeAccess, MemoryStore
from arras.graphfile import GraphFile
from arras.sandbox import Sandbox
from arras.types import Principal
from arras.umf import parse_module

import shop_module  # isort: skip

EXAMPLE = Path(__file__).parent.parent / "examples" / "catalog"
DOC = (EXAMPLE / "catalog.umf.json").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def box() -> Sandbox:
    return build(EXAMPLE / "catalog.umf.json", EXAMPLE / "seed.json")


def _export(box: Sandbox, who: str = "alice") -> GraphFile:
    return graphfile.export(box.arras.session(box.people[who]), "catalog")


def test_an_export_holds_every_entity_then_every_link_in_a_stable_order(box: Sandbox) -> None:
    g = _export(box)
    kinds = ["type" in r for r in g.records]
    assert kinds == sorted(kinds, reverse=True)  # entities first, then relationships
    entities = [r for r in g.records if "type" in r]
    assert len(entities) > 50 and all({"type", "key", "properties"} <= r.keys() for r in entities)
    assert all(r["key"] not in r["properties"] for r in entities)  # the key is not repeated
    order = [r["type"] for r in entities]
    assert order == sorted(
        order,
        key=[
            "UseCase",
            "Solution",
            "Product",
            "CoverageAssertion",
            "ProductVersion",
            "Finding",
        ].index,
    )
    assert graphfile.dumps(_export(box)) == graphfile.dumps(g)  # the same bytes each time


def test_an_export_leaves_out_what_is_not_set(box: Sandbox) -> None:
    g = _export(box)
    assert all("original_author" not in r and "original_at" not in r for r in g.records)
    assert all(v is not None for r in g.records if "type" in r for v in r["properties"].values())


def test_the_file_is_canonical_text_that_reads_back() -> None:
    g = GraphFile("m", ({"type": "T", "key": "k", "properties": {"b": 1, "a": "é"}},))
    text = graphfile.dumps(g)
    assert text.endswith("}\n") and text.index('"a"') < text.index('"b"')
    assert "é" in text  # not escaped
    assert graphfile.loads(text) == g


@pytest.mark.parametrize(
    "text, why",
    [
        ("nope", "not JSON"),
        ("[]", "a JSON object"),
        ('{"format": "x"}', "not a graph file"),
        ('{"format": "arras.graph", "version": 2}', "version 1"),
        ('{"format": "arras.graph", "version": 1}', '"module"'),
        ('{"format": "arras.graph", "version": 1, "module": "m", "records": [1]}', '"records"'),
    ],
)
def test_a_file_of_the_wrong_shape_says_what_is_wrong(text: str, why: str) -> None:
    with pytest.raises(ValueError, match=why):
        graphfile.loads(text)


def test_loading_an_export_into_a_fresh_graph_reproduces_it(box: Sandbox) -> None:
    """The loop: what was exported is what loads, so a file kept in git is the graph."""
    first = _export(box)
    fresh = Sandbox().load(DOC, (), first)
    again = _export(fresh)
    assert graphfile.dumps(again) == graphfile.dumps(first)
    # and loading it again changes nothing: an import is idempotent
    again_too = Sandbox().load(DOC, (), first)
    root = again_too.arras.session(again_too.people["root"])
    result = root.import_records("catalog", first.records, load_id="twice")
    assert result.created == 0 and result.skipped == len(first.records) and not result.rejected


def test_edits_made_through_actions_are_in_the_next_export(box: Sandbox) -> None:
    edited = build(EXAMPLE / "catalog.umf.json", EXAMPLE / "seed.json")
    o = edited.arras.session(edited.people["alice"])
    o.invoke(
        "catalog.UpdateFinding",
        {
            "finding": "fnd-seed-logs-1",
            "statement": "Rewritten",
            "kind": "capability",
            "status": "resolved",
        },
    )
    o.invoke(
        "catalog.UnaddressUseCase",
        {"solution": "lumen-triage-prompt", "useCase": "triage-incident-alerts"},
    )
    after = _export(edited)
    before = _export(box)
    assert after.records != before.records
    reloaded = Sandbox().load(DOC, (), after)
    assert graphfile.dumps(_export(reloaded)) == graphfile.dumps(after)
    revised = next(r for r in after.records if r.get("key") == "fnd-seed-logs-1")
    assert revised["properties"]["statement"] == "Rewritten"
    link = {
        "relationship": "addresses",
        "source": "lumen-triage-prompt",
        "target": "triage-incident-alerts",
    }
    assert link in before.records and link not in after.records


def test_paging_walks_the_same_records_as_one_read(box: Sandbox) -> None:
    o = box.arras.session(box.people["alice"])
    whole = o.export_records("catalog", limit=500).items
    seen, after = [], None
    while True:
        page = o.export_records("catalog", limit=7, after=after)
        seen += page.items
        after = page.next_cursor
        if after is None:
            break
    assert tuple(seen) == tuple(whole) == graphfile.export(o, "catalog").records


def test_paging_is_stable_when_a_record_is_written_between_pages() -> None:
    """A cursor is a place in the canonical order, not an offset: a record added before the
    cursor is not repeated, one added after it is not skipped, and one removed is not missed."""
    mine = build(EXAMPLE / "catalog.umf.json", EXAMPLE / "seed.json")
    o = mine.arras.session(mine.people["alice"])
    first = o.export_records("catalog", limit=3)
    assert first.next_cursor is not None
    o.invoke("catalog.AddUseCase", {"code": "aaa-new", "name": "Sorts first"})  # before the cursor
    o.invoke("catalog.AddUseCase", {"code": "zzz-new", "name": "Sorts last"})  # after it
    seen = list(first.items)
    after = first.next_cursor
    while after is not None:
        page = o.export_records("catalog", limit=3, after=after)
        seen += page.items
        after = page.next_cursor
    keys = [(r["type"], r["key"]) for r in seen if "type" in r]
    assert len(keys) == len(set(keys))  # nothing repeated
    assert ("UseCase", "zzz-new") in keys  # nothing after the cursor skipped
    assert ("UseCase", "aaa-new") not in keys  # what sorts before the cursor was already passed


def test_an_export_is_read_as_the_viewer(box: Sandbox) -> None:
    with pytest.raises(Invalid):  # dave holds nothing on catalog: it is as if there were none
        box.arras.session(box.people["dave"]).export_records("catalog")
    with pytest.raises(Refused):  # the administrative principal reads nothing
        box.arras.session(box.people["root"]).export_records("catalog")
    assert _export(box, "carol").records == _export(box, "alice").records  # a reader may export


def test_a_bad_page_or_cursor_is_refused(box: Sandbox) -> None:
    o = box.arras.session(box.people["alice"])
    with pytest.raises(Invalid):
        o.export_records("catalog", limit=0)
    with pytest.raises(Invalid):
        o.export_records("catalog", limit=501)
    with pytest.raises(Invalid):
        o.export_records("catalog", after="x")
    with pytest.raises(Invalid):
        o.export_records("catalog", after="-1")
    for forged in ([0, "catalog.Nope", "k"], [2, "x"], [[0], "a", "b"], [0, "catalog.UseCase"]):
        cursor = base64.urlsafe_b64encode(json.dumps(forged).encode()).decode().rstrip("=")
        with pytest.raises(Invalid):
            o.export_records("catalog", after=cursor)


def test_a_module_that_is_not_there_is_not_exported(box: Sandbox) -> None:
    with pytest.raises(Invalid):
        box.arras.session(box.people["alice"]).export_records("nowhere")


def test_the_dev_host_loads_a_graph_file(tmp_path: Path, box: Sandbox) -> None:
    out = tmp_path / "catalog.graph.json"
    out.write_text(graphfile.dumps(_export(box)), encoding="utf-8")
    served = build(EXAMPLE / "catalog.umf.json", None, records=out)
    assert graphfile.dumps(_export(served)) == out.read_text(encoding="utf-8")
    wrong = tmp_path / "other.graph.json"
    wrong.write_text(graphfile.dumps(GraphFile("other", ())), encoding="utf-8")
    with pytest.raises(ValueError, match="not 'catalog'"):
        build(EXAMPLE / "catalog.umf.json", None, records=wrong)


def _loaded(tmp_path: Path, body: dict, caplog) -> Sandbox:
    out = tmp_path / "catalog.graph.json"
    out.write_text(json.dumps({"format": "arras.graph", "version": 1, **body}), encoding="utf-8")
    with caplog.at_level("WARNING", logger="arras.sandbox"):
        return build(EXAMPLE / "catalog.umf.json", None, records=out)


def test_a_file_that_is_not_the_whole_graph_loads_and_says_so(tmp_path: Path, caplog) -> None:
    partial = {
        "module": "catalog",
        "complete": False,
        "omitted": ["catalog.Solution"],
        "records": [],
    }
    served = _loaded(tmp_path, partial, caplog)
    [warning] = served.warnings
    assert "not the whole graph" in warning and "catalog.Solution" in warning
    assert [r.getMessage() for r in caplog.records] == [warning]


def test_a_file_that_does_not_say_it_is_complete_is_not_taken_to_be(tmp_path, caplog) -> None:
    served = _loaded(tmp_path, {"module": "catalog", "records": []}, caplog)
    [warning] = served.warnings
    assert "not marked complete" in warning and caplog.records


def test_a_complete_file_loads_without_a_warning(tmp_path: Path, caplog) -> None:
    served = _loaded(tmp_path, {"module": "catalog", "complete": True, "records": []}, caplog)
    assert served.warnings == [] and not caplog.records


def test_a_file_the_graph_cannot_take_is_refused_with_the_first_reason() -> None:
    bad = GraphFile("catalog", ({"type": "Nope", "key": "k", "properties": {}},))
    with pytest.raises(ValueError, match="rejected"):
        Sandbox().load(DOC, (), bad)


_VECTOR_FILE = json.loads(
    (Path(__file__).parent / "vectors" / "graphfile.json").read_text(encoding="utf-8")
)
VECTORS = _VECTOR_FILE["vectors"]
REJECTED = _VECTOR_FILE["rejected"]


@pytest.mark.parametrize("v", VECTORS, ids=[v["name"] for v in VECTORS])
def test_the_file_is_the_bytes_the_interface_writes_too(v: dict) -> None:
    """The same vectors are checked by the UI (ui/src/test/graph-file.test.ts): a file saved by the
    Export control and one written by the library are the same text."""
    g = v["graph"]
    graph = GraphFile(g["module"], tuple(g["records"]), g["complete"], tuple(g["omitted"]))
    assert graphfile.dumps(graph) == v["text"]
    assert graphfile.loads(v["text"]) == graph


@pytest.mark.parametrize("v", REJECTED, ids=[v["name"] for v in REJECTED])
def test_a_number_that_is_not_an_integer_is_refused_naming_where(v: dict) -> None:
    """A decimal travels as a string; the same cases are refused by the UI's reader
    (ui/src/test/graph-file.test.ts)."""
    with pytest.raises(ValueError) as e:
        graphfile.loads(v["text"])
    assert str(e.value) == (
        f"{v['path']}: {v['token']} is not an integer (a decimal is written as a string)"
    )


UNWRITABLE = _VECTOR_FILE["unwritable"]


def _with_numbers(value: object) -> object:
    """The vector's `{"$number": token}` as the float it stands for."""
    if isinstance(value, dict) and set(value) == {"$number"}:
        return float(value["$number"])
    if isinstance(value, dict):
        return {k: _with_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_with_numbers(v) for v in value]
    return value


@pytest.mark.parametrize("v", UNWRITABLE, ids=[v["name"] for v in UNWRITABLE])
def test_a_float_is_not_written_so_no_file_is_made_that_loads_refuses(v: dict) -> None:
    """The same cases are refused by the UI's `graphText` (ui/src/test/graph-file.test.ts), with the
    message the readers give for the same number."""
    g = _with_numbers(v["graph"])
    assert isinstance(g, dict)
    graph = GraphFile(g["module"], tuple(g["records"]), g["complete"], tuple(g["omitted"]))
    with pytest.raises(ValueError) as e:
        graphfile.dumps(graph)
    assert str(e.value) == (
        f"{v['path']}: {v['token']} is not an integer (a decimal is written as a string)"
    )


def test_a_float_that_is_whole_is_not_written_either() -> None:
    graph = GraphFile("m", ({"type": "T", "key": "a", "properties": {"n": 1.0}},))
    with pytest.raises(ValueError, match=r"records\[0\]\.properties\.n: 1\.0 is not an integer"):
        graphfile.dumps(graph)


def test_integers_of_any_size_are_read_exactly() -> None:
    text = (
        '{"complete": true, "format": "arras.graph", "module": "m", '
        '"records": [{"properties": {"n": 123456789012345678901234567890, "z": -0}}], "version": 1}'
    )
    assert graphfile.loads(text).records[0]["properties"]["n"] == 123456789012345678901234567890


def _store(module: str = "shop", *, seen: bool = False) -> tuple[MemoryStore, Principal]:
    access = FakeAccess()
    store = MemoryStore(access)
    root = access.grant("root", module, "read", "write", "schema", admin=True)
    doc = shop_module.document(seen=seen)
    store.register(root, doc.encode(), parse_module(doc), unknown_endpoint="reject")
    return store, root


def test_an_export_never_carries_another_modules_relationships() -> None:
    """Two modules declare `places`; the viewer reads `shop` only, and the store is shared."""
    store, root = _store()
    access = store.access
    access.grant("root", "depot", "read", "write", "schema")
    carol = access.grant("carol", "shop", "read")
    other = shop_module.document().replace('"shop"', '"depot"')
    store.register(root, other.encode(), parse_module(other), unknown_endpoint="reject")
    for mod, c, o in (("shop", "c1", "o1"), ("depot", "d1", "p1")):
        recs = [
            {"type": "Customer", "key": c, "properties": {"name": "N", "region": "r"}},
            {
                "type": "Purchase",
                "key": o,
                "properties": {"customer": c, "total": "1.50", "qty": 1},
            },
            {"relationship": "places", "source": c, "target": o},
        ]
        res = store.import_records(root, mod, recs, load_id=mod, initiated_by="root")
        assert not res.rejected, res.rejected
    items = store.export_records(carol, "shop", limit=500, after=None).items
    assert "d1" not in json.dumps(items) and "p1" not in json.dumps(items)
    assert [r for r in items if "relationship" in r] == [
        {"relationship": "places", "source": "c1", "target": "o1"}
    ]
    g = GraphFile("shop", tuple(items))
    loaded = Sandbox().load(shop_module.document(), (), g)
    again = loaded.arras.session(loaded.people["alice"]).export_records("shop", limit=500)
    assert tuple(again.items) == g.records


def test_decimals_and_originals_are_the_same_bytes_after_a_load() -> None:
    store, carol = shop_module.shop_store()
    root = store.access.grant("root", "shop", "read", "write", "schema", admin=True)
    extra = {
        "type": "Customer",
        "key": "c9",
        "properties": {"name": "Zed", "region": "north"},
        "original_author": "ann",
        "original_at": "2020-01-01T00:00:00+00:00",
    }
    store.import_records(root, "shop", [extra], load_id="orig", initiated_by="root")
    first = store.export_records(carol, "shop", limit=500, after=None).items
    assert any(r.get("original_at") for r in first)
    assert any(r["properties"].get("total") == "10.50" for r in first if "type" in r)
    fresh, froot = _store()
    res = fresh.import_records(froot, "shop", first, load_id="again", initiated_by="root")
    assert not res.rejected, res.rejected
    frita = fresh.access.grant("carol", "shop", "read")
    second = fresh.export_records(frita, "shop", limit=500, after=None).items
    assert graphfile.dumps(GraphFile("shop", tuple(second))) == graphfile.dumps(
        GraphFile("shop", tuple(first))
    )
    ent = next(e for k, e in fresh.state.entities.items() if k.key == "c9")
    assert ent.original_at is not None and ent.original_at.year == 2020
    assert isinstance(next(iter(fresh.state.entities.values())).props, dict)


@pytest.mark.parametrize(
    "props, at, why",
    [
        ({"total": "abc"}, None, "not a decimal"),
        ({"total": "NaN"}, None, "finite"),
        ({"total": "1.234"}, None, "more than 2 places"),
        ({}, "yesterday", "original_at"),
    ],
)
def test_a_value_that_cannot_be_read_as_its_type_is_rejected(props, at, why) -> None:
    store, root = _store()
    rec = {
        "type": "Purchase",
        "key": "o1",
        "properties": {"customer": "c1", "total": "1.00", "qty": 1, **props},
    }
    if at is not None:
        rec["original_at"] = at
    res = store.import_records(root, "shop", [rec], load_id="bad", initiated_by="root")
    assert res.created == 0 and len(res.rejected) == 1
    assert why in res.rejected[0].reason
    assert not store.state.entities


def _import_customer(props, extra=None):
    store, root = _store(seen=True)
    rec = {
        "type": "Customer",
        "key": "c1",
        "properties": {"name": "Ann", "region": "east", **props},
    }
    rec.update(extra or {})
    return store, store.import_records(root, "shop", [rec], load_id="t", initiated_by="root")


@pytest.mark.parametrize(
    "props, why",
    [
        ({"name": {"a": 1}}, "name: not a string"),
        ({"name": ["x"]}, "name: not a string"),
        ({"name": 7}, "name: not a string"),
        ({"region": True}, "region: not a string"),
        ({"seen": "2026-01-02T03:04:05"}, "seen: not an ISO timestamp with an offset"),
        ({"seen": "yesterday"}, "seen: not an ISO timestamp"),
        ({"seen": 12}, "seen: not an ISO timestamp"),
        ({"seen": {"at": "2026-01-02T03:04:05Z"}}, "seen: not an ISO timestamp"),
    ],
)
def test_a_value_of_the_wrong_type_is_rejected_with_its_property(props, why) -> None:
    store, res = _import_customer(props)
    assert res.created == 0 and len(res.rejected) == 1
    assert why in res.rejected[0].reason
    assert not store.state.entities


@pytest.mark.parametrize("at", ["2026-01-02T03:04:05", "2026-01-02"])
def test_original_at_must_name_an_offset(at) -> None:
    store, res = _import_customer({}, {"original_at": at})
    assert res.created == 0
    assert "original_at: not an ISO timestamp with an offset" in res.rejected[0].reason
    assert not store.state.entities


def test_a_timestamp_property_with_an_offset_is_kept_as_a_moment() -> None:
    store, res = _import_customer(
        {"seen": "2026-01-02T03:04:05+02:00"}, {"original_at": "2020-05-06T07:08:09Z"}
    )
    assert res.created == 1 and not res.rejected
    seen = next(iter(store.state.entities.values())).props["seen"]
    assert seen.utcoffset().total_seconds() == 7200 and seen.year == 2026
