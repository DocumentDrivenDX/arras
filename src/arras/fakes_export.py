# SPDX-License-Identifier: MIT OR Apache-2.0
"""Exporting a fake authority's graph as records (CONTRACT-003, `export_records`)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from arras.exportcursor import MAX_PAGE, check_limit, cursor, ranker, resume_of
from arras.model import ModuleInfo
from arras.results import RecordsPage
from arras.serialize import jsonable
from arras.types import Freshness, Position, Principal

__all__ = ["MAX_PAGE", "ExportRecords"]


class ExportRecords:
    """`export_records` for `MemoryStore`: every entity of a module, then every relationship
    instance between them, in an order that is the same each time."""

    name: str
    state: Any

    def gate(self, principal: Principal, module: str | None, mode: Any, op: str) -> None: ...

    def position(self) -> Position: ...

    def module(self, name: str) -> ModuleInfo: ...

    def _records(self, mod: ModuleInfo) -> Iterator[tuple[tuple[Any, ...], dict[str, Any]]]:
        """Each record with its place in the canonical order: entities by type in declaration order
        then key, relationships by relationship in declaration order then source then target.
        The place is `(0, type, key)` or `(1, relationship, source, target)`; the places sort in
        the order the records are written. Only what is set is written: an unset property, and an
        author or time the record never had, are absent."""
        for t in mod.entity_types:
            rows = sorted(
                ((ref, e) for ref, e in self.state.entities.items() if ref.type == t.name),
                key=lambda re_: re_[0].key,
            )
            for ref, e in rows:
                props = {
                    k: jsonable(v, tag=False)
                    for k, v in sorted(e.props.items())
                    if k != t.key and v is not None
                }
                rec: dict[str, Any] = {"type": t.local_name, "key": ref.key, "properties": props}
                if e.original_author is not None:
                    rec["original_author"] = e.original_author
                if e.original_at is not None:
                    rec["original_at"] = jsonable(e.original_at, tag=False)
                yield (0, t.name, ref.key), rec
        for rel in mod.relationships:
            triples = sorted(
                (src.key, tgt.key)
                for name, src, tgt in self.state.relations
                if name == rel.name and src.type in rel.source and tgt.type in rel.target
            )
            for s, t_ in triples:
                yield (1, rel.name, s, t_), {"relationship": rel.name, "source": s, "target": t_}

    def export_records(
        self, principal: Principal, module: str, *, limit: int, after: str | None
    ) -> RecordsPage:
        self.gate(principal, module, "read", "export_records")
        check_limit(limit)
        mod = self.module(module)
        rank = ranker(mod)
        resume = rank(resume_of(after)) if after else None
        page: list[dict[str, Any]] = []
        last: tuple[Any, ...] = ()
        more = False
        for order, rec in self._records(mod):
            if resume is not None and rank(order) <= resume:
                continue
            if len(page) == limit:
                more = True
                break
            page.append(rec)
            last = order
        return RecordsPage(
            tuple(page),
            cursor(last) if more else None,
            (),
            Freshness(self.name, self.position(), "latest"),
        )
