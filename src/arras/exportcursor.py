# SPDX-License-Identifier: MIT OR Apache-2.0
"""The place a page of an export names, and the order that gives it meaning (CONTRACT-003, Export):
shared by every backend that serves `export_records`, so a cursor means the same on each."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any, cast

from arras.errors import Invalid, Violation
from arras.model import ModuleInfo

MAX_PAGE = 500
_BAD_CURSOR = "not a cursor of this export"
_MAX_CURSOR = 1024


def cursor(order: tuple[Any, ...]) -> str:
    """The cursor after the record at `order`: the record's own place in the canonical order, so a
    page resumes after it whatever has been written since."""
    raw = json.dumps(order, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def refuse() -> Invalid:
    return Invalid([Violation("after", "cursor", _BAD_CURSOR)])


def resume_of(after: str) -> tuple[Any, ...]:
    """The place a cursor names: `(0, type, key)` or `(1, relationship, source, target)`."""
    try:
        if len(after) > _MAX_CURSOR:
            raise ValueError(after)
        order: Any = json.loads(base64.urlsafe_b64decode(after + "=" * (-len(after) % 4)))
    except ValueError:  # not base64, not JSON, not text
        raise refuse() from None
    if not isinstance(order, list) or not order or order[0] not in (0, 1):
        raise refuse()
    parts = cast(list[Any], order)[1:]
    if len(parts) != (2 if order[0] == 0 else 3) or not all(isinstance(x, str) for x in parts):
        raise refuse()
    return (order[0], *parts)


def ranker(mod: ModuleInfo) -> Callable[[tuple[Any, ...]], tuple[Any, ...]]:
    """A place with its type or relationship as a declaration index, so places compare in the
    canonical order; a name the module does not declare is `Invalid` (not a cursor of this export)."""
    kinds: tuple[dict[str, int], dict[str, int]] = (
        {t.name: i for i, t in enumerate(mod.entity_types)},
        {r.name: i for i, r in enumerate(mod.relationships)},
    )

    def rank(order: tuple[Any, ...]) -> tuple[Any, ...]:
        table: dict[str, int] = kinds[1 if order[0] else 0]
        at = table.get(order[1])
        if at is None:
            raise refuse()
        return (order[0], at, *order[2:])

    return rank


def check_limit(limit: int) -> None:
    if not 1 <= limit <= MAX_PAGE:
        raise Invalid([Violation("limit", "bound", f"limit is an integer from 1 to {MAX_PAGE}")])
