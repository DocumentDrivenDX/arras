# SPDX-License-Identifier: MIT OR Apache-2.0
"""`Ontology.search`: a composed read over the types of one module (CONTRACT-010, section C).

Search is not a backend operation. For each type that has a searchable property and whose serving
backend declares `substring`, it makes one ordinary read as the viewer, with a structured text
match on the resolved query, capped at 50 candidates, one type after another and all under the one
registry revision it began with. The library re-checks every candidate, ranks, and names every
type it did not search and why, so that a type that was not searched is never read as one with no
hits. The text and the words are never an attribute of a span, metric or log.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from arras.entityread import entity_rows, related_keys_select
from arras.errors import Conflict, Invalid, Refused, Unavailable, Unsupported, Violation
from arras.model import EntityTypeInfo, ModuleInfo
from arras.names import quoted, quoted_type
from arras.searchplan import (
    CANDIDATES,
    MAX_LIMIT,
    MAX_TYPES,
    Budget,
    EntityBudget,
    NotSearched,
    SearchHit,
    SearchPage,
    Segment,
    TextMatch,
    TypeCount,
    check_text,
    excerpt,
    rank,
)
from arras.types import Consistency, Freshness, Revision, Rows
from arras.view import ResolvedModule, ResolvedView, placeholders, title_of

if TYPE_CHECKING:
    from arras.core import Ontology


RELATED_KEYS = 100  # the keys a hit's relationship carries, as the console's entities do


def _bad(path: str, message: str) -> Invalid:
    return Invalid([Violation(path, "bound", message)])


def _chosen_types(mod: ModuleInfo, view: ResolvedModule, types: Sequence[str] | None) -> list[str]:
    """The local names to search, in the module's declaration order. Named types must be the
    module's; by default, every type that has a search property."""
    local = [t.local_name for t in mod.entity_types]
    if types is None:
        return [n for n in local if view.view(n).search]
    unknown = [n for n in dict.fromkeys(types) if n not in local]
    if unknown:
        raise _bad("types", f"{', '.join(unknown)} is not a type of {mod.name}")
    return [n for n in local if n in types]


def _readers(mod: ModuleInfo, consistency: Consistency) -> tuple[str, ...]:
    """The backends that may serve a read, first choice first: `latest` only from the record
    store; `bulk` from a replica that can, else the record store."""
    if consistency == "latest":
        return (mod.placement.record,)
    return (*mod.placement.replicas, mod.placement.record)


class _Plan:
    """Which backend serves a type and over which properties, or why none does."""

    def __init__(self, backend: str | None, properties: tuple[str, ...], why: NotSearched | None):
        self.backend, self.properties, self.why = backend, properties, why


def _plan(mod: ModuleInfo, t: EntityTypeInfo, wanted: Sequence[str], c: Consistency) -> _Plan:
    local = t.local_name
    if not wanted:
        return _Plan(None, (), NotSearched(local, "no_searchable_property"))
    declined = False
    for name in _readers(mod, c):
        status = mod.status.get(name)
        if status is not None and not status.available:
            return _Plan(None, (), NotSearched(local, "unavailable", name))
        caps = t.capabilities.get(name)
        if caps is None:
            if name == mod.placement.record:  # the record store did not describe the type
                return _Plan(None, (), NotSearched(local, "unavailable", name))
            continue
        if not caps.read or caps.search != "substring":
            declined = True
            continue
        props = tuple(p for p in wanted if p in caps.searchable)
        if props:
            return _Plan(name, props, None)
        return _Plan(None, (), NotSearched(local, "no_searchable_property", name))
    reason = "no_capability" if declined else "unavailable"
    return _Plan(None, (), NotSearched(local, reason, mod.placement.record))


def _excerpt_of(
    row: Mapping[str, Any], matched: Sequence[str], titled: set[str], words: tuple[str, ...]
) -> tuple[Segment, ...]:
    """Cut from the first matched property the title does not use, so the title is not shown
    twice; empty when the title uses every matched property."""
    for name in matched:
        value = row.get(name)
        if name not in titled and isinstance(value, str):
            return excerpt(value, words)
    return ()


def _hits(
    t: EntityTypeInfo,
    view: ResolvedView,
    props: tuple[str, ...],
    words: tuple[str, ...],
    rows: Rows,
) -> list[SearchHit]:
    """The candidates that match, ranked: every candidate is re-checked with the library's fold."""
    out: list[SearchHit] = []
    titled = set(placeholders(view.title))
    for row in rows.rows:
        ranked = rank(words, props, row)
        if ranked is None:
            continue
        key = str(row[t.key])
        segments = _excerpt_of(row, ranked.matched, titled, words)
        out.append(
            SearchHit(
                type=t.local_name,
                key=key,
                score=ranked.score,
                label=title_of(view, row, key),
                excerpt=segments or None,
                matched=ranked.matched,
                row=row,
                freshness=rows.freshness,
            )
        )
    return out


class _Run:
    """One search: its reads, results and what it did not search."""

    def __init__(self, o: Ontology, mod: ModuleInfo, words: tuple[str, ...], budget: Budget):
        self.o, self.mod, self.words, self.budget = o, mod, words, budget
        self.hits: list[SearchHit] = []
        self.counts: list[TypeCount] = []
        self.skipped: list[NotSearched] = []
        self.truncated = False
        self.freshness: dict[str, Freshness] = {}

    def read(self, t: EntityTypeInfo, plan: _Plan, c: Consistency, at_least: str | None) -> Rows:
        text = TextMatch(self.words, plan.properties)
        # the whole entity with its relationships' keys (a hit is the entity, from the same row),
        # an entity page in key order; one row more than the cap, so `truncated` says it cut
        keys = related_keys_select(self.mod, t, RELATED_KEYS)
        order = f"ORDER BY x.{quoted(t.key)} LIMIT {CANDIDATES + 1}"
        sql = f"SELECT x.*{keys} FROM {quoted_type(t.name)} x {order}"
        rows = self.o.query(
            self.mod.name, sql, None, limit=CANDIDATES, consistency=c, at_least=at_least, text=text
        )
        return entity_rows(self.mod, t, rows)

    def one(
        self,
        t: EntityTypeInfo,
        view: ResolvedView,
        wanted: Sequence[str],
        c: Consistency,
        at: str | None,
    ) -> None:
        plan = _plan(self.mod, t, wanted, c)
        if plan.why is not None:
            self.skipped.append(plan.why)
            return
        if not self.budget.try_reserve(CANDIDATES):
            self.skipped.append(NotSearched(t.local_name, "over_budget"))
            return
        try:
            rows = self.read(t, plan, c, at)
        except Unavailable as e:
            self.budget.settle(CANDIDATES, 0)
            self.skipped.append(NotSearched(t.local_name, "unavailable", e.backend))
            return
        except Unsupported:
            self.budget.settle(CANDIDATES, 0)
            self.skipped.append(NotSearched(t.local_name, "no_capability", plan.backend))
            return
        except Refused as e:
            self.budget.settle(CANDIDATES, 0)
            if e.reason == "token_expired":
                raise
            return  # a type the viewer may not read is absent from everything
        self.budget.settle(CANDIDATES, len(rows.rows))
        if rows.revision != self.mod.revision:
            raise Conflict("revision", f"{self.mod.name} changed while the search ran")
        assert plan.backend is not None
        self.freshness.setdefault(rows.freshness.backend, rows.freshness)
        found = _hits(t, view, plan.properties, self.words, rows)
        capped = len(rows.rows) >= CANDIDATES or rows.truncated
        self.truncated = self.truncated or capped
        self.counts.append(TypeCount(t.local_name, len(found), capped))
        self.hits.extend(found)


def run_search(
    o: Ontology,
    module: str,
    text: str,
    types: Sequence[str] | None = None,
    limit: int = 20,
    consistency: Consistency = "latest",
    at_least: str | None = None,
    *,
    budget: Budget | None = None,
    revision: Revision | Mapping[str, Any] | None = None,
) -> SearchPage:
    """The search read. `budget` is the request's entity budget when a request has one;
    `revision` is the module revision the caller began under (a different one now is a `Conflict`
    of reason `revision`)."""
    folded, words = check_text(text)
    if not (type(limit) is int and 1 <= limit <= MAX_LIMIT):
        raise _bad("limit", f"limit is 1 to {MAX_LIMIT}")
    if consistency not in ("latest", "bulk"):
        raise Invalid([Violation("consistency", "value", "latest or bulk")])
    mod = o.describe(module)[0]
    if revision is not None:
        want = revision if isinstance(revision, Revision) else Revision.from_wire(revision)
        if want != mod.revision:
            raise Conflict("revision", f"{mod.name} is at another revision than the caller's")
    view = o.view_of(mod)
    names = _chosen_types(mod, view, types)
    run = _Run(o, mod, words, budget or EntityBudget())
    for i, name in enumerate(names):
        t = mod.entity_type(name)
        assert t is not None
        if i >= MAX_TYPES:
            run.skipped.append(NotSearched(name, "over_budget"))
        else:
            v = view.view(name)
            run.one(t, v, v.search, consistency, at_least)
    order = {t.local_name: i for i, t in enumerate(mod.entity_types)}
    ranked = sorted(run.hits, key=lambda h: (-h.score, order[h.type], h.key))
    return SearchPage(
        text=folded,
        hits=tuple(ranked[:limit]),
        counts=tuple(run.counts),
        not_searched=tuple(run.skipped),
        truncated=run.truncated or len(ranked) > limit,
        freshness=tuple(run.freshness.values()),
    )
