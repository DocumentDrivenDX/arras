# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The tool list generated from the registry, and the wire shapes of action inputs (CONTRACT-007)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from arras.actions import ActionInfo, InputSpec
from arras.inputs import convert_inputs, to_python
from arras.model import ModuleInfo

__all__ = ["convert_inputs", "to_python"]

FIXED = ("describe", "query", "validate_action")
MAX_BATCH = 100
_INT_53 = 2**53

STATEMENT = (
    "Name the module the statement reads in module; the statement is one read-only Weft SQL "
    "statement (DocumentDrivenDX/weft) over that module's types, with :name markers bound from "
    "params. The serving backend compiles it, and what it serves is what its declared Weft profiles "
    "admit (a refused construct comes back unsupported, saying what is supported). Name types as "
    "module.Type; a relationship's keys are RELATED_KEYS(alias.relationship, n) and a relationship "
    "predicate is HAS_RELATED(alias.relationship, KEY(:key)). Page with ORDER BY the key, LIMIT and "
    "a keyset predicate (alias.key > :last); truncated says the limit or the answer budget cut the "
    "result. consistency is 'latest' (the record store) or 'bulk' (possibly a replica); at_least is "
    "a receipt's token."
)


def snake(name: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


@dataclass(frozen=True)
class ActionTool:
    tool: str
    action: ActionInfo
    module: ModuleInfo

    @property
    def destructive(self) -> bool:
        """Any delete or unlink, or a handler: its effects are not known until it runs."""
        return self.action.handler is not None or any(_destructive(e) for e in self.action.effects)


def _destructive(e: Any) -> bool:
    return e.op in ("delete", "unlink") or any(_destructive(b) for b in e.body)


def action_tools(modules: list[ModuleInfo]) -> list[ActionTool]:
    """One tool per declared action, `<module>_<snake_action>`; a collision gets a suffix."""
    taken: set[str] = set(FIXED)
    out: list[ActionTool] = []
    for m in modules:
        for a in m.actions:
            base = f"{m.name}_{snake(a.name.split('.', 1)[1])}"
            name, n = base, 1
            while name in taken:
                n += 1
                name = f"{base}_{n}"
            taken.add(name)
            out.append(ActionTool(name, a, m))
    return out


# -- JSON Schema from the action's input types ---------------------------------------------

_SCALAR_SCHEMAS: dict[str, dict[str, Any]] = {
    "string": {"type": "string"},
    "boolean": {"type": "boolean"},
    # an integer as a JSON integer when it fits 53 bits, otherwise as a decimal string
    "integer": {
        "oneOf": [
            {"type": "integer", "minimum": -(_INT_53 - 1), "maximum": _INT_53 - 1},
            {"type": "string", "pattern": r"^-?[0-9]+$"},
        ]
    },
    "decimal": {
        "type": "string",
        "pattern": r"^-?[0-9]+(\.[0-9]+)?$",
        "description": "a decimal as text",
    },
    "timestamp": {
        "type": "string",
        "format": "date-time",
        "description": "RFC 3339 with an offset",
    },
    "binary": {"type": "string", "contentEncoding": "base64"},
}


def input_schema(spec: InputSpec, module: ModuleInfo) -> dict[str, Any]:
    if spec.kind == "scalar":
        base = dict(_SCALAR_SCHEMAS[spec.type])
    elif spec.kind == "ref":
        base = {"type": "string", "description": f"the key of a {spec.type}"}
    else:
        vt = next((v for v in module.value_types if v.name == f"{module.name}.{spec.type}"), None)
        props = {
            p.name: input_schema(
                InputSpec(p.name, p.type, "scalar" if p.scalar else "record", p.cardinality), module
            )
            for p in (vt.properties if vt else ())
        }
        req = [p.name for p in (vt.properties if vt else ()) if p.required]
        base = {
            "type": "object",
            "properties": props,
            "required": req,
            "additionalProperties": False,
        }
    return {"type": "array", "items": base} if spec.cardinality == "many" else base


def inputs_schema(action: ActionInfo, module: ModuleInfo) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {s.name: input_schema(s, module) for s in action.inputs},
        "required": [s.name for s in action.inputs if s.cardinality == "one"],
        "additionalProperties": False,
    }


def action_tool_schema(t: ActionTool) -> dict[str, Any]:
    one = inputs_schema(t.action, t.module)
    return {
        "type": "object",
        "properties": {
            "inputs": one,
            "items": {"type": "array", "minItems": 1, "maxItems": MAX_BATCH, "items": one},
            "atomic": {"type": "boolean"},
            "stop_on_error": {"type": "boolean"},
            "idempotency_key": {"type": "string"},
        },
        "additionalProperties": False,  # exactly one of inputs or items: checked on the call
    }
