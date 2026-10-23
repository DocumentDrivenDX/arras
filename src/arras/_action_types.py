# SPDX-License-Identifier: MIT OR Apache-2.0
"""Private typed boundary between official action admission and Arras execution.

These values carry facts produced by the selected UMF action runtime.  They are not public
constructors or an alternate action evaluator; only the semantic bridge may create them.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TypeAlias

from arras.actions import Ref
from arras.model import ModuleInfo

ActionScalar: TypeAlias = str


def _scalar_map(values: Mapping[str, object]) -> Mapping[str, ActionScalar]:
    copied: dict[str, ActionScalar] = {}
    for key, value in values.items():
        if type(key) is not str or not key:
            raise TypeError("action property identifiers must be nonempty strings")
        if type(value) is not str:
            raise TypeError("the selected action profile accepts exact string values only")
        copied[key] = value
    return MappingProxyType(copied)


@dataclass(frozen=True)
class SetBinding:
    """One source-declared input assignment, retaining exact authored identifiers."""

    input_id: str
    field_id: str
    property: str


@dataclass(frozen=True)
class PreparedSetModule:
    """Exact original source and the bounded SET subset bound to its current registration."""

    source: bytes = field(repr=False)
    sha256: str
    module: ModuleInfo
    document_id: str
    source_revision: str
    module_id: str
    record_id: str
    action_id: str
    action_local_id: str
    key_field_id: str
    key_property: str
    entity_parameter: str
    bindings: tuple[SetBinding, ...]
    frames: tuple[str, ...]
    policy_profile: str
    resources: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.policy_profile != "arras.module-write/1":
            raise ValueError("unsupported module-write policy profile")
        if type(self.source) is not bytes:
            raise TypeError("prepared source must be exact bytes")
        digest = hashlib.sha256(self.source).hexdigest()
        if self.sha256 != digest or self.source_revision != f"sha256:{digest}":
            raise ValueError("prepared source identity does not match its exact bytes")
        if any(type(item) is not str or not item for item in self.resources):
            raise TypeError("prepared resources must be exact nonempty identifiers")


@dataclass(frozen=True)
class AdmittedSet:
    """A SET effect materialized by the authoritative UMF action runtime."""

    ref: Ref
    set_values: Mapping[str, ActionScalar]
    inputs_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "set_values", _scalar_map(self.set_values))


@dataclass(frozen=True)
class AdmittedRecord:
    """A record value admitted by the authoritative UMF record/key/value runtime."""

    ref: Ref
    properties: Mapping[str, ActionScalar]

    def __post_init__(self) -> None:
        object.__setattr__(self, "properties", _scalar_map(self.properties))
