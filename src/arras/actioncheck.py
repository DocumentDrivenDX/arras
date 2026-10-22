# SPDX-License-Identifier: MIT OR Apache-2.0
"""Checking an action declaration against its module's types (CONTRACT-003).

A declaration that passes resolves for any inputs that are valid; `actions.resolve` then meets
only faults that depend on the inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arras.actions import (
    ActionInfo,
    AliasKey,
    EffectDecl,
    Expr,
    Generate,
    Input,
    InputSpec,
    Item,
    Literal_,
    PreconditionDecl,
)
from arras.errors import Violation
from arras.model import SCALAR_FAMILIES, ModuleInfo
from arras.names import check_name

_COMPARISONS = ("=", "!=", "<", "<=", ">", ">=")


@dataclass(frozen=True)
class _Shape:
    kind: str  # scalar, ref, record, generated
    type: str  # a scalar family, or a local type name
    card: str


class _Check:
    def __init__(self, action: ActionInfo, module: ModuleInfo) -> None:
        self.action = action
        self.module = module
        self.out: list[Violation] = []
        self.path = f"actions.{action.name}"
        self.types = {t.local_name: t for t in module.entity_types}
        self.values = {v.name.split(".", 1)[1]: v for v in module.value_types}
        self.rels = {r.name: (r, False) for r in module.relationships}
        self.rels.update({r.inverse: (r, True) for r in module.relationships if r.inverse})
        self.inputs = {s.name: s for s in action.inputs}
        self.aliases: dict[str, str] = {}
        self.item: _Shape | None = None
        self.item_spec: InputSpec | None = None

    def bad(self, where: str, message: str, code: str = "invalid_document") -> None:
        self.out.append(Violation(where, code, message))

    # -- expressions
    def shape(self, e: Expr | None, where: str, *, over: bool = False) -> _Shape | None:
        if isinstance(e, Input):
            s = self.inputs.get(e.name)
            if s is None:
                self.bad(where, f"no input {e.name!r}")
                return None
            if s.cardinality == "many" and not over:
                self.bad(where, f"list input {e.name!r} is only used by foreach")
                return None
            return _Shape(s.kind, s.type, s.cardinality)
        if isinstance(e, Literal_):
            v = e.value
            fam = (
                "boolean"
                if isinstance(v, bool)
                else "integer"
                if isinstance(v, int)
                else "decimal"
                if isinstance(v, Decimal)
                else "string"
            )
            return _Shape("scalar", fam, "one")
        if isinstance(e, Item):
            if self.item is None:
                self.bad(where, "item is only valid inside foreach")
                return None
            if e.field is None:
                return self.item
            vt = self.values.get(self.item.type) if self.item.kind == "record" else None
            p = next((p for p in vt.properties if p.name == e.field), None) if vt else None
            if p is None:
                self.bad(where, f"item has no field {e.field!r}")
                return None
            return _Shape("scalar" if p.scalar else "record", p.type, p.cardinality)
        if isinstance(e, AliasKey):
            if e.alias not in self.aliases:
                self.bad(where, f"alias {e.alias!r} is not defined earlier")
                return None
            return _Shape("ref", self.aliases[e.alias], "one")
        if isinstance(e, Generate):
            return _Shape("generated", "uuid", "one")
        self.bad(where, "an expression is required")
        return None

    def key_of_new(self, e: Expr | None, where: str) -> None:
        s = self.shape(e, where)
        if s is None:
            return
        ok = s.kind == "generated" or (s.kind == "scalar" and s.type == "string") or s.kind == "ref"
        if not ok or s.card != "one":
            self.bad(where, "a new key is generated, or a required string or key value")

    def ref_of(self, e: Expr | None, local: str | None, where: str) -> str | None:
        """An existing entity named by `e`; returns its local type."""
        s = self.shape(e, where)
        if s is None:
            return None
        if s.kind != "ref" or s.card != "one":
            self.bad(where, "an entity is named by an alias or a required ref input")
            return None
        if local is not None and s.type != local:
            self.bad(where, f"expected a {local}, found a {s.type}")
        return s.type

    def value_for(
        self, e: Expr | None, prop_type: str, scalar: bool, card: str, where: str
    ) -> None:
        s = self.shape(e, where)
        if s is None:
            return
        if s.kind == "generated":
            self.bad(where, "generate is only a key")
            return
        want_card_ok = {
            "one": s.card == "one",
            "optional": s.card in ("one", "optional"),
            "many": s.card == "many",
        }[card]
        if card == "many" and isinstance(e, Input) and s.card == "many":
            want_card_ok = True
        compatible = (
            (
                scalar
                and s.kind == "scalar"
                and (s.type == prop_type or (prop_type == "decimal" and s.type == "integer"))
            )
            or (scalar and prop_type == "string" and s.kind == "ref")
            or (not scalar and s.kind == "record" and s.type == prop_type)
        )
        if not compatible or not want_card_ok:
            self.bad(where, f"value does not fit a {card} {prop_type} property")

    # -- declaration
    def declaration(self) -> None:
        a = self.action
        if len(self.inputs) != len(a.inputs):
            self.bad(self.path, "an input name is declared twice")
        for s in a.inputs:
            where = f"{self.path}.inputs.{s.name}"
            if (v := check_name(s.name, where)) is not None:
                self.out.append(v)
            if s.kind == "ref" and s.type not in self.types:
                self.bad(where, f"{s.type} is not an entity type", "unknown_type")
            if s.kind == "record" and s.type not in self.values:
                self.bad(where, f"{s.type} is not a value object", "unknown_type")
            if s.kind == "scalar" and s.type not in SCALAR_FAMILIES:
                self.bad(where, f"{s.type} is not a scalar family")
        if not a.effects and a.handler is None:
            self.bad(self.path, "an action has effects or a handler")
        ids = [p.id for p in a.preconditions]
        for dup in {i for i in ids if ids.count(i) > 1}:
            self.bad(f"{self.path}.preconditions", f"precondition id {dup!r} is used twice")
        for p in a.preconditions:
            self.precondition(p, f"{self.path}.preconditions.{p.id}")
        self.walk(a.effects, f"{self.path}.effects")

    def precondition(self, p: PreconditionDecl, w: str) -> None:
        need = {
            "exists": {"ref"},
            "absent": {"type", "key"},
            "property_equals": {"ref", "property", "value"},
            "no_relationship": {"relationship", "source"},
            "count": {"relationship", "source", "cmp", "n"},
        }[p.op]
        extra: set[str] = {"target"} if p.op == "no_relationship" else set()
        if not need <= set(p.args) or set(p.args) - need - extra:
            self.bad(w, f"{p.op} takes {sorted(need | extra)}")
            return
        a = p.args
        if "relationship" in a and a["relationship"] not in self.rels:
            self.bad(w, f"{a['relationship']!r} is not a relationship", "unknown_type")
        if p.op == "absent":
            if a["type"] not in self.types:
                self.bad(w, f"{a['type']!r} is not an entity type", "unknown_type")
            self.key_of_new(a["key"], w)  # a key to look for: never generated
            if isinstance(a["key"], Generate):
                self.bad(w, "absent looks for a given key")
        for k in ("ref", "source", "target"):
            if k in a:
                self.ref_of(a[k], None, w)
        if p.op == "property_equals":
            t = self.types.get(self.ref_of(a["ref"], None, w) or "")
            prop = t.property(str(a["property"])) if t else None
            if t is not None and (prop is None or not prop.scalar):
                self.bad(w, f"{a['property']!r} is not a scalar property")
            elif prop is not None:
                self.value_for(a["value"], prop.type, True, "one", w)
        if p.op == "count" and (
            a["cmp"] not in _COMPARISONS or not isinstance(a["n"], int) or a["n"] < 0
        ):
            self.bad(w, f"cmp is one of {_COMPARISONS} and n a non-negative integer")

    def walk(self, decls: tuple[EffectDecl, ...], where: str) -> None:
        for i, d in enumerate(decls):
            w = f"{where}[{i}]"
            if d.alias is not None:
                if d.op != "create":
                    self.bad(w, "only create has an alias")
                elif d.alias in self.aliases:
                    self.bad(w, f"alias {d.alias!r} is declared twice")
            if d.op == "foreach":
                self.foreach(d, w)
            elif d.op == "create":
                self.create(d, w)
            elif d.op in ("update", "delete"):
                self.change(d, w)
            else:
                self.link(d, w)

    def foreach(self, d: EffectDecl, w: str) -> None:
        spec = self.inputs.get(d.over or "")
        if spec is None or spec.cardinality != "many":
            self.bad(w, "foreach runs over a list input")
            return
        if self.item is not None:
            self.bad(w, "foreach does not nest")
            return
        self.item, self.item_spec = _Shape(spec.kind, spec.type, "one"), spec
        self.walk(d.body, f"{w}.body")
        self.item = self.item_spec = None

    def create(self, d: EffectDecl, w: str) -> None:
        t = self.types.get(d.type or "")
        if t is None:
            self.bad(w, f"{d.type} is not an entity type", "unknown_type")
            return
        if d.key is None:
            self.bad(w, "create has a key")
        else:
            self.key_of_new(d.key, f"{w}.key")
        if d.alias:
            self.aliases[d.alias] = t.local_name
        given = d.properties or {}
        for p in t.properties:
            if p.name == t.key:
                if p.name in given:
                    self.bad(w, "the key is set by `key`, not as a property")
            elif p.name in given:
                self.value_for(given[p.name], p.type, p.scalar, p.cardinality, f"{w}.{p.name}")
            elif p.required:
                self.bad(w, f"create {t.local_name} sets no {p.name}", "missing_required")
        for g in set(given) - {p.name for p in t.properties}:
            self.bad(w, f"{t.local_name} has no property {g!r}")

    def change(self, d: EffectDecl, w: str) -> None:
        t = self.types.get(d.ref_type or "")
        if t is None:
            self.bad(w, f"{d.ref_type} is not an entity type", "unknown_type")
            return
        self.ref_of(d.key, t.local_name, f"{w}.key")
        if d.op == "delete":
            if d.properties or d.unset:
                self.bad(w, "delete sets and unsets nothing")
            return
        given = d.properties or {}
        for g in set(given) | set(d.unset):
            p = t.property(g)
            if p is None:
                self.bad(w, f"{t.local_name} has no property {g!r}")
            elif g == t.key:
                self.bad(w, "a key cannot be updated")
            elif g in d.unset and p.required:
                self.bad(w, f"required property {g!r} cannot be unset", "missing_required")
            elif g in given:
                if g in d.unset:
                    self.bad(w, f"{g!r} is both set and unset")
                self.value_for(given[g], p.type, p.scalar, p.cardinality, f"{w}.{g}")

    def link(self, d: EffectDecl, w: str) -> None:
        found = self.rels.get(d.type or "")
        if found is None:
            self.bad(w, f"{d.type} is not a relationship of the module", "unknown_type")
            return
        if d.properties:
            self.bad(w, "relationship properties are not declared")
        rel, inverse = found
        want_src, want_tgt = (rel.target, rel.source) if inverse else (rel.source, rel.target)
        for expr, wants, side in ((d.source, want_src, "source"), (d.target, want_tgt, "target")):
            local = self.ref_of(expr, None, f"{w}.{side}")
            if local is not None and f"{self.module.name}.{local}" not in wants:
                self.bad(f"{w}.{side}", f"{local} is not an endpoint of {d.type}")


def check_action(action: ActionInfo, module: ModuleInfo) -> list[Violation]:
    """What a declaration can be checked for against its module's types.

    A declaration that passes resolves for any inputs that are valid; `resolve` meets only
    faults that depend on the inputs.
    """
    c = _Check(action, module)
    c.declaration()
    return c.out
