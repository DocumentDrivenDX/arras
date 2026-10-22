# SPDX-License-Identifier: MIT OR Apache-2.0
"""The memory adapter's evaluation of a resolved statement over its in-memory rows (W-011).

A small relational pipeline: scan each source in key order, join the scans as a bag (every
matching combination, duplicates kept), filter, then group and aggregate (`COUNT(*)` counts the
bag's rows, join duplicates included; `SUM` is exact, at its argument's scale), order ascending,
apply the statement's `LIMIT`, project, and finally cut at Arras's `limit` cap, saying so with
`truncated`. A join is a hash join on its equality pairs that link the new source to an earlier
one; one with no such pair compares every combination. The work is bounded by `MAX_WORK`: the
rows a join produces, and the combinations a join without a linking pair would compare, which is
charged before it starts. A statement over the bound is `Unsupported`: the bound is the memory
adapter's, a limit of the data it would read, not a fault of the request.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any

from arras.actions import Ref as EntityRef
from arras.errors import Unsupported
from arras.fakes_plan import Cond, Plan, Ref
from arras.fakes_sql import SUBSET
from arras.fakes_state import State
from arras.fakes_state import deep_copy as _copy
from arras.types import Column

MAX_WORK = 10_000  # the join work (rows produced, combinations compared) the memory adapter does

Combo = tuple[EntityRef, ...]


def columns(plan: Plan) -> tuple[Column, ...]:
    return tuple(Column(o.name, o.kind != "related" and o.scalar, o.type) for o in plan.outputs)


class _Run:
    def __init__(self, plan: Plan, state: State) -> None:
        self.plan, self.state = plan, state
        self._related: dict[tuple[str, bool], dict[EntityRef, list[str]]] = {}

    def value(self, combo: Combo, ref: Ref) -> Any:
        return self.state.entities[combo[ref.scan]].props.get(ref.name)

    def operand(self, combo: Combo, v: object) -> Any:
        return self.value(combo, v) if isinstance(v, Ref) else v

    def related(self, r: EntityRef, canonical: str, out: bool) -> list[str]:
        """The keys at the other end of `canonical` from `r`, from an index built once a run."""
        index = self._related.get((canonical, out))
        if index is None:
            index = dict[EntityRef, list[str]]()
            for name, src, tgt in self.state.relations:
                if name == canonical:
                    near, far = (src, tgt) if out else (tgt, src)
                    index.setdefault(near, []).append(far.key)
            for keys in index.values():
                keys.sort()
            self._related[(canonical, out)] = index
        return index.get(r, [])

    def holds(self, combo: Combo, c: Cond) -> bool:
        if c.kind == "related":
            assert c.rel is not None
            return c.right[0] in self.related(combo[c.rel.scan], c.rel.canonical, c.rel.out)
        left = [self.value(combo, r) for r in c.left]
        right = [self.operand(combo, v) for v in c.right]
        if any(v is None for v in (*left, *right)):
            return False
        if c.kind == "=":
            return left[0] == right[0]
        return tuple(left) > tuple(right)  # `>` and the keyset tuple compare in order

    def scan(
        self, i: int, text_matches: Callable[[Mapping[str, Any], object], bool]
    ) -> list[EntityRef]:
        t = self.plan.scans[i].type.name
        refs = sorted((r for r in self.state.entities if r.type == t), key=lambda r: r.key)
        if i == 0 and self.plan.text is not None:  # a search's text match narrows its one type
            refs = [r for r in refs if text_matches(self.state.entities[r].props, self.plan.text)]
        return refs

    def bag(self, text_matches: Callable[[Mapping[str, Any], object], bool]) -> list[Combo]:
        bag: list[Combo] = [(r,) for r in self.scan(0, text_matches)]
        for i, pairs in enumerate(self.plan.joins, start=1):
            bag = self.join(bag, i, pairs, self.scan(i, text_matches))
        return [c for c in bag if all(self.holds(c, cond) for cond in self.plan.conds)]

    def join(
        self, bag: list[Combo], i: int, pairs: tuple[tuple[Ref, Ref], ...], right: list[EntityRef]
    ) -> list[Combo]:
        """Bring in scan `i`: a hash join on the pairs that link it to an earlier scan, the other
        pairs checked on each combination; without a linking pair, every combination."""
        links: list[tuple[Ref, Ref]] = []  # (the earlier scan's side, scan i's side)
        rest: list[tuple[Ref, Ref]] = []
        for a, b in pairs:
            if a.scan == i and b.scan < i:
                links.append((b, a))
            elif b.scan == i and a.scan < i:
                links.append((a, b))
            else:
                rest.append((a, b))
        joined: list[Combo] = []
        if links:
            index: dict[tuple[Any, ...], list[EntityRef]] = {}
            for r in right:
                props = self.state.entities[r].props
                key = tuple(props.get(new.name) for _, new in links)
                if None not in key:
                    index.setdefault(key, []).append(r)
            candidates = (
                (combo, index.get(tuple(self.value(combo, old) for old, _ in links), []))
                for combo in bag
            )
        else:
            if len(bag) * len(right) > MAX_WORK:  # charged before comparing anything
                raise _over_work()
            candidates = ((combo, right) for combo in bag)
        for combo, matches in candidates:
            for r in matches:
                c = (*combo, r)
                if all(_equal(self.value(c, a), self.value(c, b)) for a, b in rest):
                    joined.append(c)
                    if len(joined) > MAX_WORK:
                        raise _over_work()
        return joined

    def row(self, combo: Combo) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for o in self.plan.outputs:
            if o.kind == "fact":
                out[o.name] = _fact(self.state, combo[o.scan], o.name)
            elif o.kind == "related":
                assert o.rel is not None
                out[o.name] = self.related(combo[o.rel.scan], o.rel.canonical, o.rel.out)[: o.n]
            else:
                assert o.ref is not None
                props = self.state.entities[combo[o.ref.scan]].props
                if o.star and o.ref.name not in props:
                    continue
                out[o.name] = _copy(props.get(o.ref.name))
        return out

    def ordered(self, combos: list[Combo]) -> list[Combo]:
        if not self.plan.order:
            return combos
        return sorted(combos, key=lambda c: tuple(_asc(self.value(c, r)) for r in self.plan.order))

    def grouped(self, combos: list[Combo]) -> list[dict[str, Any]]:
        groups: dict[tuple[Any, ...], list[Combo]] = {}
        for c in combos:
            groups.setdefault(tuple(self.value(c, g) for g in self.plan.group), []).append(c)
        if not self.plan.group:
            groups = {(): combos}  # a global aggregate answers one row, also over nothing
        order = self.plan.order or self.plan.group
        positions = [self.plan.group.index(r) for r in order]
        keys = sorted(groups, key=lambda k: tuple(_asc(k[i]) for i in positions))
        return [self.aggregate(k, groups[k]) for k in keys]

    def aggregate(self, key: tuple[Any, ...], combos: list[Combo]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for o in self.plan.outputs:
            if o.kind == "count":
                out[o.name] = len(combos)  # the bag's rows, join duplicates included
            elif o.kind == "sum":
                assert o.ref is not None
                out[o.name] = _sum([self.value(c, o.ref) for c in combos], o.type, o.scale)
            else:
                assert o.ref is not None
                out[o.name] = key[self.plan.group.index(o.ref)]
        return out


def _over_work() -> Unsupported:
    return Unsupported(
        f"a join doing more than {MAX_WORK} rows of work, the memory adapter's bound",
        ["narrow the joined sources, or link each to an earlier one with ON a.x = b.y", *SUBSET],
    )


def _equal(a: Any, b: Any) -> bool:
    return a is not None and b is not None and a == b


def _asc(v: Any) -> tuple[bool, Any]:
    """Ascending, with an absent value last."""
    return (v is None, v if v is not None else 0)


def _sum(values: list[Any], family: str, scale: int | None) -> int | Decimal | None:
    """An exact sum; a decimal sum carries its argument's scale (Weft CONTRACT-001)."""
    present = [v for v in values if v is not None]
    if not present:
        return None
    if family != "decimal":
        return sum(present, 0)
    total = sum((Decimal(v) for v in present), Decimal(0))
    return total.quantize(Decimal(1).scaleb(-scale)) if scale is not None else total


def _fact(state: State, r: EntityRef, name: str) -> Any:
    e = state.entities[r]
    return {
        "_version": e.version,
        "_created_by": e.created_by,
        "_created_at": e.created_at,
        "_updated_by": e.updated_by,
        "_updated_at": e.updated_at,
        "_original_author": e.original_author,
        "_original_at": e.original_at,
        "_load_id": e.load_id,
    }[name]


def evaluate(
    plan: Plan,
    state: State,
    *,
    limit: int,
    text_matches: Callable[[Mapping[str, Any], object], bool],
) -> tuple[tuple[Column, ...], tuple[dict[str, Any], ...], bool]:
    """The columns, the rows within Arras's `limit` cap, and whether the cap cut them."""
    run = _Run(plan, state)
    combos = run.bag(text_matches)
    if plan.aggregated:
        rows = run.grouped(combos)
    else:
        rows = [run.row(c) for c in run.ordered(combos)]
    if plan.limit is not None:
        rows = rows[: plan.limit]
    return columns(plan), tuple(rows[:limit]), len(rows) > limit
