# SPDX-License-Identifier: MIT OR Apache-2.0
"""Importing records into a fake authority (CONTRACT-003, `import_records`)."""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from arras.actions import KEY_VALUE, Ref
from arras.fakes_domain import Domains, stored_props
from arras.fakes_state import Entity, State, canonical, deep_copy
from arras.inputs import parse_timestamp
from arras.model import ModuleInfo, PropertyInfo
from arras.results import Rejection


def _timestamp(v: object) -> datetime:
    """An ISO 8601 timestamp that names its offset: a time with none is not a moment."""
    if isinstance(v, datetime):
        at = v
    elif isinstance(v, str):
        parsed = parse_timestamp(v)  # RFC 3339, as every other way in
        if parsed is None:
            raise ValueError("not an ISO timestamp with an offset")
        at = parsed
    else:
        raise ValueError("not an ISO timestamp")
    if at.tzinfo is None:
        raise ValueError("not an ISO timestamp with an offset")
    return at


def _decimal(v: object) -> Decimal:
    if isinstance(v, bool) or not isinstance(v, int | str | Decimal):
        raise ValueError("not a decimal")
    try:
        d = Decimal(v)
    except InvalidOperation:
        raise ValueError("not a decimal") from None
    if not d.is_finite():
        raise ValueError("not a finite decimal")
    return d


def _binary(v: object) -> bytes:
    if isinstance(v, bytes):
        return v
    if not isinstance(v, str):
        raise ValueError("not base64 text")
    try:
        return base64.b64decode(v, validate=True)
    except ValueError:
        raise ValueError("not base64 text") from None


def _is_string(v: object) -> str:
    if not isinstance(v, str):
        raise ValueError("not a string")
    return v


def _is_integer(v: object) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError("not an integer")
    return v


def _is_boolean(v: object) -> bool:
    if not isinstance(v, bool):
        raise ValueError("not a boolean")
    return v


_READERS: dict[str, Callable[[object], Any]] = {
    "string": _is_string,
    "integer": _is_integer,
    "decimal": _decimal,
    "boolean": _is_boolean,
    "timestamp": _timestamp,
    "binary": _binary,
}


def _coerce(p: PropertyInfo, v: Any) -> Any:
    """A value read from a file as its field holds it: a decimal string is a `Decimal`, an ISO
    string a `datetime`, base64 text bytes. `ValueError` when the value is not of the declared
    scalar type (an object in a string field, a text timestamp with no offset)."""
    read = _READERS.get(p.type)
    if v is None or not p.scalar or read is None:
        return v
    if p.cardinality == "many":
        if not isinstance(v, list):
            raise ValueError("not a list")
        return [read(x) for x in cast(list[object], v)]
    return read(v)


def _read(kinds: Mapping[str, PropertyInfo], props: Mapping[str, Any]) -> dict[str, Any]:
    """Each property read as its field's type; `ValueError((name, reason))` for the first that is not."""
    out: dict[str, Any] = {}
    for k, v in props.items():
        try:
            out[k] = _coerce(kinds[k], v)
        except ValueError as e:
            raise ValueError(k, str(e)) from None
    return out


class ImportRecords:
    """The two record kinds a load may hold; `MemoryStore.import_records` applies them."""

    def _import_entity(
        self,
        work: State,
        mod: ModuleInfo,
        r: Mapping[str, object],
        load_id: str,
        by: str,
        now: datetime,
        found: Domains | None = None,
    ) -> tuple[int, int, list[Rejection]]:
        key = str(r.get("key", ""))
        ref = Ref(f"{mod.name}.{r['type']}", key)
        t = mod.entity_type(str(r["type"]))
        props = cast(Mapping[str, Any], r.get("properties") or {})
        if t is None or not KEY_VALUE.fullmatch(key):
            return 0, 0, [Rejection("entity", str(ref), "unknown type or not a key")]
        declared = {p.name for p in t.properties}
        missing = [
            p.name for p in t.properties if p.required and p.name != t.key and p.name not in props
        ]
        extra = set(props) - declared
        if missing or extra:
            return (
                0,
                0,
                [Rejection("entity", str(ref), f"missing {missing}, undeclared {sorted(extra)}")],
            )
        if ref in work.entities or ref in work.tombstones:
            return 0, 1, []
        kinds = {p.name: p for p in t.properties}
        try:  # a value is read as its field's type, then a number is held at its domain
            props = _read(kinds, props)
            props = stored_props(found or {}, mod.name, t.local_name, props)
        except ValueError as e:
            why = f"{e.args[0]}: {e.args[1]}" if len(e.args) > 1 else str(e)
            return 0, 0, [Rejection("entity", str(ref), why)]
        author, at = r.get("original_author"), r.get("original_at")
        if at is not None:
            try:
                at = _timestamp(at)
            except ValueError as e:
                return 0, 0, [Rejection("entity", str(ref), f"original_at: {e}")]
        work.entities[ref] = Entity(
            {**deep_copy(dict(props)), t.key: key},
            1,
            by,
            now,
            by,
            now,
            str(author) if author is not None else None,
            at,
            load_id,
        )
        return 1, 0, []

    def _import_relation(
        self, work: State, mod: ModuleInfo, r: Mapping[str, object]
    ) -> tuple[int, int, list[Rejection]]:
        name, s, t = str(r.get("relationship")), str(r.get("source")), str(r.get("target"))
        ident = f"{name}/{s}/{t}"
        found = canonical(mod, name)
        if found is None:
            return 0, 0, [Rejection("record", ident, "neither an entity nor a relationship")]
        rel, inverse = found
        if inverse:
            s, t = t, s
        src = next((x for x in work.entities if x.key == s and x.type in rel.source), None)
        tgt = next((x for x in work.entities if x.key == t and x.type in rel.target), None)
        if src is None or tgt is None:
            return (
                0,
                0,
                [Rejection("relationship", ident, "an endpoint is missing or of the wrong type")],
            )
        triple = (rel.name, src, tgt)
        if triple in work.relations:
            return 0, 1, []
        work.relations.add(triple)
        return 1, 0, []
