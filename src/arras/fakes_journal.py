# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The fake authority's audit journal (CONTRACT-001, Audit reads; CONTRACT-004).

A change is recorded in the working state of a group, so a group that fails, a dry run and a
refusal leave no row. A reader needs the `journal` grant, which is separate from `read`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from arras.actions import Create, Delete, Link, Plan, Ref, Unlink, Update
from arras.errors import Invalid, Violation
from arras.results import Change, ChangesPage, Load, LoadsPage
from arras.types import Freshness, Position, Principal

MAX_PAGE = 100


def _ref(r: Ref) -> dict[str, str]:
    return {"type": r.type, "key": r.key}


def ops_of(plan: Plan, touched: Mapping[Ref, int]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in plan.effects:
        if isinstance(e, Create | Update | Delete):
            kind = (
                "create"
                if isinstance(e, Create)
                else "update"
                if isinstance(e, Update)
                else "delete"
            )
            out.append(
                {"kind": kind, "type": e.ref.type, "key": e.ref.key, "version": touched.get(e.ref)}
            )
        elif isinstance(e, Link | Unlink):
            kind = "link" if isinstance(e, Link) else "unlink"
            out.append(
                {
                    "kind": kind,
                    "relationship": e.relationship,
                    "source": _ref(e.source),
                    "target": _ref(e.target),
                }
            )
    return out


def record_change(
    work: Any,
    *,
    group: str,
    now: datetime,
    by: str,
    backend: str,
    entries: Sequence[tuple[Plan, Mapping[Ref, int]]],
) -> None:
    """One change for a group: every plan in it, in order."""
    plan0 = entries[0][0]
    ops = tuple(op for plan, touched in entries for op in ops_of(plan, touched))
    work.changes.append(
        Change(group, now, by, plan0.action, plan0.action.split(".", 1)[0], ops, backend)
    )


def _touches(c: Change, type_: str, key: str | None) -> bool:
    for op in c.ops:
        refs = [op] if "type" in op else [op["source"], op["target"]]
        if any(r["type"] == type_ and (key is None or r["key"] == key) for r in refs):
            return True
    return False


def _page(rows: list[Any], limit: int, after: str | None) -> tuple[tuple[Any, ...], str | None]:
    if not 1 <= limit <= MAX_PAGE:
        raise Invalid([Violation("limit", "bound", f"limit is an integer from 1 to {MAX_PAGE}")])
    try:
        start = int(after) if after else 0
    except ValueError:
        raise Invalid([Violation("after", "cursor", "not a cursor of this statement")]) from None
    if start < 0:
        raise Invalid([Violation("after", "cursor", "not a cursor of this statement")])
    end = start + limit
    return tuple(rows[start:end]), (str(end) if end < len(rows) else None)


class JournalReads:
    """`changes` and `loads` for `MemoryStore`."""

    name: str
    state: Any
    access: Any

    def gate(self, principal: Principal, module: str | None, mode: Any, op: str) -> None: ...

    def position(self) -> Position: ...

    def changes(
        self,
        principal: Principal,
        *,
        module: str | None,
        type: str | None,  # noqa: A002
        key: str | None,
        by: str | None,
        action: str | None,
        group: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        after: str | None,
    ) -> ChangesPage:
        self.gate(principal, module, "journal", "changes")
        if key is not None and type is None:
            raise Invalid([Violation("key", "scope", "a key names a type")])
        rows = [
            c
            for c in reversed(self.state.changes)
            if self.access.allowed(principal, c.module, "journal")
            and (module is None or c.module == module)
            and (type is None or _touches(c, type, key))
            and (by is None or c.by == by)
            and (action is None or c.action == action)
            and (group is None or c.group == group)
            and (since is None or c.at >= since)
            and (until is None or c.at <= until)
        ]
        items, nxt = _page(rows, limit, after)
        return ChangesPage(items, nxt, False, Freshness(self.name, self.position(), "latest"))

    def loads(
        self, principal: Principal, module: str, *, limit: int, after: str | None
    ) -> LoadsPage:
        self.gate(principal, module, "journal", "loads")
        rows = [ld for ld in reversed(self.state.loads) if ld.module == module]
        items, nxt = _page(rows, limit, after)
        return LoadsPage(items, nxt, False, Freshness(self.name, self.position(), "latest"))


__all__ = ["JournalReads", "Load", "record_change"]
