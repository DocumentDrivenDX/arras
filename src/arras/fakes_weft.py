# SPDX-License-Identifier: MIT OR Apache-2.0
"""The memory adapter's stand-in for Weft: a declared subset of Weft SQL 0.2 (CONTRACT-001,
CONTRACT-004), and the Weft read profiles it serves.

Arras defines no query language; a backend that serves `query` hosts Weft and compiles the
statement itself. The memory adapter cannot (Weft gives no plan without a registered backend
binding), so it reads a subset of Weft's syntax (`arras.fakes_sql`), resolves it against the
named module (`arras.fakes_plan`) and evaluates it as a small relational pipeline over its rows
(`arras.fakes_eval`). `SUBSET` is everything it serves; every other construct is `Unsupported`
carrying that list. It is not Weft and makes no claim about Weft: the conformance corpus, the
statement check and the differential test against Weft's own parser are the only claims.

Profiles. The named profiles keep Weft's rules: `entity-page` and `related-entity-page` are one
source in key order with a `LIMIT`; `count-summary` is `COUNT(*)` with grouped scalars and equality
filters, inner joins admitted, a grouped count ordered by its whole grouping with a `LIMIT`.
`general` is the unprofiled dialect (joins, `SUM`, grouping, any order), which Weft does not
bound, so the memory adapter bounds it itself: a general statement names a `LIMIT` (or is a global
aggregate, one row), and the join work it does may not pass `fakes_eval.MAX_WORK` (`Unsupported`, a
bound of the memory adapter's, not of the request). A declared `general` covers every shape the
named profiles describe, since each of those is bounded too.
"""

from __future__ import annotations

from arras.errors import Unsupported
from arras.fakes_domain import domains
from arras.fakes_plan import (
    COUNT,
    ENTITY,
    GENERAL,
    RELATED,
    Plan,
    bounded,
    profiles_needed,
    resolve_plan,
    shape_hint,
)
from arras.fakes_sql import SUBSET, Ident, Query, parse
from arras.model import ModuleInfo
from arras.results import WeftSupport
from arras.types import Statement

# A fake version, and the Weft read profiles whose shapes the subset serves.
WEFT = WeftSupport("weft-sql/0.2.0+memory-subset", (ENTITY, RELATED, COUNT, GENERAL))

__all__ = [
    "COUNT",
    "ENTITY",
    "GENERAL",
    "RELATED",
    "SUBSET",
    "WEFT",
    "Ident",
    "Plan",
    "Query",
    "check_profiles",
    "parse",
    "profiles_needed",
    "resolve",
]


def check_profiles(plan: Plan, weft: WeftSupport | None) -> None:
    """`Unsupported` unless the statement takes the shape of a profile the backend declares: its
    own named profile, or `general`, which admits any shape of the subset the memory adapter can
    bound."""
    declared = weft.profiles if weft is not None else ()
    needed = profiles_needed(plan)[0]
    if needed in declared and (needed != GENERAL or bounded(plan)):
        return
    if GENERAL in declared and bounded(plan):
        return
    version = weft.version if weft is not None else "no Weft"
    served = f"{version}: {', '.join(declared) or 'no profiles'}"
    if needed == GENERAL or GENERAL in declared:  # the shape it lacks
        raise Unsupported(shape_hint(plan), [served, *SUBSET])
    raise Unsupported(f"profile {needed}", [served, *SUBSET])


def resolve(statement: Statement, module: ModuleInfo, document: bytes | None = None) -> Plan:
    """Parse and resolve a statement over the one module the caller named; a statement that reads
    another module is `Unsupported` (an answer carries one module's revision). With the module's
    registered `document`, literals and parameters are held to its fields' numeric domains."""
    found = domains(document) if document is not None else None
    return resolve_plan(parse(statement.sql, statement.params), module, found)
