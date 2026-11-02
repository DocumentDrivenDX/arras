# SPDX-License-Identifier: MIT OR Apache-2.0
"""Validation for the explicit, bounded legacy-read alias tuples."""

from __future__ import annotations

import re
from typing import cast

_NAME = re.compile(r"[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+")


def validate_alias_tuple(value: object, field: str, canonical: str) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise ValueError(f"{field}: a tuple of at most 16 names")
    aliases = cast(tuple[object, ...], value)
    if len(aliases) > 16:
        raise ValueError(f"{field}: a tuple of at most 16 names")
    seen: set[str] = set()
    for candidate in aliases:
        if type(candidate) is not str:
            raise ValueError(f"{field}: invalid, reserved or duplicate alias")
        name = candidate
        if (
            not 1 <= len(name) <= 64
            or not name.isascii()
            or not _NAME.fullmatch(name)
            or name == canonical
            or name.startswith(("arras.", "umf."))
            or name in seen
        ):
            raise ValueError(f"{field}: invalid, reserved or duplicate alias")
        seen.add(name)
    return cast(tuple[str, ...], aliases)


def validate_alias_policy(view: object, graph: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    selected_view = validate_alias_tuple(view, "view_vocabulary_aliases", "arras.view")
    selected_graph = validate_alias_tuple(graph, "graph_format_aliases", "arras.graph")
    if set(selected_view) & set(selected_graph):
        raise ValueError("view_vocabulary_aliases/graph_format_aliases: aliases must not overlap")
    return selected_view, selected_graph
