# SPDX-License-Identifier: MIT OR Apache-2.0
"""Value types of the interface (CONTRACT-001, CONTRACT-002)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Literal

Consistency = Literal["latest", "bulk"]


@dataclass(frozen=True)
class Principal:
    user: str
    token: str = field(repr=False)
    groups: tuple[str, ...] = ()
    admin: bool = False  # the host's administrative principal: registry, handlers, imports


@dataclass(frozen=True)
class Position:
    """Opaque feed or transaction position; only the issuing adapter interprets `value`."""

    value: str
    at: datetime


@dataclass(frozen=True)
class Revision:
    """A module's revision as its authority states it: one entry per backend that publishes one,
    keyed by the host's name for it (`{"memory": 3}`). A value is an integer, text, or `None` while
    unknown, and means something only to the backend that issued it: no two are comparable."""

    by_backend: Mapping[str, int | str | None] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_backend", MappingProxyType(dict(self.by_backend)))

    @classmethod
    def from_wire(cls, raw: Mapping[str, Any]) -> Revision:
        """A revision as a caller states it: an object keyed by backend name whose values are an
        integer, text or null. A `ValueError` says what is wrong."""
        for name, value in raw.items():
            if not isinstance(name, str) or not name:  # pyright: ignore[reportUnnecessaryIsInstance]
                raise ValueError("a revision is keyed by backend name")
            if value is not None and (isinstance(value, bool) or not isinstance(value, int | str)):
                raise ValueError(f"{name}: an integer, text or null")
        return cls(raw)

    def __getitem__(self, backend: str) -> int | str | None:
        return self.by_backend.get(backend)

    def __hash__(self) -> int:
        return hash(tuple(sorted(self.by_backend.items(), key=lambda kv: kv[0])))


@dataclass(frozen=True)
class Freshness:
    backend: str
    as_of: Position
    consistency: Consistency


@dataclass(frozen=True)
class Statement:
    """A Weft SQL statement and its parameters, exactly as the caller gave them (CONTRACT-001,
    CONTRACT-004). Arras neither parses nor rewrites either: the serving backend compiles it."""

    sql: str
    params: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))

    def __hash__(self) -> int:
        return hash((self.sql, repr(sorted(self.params.items(), key=lambda kv: kv[0]))))


@dataclass(frozen=True)
class Column:
    name: str
    scalar: bool
    type: str


@dataclass(frozen=True)
class Rows:
    columns: tuple[Column, ...]
    rows: tuple[Mapping[str, Any], ...]
    truncated: bool  # the `limit` cap cut the result; continuation is the statement's own
    freshness: Freshness
    revision: Revision
