# SPDX-License-Identifier: MIT OR Apache-2.0
"""Legacy Arras action declarations and the plans resolved for invocation (CONTRACT-003).

Arras resolves an action against its inputs into an ordered `Plan` of effects, with every key
and value concrete. Evaluating the preconditions and applying the effects are the authority's, as
one atomic unit. This parser's JSON shape is a legacy Arras subset pending official UMF Python
adoption and qualification (PLAN-ARRAS-INTEGRATION-20261022, A1-A4). UMF is the canonical
authority for action metadata and meaning; this module does not establish official UMF action
support.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, cast

from arras.errors import Invalid, Violation
from arras.model import Cardinality, EntityTypeInfo, ModuleInfo

KEY_VALUE = re.compile(r"[A-Za-z0-9._:-]{1,128}")
MAX_EFFECTS = 1000
MAX_LIST_ITEMS = 1000

# --- declaration ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InputSpec:
    name: str
    type: str  # a scalar family, a value object's name, or the entity type of a ref
    kind: Literal["scalar", "record", "ref"]
    cardinality: Cardinality


@dataclass(frozen=True)
class Input:
    name: str


@dataclass(frozen=True)
class Literal_:
    value: Any


@dataclass(frozen=True)
class Item:
    """A field of the current `foreach` item (or the item itself when `field` is None)."""

    field: str | None = None


@dataclass(frozen=True)
class AliasKey:
    alias: str


@dataclass(frozen=True)
class Generate:
    kind: str = "uuid"


Expr = Input | Literal_ | Item | AliasKey | Generate


@dataclass(frozen=True)
class PreconditionDecl:
    id: str
    reason: str
    op: Literal["exists", "absent", "property_equals", "no_relationship", "count"]
    args: Mapping[str, Any]  # op-specific; values are Expr or plain names


@dataclass(frozen=True)
class EffectDecl:
    op: Literal["create", "update", "delete", "link", "unlink", "foreach"]
    alias: str | None = None
    type: str | None = None  # entity type (create) or relationship name (link, unlink)
    ref_type: str | None = None  # for update/delete: the entity type of the ref
    key: Expr | None = None
    source: Expr | None = None
    target: Expr | None = None
    properties: Mapping[str, Expr] | None = None
    unset: tuple[str, ...] = ()
    over: str | None = None  # foreach: a list-typed input
    body: tuple[EffectDecl, ...] = ()


@dataclass(frozen=True)
class ActionInfo:
    name: str  # module-qualified
    description: str
    inputs: tuple[InputSpec, ...]
    preconditions: tuple[PreconditionDecl, ...]
    effects: tuple[EffectDecl, ...]
    handler: str | None = None

    @property
    def module(self) -> str:
        return self.name.split(".", 1)[0]


# --- plan ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Ref:
    type: str
    key: str
    generated: bool = field(default=False, compare=False)  # a key made for this invocation


@dataclass(frozen=True)
class Create:
    ref: Ref
    properties: Mapping[str, Any]
    generated: bool = False


@dataclass(frozen=True)
class Update:
    ref: Ref
    set: Mapping[str, Any]
    unset: tuple[str, ...] = ()


@dataclass(frozen=True)
class Delete:
    ref: Ref


@dataclass(frozen=True)
class Link:
    relationship: str
    source: Ref
    target: Ref


@dataclass(frozen=True)
class Unlink:
    relationship: str
    source: Ref
    target: Ref


Effect = Create | Update | Delete | Link | Unlink


@dataclass(frozen=True)
class Precondition:
    id: str
    reason: str
    op: str
    args: Mapping[str, Any]  # refs resolved to `Ref`, values to scalars


@dataclass(frozen=True)
class Plan:
    action: str
    preconditions: tuple[Precondition, ...]
    effects: tuple[Effect, ...]
    inputs_digest: str = ""  # identifies the inputs, so a retry with fresh generated keys matches


# --- resolving -----------------------------------------------------------------------------
#
# Inputs reach `resolve` as Python values. A binding that receives text (MCP, GraphQL) converts a
# timestamp or a decimal before it calls; `resolve` accepts `datetime` with an offset, finite
# `Decimal` and `int` for a decimal, and refuses the rest.


def _is_scalar(family: str, x: Any) -> bool:
    is_int = isinstance(x, int) and not isinstance(x, bool)
    match family:
        case "string":
            return isinstance(x, str)
        case "integer":
            return is_int
        case "decimal":
            return is_int or (isinstance(x, Decimal) and x.is_finite())
        case "boolean":
            return isinstance(x, bool)
        case "timestamp":
            return isinstance(x, datetime) and x.tzinfo is not None
        case "binary":
            return isinstance(x, bytes)
        case _:
            return False


def _v(path: str, code: str, message: str) -> Violation:
    return Violation(path, code, message)


def _coerce(
    spec_type: str, kind: str, value: Any, path: str, module: ModuleInfo, out: list[Violation]
) -> Any:
    if kind == "ref":
        if not isinstance(value, str) or not KEY_VALUE.fullmatch(value):
            out.append(_v(path, "key", "a key is 1 to 128 characters of [A-Za-z0-9._:-]"))
        return value
    if kind == "record":
        vt = next((v for v in module.value_types if v.name == f"{module.name}.{spec_type}"), None)
        if not isinstance(value, Mapping) or vt is None:
            out.append(_v(path, "type", f"expected an object of {spec_type}"))
            return None
        fields = cast(Mapping[str, Any], value)
        known = {p.name: p for p in vt.properties}
        for k in fields.keys() - known.keys():
            out.append(_v(f"{path}.{k}", "unknown_field", f"{spec_type} has no field {k!r}"))
        result: dict[str, Any] = {}
        for p in vt.properties:
            if fields.get(p.name) is not None:
                result[p.name] = _input_value(
                    p.type, p.scalar, p.cardinality, fields[p.name], f"{path}.{p.name}", module, out
                )
            elif p.required:
                out.append(_v(f"{path}.{p.name}", "required", "a value is required"))
        return result
    if not _is_scalar(spec_type, value):
        out.append(_v(path, "type", f"expected a {spec_type}"))
        return value
    return Decimal(value) if spec_type == "decimal" else value


def _input_value(
    typ: str,
    scalar: bool,
    card: str,
    value: Any,
    path: str,
    module: ModuleInfo,
    out: list[Violation],
    *,
    ref: bool = False,
) -> Any:
    kind = "ref" if ref else ("scalar" if scalar else "record")
    if card == "many":
        if not isinstance(value, list | tuple):
            out.append(_v(path, "type", "expected a list"))
            return None
        items = list(cast(list[Any], value))
        if len(items) > MAX_LIST_ITEMS:
            out.append(
                _v(path, "bound", f"{len(items)} items exceed the bound of {MAX_LIST_ITEMS}")
            )
            return None
        return [_coerce(typ, kind, x, f"{path}[{i}]", module, out) for i, x in enumerate(items)]
    return _coerce(typ, kind, value, path, module, out)


def resolve(
    action: ActionInfo,
    inputs: Mapping[str, Any],
    module: ModuleInfo,
    *,
    new_key: Callable[[], str] = lambda: str(uuid.uuid4()),
    handler: Callable[[Mapping[str, Any]], Sequence[Effect]] | None = None,
) -> Plan:
    """Validate `inputs`, expand the action into concrete effects; `Invalid` lists every fault.

    The action must have passed `check_action`; the resolver then meets only faults that depend
    on the inputs (a value of the wrong type, a computed key that is not a key, too many effects).
    """
    out: list[Violation] = []
    values: dict[str, Any] = {}
    specs = {s.name: s for s in action.inputs}
    for k in inputs.keys() - specs.keys():
        out.append(_v(f"inputs.{k}", "unknown_input", f"{action.name} has no input {k!r}"))
    for s in action.inputs:
        path = f"inputs.{s.name}"
        if s.name not in inputs or inputs[s.name] is None:
            if s.cardinality == "one":
                out.append(_v(path, "required", "a value is required"))
            continue
        values[s.name] = _input_value(
            s.type,
            s.kind == "scalar",
            s.cardinality,
            inputs[s.name],
            path,
            module,
            out,
            ref=s.kind == "ref",
        )
    if out:
        raise Invalid(out)
    total = _expanded_count(action.effects, values)
    if total > MAX_EFFECTS:
        raise Invalid(
            [_v("effects", "bound", f"{total} effects exceed the bound of {MAX_EFFECTS}")]
        )
    r = _Resolver(action, values, module, new_key)
    effects = r.run(action.effects, "effects")
    if r.out:
        raise Invalid(r.out)
    if handler is not None:  # only once the declared part is sound
        made: Any = handler(values)
        if not isinstance(made, Sequence) or isinstance(made, str):
            raise Invalid([_v("effects", "handler", "a handler returns a list of effects")])
        effects += check_effects(list(cast(Sequence[Any], made)), module)
    if len(effects) > MAX_EFFECTS:
        raise Invalid(
            [_v("effects", "bound", f"{len(effects)} effects exceed the bound of {MAX_EFFECTS}")]
        )
    pres = tuple(r.precondition(i, p) for i, p in enumerate(action.preconditions))
    digest = hashlib.sha256(repr(sorted(values.items())).encode()).hexdigest()
    return Plan(action.name, pres, tuple(effects), digest)


class _EffectCheck:
    """The checks on effects a handler made, one method per kind of effect."""

    def __init__(self, module: ModuleInfo) -> None:
        self.module = module
        self.out: list[Violation] = []
        self.types = {t.name: t for t in module.entity_types}
        self.rels = {r.name: r for r in module.relationships}

    def ref_ok(self, ref: Any, where: str) -> EntityTypeInfo | None:
        if not isinstance(ref, Ref) or ref.type not in self.types:
            self.out.append(_v(where, "unknown_type", f"not an entity type of {self.module.name}"))
            return None
        if not KEY_VALUE.fullmatch(ref.key):
            self.out.append(_v(where, "key", "a key is 1 to 128 characters of [A-Za-z0-9._:-]"))
        return self.types[ref.type]

    def values_ok(self, t: EntityTypeInfo, props: Mapping[str, Any], where: str) -> None:
        for k, v in props.items():
            p = t.property(k)
            if p is None or k == t.key:
                self.out.append(
                    _v(f"{where}.{k}", "unknown_field", f"{t.local_name} has no settable {k}")
                )
            elif p.scalar and p.cardinality != "many" and not _is_scalar(p.type, v):
                self.out.append(_v(f"{where}.{k}", "type", f"expected a {p.type}"))

    def create(self, e: Create, w: str) -> None:
        t = self.ref_ok(e.ref, w)
        if t is None:
            return
        self.values_ok(t, e.properties, w)
        for p in t.properties:
            if p.required and p.name != t.key and p.name not in e.properties:
                self.out.append(_v(f"{w}.{p.name}", "required", "a value is required"))

    def update(self, e: Update, w: str) -> None:
        t = self.ref_ok(e.ref, w)
        if t is None:
            return
        self.values_ok(t, e.set, w)
        for u in e.unset:
            p = t.property(u)
            if p is None or u == t.key or p.required:
                self.out.append(_v(f"{w}.{u}", "required", "cannot be unset"))

    def link(self, e: Link | Unlink, w: str) -> None:
        rel = self.rels.get(e.relationship)
        ts, tt = self.ref_ok(e.source, w), self.ref_ok(e.target, w)
        if rel is None:
            self.out.append(
                _v(w, "unknown_type", f"{e.relationship} is not a canonical relationship")
            )
        elif ts and tt and (ts.name not in rel.source or tt.name not in rel.target):
            self.out.append(_v(w, "unknown_type", "endpoints do not fit the relationship"))

    def effect(self, e: Any, w: str) -> None:
        if isinstance(e, Create):
            self.create(e, w)
        elif isinstance(e, Update):
            self.update(e, w)
        elif isinstance(e, Delete):
            self.ref_ok(e.ref, w)
        elif isinstance(e, Link | Unlink):
            self.link(e, w)
        else:
            self.out.append(_v(w, "handler", "not an effect"))


def check_effects(effects: list[Any], module: ModuleInfo) -> list[Effect]:
    """Check effects a handler made, as declared ones are checked: types, module, keys, values."""
    c = _EffectCheck(module)
    for i, e in enumerate(effects):
        c.effect(e, f"effects[{i}]")
    if c.out:
        raise Invalid(c.out)
    return cast(list[Effect], effects)


def _expanded_count(decls: tuple[EffectDecl, ...], values: Mapping[str, Any]) -> int:
    n = 0
    for d in decls:
        if d.op == "foreach":
            n += len(d.body) * len(values.get(d.over or "") or [])
        else:
            n += 1
    return n


class _Resolver:
    def __init__(
        self,
        action: ActionInfo,
        values: dict[str, Any],
        module: ModuleInfo,
        new_key: Callable[[], str],
    ) -> None:
        self.action = action
        self.values = values
        self.module = module
        self.new_key = new_key
        self.aliases: dict[str, Ref] = {}
        self.specs = {s.name: s for s in action.inputs}
        self.out: list[Violation] = []
        self.rels = {r.name: r for r in module.relationships}
        self.inverses = {r.inverse: r for r in module.relationships if r.inverse}

    def qualified(self, local: str) -> str:
        return f"{self.module.name}.{local}"

    def value(self, e: Expr | None, item: Any) -> Any:
        if isinstance(e, Input):
            return self.values.get(e.name)
        if isinstance(e, Literal_):
            return e.value
        if isinstance(e, Item):
            return item if e.field is None else cast(Mapping[str, Any], item).get(e.field)
        if isinstance(e, AliasKey):
            return self.aliases[e.alias].key
        return None

    def key(self, e: Expr | None, item: Any, where: str) -> Ref | str:
        """A key as text, made if `e` asks for a generated one; a fault is recorded."""
        if isinstance(e, Generate):
            return self.new_key()
        k = self.value(e, item)
        if not isinstance(k, str) or not KEY_VALUE.fullmatch(k):
            self.out.append(_v(where, "key", "a key is 1 to 128 characters of [A-Za-z0-9._:-]"))
            return "_invalid"
        return k

    def ref(self, local: str | None, e: Expr | None, item: Any, where: str) -> Ref:
        if isinstance(e, AliasKey):
            return self.aliases[e.alias]
        return Ref(self.qualified(str(local)), str(self.key(e, item, where)))

    def props(self, d: EffectDecl, item: Any) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, e in (d.properties or {}).items():
            v = self.value(e, item)
            if v is not None:  # an absent optional value stays absent
                out[k] = v
        return out

    def run(
        self,
        decls: tuple[EffectDecl, ...],
        where: str,
        item: Any = None,
        item_type: str | None = None,
    ) -> list[Effect]:
        out: list[Effect] = []
        for i, d in enumerate(decls):
            w = f"{where}[{i}]"
            if d.op == "foreach":
                spec = self.specs[str(d.over)]
                for n, it in enumerate(cast(list[Any], self.values.get(spec.name) or [])):
                    out.extend(
                        self.run(
                            d.body,
                            f"{w}.each[{n}].body",
                            it,
                            spec.type if spec.kind == "ref" else None,
                        )
                    )
            elif d.op == "create":
                generated = isinstance(d.key, Generate)
                key = str(self.key(d.key, item, f"{w}.key"))
                ref = Ref(self.qualified(str(d.type)), key, generated)
                if d.alias:
                    self.aliases[d.alias] = ref
                out.append(Create(ref, self.props(d, item), generated))
            elif d.op == "update":
                out.append(
                    Update(
                        self.ref(d.ref_type, d.key, item, f"{w}.key"), self.props(d, item), d.unset
                    )
                )
            elif d.op == "delete":
                out.append(Delete(self.ref(d.ref_type, d.key, item, f"{w}.key")))
            else:
                out.append(self.link(d, w, item, item_type))
        return out

    def end(self, e: Expr | None, item: Any, item_type: str | None, where: str) -> Ref:
        if isinstance(e, AliasKey):
            return self.aliases[e.alias]
        if isinstance(e, Input):
            return self.ref(self.specs[e.name].type, e, item, where)
        return self.ref(item_type, e, item, where)

    def link(self, d: EffectDecl, w: str, item: Any, item_type: str | None) -> Effect:
        src = self.end(d.source, item, item_type, f"{w}.source")
        tgt = self.end(d.target, item, item_type, f"{w}.target")
        name = str(d.type)
        if name in self.inverses:  # backends only ever see the canonical relationship
            name, src, tgt = self.inverses[name].name, tgt, src
        return Link(name, src, tgt) if d.op == "link" else Unlink(name, src, tgt)

    def precondition(self, i: int, p: PreconditionDecl) -> Precondition:
        args: dict[str, Any] = {}
        for k, v in p.args.items():
            if isinstance(v, Input) and self.specs[v.name].kind == "ref":
                args[k] = Ref(self.qualified(self.specs[v.name].type), str(self.values.get(v.name)))
            elif isinstance(v, Input | Literal_):
                args[k] = self.value(v, None)
            else:
                args[k] = v
        if p.op == "absent":
            args["type"] = self.qualified(str(args["type"]))
        return Precondition(p.id, p.reason, p.op, args)


# --- reading a declaration -------------------------------------------------------------------

_PRECONDITIONS = {"exists", "absent", "property_equals", "no_relationship", "count"}
_EFFECTS = {"create", "update", "delete", "link", "unlink", "foreach"}
_CARDS = ("one", "optional", "many")
# precondition arguments that are expressions; the others are plain names or numbers
_PRECONDITION_EXPRS = {"ref", "key", "source", "target", "value"}


def _dict(raw: Any) -> dict[str, Any]:
    return cast(dict[str, Any], raw) if isinstance(raw, dict) else {}


def _items(raw: Any) -> list[Any]:
    return cast(list[Any], raw) if isinstance(raw, list) else []


def _bad(path: str, message: str, code: str = "invalid_document") -> Violation:
    return Violation(path, code, message)


def _str(
    raw: Any, path: str, what: str, out: list[Violation], *, optional: bool = False
) -> str | None:
    if isinstance(raw, str) and raw:
        return raw
    if raw is not None or not optional:
        out.append(_bad(path, f"{what} is a non-empty string"))
    return None


def _expr(raw: Any, path: str, out: list[Violation]) -> Expr | None:
    r = _dict(raw)
    if len(r) == 1:
        ((k, v),) = r.items()
        if k == "input" and isinstance(v, str):
            return Input(v)
        if k == "literal" and isinstance(v, str | int | bool | float):
            return Literal_(Decimal(str(v)) if isinstance(v, float) else v)
        if k == "item" and (v is True or isinstance(v, str)):
            return Item(None if v is True else v)
        if k == "alias" and isinstance(v, str):
            return AliasKey(v)
        if k == "generate" and v == "uuid":
            return Generate()
    out.append(_bad(path, "an expression is input, literal, item, alias or generate"))
    return None


def _effect(raw: Any, path: str, out: list[Violation]) -> EffectDecl | None:
    r = _dict(raw)
    op = r.get("op")
    if op not in _EFFECTS:
        out.append(_bad(path, f"unsupported effect {op!r}"))
        return None

    def field_(name: str) -> Expr | None:
        return _expr(r[name], f"{path}.{name}", out) if name in r else None

    props: dict[str, Expr] = {}
    for k, v in _dict(r.get("properties")).items():
        pe = _expr(v, f"{path}.properties.{k}", out)
        if pe is not None:
            props[k] = pe
    body: list[EffectDecl] = []
    for i, b in enumerate(_items(r.get("body"))):
        be = _effect(b, f"{path}.body[{i}]", out)
        if be is not None:
            body.append(be)
    unset = [u for u in _items(r.get("unset"))]
    if not all(isinstance(u, str) for u in unset):
        out.append(_bad(f"{path}.unset", "unset is a list of property names"))
        unset = []
    return EffectDecl(
        op=op,
        alias=_str(r.get("as"), f"{path}.as", "an alias", out, optional=True),
        type=_str(r.get("type"), f"{path}.type", "a type", out, optional=True),
        ref_type=_str(r.get("refType"), f"{path}.refType", "a type", out, optional=True),
        key=field_("key"),
        source=field_("source"),
        target=field_("target"),
        properties=props,
        unset=tuple(unset),
        over=_str(r.get("over"), f"{path}.over", "an input name", out, optional=True),
        body=tuple(body),
    )


def _input_spec(raw: Any, path: str, out: list[Violation]) -> InputSpec | None:
    sd = _dict(raw)
    t = _dict(sd.get("type"))
    kind = t.get("kind")
    tname = t.get("type") if kind == "ref" else t.get("name")
    card = sd.get("cardinality", "one")
    name = sd.get("name")
    if kind not in ("scalar", "record", "ref") or card not in _CARDS:
        out.append(_bad(path, "an input has a name, a type and a cardinality"))
        return None
    if not isinstance(tname, str) or not isinstance(name, str) or not name:
        out.append(_bad(path, "an input has a name, a type and a cardinality"))
        return None
    return InputSpec(name, tname, kind, card)


def _precondition(raw: Any, path: str, out: list[Violation]) -> PreconditionDecl | None:
    pd = _dict(raw)
    pred = _dict(pd.get("predicate"))
    op = pred.get("op")
    if op not in _PRECONDITIONS or not isinstance(pd.get("id"), str) or not pd["id"]:
        out.append(_bad(path, f"a precondition has an id and a supported predicate, not {op!r}"))
        return None
    args: dict[str, Any] = {}
    for k, v in pred.items():
        if k == "op":
            continue
        if k in _PRECONDITION_EXPRS:
            pe = _expr(v, f"{path}.{k}", out)
            if pe is not None:
                args[k] = pe
        elif isinstance(v, str | int) and not isinstance(v, bool):
            args[k] = v
        else:
            out.append(_bad(f"{path}.{k}", f"{k} is a name or an integer"))
    return PreconditionDecl(pd["id"], str(pd.get("reason", "")), op, args)


def parse_action(raw: Any, module: str, out: list[Violation]) -> ActionInfo | None:
    """Read one action declaration (the stand-in JSON shape); violations go to `out`."""
    r = _dict(raw)
    aid = r.get("id")
    if not isinstance(aid, str) or not aid:
        out.append(_bad("actions", "an action id is missing"))
        return None
    path = f"actions.{module}.{aid}"
    inputs = [
        s
        for i, x in enumerate(_items(r.get("inputs")))
        if (s := _input_spec(x, f"{path}.inputs[{i}]", out)) is not None
    ]
    pres = [
        p
        for i, x in enumerate(_items(r.get("preconditions")))
        if (p := _precondition(x, f"{path}.preconditions[{i}]", out)) is not None
    ]
    effects = [
        d
        for i, x in enumerate(_items(r.get("effects")))
        if (d := _effect(x, f"{path}.effects[{i}]", out)) is not None
    ]
    handler = _str(r.get("handler"), f"{path}.handler", "a handler name", out, optional=True)
    return ActionInfo(
        f"{module}.{aid}",
        str(r.get("description", "")),
        tuple(inputs),
        tuple(pres),
        tuple(effects),
        handler,
    )
