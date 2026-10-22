# SPDX-License-Identifier: MIT OR Apache-2.0
"""Legacy Arras reader for a subset of UMF core 0.10.0 (CONTRACT-002).

This reader and its current DDD projection are a legacy Arras subset pending official UMF Python
adoption and qualification (PLAN-ARRAS-INTEGRATION-20261022, A1-A2). UMF is the canonical
authority for metadata validity and meaning. `UMF_VERSION` gates this reader's expected document
shape; it is not a claim that Arras supports or conforms to that UMF release. The reader handles
the shape of `docs/helix/02-design/contracts/examples/catalog.umf.json`, reports violations it
detects, and refuses constructs it does not interpret as `invalid_document`, naming them. The
current projection treats a record as an entity when its `umf.ddd` kind is `entity` and as a
structured value when it is `value-object`.

Not here, because they need a registry or a backend: a placement the host gave naming an
unconfigured backend (`invalid_placement`; a document carries none), `register` on a read-only authority (`read_only_module`), foreign endpoints
(`unreadable_module`, `unknown_type`, and the `unknown_endpoint` policy), names that collide once
GraphQL fields are generated (CONTRACT-006), retired names, and a check that another module does
not name a removed type. Actions are read from the legacy Arras declaration shape handled by
`actions.parse_action`.
"""

from __future__ import annotations

import json
from typing import Any, cast

from arras.actioncheck import check_action
from arras.actions import parse_action
from arras.errors import Invalid, Violation
from arras.model import (
    SCALAR_FAMILIES,
    UNPLACED,
    Cardinality,
    EntityTypeInfo,
    ModuleInfo,
    Multiplicity,
    PropertyInfo,
    RelationshipInfo,
    ValueTypeInfo,
)
from arras.names import MODULE_NAME, check_name
from arras.types import Revision
from arras.view import VOCABULARY as VIEW_VOCABULARY
from arras.view import parse_view

UMF_VERSION = "0.10.0"
_CARDINALITIES: tuple[Cardinality, ...] = ("one", "optional", "many")
_ROOT_KEYS = {"umf", "id", "vocabularies", "extensions", "modules"}
_MODULE_KEYS = {"id", "namespace", "extensions", "elements", "relationships", "actions"}
_VOCABULARIES = {"umf.ddd", VIEW_VOCABULARY}
_RECORD_KINDS = {"entity", "value-object"}

Obj = dict[str, Any]


def _obj(value: Any) -> Obj:
    return cast(Obj, value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _doc(path: str, message: str) -> Violation:
    return Violation(path, "invalid_document", message)


def _no_duplicates(pairs: list[tuple[str, Any]]) -> Obj:
    seen: dict[str, Any] = {}
    for k, v in pairs:
        if k in seen:
            raise ValueError(f"duplicate key {k!r}")
        seen[k] = v
    return seen


def _text(value: Any, path: str, what: str, out: list[Violation]) -> str | None:
    if isinstance(value, str) and value:
        return value
    out.append(_doc(path, f"{what} is missing"))
    return None


class _Names:
    """Names that share one case-folded namespace within a module."""

    def __init__(self, out: list[Violation]) -> None:
        self.out = out
        self.seen: dict[str, str] = {}

    def add(self, name: str, path: str) -> None:
        folded = name.lower()
        if folded in self.seen:
            how = "is declared twice" if self.seen[folded] == name else "differs only by case from"
            other = "" if self.seen[folded] == name else f" {self.seen[folded]!r}"
            self.out.append(Violation(path, "invalid_name", f"{name!r} {how}{other}"))
        else:
            self.seen[folded] = name


def parse_module(document: bytes | str) -> ModuleInfo:
    """Read one UMF module document; raise `Invalid` listing every violation."""
    try:
        raw = json.loads(document, object_pairs_hook=_no_duplicates)
    except ValueError as e:
        raise Invalid([_doc("document", f"not valid JSON: {e}")]) from None
    root = _obj(raw)
    out: list[Violation] = []
    if root.get("umf") != UMF_VERSION:
        out.append(_doc("umf", f"UMF core {UMF_VERSION} is required"))
    for k in root.keys() - _ROOT_KEYS:
        out.append(_doc(k, f"unsupported construct {k!r}"))
    vocabularies = _obj(root.get("vocabularies"))
    for v in vocabularies.keys() - _VOCABULARIES:
        out.append(_doc(f"vocabularies.{v}", f"unsupported vocabulary {v!r}"))
    if "umf.ddd" in vocabularies:
        ddd_vocabulary = vocabularies["umf.ddd"]
        ddd_version = (
            cast(Obj, ddd_vocabulary).get("version") if isinstance(ddd_vocabulary, dict) else None
        )
        if ddd_version != "0.1.0":
            out.append(
                _doc(
                    "vocabularies.umf.ddd.version",
                    "umf.ddd vocabulary version 0.1.0 is required",
                )
            )
    modules = _list(root.get("modules"))
    if len(modules) != 1:
        out.append(_doc("modules", f"a document defines exactly one module, found {len(modules)}"))
        raise Invalid(out)
    mod = _obj(modules[0])
    for k in mod.keys() - _MODULE_KEYS:
        out.append(_doc(f"modules[0].{k}", f"unsupported construct {k!r}"))
    name = mod.get("id")
    if not isinstance(name, str) or not MODULE_NAME.fullmatch(name):
        out.append(
            Violation("modules[0].id", "invalid_name", "a module id is [a-z][a-z0-9_]{0,40}")
        )
        name = str(name)
    declared = _obj(root.get("vocabularies")).keys()
    for ext in _obj(mod.get("extensions")).keys() - (_VOCABULARIES & (declared | {"umf.ddd"})):
        out.append(_doc(f"extensions.{ext}", f"unsupported extension {ext!r}"))
    names = _Names(out)
    entities, values = _records(mod, name, names, out)
    relationships = _relationships(mod, name, entities, names, out)
    actions = tuple(
        a for raw in _list(mod.get("actions")) if (a := parse_action(raw, name, out)) is not None
    )
    info = ModuleInfo(
        name=name,
        placement=UNPLACED,
        revision=Revision(),
        entity_types=tuple(entities.values()),
        relationships=tuple(relationships),
        value_types=tuple(values.values()),
        actions=actions,
    )
    seen_actions = _Names(out)
    for a in actions:
        seen_actions.add(a.name.split(".", 1)[1], f"actions.{a.name}")
        if (v := check_name(a.name.split(".", 1)[1], f"actions.{a.name}")) is not None:
            out.append(v)
        out.extend(check_action(a, info))
    # Presentation is examined only if the vocabulary is declared.
    out.extend(parse_view(root, info)[1])
    if out:
        raise Invalid(out)
    return ModuleInfo(
        name=name,
        placement=UNPLACED,
        revision=Revision(),
        entity_types=tuple(entities.values()),
        relationships=tuple(relationships),
        value_types=tuple(values.values()),
        actions=actions,
    )


def _records(
    mod: Obj, module: str, names: _Names, out: list[Violation]
) -> tuple[dict[str, EntityTypeInfo], dict[str, ValueTypeInfo]]:
    elements = [_obj(e) for e in _list(mod.get("elements"))]
    fields: dict[str, Obj] = {}
    records: list[Obj] = []
    for i, el in enumerate(elements):
        kind = el.get("kind")
        eid = _text(el.get("id"), f"elements[{i}].id", "an element id", out)
        if kind == "field" and eid is not None:
            if eid in fields:
                out.append(_doc(f"elements.{eid}", f"element {eid!r} is declared twice"))
            fields[eid] = el
        elif kind == "record" and eid is not None:
            records.append(el)
        elif kind not in ("field", "record"):
            out.append(_doc(f"elements[{i}]", f"unsupported element kind {kind!r}"))
    kinds: dict[str, str] = {}
    for el in records:
        ddd = _obj(_obj(el.get("extensions")).get("umf.ddd"))
        kinds[str(el["id"])] = str(ddd.get("kind"))
    entities: dict[str, EntityTypeInfo] = {}
    values: dict[str, ValueTypeInfo] = {}
    claimed: set[str] = set()
    for el in records:
        tname = str(el["id"])
        path = f"elements.{tname}"
        ddd = _obj(_obj(el.get("extensions")).get("umf.ddd"))
        kind = kinds[tname]
        if kind not in _RECORD_KINDS:
            out.append(_doc(path, f"unsupported record kind {kind!r}"))
            continue
        entity = kind == "entity"
        if (v := check_name(tname, path, entity_type=entity)) is not None:
            out.append(v)
        names.add(tname, path)
        props = _properties(ddd, tname, path, kinds, out)
        claimed |= _cross_check(el, ddd, tname, props, fields, path, out)
        if entity:
            key = _key(el, module, tname, props, fields, path, out)
            entities[tname] = EntityTypeInfo(
                name=f"{module}.{tname}", key=key or "", properties=tuple(props)
            )
        else:
            if el.get("keys"):
                out.append(_doc(path, "a value object has no key"))
            values[tname] = ValueTypeInfo(name=f"{module}.{tname}", properties=tuple(props))
    for fid in fields.keys() - claimed:
        out.append(_doc(f"elements.{fid}", f"field {fid!r} belongs to no record"))
    return entities, values


def _properties(
    ddd: Obj, tname: str, path: str, kinds: dict[str, str], out: list[Violation]
) -> list[PropertyInfo]:
    props: list[PropertyInfo] = []
    names = _Names(out)
    for pname, spec in _obj(ddd.get("fields")).items():
        ppath = f"{path}.{pname}"
        spec = _obj(spec)
        if (v := check_name(pname, ppath)) is not None:
            out.append(v)
        names.add(pname, ppath)
        card = spec.get("cardinality")
        if card not in _CARDINALITIES:
            out.append(_doc(ppath, f"cardinality must be one of {_CARDINALITIES}"))
            continue
        typ = _obj(spec.get("type"))
        tn = typ.get("name")
        if typ.get("kind") == "scalar":
            if tn not in SCALAR_FAMILIES:
                out.append(_doc(ppath, f"scalar {tn!r} is not a supported family"))
                continue
            props.append(PropertyInfo(pname, str(tn), True, card))
        elif typ.get("kind") == "record" and isinstance(tn, str):
            if kinds.get(tn) != "value-object":
                out.append(_doc(ppath, f"{tn!r} is not a value object of this module"))
                continue
            props.append(PropertyInfo(pname, tn, False, card))
        else:
            out.append(_doc(ppath, f"unsupported type {typ.get('kind')!r}"))
    return props


def _cross_check(
    el: Obj,
    ddd: Obj,
    tname: str,
    props: list[PropertyInfo],
    fields: dict[str, Obj],
    path: str,
    out: list[Violation],
) -> set[str]:
    """The record's `ddd.fields` and its `field` elements must agree; returns the ids it claims."""
    members = {str(_obj(m).get("element")) for m in _list(el.get("members"))}
    claimed: set[str] = set()
    for p in props:
        fid = f"{tname}.{p.name}"
        fel = fields.get(fid)
        if fel is None or fid not in members:
            out.append(_doc(f"{path}.{p.name}", f"no field element {fid!r} among the members"))
            continue
        claimed.add(fid)
        if p.scalar and fel.get("scalarType") != p.type:
            out.append(_doc(f"{path}.{p.name}", "the field element's scalar type differs"))
        if (fel.get("nullability") == "required") != (p.cardinality == "one"):
            out.append(_doc(f"{path}.{p.name}", "required-ness differs between the two forms"))
        if (fel.get("cardinality") == "many") != (p.cardinality == "many"):
            out.append(_doc(f"{path}.{p.name}", "the field element's cardinality differs"))
    declared = {f"{tname}.{p.name}" for p in props}
    for extra in members - declared:
        out.append(_doc(path, f"member {extra!r} has no field in the record"))
    return claimed


def _key(
    el: Obj,
    module: str,
    tname: str,
    props: list[PropertyInfo],
    fields: dict[str, Obj],
    path: str,
    out: list[Violation],
) -> str | None:
    primary = [k for k in (_obj(k) for k in _list(el.get("keys"))) if k.get("primary") is True]
    if len(primary) != 1:
        out.append(Violation(path, "missing_key", "declare exactly one primary key"))
        return None
    members = [_obj(m) for m in _list(primary[0].get("fields"))]
    if len(members) != 1:
        out.append(Violation(path, "missing_key", "a key is exactly one field"))
        return None
    ref = str(members[0].get("element", ""))
    fname = ref.removeprefix(f"{tname}.")
    if members[0].get("module") != module or ref != f"{tname}.{fname}":
        out.append(Violation(path, "missing_key", "the key names a field of another record"))
        return None
    prop = next((p for p in props if p.name == fname), None)
    required = _obj(fields.get(ref)).get("nullability") == "required"
    if prop is None or prop.type != "string" or prop.cardinality != "one" or not required:
        out.append(Violation(path, "missing_key", "the key is a required string field"))
        return None
    return fname


def _multiplicity(value: Any, path: str, out: list[Violation]) -> Multiplicity | None:
    m = _obj(value)
    lo, hi = m.get("min"), m.get("max")
    if not isinstance(lo, int) or isinstance(lo, bool) or lo < 0:
        out.append(_doc(path, "min is an integer of at least 0"))
        return None
    if hi == "*":
        return Multiplicity(lo, None)
    if not isinstance(hi, int) or isinstance(hi, bool) or hi < max(lo, 1):
        out.append(_doc(path, "max is '*' or an integer of at least min and 1"))
        return None
    return Multiplicity(lo, hi)


def _relationships(
    mod: Obj,
    module: str,
    entities: dict[str, EntityTypeInfo],
    names: _Names,
    out: list[Violation],
) -> list[RelationshipInfo]:
    result: list[RelationshipInfo] = []
    # per local endpoint type: the property names its relationship columns must not collide with
    columns: dict[str, _Names] = {t: _Names(out) for t in entities}
    for t, info in entities.items():
        columns[t].seen = {p.name.lower(): p.name for p in info.properties}
    for i, rel in enumerate(_obj(r) for r in _list(mod.get("relationships"))):
        rname = _text(rel.get("name"), f"relationships[{i}].name", "a relationship name", out)
        if rname is None:
            continue
        path = f"relationships.{rname}"
        if (v := check_name(rname, path)) is not None:
            out.append(v)
        names.add(rname, path)
        inverse = rel.get("inverse")
        if inverse is not None:
            if not isinstance(inverse, str):
                out.append(_doc(f"{path}.inverse", "an inverse is a name"))
                inverse = None
            else:
                if (v := check_name(inverse, f"{path}.inverse")) is not None:
                    out.append(v)
                names.add(inverse, f"{path}.inverse")
        ends: list[tuple[str, ...]] = []
        for side, col in (("source", rname), ("target", inverse)):
            eps: list[str] = []
            for ep in (_obj(e) for e in _list(rel.get(side))):
                m = _text(ep.get("module"), f"{path}.{side}", "an endpoint module", out)
                e = _text(ep.get("element"), f"{path}.{side}", "an endpoint type", out)
                if m is None or e is None:
                    continue
                if m == module:
                    if e not in entities:
                        out.append(
                            Violation(
                                f"{path}.{side}", "unknown_type", f"{module}.{e} is not defined"
                            )
                        )
                    elif isinstance(col, str):
                        columns[e].add(col, f"{path}.{side}")
                eps.append(f"{m}.{e}")
            if not eps:
                out.append(_doc(f"{path}.{side}", "a relationship names its endpoint types"))
            ends.append(tuple(eps))
        sm = _multiplicity(rel.get("sourceMultiplicity"), f"{path}.sourceMultiplicity", out)
        tm = _multiplicity(rel.get("targetMultiplicity"), f"{path}.targetMultiplicity", out)
        if sm is None or tm is None:
            continue
        result.append(
            RelationshipInfo(
                name=rname,
                source=ends[0],
                target=ends[1],
                source_multiplicity=sm,
                target_multiplicity=tm,
                lifecycle=str(rel.get("targetLifecycle", "independent")),
                inverse=inverse if isinstance(inverse, str) else None,
            )
        )
    return result
