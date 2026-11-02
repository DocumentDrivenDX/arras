# SPDX-License-Identifier: MIT OR Apache-2.0
"""What the registry holds about a module: its types, relationships and placement (CONTRACT-002)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from arras.types import Revision

if TYPE_CHECKING:
    from arras.actions import ActionInfo
    from arras.results import BackendStatus

Cardinality = Literal["one", "optional", "many"]
LatencyClass = Literal["interactive", "batch"]
SearchMode = Literal["none", "substring"]  # `word` and `ranked` are reserved (CONTRACT-010)
MetadataProfile = Literal["legacy-arras/1", "umf-core-metadata/1", "arras-umf-set/1"]
ActionProfile = Literal["arras-umf-set/1"]

SCALAR_FAMILIES = ("string", "integer", "decimal", "boolean", "binary", "timestamp")
# Scalars `query` may select as columns, filter on, or count by (CONTRACT-001).
COLUMN_SCALARS = ("string", "integer", "decimal", "boolean")


@dataclass(frozen=True)
class Placement:
    """Where a module lives, as the host decides it (CONTRACT-002), never the document.

    `record` is the reader that is the system of record for the module's graph: it serves `latest`
    and holds the registered document and the revision. `replicas` are other readers, in the order
    a `bulk` read tries them. `providers` binds an action (`module.Action`) to the backend that
    runs it; an action it does not list runs on the record store."""

    record: str
    replicas: tuple[str, ...] = ()
    providers: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}), hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "providers", MappingProxyType(dict(self.providers)))

    def provider_of(self, action: str) -> str:
        return self.providers.get(action, self.record)

    @property
    def readers(self) -> tuple[str, ...]:
        return (self.record, *self.replicas)


UNPLACED = Placement("")  # what a document or a backend's own catalog says: nothing about placement


@dataclass(frozen=True)
class PropertyInfo:
    name: str
    type: str  # a scalar family, or the name of a structured value
    scalar: bool
    cardinality: Cardinality

    @property
    def required(self) -> bool:
        return self.cardinality == "one"


@dataclass(frozen=True)
class Capabilities:
    """What one backend serves for one type (CONTRACT-004); supplied by the backend."""

    read: bool = False
    columns: tuple[str, ...] = ()
    relationships: tuple[str, ...] = ()
    count: bool = False
    mutable: bool = False
    latency_class: LatencyClass = "batch"
    # Text search (CONTRACT-010): `substring` when the backend matches a structured text match on
    # the string properties in `searchable`; `none` otherwise.
    search: SearchMode = "none"
    searchable: tuple[str, ...] = ()


@dataclass(frozen=True)
class EntityTypeInfo:
    name: str  # module-qualified
    key: str
    properties: tuple[PropertyInfo, ...]
    # Supplied by the backends, so it takes no part in equality: a re-registration compares only
    # what the document derives.
    capabilities: Mapping[str, Capabilities] = field(
        default_factory=lambda: MappingProxyType({}), compare=False, hash=False
    )

    @property
    def local_name(self) -> str:
        return self.name.split(".", 1)[1]

    def property(self, name: str) -> PropertyInfo | None:
        return next((p for p in self.properties if p.name == name), None)


@dataclass(frozen=True)
class ValueTypeInfo:
    """A record without identity: a structured value inside its owner."""

    name: str  # module-qualified
    properties: tuple[PropertyInfo, ...]


@dataclass(frozen=True)
class Multiplicity:
    min: int
    max: int | None  # None is unbounded

    def __str__(self) -> str:
        return f"{self.min}..{'*' if self.max is None else self.max}"


@dataclass(frozen=True)
class RelationshipInfo:
    name: str
    source: tuple[str, ...]
    target: tuple[str, ...]
    source_multiplicity: Multiplicity
    target_multiplicity: Multiplicity
    lifecycle: str
    inverse: str | None = None


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    placement: Placement
    revision: Revision
    entity_types: tuple[EntityTypeInfo, ...]
    relationships: tuple[RelationshipInfo, ...] = ()
    value_types: tuple[ValueTypeInfo, ...] = ()
    actions: tuple[ActionInfo, ...] = ()
    # what `describe` adds: each backend's status. Not part of what a document derives.
    status: Mapping[str, BackendStatus] = field(
        default_factory=lambda: MappingProxyType({}), compare=False, hash=False
    )
    metadata_profile: MetadataProfile = "legacy-arras/1"

    def entity_type(self, local_name: str) -> EntityTypeInfo | None:
        return next((t for t in self.entity_types if t.local_name == local_name), None)
