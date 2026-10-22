# SPDX-License-Identifier: MIT OR Apache-2.0
"""The memory adapter's resolution of a parsed statement against one module's types (W-011).

A `Plan` is the small relational pipeline `arras.fakes_eval` runs: the scans and their inner
joins, the filters, the grouping and aggregates, the order, the limit and the outputs. Names are
checked against the named module's types as Weft would (an unknown name is `Invalid`, a construct
outside the subset `Unsupported`, carrying `SUBSET`); types are checked by family without implicit
conversion, and literals and parameters to the field's numeric domain (`arras.fakes_domain`); a
plain projection in a grouped query must be grouped; repeated aliases and output
names are refused. `profiles_needed` tells which Weft read profile a plan's shape stands in for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from arras.actions import KEY_VALUE
from arras.errors import Invalid, Unsupported, Violation
from arras.fakes_domain import Domain, Domains, fault
from arras.fakes_sql import (
    SUBSET,
    Bound,
    Col,
    Ident,
    Item,
    Predicate,
    Query,
    Scalar,
    Source,
    Value,
)
from arras.model import COLUMN_SCALARS, EntityTypeInfo, ModuleInfo, PropertyInfo, RelationshipInfo

ENTITY, RELATED, COUNT, GENERAL = "entity-page", "related-entity-page", "count-summary", "general"

FACTS: tuple[tuple[str, str], ...] = (
    ("_version", "integer"),
    ("_created_by", "string"),
    ("_updated_by", "string"),
    ("_original_author", "string"),
    ("_created_at", "timestamp"),
    ("_updated_at", "timestamp"),
    ("_original_at", "timestamp"),
    ("_load_id", "string"),
)
ATTRIBUTION = frozenset(n for n, _ in FACTS)


@dataclass(frozen=True)
class Ref:
    """A property of one scan."""

    scan: int
    name: str


@dataclass(frozen=True)
class Rel:
    """A relationship as one scan's end names it: `canonical` is its declared name, `out` when the
    scan's type is its source."""

    scan: int
    name: str
    canonical: str
    out: bool


@dataclass(frozen=True)
class Scan:
    alias: Ident
    type: EntityTypeInfo


@dataclass(frozen=True)
class Cond:
    """`=` and `>` (one ref against one value), `tuple` (refs > values), `related` (`rel`, `keys`)."""

    kind: str
    left: tuple[Ref, ...] = ()
    right: tuple[Ref | Scalar, ...] = ()
    rel: Rel | None = None


@dataclass(frozen=True)
class Output:
    name: str
    kind: Literal["col", "count", "sum", "related", "fact"]
    type: str  # the column's type: a scalar family, `keys` or a fact's
    ref: Ref | None = None
    rel: Rel | None = None
    n: int = 0
    scan: int = 0  # a fact's scan
    star: bool = False  # from `alias.*`: a property with no value has no member in the row
    scalar: bool = True
    scale: int | None = None  # a decimal SUM carries its argument's scale


@dataclass(frozen=True)
class Plan:
    module: str
    scans: tuple[Scan, ...]
    joins: tuple[tuple[tuple[Ref, Ref], ...], ...]  # joins[i] brings in scans[i + 1]
    conds: tuple[Cond, ...]
    group: tuple[Ref, ...]
    aggregated: bool
    outputs: tuple[Output, ...]
    order: tuple[Ref, ...]
    limit: int | None
    whole: bool  # an `alias.*` is among the outputs
    text: object | None = field(default=None, compare=False)  # a search's text match, beside it

    @property
    def type(self) -> str:
        return self.scans[0].type.name

    @property
    def key(self) -> str:
        return self.scans[0].type.key


def _unsupported(construct: str, hint: str | None = None) -> Unsupported:
    return Unsupported(construct, [hint, *SUBSET] if hint else SUBSET)


def _fits(prop: PropertyInfo, v: Scalar, param: bool) -> bool:
    """A literal or a parameter of the field's family. A decimal field takes an integer literal
    but not an integer parameter: Weft types a parameter by its own family."""
    if prop.type == "string":
        return isinstance(v, str)
    if prop.type == "boolean":
        return isinstance(v, bool)
    if prop.type == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if prop.type == "decimal":
        whole = isinstance(v, int) and not isinstance(v, bool)
        return isinstance(v, Decimal) or (whole and not param)
    return False


Column = tuple[Ref, PropertyInfo, Domain | None]


class _Resolver:
    def __init__(self, q: Query, mod: ModuleInfo, found: Domains | None = None) -> None:
        self.q, self.mod, self.domains = q, mod, found
        self.out: list[Violation] = []
        self.scans: list[Scan] = []
        rels = {r.name: r for r in mod.relationships}
        self.rels: dict[str, RelationshipInfo] = rels | {
            r.inverse: r for r in mod.relationships if r.inverse
        }

    def fault(self, path: str, code: str, message: str) -> None:
        self.out.append(Violation(path, code, message))

    # -- names
    def scan_of(self, src: Source) -> Scan:
        if src.module is not None and not src.module.matches(self.mod.name):
            raise _unsupported(
                f"a statement reading {src.module.text}.{src.type.text} outside module {self.mod.name}",
                f"one module per statement: name the types of {self.mod.name}",
            )
        t = next((t for t in self.mod.entity_types if src.type.matches(t.local_name)), None)
        if t is None:  # the module is held here, the type is not: another reader may serve it
            raise _unsupported(
                f"type {self.mod.name}.{src.type.text}, which this backend does not hold",
                f"the types of {self.mod.name} held here",
            )
        if any(s.alias.same(src.alias) for s in self.scans):
            self.fault("sql", "duplicate_alias", f"the alias {src.alias.text!r} is used twice")
        return Scan(src.alias, t)

    def scan_index(self, alias: Ident, upto: int) -> int | None:
        found = next((i for i, s in enumerate(self.scans[:upto]) if s.alias.same(alias)), None)
        if found is None:
            self.fault("sql", "unknown_alias", f"unknown alias {alias.text!r}")
        return found

    def rel_names(self, t: EntityTypeInfo) -> list[str]:
        return [
            n for n, r in self.rels.items() if t.name in (r.target if n == r.inverse else r.source)
        ]

    def column(self, c: Col, role: str, upto: int | None = None) -> Column | None:
        i = self.scan_index(c.alias, len(self.scans) if upto is None else upto)
        if i is None:
            return None
        t = self.scans[i].type
        if c.name.text in ATTRIBUTION:
            raise _unsupported(
                f"{role} {c.name.text} (attribution)",
                f"a {role} is on a declared property; attribution is read with alias.*",
            )
        prop = next((p for p in t.properties if c.name.matches(p.name)), None)
        if prop is None:
            if any(c.name.matches(n) for n in self.rel_names(t)):
                raise _unsupported(
                    f"relationship {c.name.text} as a {role}",
                    f"HAS_RELATED(alias.{c.name.text}, KEY(literal | :name)) or RELATED_KEYS",
                )
            msg = f"{t.local_name} has no property {c.name.text!r}"
            self.fault(f"sql.{c.name.text}", "unknown_field", msg)
            return None
        # a projected column may be absent (null); every other role needs a required field
        optional_ok = role == "column" and prop.cardinality == "optional"
        if (
            not prop.scalar
            or prop.type not in COLUMN_SCALARS
            or (prop.cardinality != "one" and not optional_ok)
        ):
            hint = (
                "use alias.* for properties that are not single-valued scalars"
                if role == "column"
                else f"a {role} is on a required, single-valued string, integer, decimal or boolean"
            )
            raise _unsupported(f"{role} {prop.name} ({prop.cardinality} {prop.type})", hint)
        domain = None
        if self.domains is not None and prop.type in ("integer", "decimal"):
            domain = self.domains.get((self.mod.name, t.local_name, prop.name))
            if domain is None and prop.type == "integer":
                domain = Domain("integer")
            if domain is None or not domain.served:
                raise _unsupported(
                    f"{role} {prop.name} (a decimal without precision and scale)",
                    "a decimal is read when its field declares precision and scale",
                )
        return Ref(i, prop.name), prop, domain

    def relationship(self, c: Col) -> Rel | None:
        i = self.scan_index(c.alias, len(self.scans))
        if i is None:
            return None
        t = self.scans[i].type
        name = next((n for n in self.rel_names(t) if c.name.matches(n)), None)
        if name is None:
            msg = f"{t.local_name} has no relationship {c.name.text!r}"
            self.fault(f"sql.{c.name.text}", "unknown_field", msg)
            return None
        r = self.rels[name]
        return Rel(i, name, r.name, t.name in r.source and name != r.inverse)

    # -- clauses
    def compare(self, a: PropertyInfo, b: PropertyInfo, path: str) -> None:
        """Compared fields are of one exact family: no integer is a decimal (Weft `WFT-TYPE`)."""
        if a.type != b.type:
            self.fault(path, "type", f"{a.name} is a {a.type} and {b.name} a {b.type}")

    def value(
        self, prop: PropertyInfo, domain: Domain | None, v: Value, path: str
    ) -> Ref | Scalar | None:
        if isinstance(v, Col):
            other = self.column(v, "filter")
            if other is None:
                return None
            self.compare(prop, other[1], path)
            return other[0]
        param = isinstance(v, Bound)
        raw = v.value if isinstance(v, Bound) else v
        if not isinstance(raw, str | int | Decimal) or not _fits(prop, raw, param):
            what = "parameter" if param else "value"
            self.fault(path, "type", f"{prop.name} is a {prop.type}, and the {what} is not")
            return None
        if domain is not None and not isinstance(raw, str | bool):
            why = fault(domain, raw)
            if why is not None:
                self.fault(path, "numeric_domain", f"{prop.name} holds no {why}")
                return None
        return raw

    def cond(self, p: Predicate) -> Cond | None:
        if p.kind == "related":
            rel = self.relationship(p.left[0])
            keys = tuple(k.value if isinstance(k, Bound) else k for k in p.right)
            if len(keys) != 1:
                self.fault("sql", "key", "a key here has one part")
            elif not isinstance(keys[0], str) or not KEY_VALUE.fullmatch(keys[0]):
                self.fault(
                    f"sql.{p.left[0].name.text}", "key", "a relationship is compared with a key"
                )
            return Cond("related", right=(keys[0],), rel=rel) if rel and keys else None  # type: ignore[arg-type]
        lefts: list[Ref] = []
        rights: list[Ref | Scalar | None] = []
        for c, v in zip(p.left, p.right, strict=True):
            got = self.column(c, "filter")
            if got is None:
                continue
            lefts.append(got[0])
            rights.append(self.value(got[1], got[2], v, f"sql.{c.name.text}"))
        if len(lefts) != len(p.left):
            return None
        return Cond(p.kind, tuple(lefts), tuple(r for r in rights if r is not None))

    def outputs(self, aggregated: bool) -> list[Output]:
        outs: list[Output] = []
        quoted: set[str] = set()  # names written as quoted output names compare exactly
        for item in self.q.items:
            got = self.item(item, aggregated)
            if item.output is not None and item.output.quoted:
                quoted.update(o.name for o in got)
            outs += got
        seen: set[str] = set()
        for o in outs:  # every other name compares case-folded, as Weft compares output names
            name = o.name if o.name in quoted else o.name.lower()
            if name in seen:
                self.fault(
                    f"sql.{o.name}", "duplicate_column", f"the column {o.name!r} is named twice"
                )
            seen.add(name)
        return outs

    def item(self, item: Item, aggregated: bool) -> list[Output]:
        named = item.output.text if item.output else None
        if item.kind == "count":
            return [Output(named or "count", "count", "integer")]
        assert item.col is not None
        if item.kind == "star":
            if aggregated:
                raise _unsupported("alias.* in a grouped or aggregated statement")
            i = self.scan_index(item.col.alias, len(self.scans))
            if i is None:
                return []
            t = self.scans[i].type
            cols = [
                Output(p.name, "col", p.type, Ref(i, p.name), star=True, scalar=p.scalar)
                for p in t.properties
            ]
            return cols + [Output(n, "fact", ty, scan=i) for n, ty in FACTS]
        if item.kind == "related":
            if aggregated:
                raise _unsupported("RELATED_KEYS in a grouped or aggregated statement")
            rel = self.relationship(item.col)
            return [Output(named or rel.name, "related", "keys", rel=rel, n=item.n)] if rel else []
        got = self.column(item.col, "column" if item.kind == "col" else "sum")
        if got is None:
            return []
        ref, prop, domain = got
        if item.kind == "sum":
            if prop.type not in ("integer", "decimal"):
                self.fault(f"sql.{prop.name}", "type", "SUM requires an integer or decimal field")
            scale = domain.scale if domain is not None else None
            return [Output(named or "sum", "sum", prop.type, ref, scale=scale)]
        return [Output(named or prop.name, "col", prop.type, ref)]

    def resolve(self) -> Plan:
        q = self.q
        self.scans.append(self.scan_of(q.source))
        joins: list[tuple[tuple[Ref, Ref], ...]] = []
        for j in q.joins:
            self.scans.append(self.scan_of(j.source))
            pairs: list[tuple[Ref, Ref]] = []
            for a, b in j.on:  # ON sees the earlier scans and its own, never a later one
                ra, rb = self.column(a, "join"), self.column(b, "join")
                if ra and rb:
                    self.compare(ra[1], rb[1], f"sql.{a.name.text}")
                    pairs.append((ra[0], rb[0]))
            joins.append(tuple(pairs))
        conds = [c for p in q.predicates if (c := self.cond(p)) is not None]
        group = [g[0] for c in q.group_by if (g := self.column(c, "group by"))]
        aggregated = bool(q.group_by) or any(i.kind in ("count", "sum") for i in q.items)
        outputs = self.outputs(aggregated)
        order = [o[0] for c in q.order_by if (o := self.column(c, "order"))]
        if aggregated:
            for o in outputs:
                if o.kind == "col" and o.ref not in group:
                    self.fault("sql", "group_by", f"{o.name} is projected and not grouped")
            for ref in order:
                if ref not in group:
                    self.fault("sql", "group_by", f"{ref.name} is ordered by and not grouped")
        if self.out:
            raise Invalid(self.out)
        return Plan(
            self.mod.name,
            tuple(self.scans),
            tuple(joins),
            tuple(conds),
            tuple(group),
            aggregated,
            tuple(outputs),
            tuple(order),
            q.limit,
            any(i.kind == "star" for i in q.items),
        )


def resolve_plan(q: Query, mod: ModuleInfo, found: Domains | None = None) -> Plan:
    """Resolve a parsed statement over the one module the caller named; with `found`, the
    module's numeric domains, literals and parameters are held to them."""
    return _Resolver(q, mod, found).resolve()


# -- the Weft read profile a plan's shape stands in for (Weft CONTRACT-004, application reads)


def _related(p: Plan) -> bool:
    return any(c.kind == "related" for c in p.conds) or any(o.kind == "related" for o in p.outputs)


def _page(p: Plan) -> bool:
    """One source, no aggregation, in key order with a LIMIT, filtered by equality (on a value or
    another column) and at most a keyset on the key against values."""
    key = Ref(0, p.key)
    filters_ok = all(
        c.kind == "="
        or (c.kind in (">", "tuple") and c.left == (key,) and not isinstance(c.right[0], Ref))
        or c.kind == "related"
        for c in p.conds
    )
    return (
        len(p.scans) == 1
        and not p.aggregated
        and p.order == (key,)
        and p.limit is not None
        and filters_ok
    )


def _count(p: Plan) -> bool:
    """COUNT(*), grouped scalars and equality filters, inner joins admitted; a grouped count orders
    by the whole grouping and names a LIMIT, a global one names neither."""
    if not p.aggregated or any(o.kind == "sum" for o in p.outputs):
        return False
    if not any(o.kind == "count" for o in p.outputs):
        return False
    if any(c.kind != "=" for c in p.conds):
        return False
    if p.group:
        return p.order == p.group and p.limit is not None
    return not p.order and p.limit is None


def profiles_needed(p: Plan) -> tuple[str, ...]:
    """The one Weft read profile whose shape this statement takes: a named one, else `general`."""
    if _page(p):
        return (RELATED,) if _related(p) else (ENTITY,)
    if _count(p):
        return (COUNT,)
    return (GENERAL,)


def bounded(p: Plan) -> bool:
    """Whether the memory adapter bounds a general statement's answer: it names a LIMIT, or it is an
    aggregate with no grouping, which answers one row."""
    return p.limit is not None or (p.aggregated and not p.group)


def shape_hint(p: Plan) -> str:
    """The construct an `Unsupported` names when a statement takes no profile the backend serves:
    the shape a named profile needs that it lacks, the LIMIT the memory adapter bounds a general
    statement with, else the `general` profile itself."""
    if p.aggregated and any(o.kind == "count" for o in p.outputs):
        if any(c.kind == "related" for c in p.conds):
            return "HAS_RELATED with COUNT(*)"
        if any(c.kind in (">", "tuple") for c in p.conds):
            return "a keyset predicate with COUNT(*)"
        if p.group and (p.order != p.group or p.limit is None):
            names = ", ".join(f"alias.{g.name}" for g in p.group)
            return f"a grouped count without ORDER BY {names} and LIMIT"
    single = len(p.scans) == 1 and not p.aggregated
    if single and (p.order != (Ref(0, p.key),) or p.limit is None):
        return f"a page without ORDER BY alias.{p.key} and LIMIT"
    if not bounded(p):
        return "a statement without LIMIT, which the memory adapter does not bound"
    return f"profile {GENERAL}"
