# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""CONTRACT-010, section B: the resolved view on the meta schema, read from the registered
document and cached by module and revision; and the property that a view changes no type."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from arras.fakes import MemoryStore
from arras.model import EntityTypeInfo, ModuleInfo
from arras.sandbox import Sandbox
from arras.umf import parse_module
from test_console import Client
from test_view import SOLUTION_VIEW, VIEW, declare, full_document, plain

QUERY = """{ modules { name view { title description } entityTypes { name view {
  declared label icon tone title summary search
  sections { label properties collapsed }
  fields { property label format hideWhenEmpty tones }
  relationships { field label hideWhenEmpty order } } } } }"""


def served(client: Client, user: str = "carol") -> dict[str, Any]:
    status, r, _ = client.gql(QUERY, "/graphql", user=user)
    assert status == 200 and "errors" not in r, r
    return r["data"]["modules"][0]


def with_view(document: dict[str, Any]) -> Client:
    c = Client()
    c.box = Sandbox().load(json.dumps(document))
    c.h = c.box.arras
    c.app.h = c.h
    return c


def test_the_meta_schema_serves_the_defaults_for_a_module_with_no_view() -> None:
    """@covers US-067-AC1: the resolved view is derived on the server; no client derives one."""
    m = served(Client())
    assert m["view"] == {"title": "catalog", "description": None}
    types = {t["name"]: t["view"] for t in m["entityTypes"]}
    uc = types["catalog.UseCase"]
    assert (uc["declared"], uc["label"], uc["icon"], uc["tone"]) == (
        False,
        "Use case",
        "circle",
        "slate",
    )
    assert (uc["title"], uc["summary"], uc["search"]) == ("{name}", None, ["name", "code"])
    assert uc["sections"] == [{"label": "Details", "properties": ["workArea"], "collapsed": False}]
    assert [f["property"] for f in uc["fields"]] == ["code", "name", "workArea"]
    assert uc["relationships"] == [
        {"field": "addressedBy", "label": "Addressed by", "hideWhenEmpty": False, "order": 50}
    ]
    assert types["catalog.Solution"]["tone"] == "blue"


def test_the_meta_schema_serves_a_declared_view_from_the_registered_document() -> None:
    """@covers US-070-AC1, US-070-AC2: the type's description carries the declared view."""
    c = with_view(full_document())
    m = served(c)
    assert m["view"]["title"] == "Product catalog"
    solution = next(t["view"] for t in m["entityTypes"] if t["name"] == "catalog.Solution")
    assert (solution["declared"], solution["label"], solution["icon"]) == (
        True,
        "Offering",
        "puzzle",
    )
    assert solution["title"] == "{name}[ ({code})]"
    delivery = next(f for f in solution["fields"] if f["property"] == "deliveryMode")
    assert delivery["format"] == "badge" and delivery["tones"] == {"app": "teal", "chat": "blue"}
    assert [s["label"] for s in solution["sections"]] == ["Delivery", "How it works"]


def test_a_view_is_read_once_per_module_and_revision(monkeypatch) -> None:
    """The resolution is cached by module and revision (CONTRACT-010, Where the view lives); a
    change of the document is a new revision and so a new view."""
    c = with_view(full_document())
    reads: list[str] = []
    real = MemoryStore.document

    def counting(self, principal, module):
        reads.append(module)
        return real(self, principal, module)

    monkeypatch.setattr(MemoryStore, "document", counting)
    first = served(c)
    assert served(c, user="bob") == first and len(reads) == 1  # another person, the same revision
    changed = declare(full_document(), Solution={**SOLUTION_VIEW, "label": "Thing"})
    root = c.h.session(c.box.people["root"])
    root.registry().register(json.dumps(changed))
    later = served(c)
    assert len(reads) == 2
    assert (
        next(t for t in later["entityTypes"] if t["name"] == "catalog.Solution")["view"]["label"]
        == "Thing"
    )


def test_a_viewer_who_may_not_read_the_module_sees_no_view() -> None:
    """The view grants nothing: the module is not described to a viewer without access."""
    c = with_view(full_document())
    status, r, _ = c.gql(QUERY, "/graphql", user="dave")
    assert status == 200 and r["data"]["modules"] == []


def test_the_registry_types_carry_no_view_data() -> None:
    """A view is read at request time: it is in no catalog, in `ModuleInfo` or `EntityTypeInfo`."""
    names = {f.name for f in dataclasses.fields(ModuleInfo)} | {
        f.name for f in dataclasses.fields(EntityTypeInfo)
    }
    assert not any("view" in n for n in names)
    c = with_view(full_document())
    stored = c.box.store.modules["catalog"]
    assert stored == dataclasses.replace(
        parse_module(json.dumps(plain())), revision=stored.revision, placement=stored.placement
    )


# -- the registry is the same with and without a view, for any valid declaration ----------------

_PROPS = ["code", "name", "summary", "workflow", "prompt", "audience", "launchUrl", "deliveryMode"]
_text = st.text(alphabet=st.characters(blacklist_categories=("Cs", "Cc")), min_size=1, max_size=40)
_icons = st.sampled_from(["box", "puzzle", "star", "circle", "scale"])
_tones = st.sampled_from(["slate", "blue", "teal", "green", "amber", "red", "violet", "rose"])
_template = st.sampled_from(["{name}", "{name}[ ({code})]", "{code} - {name}", "plain", "\\{x\\}"])


@st.composite
def solution_views(draw: Any) -> dict[str, Any]:
    terms: dict[str, Any] = {}
    if draw(st.booleans()):
        terms["label"] = draw(_text)
    if draw(st.booleans()):
        terms["icon"] = draw(_icons)
    if draw(st.booleans()):
        terms["tone"] = draw(_tones)
    if draw(st.booleans()):
        terms["title"] = draw(_template)
    if draw(st.booleans()):
        terms["summary"] = draw(_template)
    if draw(st.booleans()):
        props = draw(st.lists(st.sampled_from(_PROPS), unique=True, max_size=8))
        terms["search"] = props
    if draw(st.booleans()):
        props = draw(st.lists(st.sampled_from(_PROPS), unique=True, min_size=1, max_size=8))
        cut = draw(st.integers(1, len(props)))
        groups = [props[:cut], props[cut:]]
        terms["sections"] = [
            {"label": f"S{i}", "properties": g, "collapsed": draw(st.booleans())}
            for i, g in enumerate(groups)
            if g
        ]
    return terms


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(solution_views(), st.booleans(), _text)
def test_a_view_changes_no_type_relationship_or_action(
    terms: dict[str, Any], hide: bool, label: str
) -> None:
    """@covers US-070-AC7: for any valid declaration the registry's types, relationships and
    actions are equal to those of the document without one."""
    base = parse_module(json.dumps(plain()))
    doc = declare(
        Solution=terms,
        Solution__launchUrl={"hideWhenEmpty": hide, "label": label, "format": "link"},
        module={"title": label[:80], "description": label[:200]},
    )
    with_declared = parse_module(json.dumps(doc))
    assert with_declared == base
    assert with_declared.entity_types == base.entity_types
    assert (
        with_declared.relationships == base.relationships and with_declared.actions == base.actions
    )
    assert VIEW in doc["vocabularies"]


def test_the_catalog_example_declares_a_view_for_each_of_its_six_types() -> None:
    """@covers US-070-AC1, US-070-AC7: the example's views register, resolve, and change no type."""
    from test_view import CATALOG, view_of

    doc = json.loads(CATALOG.read_text())
    assert doc["vocabularies"][VIEW] == {"version": "0.1.0"}
    resolved = view_of(doc)
    assert [v.declared for v in resolved.types.values()] == [True] * 6
    assert resolved.module.title == "Product catalog"
    assert parse_module(json.dumps(doc)) == parse_module(json.dumps(plain()))
    solution = resolved.view("Solution")
    assert (solution.icon, solution.tone, solution.title) == ("puzzle", "blue", "{name}[ ({code})]")
    assert len({v.icon for v in resolved.types.values()}) == 6  # a glyph each
