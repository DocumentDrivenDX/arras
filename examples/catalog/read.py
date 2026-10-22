# SPDX-License-Identifier: MIT OR Apache-2.0
"""The reads a page over the catalog needs, written against Arras's query interface.

`cards` gives one card per solution: what it is, how it is delivered, the use case it addresses and
the product that provides it. `use_case` gives one use case with every way of doing it: its
solutions, and the products recorded as covering it. `products` gives every product with its
status, its versions, the use cases it covers and the solutions it provides. A use case also
carries its findings: what an evaluation observed, about which product and version.

All take an `Ontology` (an `Arras` session for one person), so the person's own access decides
what is read. They return plain dictionaries with JSON-friendly keys, ready to send to a page.

Shaped by what the memory backend's Weft profiles serve: one entity by key, a list filtered on
required fields, the entities linked to a key (`HAS_RELATED`), and each entity's relationship keys
(`RELATED_KEYS`). Pages are the statement's own: key order, `LIMIT` and a keyset predicate. There
is no `IN` and no filter on an optional field, so a card's use case and product are read one key at
a time (remembered within a call), and `audience` is compared here. At catalog size that is a few
dozen small reads.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any, cast

from arras.core import Ontology
from arras.names import quoted, quoted_type

Row = Mapping[str, Any]
PAGE = 100


# The relationships each type's rows carry, read with RELATED_KEYS.
RELATED: dict[str, tuple[str, ...]] = {
    "Solution": ("addresses", "providedBy"),
    "Finding": ("about", "aboutVersion"),
    "CoverageAssertion": ("ofProduct", "ofUseCase"),
    "ProductVersion": ("versionOf",),
    "Product": ("provides", "findings"),
}


def rows(
    o: Ontology,
    type_name: str,
    where: str = "",
    params: Mapping[str, Any] | None = None,
    *,
    page: int = PAGE,
) -> list[Row]:
    """Every entity of a catalog type that matches `where` (a predicate over alias `x`), each with
    its relationship keys, read a page at a time with a keyset on the key."""
    # generated names are written as Weft quoted identifiers: any legal UMF name reads exactly
    keys = "".join(
        f", RELATED_KEYS(x.{quoted(r)}, 100) AS {quoted(r)}" for r in RELATED.get(type_name, ())
    )
    out: list[Row] = []
    last: str | None = None
    while True:
        bound = [where] if where else []
        if last is not None:
            bound.append('x."code" > :_last')
        clause = f" WHERE {' AND '.join(bound)}" if bound else ""
        source = quoted_type(f"catalog.{type_name}")
        sql = f'SELECT x.*{keys} FROM {source} x{clause} ORDER BY x."code" LIMIT {page}'
        args = {**(params or {}), **({"_last": last} if last is not None else {})}
        answer = o.query("catalog", sql, args, limit=page)
        out.extend(answer.rows)
        if len(answer.rows) < page:
            return out
        last = answer.rows[-1]["code"]


class _Lookup:
    """Entities read by key, each read once."""

    def __init__(self, o: Ontology) -> None:
        self.o = o
        self.seen: dict[tuple[str, str], Row | None] = {}

    def get(self, type_name: str, key: str | None) -> Row | None:
        if key is None:
            return None
        if (type_name, key) not in self.seen:
            found = rows(self.o, type_name, "x.code = :k", {"k": key})
            self.seen[type_name, key] = found[0] if found else None
        return self.seen[type_name, key]


def _first(row: Row, relationship: str) -> str | None:
    keys = cast(list[str], row.get(relationship) or [])
    return keys[0] if keys else None


def _use_case(row: Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["code"],
        "name": row["name"],
        "workArea": row.get("workArea"),
        "description": row.get("description"),
        "problem": row.get("problem"),
    }


def _product(row: Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["code"],
        "name": row["name"],
        "vendor": row.get("vendor"),
        "category": row.get("category"),
        "summary": row.get("summary"),
        "lifecycleStatus": row.get("lifecycleStatus"),
        "availability": row.get("availability"),
        "caveat": row.get("caveat"),
    }


def _finding(finding: Row, relation: str, lookup: _Lookup) -> dict[str, Any]:
    version = lookup.get("ProductVersion", _first(finding, "aboutVersion"))
    return {
        "id": finding["code"],
        "statement": finding["statement"],
        "kind": finding.get("kind"),
        "status": finding.get("status"),
        # `primary` when the finding is evidence for the use case, `adjacent` when it bears on it
        "relation": relation,
        "product": _product(lookup.get("Product", _first(finding, "about"))),
        "version": None if version is None else {"id": version["code"], "label": version["label"]},
    }


def _card(solution: Row, lookup: _Lookup) -> dict[str, Any]:
    return {
        "id": solution["code"],
        "title": solution["name"],
        "summary": solution.get("summary"),
        "deliveryMode": solution["deliveryMode"],
        "workflow": solution.get("workflow"),
        "prompt": solution.get("prompt"),
        "audience": solution.get("audience"),
        "launchUrl": solution.get("launchUrl"),
        "useCase": _use_case(lookup.get("UseCase", _first(solution, "addresses"))),
        "provider": _product(lookup.get("Product", _first(solution, "providedBy"))),
    }


def _shown(solution: Row, audiences: Collection[str]) -> bool:
    audience = solution.get("audience")
    return audience is None or audience in audiences


def cards(o: Ontology, *, audiences: Collection[str] = ()) -> list[dict[str, Any]]:
    """One card per solution, in key order.

    A solution that names an `audience` is left out unless that audience is in `audiences`. That
    decides what a page offers, not what a person may read: access is the backends' own."""
    lookup = _Lookup(o)
    solutions = rows(o, "Solution")
    return [_card(s, lookup) for s in solutions if _shown(s, audiences)]


def use_case(o: Ontology, code: str, *, audiences: Collection[str] = ()) -> dict[str, Any] | None:
    """One use case with its solutions and the products that cover it, or `None` if there is none."""
    lookup = _Lookup(o)
    found = _use_case(lookup.get("UseCase", code))
    if found is None:
        return None
    solutions = rows(o, "Solution", "HAS_RELATED(x.addresses, KEY(:k))", {"k": code})
    assertions = rows(o, "CoverageAssertion", "HAS_RELATED(x.ofUseCase, KEY(:k))", {"k": code})
    primary = rows(o, "Finding", "HAS_RELATED(x.appliesTo, KEY(:k))", {"k": code})
    adjacent = rows(o, "Finding", "HAS_RELATED(x.adjacentTo, KEY(:k))", {"k": code})
    return {
        **found,
        "solutions": [_card(s, lookup) for s in solutions if _shown(s, audiences)],
        "coverage": [
            {
                "product": _product(lookup.get("Product", _first(c, "ofProduct"))),
                "level": c["level"],
                "notes": c.get("notes"),
            }
            for c in assertions
        ],
        "findings": [
            *(_finding(f, "primary", lookup) for f in primary),
            *(_finding(f, "adjacent", lookup) for f in adjacent),
        ],
    }


def products(o: Ontology) -> list[dict[str, Any]]:
    """Every product, in key order, with the use cases it is recorded as covering and at what
    level, and the solutions it provides.

    Three list reads joined here (products, coverage assertions, use cases), so the cost does
    not grow with the number of products."""
    names = {u["code"]: u for u in rows(o, "UseCase")}
    covered: dict[str, list[dict[str, Any]]] = {}
    for assertion in rows(o, "CoverageAssertion"):
        product, use_case_key = _first(assertion, "ofProduct"), _first(assertion, "ofUseCase")
        found = names.get(use_case_key or "")
        if product is None or found is None:
            continue
        covered.setdefault(product, []).append(
            {
                "id": found["code"],
                "name": found["name"],
                "workArea": found.get("workArea"),
                "level": assertion["level"],
            }
        )
    versions: dict[str, list[Row]] = {}
    for version in rows(o, "ProductVersion"):
        versions.setdefault(_first(version, "versionOf") or "", []).append(version)
    return [
        {
            **(_product(p) or {}),
            "coverage": sorted(covered.get(p["code"], []), key=lambda c: c["id"]),
            "solutions": list(cast(list[str], p.get("provides") or [])),
            "versions": [
                {"id": v["code"], "label": v["label"], "status": v.get("status")}
                for v in versions.get(p["code"], [])
            ],
            "findings": list(cast(list[str], p.get("findings") or [])),
        }
        for p in rows(o, "Product")
    ]
