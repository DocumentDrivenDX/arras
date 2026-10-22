# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""QUERY-010, sections A and B: the `arras.view` vocabulary, its checks at registration, the
defaults and the resolved view. The document under test is the catalog example, with whatever view
it declares removed first, so each test states exactly what it declares."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from arras import Invalid
from arras.sandbox import Sandbox
from arras.umf import parse_module
from arras.view import (
    ICONS,
    TONES,
    DeclaredView,
    ResolvedModule,
    TemplateError,
    declared_from_text,
    default_format,
    evaluate,
    parse_template,
    placeholders,
    pluralize,
    resolve,
    split_words,
    title_of,
)

CATALOG = Path(__file__).parent.parent / "examples" / "catalog" / "catalog.umf.json"
VIEW = "arras.view"


def plain() -> dict[str, Any]:
    """The catalog document with no view at all."""
    doc = json.loads(CATALOG.read_text())
    doc["vocabularies"].pop(VIEW, None)
    mod = doc["modules"][0]
    mod["extensions"].pop(VIEW, None)
    for carrier in (*mod["elements"], *mod["relationships"]):
        carrier.get("extensions", {}).pop(VIEW, None)
    return doc


def declare(doc: dict[str, Any] | None = None, **where: Any) -> dict[str, Any]:
    """`where` maps a place to its terms: `module`, a record or field id (`Solution`,
    `Solution.deliveryMode`), or `rel:<name>`."""
    doc = copy.deepcopy(doc or plain())
    doc["vocabularies"][VIEW] = {"version": "0.1.0"}
    mod = doc["modules"][0]
    for place, terms in where.items():
        if place == "module":
            mod["extensions"][VIEW] = terms
        elif place.startswith("rel_"):
            rel = next(r for r in mod["relationships"] if r["name"] == place[4:])
            rel.setdefault("extensions", {})[VIEW] = terms
        else:
            el = next(e for e in mod["elements"] if e["id"] == place.replace("__", "."))
            el.setdefault("extensions", {})[VIEW] = terms
    return doc


def refused(doc: dict[str, Any]) -> list[tuple[str, str]]:
    with pytest.raises(Invalid) as e:
        parse_module(json.dumps(doc))
    return [(v.path, v.code) for v in e.value.violations]


def codes(doc: dict[str, Any]) -> set[str]:
    return {c for _, c in refused(doc)}


def view_of(doc: dict[str, Any]) -> ResolvedModule:
    mod = parse_module(json.dumps(doc))
    return resolve(mod, declared_from_text(json.dumps(doc), mod))


# -- templates ---------------------------------------------------------------------------------


def test_template_grammar_placeholders_optional_groups_and_escapes() -> None:
    row = {"name": "Lumen", "code": "h-1", "empty": "", "none": None, "n": 3}
    assert evaluate("{name}", row) == "Lumen"
    assert evaluate("{name}[ ({code})]", row) == "Lumen (h-1)"
    assert evaluate("{name}[ ({empty})]", row) == "Lumen"
    assert evaluate("{name}[ ({none})]", row) == "Lumen"
    assert evaluate("{name}[ ({missing})]", row) == "Lumen"
    assert evaluate("{missing}", row) == ""
    assert evaluate("{n} items", row) == "3 items"
    assert evaluate(r"\{name\} \[x\] \\", row) == "{name} [x] \\"
    assert evaluate("[a {code}][ b {empty}]", row) == "a h-1"
    assert (
        evaluate("[a {code}[ b {empty}]]", row) == ""
    )  # a group needs every placeholder inside it
    assert placeholders("{name}[ ({code})] {name}") == ["name", "code"]


@pytest.mark.parametrize(
    "text", ["{name", "name}", "{}", "{a b}", "[x", "x]", "{1a}", "{na-me}", "[{x]}"]
)
def test_a_malformed_template_is_refused(text: str) -> None:
    with pytest.raises(TemplateError):
        parse_template(text)


def test_a_template_is_text_never_markup() -> None:
    row = {"name": "<script>alert(1)</script>"}
    assert evaluate("{name}", row) == "<script>alert(1)</script>"
    assert title_of(resolve(parse_module(json.dumps(plain()))).view("Product"), {}, "k-1") == "k-1"


def test_an_empty_title_is_replaced_by_the_key() -> None:
    v = view_of(plain()).view("catalog.Product")
    assert title_of(v, {"name": "Lumen"}, "lumen") == "Lumen"
    assert title_of(v, {"name": ""}, "lumen") == "lumen"


# -- defaults (US-067-AC1, US-067-AC2) ---------------------------------------------------------


def test_default_labels_split_the_name_into_words() -> None:
    assert split_words("UseCase") == "Use case"
    assert split_words("workArea") == "Work area"
    assert split_words("HTTPServer") == "HTTP server"
    assert split_words("providedBy") == "Provided by"
    assert split_words("Product") == "Product"


@pytest.mark.parametrize(
    ("label", "plural"),
    [
        ("Use case", "Use cases"),
        ("Finding", "Findings"),
        ("Coverage", "Coverages"),
        ("Product version", "Product versions"),
        ("Category", "Categories"),
        ("Address", "Addresses"),
        ("Survey", "Surveys"),
        ("Box", "Boxes"),
        ("Match", "Matches"),
        ("Dish", "Dishes"),
        ("Party to the Deal", "Party to the Deals"),
        ("Y", "Ys"),
    ],
)
def test_the_default_plural_follows_english_rules(label: str, plural: str) -> None:
    assert pluralize(label) == plural


def test_the_plural_label_defaults_from_the_label_and_may_be_declared() -> None:
    """The resolved view carries a plural for where a type names a collection."""
    plain_view = view_of(plain())
    assert plain_view.view("UseCase").plural_label == "Use cases"
    assert plain_view.view("CoverageAssertion").plural_label == "Coverage assertions"
    declared = view_of(declare(Solution={"label": "Offering"}, UseCase={"pluralLabel": "Cases"}))
    assert declared.view("Solution").plural_label == "Offerings"
    assert declared.view("UseCase").label == "Use case"
    assert declared.view("UseCase").plural_label == "Cases"


@pytest.mark.parametrize("bad", ["", "x" * 61, 3])
def test_a_plural_label_is_plain_text_of_one_to_sixty(bad: object) -> None:
    faults = refused(declare(Solution={"pluralLabel": bad}))
    assert len(faults) == 1 and faults[0][0].endswith(".extensions.arras.view.pluralLabel")


def test_a_plural_label_belongs_to_a_record() -> None:
    assert codes(declare(Solution__name={"pluralLabel": "Names"})) == {"view_unknown_term"}


def test_default_title_summary_sections_and_search() -> None:
    """@covers US-067-AC1: the title is the conventional name property, the summary the first
    conventional summary property, and one section lists every other property in order."""
    resolved = view_of(plain())
    product = resolved.view("Product")
    assert (product.title, product.summary, product.declared) == ("{name}", "{summary}", False)
    assert [s.label for s in product.sections] == ["Details"]
    assert product.sections[0].properties == (
        "vendor",
        "category",
        "lifecycleStatus",
        "availability",
        "caveat",
    )
    assert product.search == ("name", "code", "summary")
    solution = resolved.view("Solution")
    assert solution.summary == "{summary}" and "name" not in solution.sections[0].properties
    finding = resolved.view("Finding")  # no name, title or label: the first string property
    assert finding.title == "{statement}" and finding.summary is None
    assert finding.search == ("statement", "code")
    version = resolved.view("ProductVersion")  # `label` is conventional
    assert version.title == "{label}"


def test_the_default_icon_is_circle_and_the_tone_follows_the_declaration_order() -> None:
    types = view_of(plain()).types
    assert {v.icon for v in types.values()} == {"circle"}
    assert [v.tone for v in types.values()] == [TONES[i % 8] for i in range(len(types))]
    assert len(ICONS) == 24 and len(TONES) == 8


def test_default_formats_follow_the_name_and_the_type() -> None:
    """@covers US-067-AC2: the format a property shows in when none is declared."""
    types = view_of(plain()).types
    fmt = {f.property: f.format for f in types["Solution"].fields}
    assert fmt["launchUrl"] == "link" and fmt["workflow"] == "prose" and fmt["prompt"] == "prose"
    assert fmt["name"] == "text" and fmt["deliveryMode"] == "text"
    kinds = {f.property: f.format for f in types["Finding"].fields}
    assert kinds["kind"] == "badge" and kinds["status"] == "badge" and kinds["statement"] == "prose"
    assert {f.property: f.format for f in types["CoverageAssertion"].fields}["level"] == "badge"
    assert types["Solution"].fields[0].property == "code"  # the key is among the fields


def test_default_formats_by_type() -> None:
    from arras.model import Cardinality, PropertyInfo

    def p(
        name: str, typ: str, card: Cardinality = "optional", *, scalar: bool = True
    ) -> PropertyInfo:
        return PropertyInfo(name, typ, scalar, card)

    assert default_format(p("seenAt", "timestamp")) == "datetime"
    assert default_format(p("score", "integer")) == "number"
    assert default_format(p("price", "decimal")) == "number"
    assert default_format(p("active", "boolean")) == "boolean"
    assert default_format(p("tags", "string", "many")) == "tags"
    assert default_format(p("address", "Address", scalar=False)) == "json"
    assert default_format(p("homepageLink", "string")) == "link"
    assert default_format(p("ref", "string")) == "text"
    assert default_format(p("level", "string")) == "badge"
    assert default_format(p("homeURI", "string")) == "link"


def test_relationship_views_cover_both_ends_with_labels_and_order() -> None:
    types = view_of(plain()).types
    product = {r.field: r for r in types["Product"].relationships}
    assert set(product) == {"provides", "coverage", "versions", "findings"}
    assert product["provides"].label == "Provides" and product["provides"].order == 50
    solution = {r.field: r for r in types["Solution"].relationships}
    assert solution["providedBy"].label == "Provided by" and set(solution) == {
        "addresses",
        "providedBy",
    }


def test_the_module_title_defaults_to_its_name() -> None:
    mv = view_of(plain()).module
    assert (mv.title, mv.description) == ("catalog", None)


# -- a declared view (US-070-AC1, AC2, AC6, AC7) -----------------------------------------------


SOLUTION_VIEW = {
    "label": "Offering",
    "icon": "puzzle",
    "tone": "blue",
    "title": "{name}[ ({code})]",
    "summary": "{summary}",
    "sections": [
        {"label": "Delivery", "properties": ["deliveryMode", "audience", "launchUrl"]},
        {"label": "How it works", "properties": ["workflow", "prompt"], "collapsed": True},
    ],
    "search": ["name", "code", "summary"],
}


def full_document() -> dict[str, Any]:
    return declare(
        module={"title": "Product catalog", "description": "Use cases, solutions and findings"},
        Solution=SOLUTION_VIEW,
        Solution__deliveryMode={
            "label": "Delivery",
            "format": "badge",
            "tones": {"app": "teal", "chat": "blue"},
        },
        Solution__launchUrl={"label": "Launch", "format": "link", "hideWhenEmpty": True},
        rel_providedBy={"label": "Product", "inverseLabel": "Solutions", "order": 10},
    )


def test_a_declared_view_registers_and_resolves() -> None:
    """@covers US-070-AC1, US-070-AC2: the registration succeeds and the type's view carries the
    declaration, merged with the defaults for what it does not say."""
    resolved = view_of(full_document())
    assert (resolved.module.title, resolved.module.description) == (
        "Product catalog",
        "Use cases, solutions and findings",
    )
    s = resolved.view("Solution")
    assert (s.declared, s.label, s.icon, s.tone) == (True, "Offering", "puzzle", "blue")
    assert (s.title, s.summary) == ("{name}[ ({code})]", "{summary}")
    assert [(x.label, x.collapsed) for x in s.sections] == [
        ("Delivery", False),
        ("How it works", True),
    ]  # the title and summary use name, code and summary, so nothing is left for "More"
    assert s.search == ("name", "code", "summary")
    f = {x.property: x for x in s.fields}
    assert (
        f["deliveryMode"].tones == {"app": "teal", "chat": "blue"}
        and f["deliveryMode"].label == "Delivery"
    )
    assert f["launchUrl"].hide_when_empty and f["launchUrl"].format == "link"
    assert f["audience"].hide_when_empty is False and f["audience"].format == "text"
    rel = {r.field: r for r in s.relationships}
    assert (rel["providedBy"].label, rel["providedBy"].order) == ("Product", 10)
    prod = {r.field: r for r in resolved.view("Product").relationships}
    assert (prod["provides"].label, prod["provides"].order) == ("Solutions", 10)
    assert resolved.view("UseCase").declared is False  # no term for it


def test_a_module_without_a_view_registers_as_before_and_uses_the_defaults() -> None:
    """@covers US-070-AC6"""
    resolved = view_of(plain())
    assert not any(v.declared for v in resolved.types.values())


def test_the_registry_is_equal_with_and_without_a_view() -> None:
    """@covers US-070-AC7: a view changes no type, property, relationship or action."""
    without = parse_module(json.dumps(plain()))
    with_view = parse_module(json.dumps(full_document()))
    assert without == with_view
    assert [t.properties for t in without.entity_types] == [
        t.properties for t in with_view.entity_types
    ]
    assert without.relationships == with_view.relationships and without.actions == with_view.actions


def test_properties_in_no_declared_section_are_listed_last_under_more() -> None:
    doc = declare(
        Solution={"sections": [{"label": "Delivery", "properties": ["deliveryMode"]}]},
    )
    sections = view_of(doc).view("Solution").sections
    assert [s.label for s in sections] == ["Delivery", "More"]
    assert sections[1].properties == ("workflow", "prompt", "audience", "launchUrl")


def test_search_empty_list_makes_a_type_not_searchable() -> None:
    v = view_of(declare(Product={"search": []})).view("Product")
    assert v.search == ()


def test_a_declared_title_drives_the_default_summary_and_details() -> None:
    v = view_of(declare(Product={"title": "{name} - {vendor}"})).view("Product")
    assert v.summary == "{summary}"
    assert "vendor" not in v.sections[0].properties
    assert v.search[:2] == ("name", "vendor")


# -- the refusals (US-070-AC3, AC4, AC5) -------------------------------------------------------

BAD: list[tuple[str, dict[str, Any] | None, str]] = [
    ("unknown record term", declare(Solution={"colour": "#fff"}), "view_unknown_term"),
    ("markup as a term", declare(Solution={"<script>": 1}), "view_unknown_term"),
    ("url to load", declare(Solution={"icon_url": "https://x/y.png"}), "view_unknown_term"),
    ("component reference", declare(Solution={"component": "Widget"}), "view_unknown_term"),
    ("unknown module term", declare(module={"logo": "x"}), "view_unknown_term"),
    ("unknown field term", declare(Solution__name={"colour": "red"}), "view_unknown_term"),
    (
        "unknown section term",
        declare(Solution={"sections": [{"label": "A", "properties": ["name"], "color": 1}]}),
        "view_unknown_term",
    ),
    ("view on a value-less place", declare(rel_addresses={"format": "text"}), "view_unknown_term"),
    (
        "unknown property in a template",
        declare(Solution={"title": "{nme}"}),
        "view_unknown_property",
    ),
    (
        "unknown property in a section",
        declare(Solution={"sections": [{"label": "A", "properties": ["sumary"]}]}),
        "view_unknown_property",
    ),
    ("unknown property in search", declare(Solution={"search": ["nope"]}), "view_unknown_property"),
    ("relationship term on a record", declare(Solution={"order": 3}), "view_unknown_relationship"),
    ("inverseLabel without inverse", None, "view_unknown_relationship"),
    (
        "format that does not suit",
        declare(Solution__name={"format": "number"}),
        "view_format_mismatch",
    ),
    ("unknown format", declare(Solution__name={"format": "markdown"}), "view_format_mismatch"),
    (
        "tones without badge",
        declare(Solution__name={"tones": {"a": "red"}}),
        "view_format_mismatch",
    ),
    ("unknown icon", declare(Solution={"icon": "rocket"}), "view_unknown_icon"),
    ("unknown tone", declare(Solution={"tone": "#ff0000"}), "view_unknown_tone"),
    (
        "unknown tone in tones",
        declare(Solution__deliveryMode={"format": "badge", "tones": {"a": "pink"}}),
        "view_unknown_tone",
    ),
    ("unclosed placeholder", declare(Solution={"title": "{name"}), "view_bad_template"),
    ("unbalanced bracket", declare(Solution={"summary": "[{name}"}), "view_bad_template"),
    ("template over its length", declare(Solution={"title": "x" * 201}), "view_bad_template"),
    ("non-string in search", None, "view_bad_template"),
    (
        "a property in two sections",
        declare(
            Solution={
                "sections": [
                    {"label": "A", "properties": ["name"]},
                    {"label": "B", "properties": ["name"]},
                ]
            }
        ),
        "view_duplicate",
    ),
    (
        "a property twice in search",
        declare(Solution={"search": ["name", "name"]}),
        "view_duplicate",
    ),
    (
        "too many sections",
        declare(
            Solution={"sections": [{"label": f"S{i}", "properties": ["name"]} for i in range(9)]}
        ),
        "view_too_large",
    ),
    (
        "too many search properties",
        declare(
            Solution={
                "search": [
                    "name",
                    "code",
                    "summary",
                    "workflow",
                    "prompt",
                    "audience",
                    "launchUrl",
                    "deliveryMode",
                    "name",
                ]
            }
        ),
        "view_too_large",
    ),
    ("label over 60", declare(Solution={"label": "x" * 61}), "view_too_large"),
    ("unsupported version", None, "view_unsupported_version"),
]


def _special(name: str) -> dict[str, Any] | None:
    if name == "inverseLabel without inverse":
        doc = declare(rel_addresses={"inverseLabel": "x"})
        rel = next(r for r in doc["modules"][0]["relationships"] if r["name"] == "addresses")
        rel.pop("inverse")
        return doc
    if name == "non-string in search":
        doc = declare(Solution={"search": ["name"]})
        # a many-valued string is not a string property for search: add one
        return declare_many_string(doc)
    if name == "unsupported version":
        doc = declare(Solution={"label": "x"})
        doc["vocabularies"][VIEW]["version"] = "9.9.9"
        return doc
    return None


def declare_many_string(doc: dict[str, Any]) -> dict[str, Any]:
    """Make `Solution.audience` a list of strings and search over it."""
    mod = doc["modules"][0]
    sol = next(e for e in mod["elements"] if e["id"] == "Solution")
    sol["extensions"]["umf.ddd"]["fields"]["audience"]["cardinality"] = "many"
    el = next(e for e in mod["elements"] if e["id"] == "Solution.audience")
    el["cardinality"] = "many"
    sol["extensions"][VIEW] = {"search": ["audience"]}
    return doc


@pytest.mark.parametrize("name,doc,code", BAD, ids=[b[0] for b in BAD])
def test_a_faulty_declaration_is_refused_with_its_path(
    name: str, doc: dict[str, Any] | None, code: str
) -> None:
    """@covers US-070-AC3, US-070-AC4, US-070-AC5: refused with the code and the path of the fault."""
    doc = doc if doc is not None else _special(name)
    assert doc is not None
    found = refused(doc)
    assert code in {c for _, c in found}, found
    assert all(p for p, _ in found)
    paths = [p for p, c in found if c == code]
    assert any("arras.view" in p or p.startswith("vocabularies") for p in paths), paths


def test_a_fault_names_the_path_in_the_document() -> None:
    """@covers US-070-AC3: the example of QUERY-010."""
    doc = declare(Solution={"sections": [{"label": "A", "properties": ["name", "code", "sumary"]}]})
    index = next(i for i, e in enumerate(doc["modules"][0]["elements"]) if e["id"] == "Solution")
    assert refused(doc) == [
        (
            f"modules[0].elements[{index}].extensions.arras.view.sections[0].properties[2]",
            "view_unknown_property",
        )
    ]


def test_every_fault_is_reported_not_only_the_first() -> None:
    doc = declare(Solution={"icon": "rocket", "tone": "pink", "title": "{x"}, Product={"nope": 1})
    assert codes(doc) == {
        "view_unknown_icon",
        "view_unknown_tone",
        "view_bad_template",
        "view_unknown_term",
    }


def test_the_terms_of_a_document_that_does_not_use_the_vocabulary_are_not_examined() -> None:
    doc = plain()
    next(e for e in doc["modules"][0]["elements"] if e["id"] == "Solution")["extensions"][VIEW] = {
        "colour": "red"
    }
    parse_module(json.dumps(doc))  # not declared: not examined


def test_a_view_cannot_be_larger_than_its_limit() -> None:
    big = {f"v{i}": "teal" for i in range(24)}
    doc = declare(
        Solution__deliveryMode={"format": "badge", "tones": big, "label": "x" * 60},
        Solution={
            "title": "{name}",
            "label": "y" * 60,
            "sections": [{"label": "z" * 60, "properties": ["name"]}],
        },
    )
    parse_module(json.dumps(doc))  # well inside 16 KiB
    heavy = copy.deepcopy(doc)
    for el in heavy["modules"][0]["elements"]:
        if el["id"].startswith("Solution"):
            el.setdefault("extensions", {}).setdefault(VIEW, {})
    # 9 sections of 24 properties of long names is over the record limit
    names = [f"{'p' * 200}{i}" for i in range(24)]
    sections = [{"label": "S", "properties": names} for _ in range(8)]
    solution = next(e for e in heavy["modules"][0]["elements"] if e["id"] == "Solution")
    solution["extensions"][VIEW] = {"sections": sections}
    assert "view_too_large" in codes(heavy)


def test_a_refused_registration_leaves_the_registry_unchanged() -> None:
    """@covers US-070-AC3: the stored registry is unchanged."""
    from arras.sandbox import catalog_document

    box = Sandbox().seed()
    root = box.arras.session(box.people["root"])
    alice = box.arras.session(box.people["alice"])
    before = alice.describe("catalog")[0].revision
    bad = json.loads(catalog_document())
    bad["vocabularies"][VIEW] = {"version": "0.1.0"}
    bad["modules"][0]["elements"][0].setdefault("extensions", {})[VIEW] = {"icon": "rocket"}
    with pytest.raises(Invalid) as e:
        root.registry().register(json.dumps(bad))
    assert [v.code for v in e.value.violations] == ["view_unknown_icon"]
    assert alice.describe("catalog")[0].revision == before


def test_declared_view_defaults_survive_json_with_unicode_labels() -> None:
    doc = declare(Solution={"label": "Lösung", "title": "{name} · {code}"})
    assert view_of(doc).view("Solution").label == "Lösung"


def test_no_view_is_a_default_declared_view() -> None:
    assert DeclaredView().records == {}


# -- a view on a place that has none (US-070-AC4) ----------------------------------------------


def _with_value_object() -> dict[str, Any]:
    """The catalog plus `Money`, a value object of one string, with a view on it and its field."""
    doc = declare(Solution={"label": "x"})
    mod = doc["modules"][0]
    string = {"type": {"kind": "scalar", "name": "string"}, "cardinality": "one"}
    mod["elements"] += [
        {
            "id": "Money",
            "kind": "record",
            "members": [{"module": "catalog", "element": "Money.currency"}],
            "extensions": {"umf.ddd": {"kind": "value-object", "fields": {"currency": string}}},
        },
        {"id": "Money.currency", "kind": "field", **string},
    ]
    return doc


def _place(doc: dict[str, Any], element: str) -> None:
    el = next(e for e in doc["modules"][0]["elements"] if e["id"] == element)
    el.setdefault("extensions", {})[VIEW] = {"label": "x"}


def test_a_view_on_a_value_object_or_its_field_is_refused() -> None:
    doc = _with_value_object()
    _place(doc, "Money")
    _place(doc, "Money.currency")
    found = [(p, c) for p, c in refused(doc) if c.startswith("view_")]
    index = {e["id"]: i for i, e in enumerate(doc["modules"][0]["elements"])}
    assert sorted(found) == sorted(
        (f"modules[0].elements[{index[k]}].extensions.arras.view", "view_unknown_term")
        for k in ("Money", "Money.currency")
    )


def test_a_view_on_an_element_of_another_kind_an_action_or_the_root_is_refused() -> None:
    doc = declare(Solution={"label": "x"})
    mod = doc["modules"][0]
    mod["elements"].append({"id": "Odd", "kind": "enum", "extensions": {VIEW: {"label": "x"}}})
    mod["actions"][0].setdefault("extensions", {})[VIEW] = {"label": "x"}
    doc["extensions"] = {VIEW: {"title": "x"}}
    found = refused(doc)
    odd = len(mod["elements"]) - 1
    assert (f"modules[0].elements[{odd}].extensions.arras.view", "view_unknown_term") in found
    assert ("modules[0].actions[0].extensions.arras.view", "view_unknown_term") in found
    assert ("extensions.arras.view", "view_unknown_term") in found


def test_a_record_view_over_the_size_limit_is_reported_at_a_path_in_the_document() -> None:
    doc = declare(Solution={"label": "x"})
    names = [f"{'p' * 200}{i}" for i in range(24)]
    sections = [{"label": "S", "properties": names} for _ in range(8)]
    mod = doc["modules"][0]
    index = next(i for i, e in enumerate(mod["elements"]) if e["id"] == "Solution")
    mod["elements"][index]["extensions"][VIEW] = {"sections": sections}
    sized = [(p, c) for p, c in refused(doc) if c == "view_too_large"]
    assert (f"modules[0].elements[{index}].extensions.arras.view", "view_too_large") in sized
    assert not any(p.startswith("elements.") for p, _ in sized)
