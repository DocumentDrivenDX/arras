# SPDX-License-Identifier: MIT OR Apache-2.0
"""Build the catalog example's UMF module from a short description of it.

    uv run python examples/catalog/build.py          # write catalog.umf.json beside this file
    uv run python examples/catalog/build.py --check  # fail if the file has drifted from this

A UMF document says each field twice, once on its record and once as an element, and spells out
every action's inputs, preconditions and effects. Written by hand that is several hundred lines
for a handful of types. Here a type is a list of fields, a relationship is four names, and an
action is built from the type it acts on, so changing the schema is a line or two. The records
and fields come from the shared generator (`ontology.py`); the actions are this example's own,
because the catalog's links are set and cleared by actions of their own. The seed (`seed.json`) is
data and is edited directly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))
from ontology import _exists, _inputs, _lower, _update, document  # noqa: E402

MODULE = "catalog"
TARGET = Path(__file__).with_name("catalog.umf.json")
S = "string"

Json = dict[str, Any]

# Each type's fields as (name, scalar, required). The first field is the key.
TYPES: dict[str, list[tuple[str, str, bool]]] = {
    "UseCase": [
        ("code", S, True),
        ("name", S, True),
        ("workArea", S, False),
        ("description", S, False),
        ("problem", S, False),
    ],
    "Solution": [
        ("code", S, True),
        ("name", S, True),
        ("deliveryMode", S, True),
        ("summary", S, False),
        ("workflow", S, False),
        ("prompt", S, False),
        ("audience", S, False),
        ("launchUrl", S, False),
    ],
    "Product": [
        ("code", S, True),
        ("name", S, True),
        ("vendor", S, False),
        ("category", S, False),
        ("summary", S, False),
        ("lifecycleStatus", S, False),
        ("availability", S, False),
        ("caveat", S, False),
    ],
    "CoverageAssertion": [("code", S, True), ("level", S, True), ("notes", S, False)],
    "ProductVersion": [("code", S, True), ("label", S, True), ("status", S, False)],
    "Finding": [("code", S, True), ("statement", S, True), ("kind", S, True), ("status", S, True)],
}

# name, source type, target type, the name of the inverse on the target
RELATIONSHIPS: list[tuple[str, str, str, str]] = [
    ("addresses", "Solution", "UseCase", "addressedBy"),
    ("providedBy", "Solution", "Product", "provides"),
    ("ofProduct", "CoverageAssertion", "Product", "coverage"),
    ("ofUseCase", "CoverageAssertion", "UseCase", "coveredBy"),
    ("versionOf", "ProductVersion", "Product", "versions"),
    ("about", "Finding", "Product", "findings"),
    ("aboutVersion", "Finding", "ProductVersion", "versionFindings"),
    ("appliesTo", "Finding", "UseCase", "evidence"),
    ("adjacentTo", "Finding", "UseCase", "adjacentEvidence"),
]

# How each type is presented: `arras.view` terms (CONTRACT-010) by record, by `Type.field` and by
# relationship name. Presentation only: nothing here changes a type, a field or an action.
MODULE_VIEW: Json = {
    "title": "Product catalog",
    "description": "Use cases, solutions, products and what an evaluation found",
}
RECORD_VIEWS: dict[str, Json] = {
    "UseCase": {
        "label": "Use case",
        "icon": "wrench",
        "tone": "violet",
        "title": "{name}",
        "summary": "{description}",
        "sections": [
            {"label": "Where it applies", "properties": ["workArea"]},
            {"label": "The problem", "properties": ["problem"], "collapsed": True},
        ],
        "search": ["name", "code", "description", "problem", "workArea"],
    },
    "Solution": {
        "label": "Solution",
        "icon": "puzzle",
        "tone": "blue",
        "title": "{name}[ ({code})]",
        "summary": "{summary}",
        "sections": [
            {"label": "Delivery", "properties": ["deliveryMode", "audience", "launchUrl"]},
            {"label": "How it works", "properties": ["workflow", "prompt"], "collapsed": True},
        ],
        "search": ["name", "code", "summary", "audience", "workflow", "prompt"],
    },
    "Product": {
        "label": "Product",
        "icon": "package",
        "tone": "teal",
        "title": "{name}",
        "summary": "{summary}",
        "sections": [
            {"label": "Status", "properties": ["lifecycleStatus", "availability"]},
            {"label": "About", "properties": ["vendor", "category"]},
            {"label": "Caveat", "properties": ["caveat"]},
        ],
        "search": ["name", "code", "vendor", "category", "summary"],
    },
    "CoverageAssertion": {
        "label": "Coverage",
        "pluralLabel": "Coverage",
        "icon": "check-circle",
        "tone": "green",
        "title": "{code}",
        "sections": [{"label": "Notes", "properties": ["notes"]}],
        "search": ["code", "notes"],
    },
    "ProductVersion": {
        "label": "Product version",
        "icon": "tag",
        "tone": "amber",
        "title": "{label} ({code})",
        "sections": [],
        "search": ["label", "code"],
    },
    "Finding": {
        "label": "Finding",
        "icon": "flag",
        "tone": "rose",
        "title": "{code}",
        "summary": "{statement}",
        "sections": [],
        "search": ["statement", "code"],
    },
}
FIELD_VIEWS: dict[str, Json] = {
    "Solution.deliveryMode": {
        "label": "Delivery",
        "format": "badge",
        "tones": {"chat": "blue", "handoff": "amber", "app": "teal"},
    },
    "Solution.launchUrl": {"label": "Launch", "format": "link", "hideWhenEmpty": True},
    "Solution.workflow": {"hideWhenEmpty": True},
    "Solution.prompt": {"format": "code", "hideWhenEmpty": True},
    "Product.availability": {
        "format": "badge",
        "tones": {
            "live": "green",
            "limited": "amber",
            "in_evaluation": "blue",
            "purchasing": "violet",
            "not_available": "slate",
        },
    },
    "Product.caveat": {"hideWhenEmpty": True},
    "CoverageAssertion.notes": {"hideWhenEmpty": True},
    "CoverageAssertion.level": {
        "format": "badge",
        "tones": {"full": "green", "partial": "amber", "adjacent": "slate"},
    },
    "ProductVersion.status": {
        "format": "badge",
        "tones": {"current": "green", "superseded": "slate"},
    },
    "Finding.kind": {"format": "badge"},
    "Finding.status": {"format": "badge", "tones": {"active": "amber"}},
}
RELATIONSHIP_VIEWS: dict[str, Json] = {
    "addresses": {"label": "Addresses", "inverseLabel": "Addressed by", "order": 10},
    "providedBy": {"label": "Provided by", "inverseLabel": "Provides", "order": 20},
    "ofProduct": {"label": "Product", "inverseLabel": "Coverage", "order": 30},
    "ofUseCase": {"label": "Use case", "inverseLabel": "Covered by", "order": 30},
    "versionOf": {"label": "Version of", "inverseLabel": "Versions", "order": 40},
    "about": {"label": "About", "inverseLabel": "Findings", "order": 40},
    "aboutVersion": {"label": "About version", "inverseLabel": "Findings on this version"},
    "appliesTo": {"label": "Evidence for", "inverseLabel": "Evidence", "order": 60},
    "adjacentTo": {"label": "Bears on", "inverseLabel": "Adjacent evidence", "order": 70},
}

# -- actions


def _ref(type_name: str) -> str:
    """The name an action's input takes for a record of this type."""
    return _lower(type_name)


def _add(name: str, description: str, links: list[tuple[str, str]]) -> Json:
    """Add a record of `name`, linked at once to the records its `links` (relationship, target
    type) name; the input for each is named for the target type."""
    fields = TYPES[name]
    refs = [(_ref(target), target) for _, target in links]
    return {
        "id": _add_id(name),
        "description": description,
        "inputs": _inputs(fields, refs),
        "preconditions": [
            {
                "id": "fresh",
                "reason": f"a {_lower(name)} with that code exists",
                "predicate": {"op": "absent", "type": name, "key": {"input": "code"}},
            },
            *(_exists(r) for r, _ in refs),
        ],
        "effects": [
            {
                "op": "create",
                "as": "new",
                "type": name,
                "key": {"input": "code"},
                "properties": {f: {"input": f} for f, _, _ in fields[1:]},
            },
            *(
                {
                    "op": "link",
                    "type": rel,
                    "source": {"alias": "new"},
                    "target": {"input": _ref(target)},
                }
                for rel, target in links
            ),
        ],
    }


def _add_id(name: str) -> str:
    return {"CoverageAssertion": "AssertCoverage"}.get(name, f"Add{name}")


def _change(
    verb: str, name: str, description: str, fields: list[str], *, required: bool = False
) -> Json:
    chosen = [(f, S, required) for f in fields]
    return _update(name, verb, description, chosen)


def _relink(action: str, description: str, rel: str, source: str, target: str, op: str) -> Json:
    s, t = _ref(source), _ref(target)
    return {
        "id": action,
        "description": description,
        "inputs": _inputs([], [(s, source), (t, target)]),
        "preconditions": [_exists(s), _exists(t)],
        "effects": [
            {"op": op, "type": rel, "source": {"input": s}, "target": {"input": t}},
        ],
    }


def _retire(action: str, name: str, description: str) -> Json:
    ref = _ref(name)
    return {
        "id": action,
        "description": description,
        "inputs": _inputs([], [(ref, name)]),
        "preconditions": [_exists(ref)],
        "effects": [{"op": "delete", "refType": name, "key": {"input": ref}}],
    }


def actions() -> list[Json]:
    return [
        _add(
            "UseCase", "Add a use case: a kind of work someone in the organization needs done", []
        ),
        _add(
            "Solution",
            "Add a solution: one way of doing a use case",
            [("addresses", "UseCase")],
        ),
        _add(
            "Product",
            "Add a product: a tool the organization has, is trialling or is considering",
            [],
        ),
        _add(
            "CoverageAssertion",
            "Record how far a product covers a use case",
            [("ofProduct", "Product"), ("ofUseCase", "UseCase")],
        ),
        _add(
            "ProductVersion",
            "Add a version of a product",
            [("versionOf", "Product")],
        ),
        _add(
            "Finding",
            "Add a finding: something an evaluation observed about a product",
            [("about", "Product")],
        ),
        _change(
            "CorrectUseCase",
            "UseCase",
            "Correct the details of use case",
            ["workArea", "description", "problem"],
        ),
        _change("RenameUseCase", "UseCase", "Change the name of use case", ["name"], required=True),
        _change(
            "CorrectSolution",
            "Solution",
            "Correct the details of solution",
            ["summary", "workflow", "prompt", "audience", "launchUrl"],
        ),
        _change(
            "UpdateSolution",
            "Solution",
            "Update solution",
            ["name", "deliveryMode"],
            required=True,
        ),
        _change(
            "CorrectProduct",
            "Product",
            "Correct the details of product",
            ["vendor", "category", "summary", "lifecycleStatus", "availability", "caveat"],
        ),
        _change("RenameProduct", "Product", "Change the name of product", ["name"], required=True),
        _change(
            "ChangeCoverageLevel",
            "CoverageAssertion",
            "Change the level of coverage assertion",
            ["level"],
            required=True,
        ),
        _change(
            "CorrectCoverageAssertion",
            "CoverageAssertion",
            "Correct the details of coverage assertion",
            ["notes"],
        ),
        _change(
            "RelabelProductVersion",
            "ProductVersion",
            "Change the label of product version",
            ["label"],
            required=True,
        ),
        _change(
            "CorrectProductVersion",
            "ProductVersion",
            "Correct the details of product version",
            ["status"],
        ),
        _change(
            "UpdateFinding",
            "Finding",
            "Update finding",
            ["statement", "kind", "status"],
            required=True,
        ),
        _relink(
            "AddressUseCase",
            "Link solution addresses use case",
            "addresses",
            "Solution",
            "UseCase",
            "link",
        ),
        _relink(
            "UnaddressUseCase",
            "Unlink solution addresses use case",
            "addresses",
            "Solution",
            "UseCase",
            "unlink",
        ),
        _relink(
            "SetSolutionProvider",
            "Link solution providedBy product",
            "providedBy",
            "Solution",
            "Product",
            "link",
        ),
        _relink(
            "ClearSolutionProvider",
            "Unlink solution providedBy product",
            "providedBy",
            "Solution",
            "Product",
            "unlink",
        ),
        _relink(
            "SetFindingVersion",
            "Link finding aboutVersion product version",
            "aboutVersion",
            "Finding",
            "ProductVersion",
            "link",
        ),
        _relink(
            "ClearFindingVersion",
            "Unlink finding aboutVersion product version",
            "aboutVersion",
            "Finding",
            "ProductVersion",
            "unlink",
        ),
        _relink(
            "ApplyFindingTo",
            "Link finding appliesTo use case",
            "appliesTo",
            "Finding",
            "UseCase",
            "link",
        ),
        _relink(
            "UnapplyFindingTo",
            "Unlink finding appliesTo use case",
            "appliesTo",
            "Finding",
            "UseCase",
            "unlink",
        ),
        _relink(
            "RelateFindingTo",
            "Link finding adjacentTo use case",
            "adjacentTo",
            "Finding",
            "UseCase",
            "link",
        ),
        _relink(
            "UnrelateFindingTo",
            "Unlink finding adjacentTo use case",
            "adjacentTo",
            "Finding",
            "UseCase",
            "unlink",
        ),
        _retire("RetireSolution", "Solution", "Remove solution and its links"),
        _retire("RetireCoverage", "CoverageAssertion", "Remove coverage assertion and its links"),
        _retire("RetireFinding", "Finding", "Remove finding and its links"),
    ]


def build() -> Json:
    spec: Json = {
        "id": "catalog-example",
        "module": MODULE,
        "view": MODULE_VIEW,
        "types": TYPES,
        "relationships": [(n, s, t, i, False) for n, s, t, i in RELATIONSHIPS],
        "records": RECORD_VIEWS,
        "fields": FIELD_VIEWS,
        "relationshipViews": RELATIONSHIP_VIEWS,
    }
    doc = document(spec)
    doc["modules"][0]["actions"] = actions()
    return doc


def text() -> str:
    return json.dumps(build(), indent=2) + "\n"


def main(argv: list[str]) -> int:
    if "--check" in argv:
        if TARGET.read_text(encoding="utf-8") != text():
            print(
                f"{TARGET.name} has drifted from build.py: run it without --check", file=sys.stderr
            )
            return 1
        return 0
    TARGET.write_text(text(), encoding="utf-8", newline="\n")
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
