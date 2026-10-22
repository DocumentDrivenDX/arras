# SPDX-License-Identifier: MIT OR Apache-2.0
"""`query` of the Truss adapter (CONTRACT-001, CONTRACT-004, plan TR-06): Weft statements passed to
Truss's `query_in_transaction`, run as the person in one read-only transaction.

Arras defines no dialect and parses nothing: the statement and its parameters go to Truss unchanged,
and Truss compiles them with Weft. The adapter chooses only a read profile, from one lexical test (does
the text hold an `alias.*`), and maps what comes back:

- Order of checks is the memory adapter's: token and connection (the connection layer), then the module
  (`Invalid(unknown_type)`, from the person's own reader catalog read in the same transaction: Truss
  answers a non-member the same refusal for any statement and any document, so the catalog is the only
  existence signal and the cache is never consulted for access), then `text`, then the parameters, then
  Truss.
- A whole-entity statement (`alias.*`) runs under `complete-entity`, the only way Truss appends the eight
  fact columns. It is never retried without the profile: that would return rows with no facts. Any other
  statement runs with no profile and, when Truss asks for a page profile to continue a keyset, is
  retried in the same transaction under each page profile (a refusal is a value and leaves the
  transaction usable).
- The byte bound of a result is the reader catalog's (16 MiB) on both routes: Truss's validator of a
  catalog binds the `maximum_bytes` it was read under, so a combined read must present the bound the
  catalog was read with, and the ordinary read states the same one.
- `maximum_rows` is Truss's bound, not a truncation (a larger result is a `limits` refusal), so the
  adapter asks for the ceiling and caps rows at Arras's `limit` itself. `limits` is a declared bound
  of the backend: `Unsupported`.
- Error details carry Weft's fixed diagnostic codes and never the statement or a parameter value.

Truss is reached through the `Call`'s assembly and its results are recognized by class name, so the
base install imports none of it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from arras.adapters.truss.connection import Call, Connections
from arras.adapters.truss.registry import READER_BYTES, Registry, kind_of, mapped
from arras.errors import ArrasError, Invalid, Unavailable, Unsupported, Violation
from arras.model import ModuleInfo
from arras.results import Answer
from arras.searchplan import TextMatch
from arras.types import Column, Position, Principal, Statement

MAXIMUM_ROWS = 10_000  # Truss's ceiling; a result over the bound is refused, never cut
COMPLETE = "complete-entity"
PAGE_PROFILES = ("entity-page", "related-entity-page", "count-summary")
_STAR = re.compile(r"\.\s*\*")  # an `alias.*`: the only lexical test the adapter makes
_PARAM_TYPES = (str, int, bool, Decimal)  # Truss accepts exactly these, by exact type
_SUPPORTED = ["Weft statements Truss compiles within its bounds"]
# Weft codes that mean a construct or type the dialect does not take (Truss reports a plain syntax
# error under WFT-UNSUPPORTED too, so a syntax error is not told from an unsupported construct).
_UNSUPPORTED_CODES = frozenset(
    {"WFT-UNSUPPORTED", "WFT-CAPABILITY", "WFT-TYPE", "WFT-PROFILE", "WFT-SOURCE-UNAVAILABLE"}
)
_NO_SOURCE = "No queryable record matches source"  # a type outside the module or not in it
FACTS: dict[str, str] = {
    "_version": "integer",
    "_created_by": "string",
    "_updated_by": "string",
    "_original_author": "string",
    "_created_at": "timestamp",
    "_updated_at": "timestamp",
    "_original_at": "timestamp",
    "_load_id": "string",
}
_FACT_TIMES = frozenset(n for n, t in FACTS.items() if t == "timestamp")
_ABSENT = object()


def _unknown_module(module: str | None = None) -> Invalid:
    named = f" {module!r}" if module else ""
    return Invalid(
        [Violation("module", "unknown_type", f"no module{named} is held for this person")]
    )


def params_of(params: Mapping[str, Any]) -> dict[str, Any]:
    """The parameters Truss takes: a string, integer, decimal or boolean, by exact type. Anything
    else (a float, None, a list) is `Invalid` here, before Truss, which refuses it with no reason."""
    for name, value in params.items():
        if type(value) not in _PARAM_TYPES:
            raise Invalid(
                [
                    Violation(
                        f"params.{name}",
                        "param_type",
                        "a parameter is a string, integer, decimal or boolean",
                    )
                ]
            )
    return dict(params)


def refusal(backend: str, refused: Any) -> ArrasError:
    """The library error for a `QueryRefused`, by Truss's code and Weft's diagnostic codes."""
    diagnostics = tuple(getattr(refused, "diagnostics", ()))
    codes: list[str] = [str(d.code) for d in diagnostics]
    code = refused.code
    if code == "unauthorized":  # an unknown document and a non-member are the same refusal
        return _unknown_module()
    if code == "stale_context":
        return Unavailable(backend, "busy", "the catalog changed during the read")
    if code == "native_domain":
        return Invalid(
            [Violation("params", "numeric_domain", "a value is outside a field's numeric domain")]
        )
    if code in ("unsupported_query", "limits"):
        return Unsupported(_describe(code, codes), _SUPPORTED)
    # invalid_query: a construct the dialect excludes (and a syntax error) or a source Weft does not
    # find is Unsupported, as the memory adapter says; a member, a parameter or an output name that
    # is wrong is Invalid
    if any(c in _UNSUPPORTED_CODES for c in codes) or any(
        c == "WFT-NAME-MISSING" and d.message == _NO_SOURCE
        for c, d in zip(codes, diagnostics, strict=True)
    ):
        return Unsupported(_describe(code, codes), _SUPPORTED)
    return Invalid(
        [Violation("sql", (codes[0] if codes else "invalid_query").lower(), _describe(code, codes))]
    )


def _describe(code: str, codes: list[str]) -> str:
    return f"Truss refused the statement ({code}" + "".join(f", {c}" for c in codes[:3]) + ")"


def unavailable(backend: str, found: Any) -> Unavailable:
    reason = {
        "compiler": "not_configured",
        "installation": "not_configured",
        "resource": "resource",
        "observation": "busy",
    }.get(getattr(found, "reason", ""), "unreachable")
    return Unavailable(backend, reason, f"Truss cannot compile a query ({found.reason})")


def _keys(items: Any) -> list[Any]:
    return [i[0] if len(i) == 1 else list(i) for i in items]


def _cell(value: Any) -> Any:
    """A Truss value as the library's: related keys as lists, timestamps with their offset."""
    kind = kind_of(value)
    if kind == "QueryAbsent":
        return _ABSENT
    if kind == "QueryRelatedKeys":
        return _keys(value.items)
    if kind == "TextValue":
        return _text(value)
    if isinstance(value, tuple):
        return _keys([i if isinstance(i, tuple) else (i,) for i in cast(tuple[Any, ...], value)])
    return value


def _text(value: Any) -> Any:
    if value.kind != "timestamp":
        return value.text  # binary stays its exact text
    return _time(value.text)


def _time(text: Any) -> Any:
    if not isinstance(text, str):
        return text
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text
    return parsed if parsed.tzinfo is not None else text


def row_of(names: tuple[str, ...], raw: tuple[Any, ...], whole: bool) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for name, value in zip(names, raw, strict=True):
        cell = _cell(value)
        if cell is _ABSENT:
            if whole:
                continue  # an absent property has no key in a whole entity
            cell = None
        if name in _FACT_TIMES:
            cell = _time(cell)
        row[name] = cell
    return row


def _scalar_of(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, Decimal):
        return "decimal"
    if isinstance(value, datetime):
        return "timestamp"
    return "string"


def columns_of(
    names: tuple[str, ...], rows: list[dict[str, Any]], info: ModuleInfo | None
) -> tuple[Column, ...]:
    """Truss names its columns and types none: a fact has its fixed type, a property the module's
    when every type that has it agrees, a relationship column is keys, a count an integer, and any
    other expression takes its family from its first value (string when every value is null)."""
    declared: dict[str, set[tuple[str, bool]]] = {}
    for t in info.entity_types if info else ():
        for p in t.properties:
            declared.setdefault(p.name, set()).add((p.type, p.scalar))
    out: list[Column] = []
    for name in names:
        if name in FACTS:
            out.append(Column(name, True, FACTS[name]))
        elif len(declared.get(name, ())) == 1:
            (kind, scalar), *_ = declared[name]
            out.append(Column(name, scalar, kind))
        else:
            out.append(_inferred(name, rows))
    return tuple(out)


def _inferred(name: str, rows: list[dict[str, Any]]) -> Column:
    for row in rows:
        value = row.get(name)
        if isinstance(value, list):
            return Column(name, False, "keys")
        if value is not None:
            return Column(name, True, _scalar_of(value))
    return Column(name, True, "string")


class Reader:
    def __init__(self, backend: str, connections: Connections, registry: Registry) -> None:
        self.name = backend
        self.connections = connections
        self.registry = registry

    def query(
        self,
        principal: Principal,
        module: str,
        statement: Statement,
        *,
        limit: int,
        text: TextMatch | None,
    ) -> Answer:
        try:
            return self._query(principal, module, statement, limit, text)
        except Unavailable as exc:
            # an install with nothing registered holds no module: Truss refuses its catalog read
            # as a profile mismatch, which only the install state tells apart (as `catalog` does)
            if exc.reason == "unsupported_version" and self.registry.nothing_registered(
                principal, "query"
            ):
                raise _unknown_module(module) from None
            raise

    def _query(
        self,
        principal: Principal,
        module: str,
        statement: Statement,
        limit: int,
        text: TextMatch | None,
    ) -> Answer:
        with self.connections.read(principal, "query") as call:
            catalog = self.registry.call_catalog(call)
            entry = None
            if catalog is not None:
                entry = next((e for e in catalog.modules if e["moduleId"] == module), None)
            if catalog is None or entry is None:
                raise _unknown_module(module)
            if text is not None:
                raise Unsupported("text search", ["Truss declares no text search"])
            params = params_of(statement.params)
            found = self.run(call, entry["documentId"], statement.sql, params)
            info = self.registry.module_info(call, catalog.catalog_revision, entry)
            return self._answer(found, limit, info, _STAR.search(statement.sql) is not None)

    def query_current(
        self,
        principal: Principal,
        module: str,
        statement: Statement,
        *,
        limit: int,
        text: TextMatch | None,
    ) -> Answer | None:
        """The answer of one operation in one read-only transaction that reads the statement and the
        person's catalog together (`query_with_catalog_in_transaction`), or None when the ordinary
        way (the catalog, then the query) must be taken.

        It presents the validator of the catalog this person was last shown, and Truss withholds both
        the rows and the catalog if the person's current authority or the sources moved: the answer
        is given only when Truss says the catalog is `unchanged`, so what the person may read, the
        module's revision and the original source (its digest is checked against the catalog entry)
        are the ones the caller used. A person who lost access is refused by Truss as any other
        query is. None is returned before any connection when nothing was shown to this person, and
        after the read when the catalog or a source digest moved (the new snapshot is kept)."""
        cache = self.registry.cache
        held = cache.shown(principal.user)
        document = cache.document_of(module)
        snapshot = cache.snapshot(principal.user, True)
        if (
            held is None
            or document is None
            or snapshot is None
            or snapshot[1] != held[0]
            or module not in held[1]
            or text is not None
        ):
            return None
        with self.connections.read(principal, "query") as call:
            params = params_of(statement.params)
            found = self.run(call, document, statement.sql, params, validator=held[0])
            fresh = found.catalog
            if kind_of(fresh) != "ReaderCatalogUnchanged":
                cache.keep_snapshot(principal.user, True, fresh.catalog, fresh.validator)
                cache.drop_shown(principal.user)
                return None
            if not _same_sources(snapshot[0], module, document, found.documents):
                cache.drop_shown(principal.user)
                return None
            return self._answer(
                found.result, limit, held[1][module], _STAR.search(statement.sql) is not None
            )

    def run(
        self,
        call: Call,
        document: str,
        sql: str,
        params: dict[str, Any],
        *,
        validator: str | None = None,
    ) -> Any:
        """The `QueryRows` of the first profile Truss serves the statement under (with a validator,
        the `QueryCatalogRead` that carries them)."""
        ladder: tuple[str | None, ...] = (
            (COMPLETE,) if _STAR.search(sql) else (None, *PAGE_PROFILES)
        )
        first: Any = None
        for profile in ladder:
            found = self._once(call, document, sql, params, profile, validator)
            kind = kind_of(found)
            if kind in ("QueryRows", "QueryCatalogRead"):
                return found
            if kind == "QueryUnavailable":
                raise unavailable(self.name, found)
            first = first if first is not None else found
            if not _tries_next(found, profile):
                break
        raise refusal(self.name, first)

    def _once(
        self,
        call: Call,
        document: str,
        sql: str,
        params: dict[str, Any],
        profile: str | None,
        validator: str | None = None,
    ) -> Any:
        options: dict[str, Any] = {"read_profile": profile} if profile else {}
        if validator is not None:
            outcome = call.assembly.query_with_catalog_in_transaction(
                call.tx,
                sql=sql,
                document_ids=(document,),
                parameters=params or None,
                catalog_validator=validator,
                maximum_rows=MAXIMUM_ROWS,
                maximum_bytes=READER_BYTES,
                **options,
            )
            return call.unwrap(outcome, mapped)
        outcome = call.assembly.query_in_transaction(
            call.tx,
            sql=sql,
            document_ids=(document,),
            parameters=params or None,
            maximum_rows=MAXIMUM_ROWS,
            maximum_bytes=READER_BYTES,
            **options,
        )
        return call.unwrap(outcome, mapped)

    def _answer(self, found: Any, limit: int, info: ModuleInfo | None, whole: bool) -> Answer:
        position = found.as_of
        if position is None:
            raise Unavailable(self.name, "unreachable", "Truss stated no read position")
        names = tuple(found.columns)
        rows = [row_of(names, raw, whole) for raw in found.rows]
        return Answer(
            columns_of(names, rows, info),
            tuple(rows[:limit]),
            len(rows) > limit,
            Position(value=position.value, at=position.at),
        )


def _same_sources(catalog: Any, module: str, document: str, documents: Any) -> bool:
    """Whether the original source Truss returned is the document, at the digest, that the catalog
    this person was shown names for the module."""
    entry = next((e for e in catalog.modules if e["moduleId"] == module), None)
    if entry is None or entry["documentId"] != document:
        return False
    return any(d.document_id == document and d.sha256 == entry["documentSha256"] for d in documents)


def _tries_next(found: Any, profile: str | None) -> bool:
    """Whether the next profile is worth a compile. With no profile Truss asks for a page profile (a
    keyset continuation) with one refusal; a page profile that does not fit says so as unsupported."""
    if kind_of(found) != "QueryRefused" or found.code != "unsupported_query":
        return False
    if profile is not None:
        return True
    return any(d.code == "WFT-CAPABILITY" for d in found.diagnostics)
