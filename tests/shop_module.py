# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""A test-only UMF module for relational reads (W-011): customers, the orders they place and the
lines of an order, with string, integer and decimal fields and a relationship with an inverse.
`shop_store()` is a memory backend holding it with a few records, and `carol` may read it."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from arras.fakes import FakeAccess, MemoryStore
from arras.types import Principal
from arras.umf import parse_module

MODULE = "shop"


def _field(owner: str, name: str, scalar: str, required: bool) -> dict[str, Any]:
    el: dict[str, Any] = {
        "id": f"{owner}.{name}",
        "kind": "field",
        "nullability": "required" if required else "absent-allowed",
        "cardinality": "one",
        "scalarType": scalar,
        "extensions": {},
    }
    if scalar == "decimal":
        el["facets"] = {"precision": 12, "scale": 2}
    if scalar == "integer":
        el["facets"] = {"integerWidth": {"bits": 64, "signed": True}}
    return el


def _record(name: str, fields: dict[str, tuple[str, bool]]) -> list[dict[str, Any]]:
    rec: dict[str, Any] = {
        "id": name,
        "kind": "record",
        "members": [{"module": MODULE, "element": f"{name}.{f}"} for f in fields],
        "extensions": {
            "umf.ddd": {
                "kind": "entity",
                "fields": {
                    f: {
                        "type": {"kind": "scalar", "name": t},
                        "cardinality": "one" if r else "optional",
                    }
                    for f, (t, r) in fields.items()
                },
                "identity": {"fields": ["code"], "scope": "context"},
            }
        },
        "keys": [
            {
                "id": "identity",
                "name": "Identity",
                "fields": [{"module": MODULE, "element": f"{name}.code"}],
                "primary": True,
            }
        ],
    }
    return [rec, *(_field(name, f, t, r) for f, (t, r) in fields.items())]


def document(*, seen: bool = False) -> str:
    """The shop module; `seen` adds a timestamp field to Customer (Weft serves no timestamps, so only
    the import tests ask for it)."""
    customer = {
        "code": ("string", True),
        "name": ("string", True),
        "region": ("string", True),
        "note": ("string", False),
    }
    if seen:
        customer["seen"] = ("timestamp", False)
    elements = [
        *_record("Customer", customer),
        *_record("Purchase", {"code": ("string", True), "customer": ("string", True), "total": ("decimal", True), "qty": ("integer", True)}),
        *_record("Line", {"code": ("string", True), "order": ("string", True), "sku": ("string", True), "amount": ("decimal", True)}),
    ]  # fmt: skip
    rel = {
        "id": "customer-places",
        "name": "places",
        "source": [{"module": MODULE, "element": "Customer"}],
        "target": [{"module": MODULE, "element": "Purchase", "key": "identity"}],
        "sourceMultiplicity": {"min": 0, "max": "*"},
        "targetMultiplicity": {"min": 0, "max": 1},
        "targetLifecycle": "independent",
        "directed": True,
        "inverse": "placedBy",
    }
    return json.dumps(
        {
            "umf": "0.10.0",
            "id": "shop",
            "vocabularies": {"umf.ddd": {"version": "0.1.0"}},
            "extensions": {},
            "modules": [
                {
                    "id": MODULE,
                    "namespace": MODULE,
                    "extensions": {"umf.ddd": {"kind": "bounded-context", "terms": []}},
                    "elements": elements,
                    "relationships": [rel],
                }
            ],
        }
    )


CUSTOMERS = [("c1", "Ann", "east"), ("c2", "Bob", "west"), ("c3", "Cy", "east")]
ORDERS = [
    ("o1", "c1", Decimal("10.50"), 1),
    ("o2", "c1", Decimal("4.25"), 3),
    ("o3", "c2", Decimal("7.00"), 2),
    ("o4", "c2", Decimal("1.25"), 1),
]
LINES = [
    ("l1", "o1", "pen", Decimal("2.50")),
    ("l2", "o1", "ink", Decimal("8.00")),
    ("l3", "o3", "pen", Decimal("7.00")),
]


def shop_store() -> tuple[MemoryStore, Principal]:
    """A memory record store holding `shop` and its records; returns it and `carol`, a reader."""
    access = FakeAccess()
    store = MemoryStore(access)
    root = access.grant("root", MODULE, "read", "write", "schema", admin=True)
    carol = access.grant("carol", MODULE, "read")
    doc = document()
    store.register(root, doc.encode(), parse_module(doc), unknown_endpoint="reject")
    records: list[dict[str, Any]] = []
    for code, name, region in CUSTOMERS:
        records.append(
            {"type": "Customer", "key": code, "properties": {"name": name, "region": region}}
        )
    for code, cust, total, qty in ORDERS:
        records.append(
            {
                "type": "Purchase",
                "key": code,
                "properties": {"customer": cust, "total": total, "qty": qty},
            }
        )
        records.append({"relationship": "places", "source": cust, "target": code})
    for code, order, sku, amount in LINES:
        records.append(
            {
                "type": "Line",
                "key": code,
                "properties": {"order": order, "sku": sku, "amount": amount},
            }
        )
    r = store.import_records(root, MODULE, records, load_id="shop", initiated_by="root")
    assert not r.rejected, r.rejected
    return store, carol
