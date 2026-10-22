# SPDX-License-Identifier: MIT OR Apache-2.0
"""`export_records` of the Truss adapter (CONTRACT-003, CONTRACT-004): the module's graph as the
records `import_records` takes, read as the person in one read-only transaction a page at a time.

It is the person's own Weft reads, so it is as readable as they are and no more: a person who may
read no such module is `Refused` (never an empty page), and what Truss refuses a read it refuses an
export (a type of over 10,000 rows, an entity with over 100 related keys on a relationship: R17).

- Entities, one type at a time in declaration order, are listed by keyset on the key (which Truss
  orders bytewise, `COLLATE "C"`, the order the cursor and the other backends use) and each is then
  read whole by its key (`alias.*` under `complete-entity`, the only read that carries the original
  author and time, and one that takes no keyset continuation).
- Relationship records are read per relationship and source type as the source's related keys, by
  keyset on the source key; a relationship with several source types merges them by source then
  target. A resume reads the cursor's source by equality first and continues by keyset after it. A relationship is written under its declared name, never its inverse. A source with more
  than 100 targets is `Unsupported` rather than cut.
- The cursor is the last record's own place (`arras.exportcursor`), so a page resumes after it
  whatever has been written since. A page is one transaction: the next page reads what is then.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterator
from itertools import islice
from typing import Any

from arras.adapters.truss.connection import Call, Connections
from arras.adapters.truss.query import Reader, params_of, row_of
from arras.adapters.truss.registry import Registry, kind_of
from arras.errors import Refused, Unavailable, Unsupported
from arras.exportcursor import check_limit, cursor, ranker, resume_of
from arras.model import EntityTypeInfo, ModuleInfo, RelationshipInfo
from arras.results import RecordsPage
from arras.serialize import jsonable
from arras.types import Freshness, Position, Principal

BATCH = 501  # rows a read asks for: a page and the one that says there is more
RELATED = 100  # the keys Truss gives a source's relationship; more is refused, never cut
_Placed = tuple[tuple[Any, ...], dict[str, Any]]


class _Scan:
    """The reads of one page: in one call, against one document, remembering the first position."""

    def __init__(self, reader: Reader, call: Call, document: str) -> None:
        self.reader, self.call, self.document = reader, call, document
        self.position: Position | None = None

    def select(self, sql: str, after: str | None, params: dict[str, Any] | None = None) -> Any:
        params = params_of(params or ({} if after is None else {"last": after}))
        found = self.reader.run(self.call, self.document, sql, params)
        if self.position is None and found.as_of is not None:
            self.position = Position(value=found.as_of.value, at=found.as_of.at)
        return found


def _keyset(source: str, key: str, after: str | None) -> str:
    if after is None:
        return ""
    return f"WHERE {source}.{key} > :last "


def _entities(scan: _Scan, t: EntityTypeInfo, after: str | None) -> Iterator[_Placed]:
    """The type's entities by key. Truss gives a keyset continuation only under a page profile, which
    carries no facts, and the facts (the original author and time) only in a whole-entity read, which
    takes no continuation: so the keys come a batch at a time and each entity is read whole by its
    key, lazily, so a page reads only the entities it gives."""
    props = [
        p.name for p in t.properties if p.name != t.key and p.scalar and p.cardinality != "many"
    ]
    while True:
        sql = f"SELECT u.{t.key} FROM {t.name} u {_keyset('u', t.key, after)}ORDER BY u.{t.key} LIMIT {BATCH}"
        keys = [str(raw[0]) for raw in scan.select(sql, after).rows]
        for key in keys:
            whole = f"SELECT u.* FROM {t.name} u WHERE u.{t.key} = :key ORDER BY u.{t.key} LIMIT 1"
            found = scan.select(whole, None, {"key": key})
            names = tuple(found.columns)
            rows = [row_of(names, raw, True) for raw in found.rows]
            if not rows:
                continue  # deleted since its key was listed
            row = rows[0]
            record: dict[str, Any] = {
                "type": t.local_name,
                "key": key,
                "properties": {
                    n: jsonable(row[n], tag=False)
                    for n in sorted(props)
                    if n in row and row[n] is not None
                },
            }
            if row.get("_original_author") is not None:
                record["original_author"] = row["_original_author"]
            if row.get("_original_at") is not None:
                record["original_at"] = jsonable(row["_original_at"], tag=False)
            yield (0, t.name, key), record
        if len(keys) < BATCH:
            return
        after = keys[-1]


def _edges(found_rows: Any) -> Iterator[tuple[str, str]]:
    """`(source key, target key)` of the rows of a `RELATED_KEYS` read, targets sorted."""
    for src, related in found_rows:
        if kind_of(related) != "QueryRelatedKeys":
            continue  # a source that has none
        if related.truncated:
            raise Unsupported(
                "an export of a source with more than 100 related keys",
                ["a relationship of at most 100 targets per source"],
            )
        for target in sorted(str(i[0]) for i in related.items):
            yield str(src), target


def _targets(
    scan: _Scan, source: str, key: str, rel: RelationshipInfo, after: str | None
) -> Iterator[tuple[str, str]]:
    """`(source key, target key)` of one source type's edges, by source key then target key. A
    resume reads the cursor's own source by equality (Truss refuses a keyset that includes the
    place, R17.7) and then continues by keyset after it."""
    head = f"SELECT s.{key} AS src, RELATED_KEYS(s.{rel.name}, {RELATED}) AS tgt FROM {source} s "
    if after is not None:
        own = f"{head}WHERE s.{key} = :key ORDER BY s.{key} LIMIT 1"
        yield from _edges(scan.select(own, None, {"key": after}).rows)
    while True:
        sql = f"{head}{_keyset('s', key, after)}ORDER BY s.{key} LIMIT {BATCH}"
        rows: Any = scan.select(sql, after).rows
        yield from _edges(rows)
        if len(rows) < BATCH:
            return
        after = str(rows[-1][0])


def _relationships(
    scan: _Scan, info: ModuleInfo, rel: RelationshipInfo, after: tuple[str, str] | None
) -> Iterator[_Placed]:
    streams: list[Iterator[tuple[str, str]]] = []
    for name in rel.source:
        t = next(t for t in info.entity_types if t.name == name)  # `_local_sources` checked
        streams.append(_targets(scan, t.name, t.key, rel, None if after is None else after[0]))
    for src, tgt in heapq.merge(*streams):
        if after is None or (src, tgt) > after:
            yield (
                (1, rel.name, src, tgt),
                {"relationship": rel.name, "source": src, "target": tgt},
            )


def _local_sources(info: ModuleInfo) -> None:
    """Every relationship is read from its source types, so each must be in this module: one whose
    source is in another module is `Unsupported`, named, before any page is read."""
    here = {t.name for t in info.entity_types}
    for rel in info.relationships:
        outside = [n for n in rel.source if n not in here]
        if outside:
            raise Unsupported(
                f"an export of relationship {rel.name} whose source type {outside[0]} is in another module",
                ["a relationship whose source types are all in the exported module"],
            )


def _stream(scan: _Scan, info: ModuleInfo, resume: tuple[Any, ...] | None) -> Iterator[_Placed]:
    """Every record after `resume`, in the canonical order, read lazily."""
    for i, t in enumerate(info.entity_types):
        if resume is not None and resume[0] == 1:
            break  # the entities are behind a relationship's place
        if resume is not None and resume[1] > i:
            continue
        here = resume is not None and resume[1] == i
        yield from _entities(scan, t, resume[2] if here and resume else None)
    for j, rel in enumerate(info.relationships):
        if resume is not None and resume[0] == 1 and resume[1] > j:
            continue
        here = resume is not None and resume[0] == 1 and resume[1] == j
        yield from _relationships(
            scan, info, rel, (resume[2], resume[3]) if here and resume else None
        )


class Exporter:
    def __init__(self, backend: str, connections: Connections, registry: Registry, reader: Reader):
        self.name = backend
        self.connections = connections
        self.registry = registry
        self.reader = reader

    def export_records(
        self, principal: Principal, module: str, *, limit: int, after: str | None
    ) -> RecordsPage:
        with self.connections.read(principal, "export_records") as call:
            catalog = self.registry.reader_catalog(call)
            entry = None
            if catalog is not None:
                entry = next((e for e in catalog.modules if e["moduleId"] == module), None)
            info = None
            if catalog is not None and entry is not None:
                info = self.registry.module_info(call, catalog.catalog_revision, entry)
            if entry is None or info is None:
                raise Refused(self.name, "export_records", "no_access")
            check_limit(limit)
            _local_sources(info)
            rank = ranker(info)
            resume = None if not after else rank(resume_of(after))
            scan = _Scan(self.reader, call, entry["documentId"])
            got = list(islice(_stream(scan, info, resume), limit + 1))
            if scan.position is None:
                raise Unavailable(self.name, "unreachable", "Truss stated no read position")
        more = len(got) > limit
        page = got[:limit]
        return RecordsPage(
            tuple(rec for _, rec in page),
            cursor(page[-1][0]) if more else None,
            (),
            Freshness(self.name, scan.position, "latest"),
        )
