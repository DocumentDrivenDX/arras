# SPDX-License-Identifier: MIT OR Apache-2.0
"""The graph file: a module's graph as the records `import_records` takes (CONTRACT-003, Export).

It is meant to live in version control until a database holds the graph, and to ship as a known-good
fixture, so it is the same bytes for the same graph: records in a stable order, keys sorted, two-space
indent, a final newline, and nothing that changes between runs (no time, no person, no revision). The
interface's Export control writes the same bytes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from arras.core import Ontology

FORMAT = "arras.graph"
VERSION = 1
PAGE = 500


@dataclass(frozen=True)
class GraphFile:
    module: str
    records: tuple[Mapping[str, Any], ...]
    #: False when the viewer could not read every type: the file is not the whole graph. A file
    #: read without a `complete: true` is not known to be whole.
    complete: bool = True
    omitted: tuple[str, ...] = ()


def dumps(graph: GraphFile) -> str:
    """The file's text: canonical, so exporting the same graph twice gives the same bytes.

    A float is not written: a decimal travels as a string (see `loads`), so a `ValueError` names the
    path of the first float, with the message `loads` gives for the same number, and no file is made
    that `loads` would refuse.
    """
    body: dict[str, Any] = {
        "format": FORMAT,
        "version": VERSION,
        "module": graph.module,
        "complete": graph.complete,
        "records": [dict(r) for r in graph.records],
    }
    if graph.omitted:
        body["omitted"] = list(graph.omitted)
    _refuse_not_integer(body)
    return json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


@dataclass(frozen=True)
class _NotInteger:
    """A number the file wrote that is not an integer, kept as the text it was written as."""

    token: str


def _first_not_integer(value: Any, path: str = "") -> tuple[str, str] | None:
    """The path and text of the first such number, in the order the file has them."""
    if isinstance(value, _NotInteger):
        return path or "the document", value.token
    if isinstance(
        value, float
    ):  # a value to write, not a number read: json.dumps spells it as the reader would
        return path or "the document", json.dumps(value)
    if isinstance(value, dict):
        for k, v in cast(dict[str, Any], value).items():
            found = _first_not_integer(v, f"{path}.{k}" if path else k)
            if found:
                return found
    elif isinstance(value, list):
        for i, v in enumerate(cast(list[Any], value)):
            found = _first_not_integer(v, f"{path}[{i}]")
            if found:
                return found
    return None


def _refuse_not_integer(value: Any) -> None:
    if (bad := _first_not_integer(value)) is not None:
        raise ValueError(f"{bad[0]}: {bad[1]} is not an integer (a decimal is written as a string)")


def loads(text: str) -> GraphFile:
    """Read a graph file; a `ValueError` says what is wrong with it.

    A number in the file is an integer: a decimal travels as a string, so `1.0`, `1.5`, `1e3` (and
    `NaN`) are refused, naming where they are. The float a language would read from them does not write
    back as the same text in every language.
    """
    try:
        raw: Any = json.loads(text, parse_float=_NotInteger, parse_constant=_NotInteger)
    except json.JSONDecodeError as e:
        raise ValueError(f"not JSON: {e.msg} at line {e.lineno}") from None
    _refuse_not_integer(raw)
    if not isinstance(raw, dict):
        raise ValueError("a graph file is a JSON object")
    body = cast(dict[str, Any], raw)
    if body.get("format") != FORMAT:
        raise ValueError(f'not a graph file: "format" is {FORMAT!r}')
    if body.get("version") != VERSION:
        raise ValueError(f"this release reads graph file version {VERSION}")
    module, records = body.get("module"), body.get("records")
    if not isinstance(module, str) or not module:
        raise ValueError('"module" names the module the records belong to')
    if not isinstance(records, list) or not all(
        isinstance(r, dict) for r in cast(list[Any], records)
    ):
        raise ValueError('"records" is a list of entity and relationship records')
    omitted = cast(list[Any], body.get("omitted") or [])
    return GraphFile(
        module,
        tuple(cast(list[dict[str, Any]], records)),
        body.get("complete") is True,  # a file that does not say it is whole is not known to be
        tuple(str(t) for t in omitted),
    )


def export(o: Ontology, module: str) -> GraphFile:
    """Read the whole of `module` as `o`'s person, a page at a time."""
    records: list[Mapping[str, Any]] = []
    omitted: set[str] = set()
    after: str | None = None
    while True:
        page = o.export_records(module, limit=PAGE, after=after)
        records += page.items
        omitted.update(page.omitted)
        after = page.next_cursor
        if after is None:
            break
    return GraphFile(module, tuple(records), not omitted, tuple(sorted(omitted)))
