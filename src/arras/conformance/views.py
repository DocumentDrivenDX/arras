# SPDX-License-Identifier: MIT OR Apache-2.0
"""The `arras.view` cases (CONTRACT-010, section A): what registration refuses and what a view
resolves to, as data (`view_cases.json`) in the corpus's style.

These are the interface's own checks, not a backend's, so they run against `umf.parse_module` and
`view.resolve` rather than a `Harness`. A case patches the corpus module's document (`set` writes a
value at a path of keys and indexes, `remove` deletes one) and states either that it registers and
what a type resolves to, or exactly which `(code, path)` faults it is refused with.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, cast

from arras.conformance import Result
from arras.errors import Invalid
from arras.umf import parse_module
from arras.view import declared_from_text, resolve


def load_view_cases() -> dict[str, Any]:
    root = resources.files("arras.conformance")
    cases = json.loads(root.joinpath("view_cases.json").read_text())
    cases["_document"] = json.loads(root.joinpath(cases["module"]).read_text())
    return cases


def _patched(document: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    doc = json.loads(json.dumps(document))
    for step in steps:
        *parents, last = step["at"]
        node: Any = doc
        for key in parents:
            node = (
                cast(dict[str, Any], node).setdefault(key, {})
                if isinstance(node, dict)
                else node[key]
            )
        if step.get("remove"):
            del node[last]
        else:
            node[last] = step["value"]
    return doc


def _faults(expect: dict[str, Any], found: list[tuple[str, str]]) -> str | None:
    want = sorted((v["code"], v["path"]) for v in expect["violations"])
    return None if want == sorted(found) else f"refused with {sorted(found)}, expected {want}"


def _differs(want: dict[str, Any], got: dict[str, Any], what: str) -> str | None:
    for key, value in want.items():
        if got[key] != value:
            return f"{what}.{key}: {got[key]!r} != {value!r}"
    return None


def _resolution(expect: dict[str, Any], text: str) -> str | None:
    mod = parse_module(text)
    resolved = resolve(mod, declared_from_text(text, mod))
    if "module" in expect:
        got = {"title": resolved.module.title, "description": resolved.module.description}
        if (bad := _differs(expect["module"], got, "module")) is not None:
            return bad
    for name, want in expect.get("types", {}).items():
        view = resolved.view(name)
        got = {
            "declared": view.declared,
            "label": view.label,
            "pluralLabel": view.plural_label,
            "icon": view.icon,
            "tone": view.tone,
            "title": view.title,
            "summary": view.summary,
            "search": list(view.search),
            "sections": [
                {"label": s.label, "properties": list(s.properties), "collapsed": s.collapsed}
                for s in view.sections
            ],
        }
        if (bad := _differs(want, got, name)) is not None:
            return bad
    return None


def run_case(case: dict[str, Any], document: dict[str, Any]) -> Result:
    text = json.dumps(_patched(document, case["set"]))
    expect = case["expect"]
    try:
        if expect.get("ok"):
            failed = _resolution(expect, text)
        else:
            parse_module(text)
            failed = "registered, but a refusal was expected"
    except Invalid as e:
        if expect.get("ok"):
            failed = f"refused: {e}"
        else:
            failed = _faults(expect, [(v.code, v.path) for v in e.violations])
    return Result(case["id"], "passed" if failed is None else "failed", failed or "")


def run_view_cases() -> list[Result]:
    """Every case, each on a fresh copy of the corpus module's document."""
    cases = load_view_cases()
    return [run_case(c, cases["_document"]) for c in cases["cases"]]
