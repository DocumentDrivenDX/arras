# SPDX-License-Identifier: MIT OR Apache-2.0
"""The entity read Arras writes for the console and the search: the statement and its rows.

A whole entity is `alias.*` (the declared fields and the facts a backend appends) with each
relationship's keys through Weft's `RELATED_KEYS`. A backend may append a column per relationship to
`alias.*` (Truss does, whether asked or not) and refuses a second output of that name
(`WFT-OUTPUT-NAME`), so no statement names a relationship's keys by the relationship's own name;
`entity_rows` gives the rows back under it.
"""

from __future__ import annotations

from dataclasses import replace as dc_replace
from typing import Any

from arras.model import EntityTypeInfo, ModuleInfo
from arras.names import quoted, quoted_type
from arras.types import Rows

MAX_RELATIONSHIP_KEYS = 100
FACT_FIELDS = frozenset({"version", "createdBy", "createdAt", "updatedBy", "updatedAt"})


def relationships_of(mod: ModuleInfo, t: EntityTypeInfo) -> list[tuple[str, str]]:
    """(field name, the type on the other end) for every relationship the type takes part in."""
    out: list[tuple[str, str]] = []
    for r in mod.relationships:
        if t.name in r.source:
            out.append((r.name, r.target[0] if r.target else ""))
        if r.inverse and t.name in r.target:
            out.append((r.inverse, r.source[0] if r.source else ""))
    return out


def keys_column(relationship: str) -> str:
    """The output name of a relationship's keys in a whole-entity row Arras asks for. It is never
    the relationship's own name: a backend that appends a relationship's column to `alias.*` (Truss
    does, whether or not asked) refuses a second output of that name (`WFT-OUTPUT-NAME`), and a name
    cannot begin with `_`, so this one collides with no property, relationship or fact."""
    return "_" + relationship


def _alias(relationship: str) -> str:
    quoted(relationship)  # a name the rules admit, so nothing else is written into a statement
    return '"' + keys_column(relationship) + '"'


def related_keys_select(mod: ModuleInfo, t: EntityTypeInfo, count: int) -> str:
    """`, RELATED_KEYS(x.rel, count) AS _rel` for each relationship of `t`, to follow `x.*`."""
    return "".join(
        f", RELATED_KEYS(x.{quoted(n)}, {count}) AS {_alias(n)}"
        for n, _ in relationships_of(mod, t)
    )


def entity_rows(mod: ModuleInfo, t: EntityTypeInfo, rows: Rows) -> Rows:
    """`rows` of an `_entity_sql` read with each relationship's keys under the relationship's name
    (the row a client of the library sees), whether the backend appended a column of that name too
    (Truss: the same keys) or not."""
    names = {keys_column(n): n for n, _ in relationships_of(mod, t)}
    if not any(c.name in names for c in rows.columns):
        return rows
    renamed = tuple(
        dc_replace(c, name=names.get(c.name, c.name))
        for c in rows.columns
        if c.name in names or c.name not in names.values()
    )
    out = tuple(
        {
            **{k: v for k, v in r.items() if k not in names},
            **{names[k]: v for k, v in r.items() if k in names},
        }
        for r in rows.rows
    )
    return dc_replace(rows, columns=renamed, rows=out)


def selected_fields(info: Any, *, under: str | None = None) -> frozenset[str] | None:
    """The names of the fields a request selects on the entity it asks for (`under` names the field
    that holds the entities, `items` of a page), or `None` when that cannot be told (the whole
    entity is read then). Fragments are followed; an alias is ignored: the field's own name is read."""
    try:
        nodes = list(info.field_nodes)
        if under is not None:
            nodes = [
                f
                for n in nodes
                for f in (n.selection_set.selections if n.selection_set else ())
                if getattr(f, "name", None) is not None and f.name.value == under
            ]
        names: set[str] = set()
        seen: set[str] = set()

        def walk(selection_set: Any) -> None:
            for sel in selection_set.selections if selection_set else ():
                kind = type(sel).__name__
                if kind == "FieldNode":
                    names.add(sel.name.value)
                elif kind == "InlineFragmentNode":
                    walk(sel.selection_set)
                elif kind == "FragmentSpreadNode" and sel.name.value not in seen:
                    seen.add(sel.name.value)
                    walk(info.fragments[sel.name.value].selection_set)

        for n in nodes:
            walk(n.selection_set)
        return frozenset(names)
    except (AttributeError, KeyError):
        return None


def entity_sql(
    mod: ModuleInfo,
    t: EntityTypeInfo,
    where: str,
    limit: int,
    wanted: frozenset[str] | None = None,
) -> str:
    """The entity with each relationship's keys through Weft's `RELATED_KEYS`, in key order. A list
    asks for one row more than its `limit` cap, so the cap cutting the result is what `truncated`
    reports.

    The whole entity (`x.*`: the declared fields and the facts the backend appends) is read when the
    request selects a fact (`version`, an attribution field) or `wanted` is `None`. Otherwise only
    the key, the selected properties and the selected relationships are projected: a backend that
    appends the facts pays for them per row (Truss, about a thousand times the cost of the projection
    on its `complete-entity` read: truss-requirements R17.8)."""
    order = f"ORDER BY x.{quoted(t.key)} LIMIT {limit}"
    from_ = f"FROM {quoted_type(t.name)} x{where} {order}"
    if wanted is None or wanted & FACT_FIELDS:
        return f"SELECT x.*{related_keys_select(mod, t, MAX_RELATIONSHIP_KEYS)} {from_}"
    columns = [t.key, *(p.name for p in t.properties if p.name != t.key and p.name in wanted)]
    projection = ", ".join(f"x.{quoted(c)}" for c in columns)
    chosen = [r for r in relationships_of(mod, t) if r[0] in wanted]
    keys = "".join(
        f", RELATED_KEYS(x.{quoted(n)}, {MAX_RELATIONSHIP_KEYS}) AS {_alias(n)}" for n, _ in chosen
    )
    return f"SELECT {projection}{keys} {from_}"
