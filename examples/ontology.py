# SPDX-License-Identifier: MIT OR Apache-2.0
"""Shared generator for the example modules built from a short description (northwind, pizza).

A spec says: the module's id, its types (fields as `(name, scalar, required)`, the first is the key),
its relationships, their views and the seed. `document(spec)` is the UMF document; `main(spec, here)`
writes or checks `<module>.umf.json` and `seed.json` beside the example. The catalog example keeps
its own builder; this one is generic so a new ontology is a spec, not code.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

Json = dict[str, Any]
VIEW = "arras.view"
FACETS: dict[str, Json] = {
    "decimal": {"precision": 12, "scale": 2},
    "integer": {"integerWidth": {"bits": 64, "signed": True}},
}


def _scalar(t: str) -> Json:
    return {"kind": "scalar", "name": t}


def _lower(s: str) -> str:
    return s[0].lower() + s[1:]


def _cap(s: str) -> str:
    return s[0].upper() + s[1:]


def _record(spec: Json, name: str) -> Json:
    fields = spec["types"][name]
    return {
        "id": name,
        "kind": "record",
        "name": name,
        "members": [{"module": spec["module"], "element": f"{name}.{f}"} for f, _, _ in fields],
        "extensions": {
            "umf.ddd": {
                "kind": "entity",
                "fields": {
                    f: {"type": _scalar(t), "cardinality": "one" if r else "optional"}
                    for f, t, r in fields
                },
                "identity": {"fields": [fields[0][0]], "scope": "context"},
            },
            VIEW: spec["records"][name],
        },
        "keys": [
            {
                "id": "identity",
                "name": "Identity",
                "fields": [{"module": spec["module"], "element": f"{name}.{fields[0][0]}"}],
                "primary": True,
            }
        ],
    }


def _field(spec: Json, name: str, field: str, scalar: str, required: bool) -> Json:
    el: Json = {
        "id": f"{name}.{field}",
        "kind": "field",
        "name": field,
        "nullability": "required" if required else "absent-allowed",
        "cardinality": "one",
        "scalarType": scalar,
        "extensions": {},
    }
    if scalar in FACETS:
        el["facets"] = FACETS[scalar]
    if f"{name}.{field}" in spec["fields"]:
        el["extensions"][VIEW] = spec["fields"][f"{name}.{field}"]
    return el


def _relationship(spec: Json, r: tuple[str, str, str, str, bool]) -> Json:
    name, source, target, inverse, _ = r
    return {
        "id": f"{source}-{name}".lower(),
        "name": name,
        "source": [{"module": spec["module"], "element": source}],
        "target": [{"module": spec["module"], "element": target, "key": "identity"}],
        "sourceMultiplicity": {"min": 0, "max": "*"},
        "targetMultiplicity": {"min": 0, "max": "*"},
        "targetLifecycle": "independent",
        "directed": True,
        "inverse": inverse,
        "extensions": {VIEW: spec["relationshipViews"][name]},
    }


def _inputs(fields: list[tuple[str, str, bool]], refs: list[tuple[str, str]] = ()) -> list[Json]:  # type: ignore[assignment]
    return [
        {"name": f, "type": _scalar(t), "cardinality": "one" if r else "optional"}
        for f, t, r in fields
    ] + [{"name": n, "type": {"kind": "ref", "type": t}, "cardinality": "one"} for n, t in refs]


def _exists(name: str) -> Json:
    return {
        "id": f"{name}_exists",
        "reason": f"no such {name}",
        "predicate": {"op": "exists", "ref": {"input": name}},
    }


def _link(rel: str, source: Json, target: str, op: str = "link") -> Json:
    return {"op": op, "type": rel, "source": source, "target": {"input": target}}


def _update(name: str, action: str, description: str, changed: list[tuple[str, str, bool]]) -> Json:
    """An action that changes some fields of one record of type `name`."""
    ref = _lower(name)
    return {
        "id": action,
        "description": description,
        "inputs": _inputs(changed, [(ref, name)]),
        "preconditions": [_exists(ref)],
        "effects": [
            {
                "op": "update",
                "refType": name,
                "key": {"input": ref},
                "properties": {f: {"input": f} for f, _, _ in changed},
            }
        ],
    }


def _actions(spec: Json) -> list[Json]:
    out: list[Json] = []
    rels: list[tuple[str, str, str, str, bool]] = spec["relationships"]
    skip: set[str] = set(spec.get("skip", []))
    for name, fields in spec["types"].items():
        body = fields[1:]
        links = [r for r in rels if r[1] == name and r[4]]
        if f"Add{name}" not in skip:
            out.append(
                {
                    "id": f"Add{name}",
                    "description": f"Add {_lower(name)}",
                    "inputs": _inputs(fields, [(r[0], r[2]) for r in links]),
                    "preconditions": [
                        {
                            "id": "fresh",
                            "reason": f"a {_lower(name)} with that code exists",
                            "predicate": {
                                "op": "absent",
                                "type": name,
                                "key": {"input": fields[0][0]},
                            },
                        },
                        *(_exists(r[0]) for r in links),
                    ],
                    "effects": [
                        {
                            "op": "create",
                            "as": "new",
                            "type": name,
                            "key": {"input": fields[0][0]},
                            "properties": {f: {"input": f} for f, _, _ in body},
                        },
                        *(_link(r[0], {"alias": "new"}, r[0]) for r in links),
                    ],
                }
            )
        ref = _lower(name)

        optional = [(f, t, False) for f, t, r in body if not r]
        if optional and f"Correct{name}" not in skip:
            out.append(_update(name, f"Correct{name}", f"Correct the details of {ref}", optional))
        required = [(f, t, True) for f, t, r in body if r]
        if len(required) > 1:
            # Several required properties can only change together: one action, so a form.
            if f"Update{name}" not in skip:
                out.append(_update(name, f"Update{name}", f"Update {ref}", required))
        for f, t, _ in required if len(required) == 1 else []:
            action = f"Rename{name}" if f == "name" else f"Change{name}{_cap(f)}"
            if action not in skip:
                out.append(_update(name, action, f"Change the {f} of {ref}", [(f, t, True)]))
        if name in spec.get("retire", []):
            out.append(
                {
                    "id": f"Retire{name}",
                    "description": f"Remove {ref} and its links",
                    "inputs": _inputs([], [(ref, name)]),
                    "preconditions": [_exists(ref)],
                    "effects": [{"op": "delete", "refType": name, "key": {"input": ref}}],
                }
            )
    for rel, source, target, _, _ in rels:
        if rel not in spec.get("mutable", []):
            continue
        for verb, op in (("Link", "link"), ("Unlink", "unlink")):
            s, t = _lower(source), rel
            out.append(
                {
                    "id": f"{verb}{source}{_cap(rel)}",
                    "description": f"{verb} {_lower(source)} {rel} {_lower(target)}",
                    "inputs": _inputs([], [(s, source), (t, target)]),
                    "preconditions": [_exists(s), _exists(t)],
                    "effects": [_link(rel, {"input": s}, t, op)],
                }
            )
    return out


def document(spec: Json) -> Json:
    elements: list[Json] = []
    for name, fields in spec["types"].items():
        elements.append(_record(spec, name))
        elements.extend(_field(spec, name, f, t, r) for f, t, r in fields)
    return {
        "umf": "0.10.0",
        "id": spec["id"],
        "vocabularies": {"umf.ddd": {"version": "0.1.0"}, VIEW: {"version": "0.1.0"}},
        "extensions": {},
        "modules": [
            {
                "id": spec["module"],
                "namespace": spec["module"],
                "extensions": {
                    "umf.ddd": {"kind": "bounded-context", "terms": []},
                    VIEW: spec["view"],
                },
                "elements": elements,
                "relationships": [_relationship(spec, r) for r in spec["relationships"]],
                "actions": _actions(spec),
            }
        ],
    }


def seed(spec: Json) -> list[Json]:
    return [{"action": f"{spec['module']}.{a}", "inputs": inputs} for a, inputs in spec["seed"]]


def main(spec: Json, here: Path, argv: list[str]) -> int:
    files = {
        here / f"{spec['module']}.umf.json": json.dumps(document(spec), indent=2) + "\n",
        here / "seed.json": json.dumps(seed(spec), indent=2) + "\n",
    }
    if "--check" in argv:
        drifted = [p.name for p, t in files.items() if p.read_text(encoding="utf-8") != t]
        if drifted:
            print(
                f"{', '.join(drifted)} drifted from build.py: run it without --check",
                file=sys.stderr,
            )
        return 1 if drifted else 0
    for p, t in files.items():
        p.write_text(t, encoding="utf-8", newline="\n")
        print(f"wrote {p}")
    return 0
