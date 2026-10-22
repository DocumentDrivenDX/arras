# SPDX-License-Identifier: MIT OR Apache-2.0
"""`describe` and `status` of the Truss adapter (CONTRACT-004, CONTRACT-005).

`describe` takes no principal and makes no call: it states the roles, the Weft dialect Truss compiles
and, per type, what `query` serves. The types are those of the catalog the operation has just read
for the person (the call scope), and outside such an operation the modules the catalog cache has
served (core reads the catalog before it describes; a process that has served none states no types
yet).

`status` reports, never raises. With an installing connection it is the install-state read on that
connection: Truss refuses an installer every business call but states whether it is installed and at
which release. A backend with none (the MCP process holds no service identity) states what the last
call as a person showed (`Connections.observed()`: available when it reached the database,
unavailable with the reason when it could not), and `not_configured` only before any call.
"""

from __future__ import annotations

from collections.abc import Iterable
from importlib import metadata
from typing import Any, cast

from arras.adapters.truss.connection import Connections
from arras.errors import UNAVAILABLE_REASONS, ArrasError, Refused, Unavailable
from arras.model import COLUMN_SCALARS, Capabilities, EntityTypeInfo, ModuleInfo
from arras.results import BackendInfo, BackendStatus, Reason, WeftSupport

WEFT_DISTRIBUTION = "weft-sql"
WEFT_VERSION = "0.4.49"  # the Weft release Truss's compiled queries are qualified with
WEFT_DIALECT = "weft-sql/0.2.0"  # the dialect Truss compiles (its backend 0.4.40, interface 0.2.6)

# The read profiles `query` proves against Truss (the read corpus passes): Truss serves joins and
# ungrouped shapes with no profile at all, so `general` is declared with the three named ones. Its
# bound is Truss's (rows, bytes and scan), not a statement's `LIMIT`.
PROFILES = ("entity-page", "related-entity-page", "count-summary", "general")


def weft_support() -> WeftSupport | None:
    """The dialect and the read profiles `query` serves, when the Weft release Truss's queries need is
    the installed one."""
    try:
        found = metadata.version(WEFT_DISTRIBUTION)
    except metadata.PackageNotFoundError:
        return None
    return WeftSupport(WEFT_DIALECT, PROFILES) if found == WEFT_VERSION else None


def capabilities(t: EntityTypeInfo, module: ModuleInfo) -> Capabilities:
    """What `query` serves for a type: its key and required scalar properties as columns, the
    relationships it is an end of, counts. Text search is not served (CONTRACT-010). Truss reads and
    writes in about 0.1 to 0.5 s."""
    columns = tuple(
        p.name
        for p in t.properties
        if p.scalar and p.type in COLUMN_SCALARS and (p.required or p.name == t.key)
    )
    relationships = tuple(
        n
        for r in module.relationships
        for n, ends in ((r.name, r.source), (r.inverse, r.target))
        if n and t.name in ends
    )
    return Capabilities(
        read=True,
        columns=columns,
        relationships=relationships,
        count=True,
        mutable=True,
        latency_class="batch",
        search="none",
    )


def describe(name: str, modules: Iterable[ModuleInfo]) -> BackendInfo:
    caps = {t.name: capabilities(t, m) for m in modules for t in m.entity_types}
    return BackendInfo(name, ("reader", "provider"), caps, weft_support(), audit=True)


NOT_INSTALLED = "Truss is not installed here"


def status(name: str, connections: Connections | None) -> BackendStatus:
    if connections is None:
        return BackendStatus(False, "not_configured", "no connection source")
    try:
        call = connections.installer("status")
        if call is None:
            # no installing connection: the install state cannot be read, and a probe would need
            # a person, so the status is what the last per-person call showed (nothing, before one)
            seen = connections.observed()
            return seen or BackendStatus(False, "not_configured", "no installing connection")
        with call as open_call:
            value = open_call.unwrap(
                open_call.assembly.status_in_transaction(open_call.tx), _status_error
            )
    except Refused:
        return BackendStatus(False, "access_denied", "the installing connection is refused")
    except Unavailable as exc:
        reason = exc.reason if exc.reason in UNAVAILABLE_REASONS else None
        return BackendStatus(False, cast(Reason, reason or "unreachable"), exc.detail)
    except ArrasError:
        return BackendStatus(False, "unreachable", "the install state cannot be read")
    except ImportError:  # ModuleNotFoundError too: the extra is absent or broken
        return BackendStatus(False, "not_configured", "the truss extra is not installed")
    if not getattr(value, "installed", False):
        return BackendStatus(False, "not_configured", NOT_INSTALLED)
    return BackendStatus(True)


def _status_error(backend: str, operation: str, failure: Any) -> ArrasError:
    """Truss refuses the install state of a release it does not support as `unsupported_profile`."""
    if getattr(failure, "catalog_code", None) == "unsupported_profile":
        return Unavailable(backend, "unsupported_version", "the installed Truss is another release")
    if getattr(failure, "sql_state", None) == "42501":
        return Unavailable(backend, "access_denied", "the installing connection lacks the grants")
    return Unavailable(backend, "unreachable", f"truss {getattr(failure, 'code', 'failure')}")
