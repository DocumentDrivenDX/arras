# SPDX-License-Identifier: MIT OR Apache-2.0
"""The template grammar of CONTRACT-010 (`{name}`, `[` optional group `]`, escapes): its parse and its text.

Split from `arras.view`, which re-exports every name here. A template is text, never markup.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from typing import Any, cast

# -- templates ---------------------------------------------------------------------------------


class TemplateError(ValueError):
    """A template that is malformed."""


@dataclass(frozen=True)
class Placeholder:
    name: str


@dataclass(frozen=True)
class OptionalGroup:
    """`[ ... ]`: shown only if every placeholder inside it has a value."""

    nodes: tuple[Node, ...]


Node = str | Placeholder | OptionalGroup
Template = tuple[Node, ...]

_ESCAPABLE = "{}[]\\"
_PLACEHOLDER = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


@lru_cache(maxsize=2048)
def parse_template(text: str) -> Template:
    """The template grammar of CONTRACT-010: `{name}`, `[` optional group `]` and escapes
    `\\{ \\} \\[ \\] \\\\`. Raises `TemplateError` for anything unescaped that is not one of those
    forms."""
    nodes, end = _parse(text, 0, nested=False)
    assert end == len(text)
    return nodes


def _parse(text: str, i: int, *, nested: bool) -> tuple[Template, int]:
    nodes: list[Node] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            nodes.append("".join(buf))
            buf.clear()

    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text) and text[i + 1] in _ESCAPABLE:
            buf.append(text[i + 1])
            i += 2
        elif c == "{":
            end = text.find("}", i)
            name = text[i + 1 : end] if end > 0 else ""
            if not _PLACEHOLDER.fullmatch(name):
                raise TemplateError("a { starts a {name} placeholder; write \\{ for a brace")
            flush()
            nodes.append(Placeholder(name))
            i = end + 1
        elif c == "[":
            flush()
            inner, i = _parse(text, i + 1, nested=True)
            nodes.append(OptionalGroup(inner))
        elif c == "]":
            if not nested:
                raise TemplateError("a ] closes no [; write \\] for a bracket")
            flush()
            return tuple(nodes), i + 1
        elif c == "}":
            raise TemplateError("a } closes no {; write \\} for a brace")
        else:
            buf.append(c)
            i += 1
    if nested:
        raise TemplateError("a [ is never closed; write \\[ for a bracket")
    flush()
    return tuple(nodes), i


def placeholders(template: str | Template) -> list[str]:
    """The property names a template names, in order of first appearance."""
    nodes = parse_template(template) if isinstance(template, str) else template
    found: list[str] = []
    for n in nodes:
        names = (
            [n.name]
            if isinstance(n, Placeholder)
            else placeholders(n.nodes)
            if isinstance(n, OptionalGroup)
            else []
        )
        found.extend(x for x in names if x not in found)
    return found


def as_text(value: Any) -> str:
    """A property's value as the text a template shows."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return ", ".join(as_text(v) for v in cast(Sequence[Any], value))
    return str(value)


def _eval(nodes: Template, row: Mapping[str, Any]) -> tuple[str, bool]:
    """The text and whether every placeholder in it had a value."""
    out: list[str] = []
    filled = True
    for n in nodes:
        if isinstance(n, str):
            out.append(n)
        elif isinstance(n, Placeholder):
            text = as_text(row.get(n.name))
            if not text.strip():
                filled = False
            else:
                out.append(text)
        else:
            text, ok = _eval(n.nodes, row)
            filled = filled and ok
            if ok:
                out.append(text)
    return "".join(out), filled


def evaluate(template: str | Template, row: Mapping[str, Any]) -> str:
    """The template over an entity's properties. A placeholder with no value, and an optional
    group with any, produce no text; the result is text, never markup."""
    nodes = parse_template(template) if isinstance(template, str) else template
    return _eval(nodes, row)[0]
