# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""A test-only UMF module with every kind of input an action takes (CONTRACT-002, CONTRACT-003):
integer, decimal, timestamp, binary and boolean scalars, a list of strings, a ref and a structured
value. `lab.Record` creates a `Sample` from them, a `Tag` per listed string, and links the new
sample to the one it `follows`."""

from __future__ import annotations

import json
from typing import Any

from arras.sandbox import Sandbox

MODULE = "lab"


def _scalar(name: str) -> dict[str, Any]:
    return {"kind": "scalar", "name": name}


def _field(owner: str, name: str, scalar: str | None, required: bool) -> dict[str, Any]:
    el: dict[str, Any] = {
        "id": f"{owner}.{name}",
        "kind": "field",
        "nullability": "required" if required else "absent-allowed",
        "cardinality": "one",
        "extensions": {},
    }
    if scalar is not None:
        el["scalarType"] = scalar
    return el


def _record(
    name: str, fields: dict[str, tuple[dict[str, Any], bool]], *, key: str | None
) -> list[dict[str, Any]]:
    """A record element and its field elements; `key` makes it an entity keyed by that field."""
    rec: dict[str, Any] = {
        "id": name,
        "kind": "record",
        "members": [{"module": MODULE, "element": f"{name}.{f}"} for f in fields],
        "extensions": {
            "umf.ddd": {
                "kind": "entity" if key else "value-object",
                "fields": {
                    f: {"type": t, "cardinality": "one" if req else "optional"}
                    for f, (t, req) in fields.items()
                },
                **({"identity": {"fields": [key], "scope": "context"}} if key else {}),
            }
        },
    }
    if key:
        rec["keys"] = [
            {
                "id": "identity",
                "name": "Identity",
                "fields": [{"module": MODULE, "element": f"{name}.{key}"}],
                "primary": True,
            }
        ]
    out = [rec]
    for f, (t, req) in fields.items():
        out.append(_field(name, f, t["name"] if t["kind"] == "scalar" else None, req))
    return out


SAMPLE_FIELDS = {
    "code": (_scalar("string"), True),
    "count": (_scalar("integer"), False),
    "amount": (_scalar("decimal"), False),
    "at": (_scalar("timestamp"), False),
    "blob": (_scalar("binary"), False),
    "flag": (_scalar("boolean"), False),
    "dims": ({"kind": "record", "name": "Dims"}, False),
}

INPUTS: list[tuple[str, dict[str, Any], str]] = [
    ("code", _scalar("string"), "one"),
    ("count", _scalar("integer"), "optional"),
    ("amount", _scalar("decimal"), "optional"),
    ("at", _scalar("timestamp"), "optional"),
    ("blob", _scalar("binary"), "optional"),
    ("flag", _scalar("boolean"), "optional"),
    ("tags", _scalar("string"), "many"),
    ("prior", {"kind": "ref", "type": "Sample"}, "one"),
    ("dims", {"kind": "record", "name": "Dims"}, "optional"),
]


def document() -> str:
    elements = [
        *_record("Sample", SAMPLE_FIELDS, key="code"),
        *_record("Tag", {"code": (_scalar("string"), True)}, key="code"),
        *_record(
            "Dims",
            {"width": (_scalar("integer"), True), "depth": (_scalar("decimal"), False)},
            key=None,
        ),
    ]
    props = {p: {"input": p} for p in SAMPLE_FIELDS if p != "code"}
    record = {
        "id": "Record",
        "description": "Record a sample with every kind of input",
        "inputs": [{"name": n, "type": t, "cardinality": c} for n, t, c in INPUTS],
        "preconditions": [
            {"id": "prior_exists", "reason": "no such prior sample", "predicate": {"op": "exists", "ref": {"input": "prior"}}}
        ],
        "effects": [
            {"op": "create", "as": "s", "type": "Sample", "key": {"input": "code"}, "properties": props},
            {"op": "link", "type": "follows", "source": {"alias": "s"}, "target": {"input": "prior"}},
            {"op": "foreach", "over": "tags", "body": [{"op": "create", "type": "Tag", "key": {"item": True}}]},
        ],
    }  # fmt: skip
    doc = {
        "umf": "0.10.0",
        "id": "lab",
        "vocabularies": {"umf.ddd": {"version": "0.1.0"}},
        "extensions": {},
        "modules": [
            {
                "id": MODULE,
                "namespace": MODULE,
                "extensions": {
                    "umf.ddd": {"kind": "bounded-context", "terms": []},
                },
                "elements": elements,
                "relationships": [
                    {
                        "id": "sample-follows",
                        "name": "follows",
                        "source": [{"module": MODULE, "element": "Sample"}],
                        "target": [{"module": MODULE, "element": "Sample", "key": "identity"}],
                        "sourceMultiplicity": {"min": 0, "max": "*"},
                        "targetMultiplicity": {"min": 0, "max": "*"},
                        "targetLifecycle": "independent",
                        "directed": True,
                        "inverse": "followedBy",
                    }
                ],
                "actions": [record],
            }
        ],
    }
    return json.dumps(doc)


def lab_sandbox() -> Sandbox:
    """The sandbox with `lab` registered beside `catalog` and one sample, `s0`, to follow."""
    box = Sandbox().seed().load(document())
    root = box.arras.session(box.people["root"])
    root.import_records(
        MODULE, [{"type": "Sample", "key": "s0", "properties": {}}], load_id="lab-seed"
    )
    box.replica.feed()
    return box


VALID = {
    "code": "s1",
    "count": "9007199254740993",
    "amount": "12.50",
    "at": "2026-10-09T14:02:11.5+02:00",
    "blob": "aGk=",
    "flag": True,
    "tags": ["t-a", "t-b"],
    "prior": "s0",
    "dims": {"width": "3", "depth": "0.25"},
}
