# SPDX-License-Identifier: MIT OR Apache-2.0
"""The state a fake authority keeps, and two helpers both fakes use (CONTRACT-004)."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from arras.actions import Ref
from arras.model import ModuleInfo, RelationshipInfo
from arras.results import Change, Load

Triple = tuple[str, Ref, Ref]  # canonical relationship, source, target


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Entity:
    props: dict[str, Any]
    version: int
    created_by: str
    created_at: datetime
    updated_by: str
    updated_at: datetime
    original_author: str | None = None
    original_at: datetime | None = None
    load_id: str | None = None


@dataclass
class State:
    entities: dict[Ref, Entity] = field(default_factory=dict[Ref, Entity])
    tombstones: set[Ref] = field(default_factory=set[Ref])
    relations: set[Triple] = field(default_factory=set[Triple])
    seq: int = 0
    at: datetime = field(default_factory=utcnow)
    changes: list[Change] = field(default_factory=list[Change])  # the audit journal
    loads: list[Load] = field(default_factory=list[Load])
    declared_replays: dict[tuple[str, str, str, str, str], tuple[str, Any]] = field(
        default_factory=dict[tuple[str, str, str, str, str], tuple[str, Any]]
    )
    declared_tokens: dict[str, tuple[str, str, int]] = field(
        default_factory=dict[str, tuple[str, str, int]]
    )


@dataclass
class Counts:
    created: int = 0
    updated: int = 0
    deleted: int = 0
    linked: int = 0
    unlinked: int = 0


def canonical(mod: ModuleInfo, name: str) -> tuple[RelationshipInfo, bool] | None:
    """The declared relationship a name refers to, and whether the name is its inverse."""
    for r in mod.relationships:
        if name == r.name:
            return r, False
        if name == r.inverse:
            return r, True
    return None


def deep_copy(v: Any) -> Any:
    return copy.deepcopy(v)
