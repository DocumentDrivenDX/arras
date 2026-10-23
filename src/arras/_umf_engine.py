# SPDX-License-Identifier: MIT OR Apache-2.0
"""Private, inert bridge to the selected official UMF Python engine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import version
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from umf import Registry, Validation

    OfficialRegistryFactory = Callable[[], Registry]
    OfficialValidator = Callable[[object, Registry | None], Validation]
else:
    OfficialRegistryFactory = Callable[..., Any]
    OfficialValidator = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class EngineDiagnostic:
    code: str
    path: str
    message: str
    severity: str


@dataclass(frozen=True, slots=True)
class EngineResult:
    distribution: str
    version: str
    valid: bool
    complete: bool
    diagnostics: tuple[EngineDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class ReaderRefusal:
    distribution: str
    version: str


def read_and_validate(text: str) -> EngineResult | ReaderRefusal:
    """Use the official reader and validator with a new empty registry."""
    sdk = cast(Any, import_module("umf"))

    installed_version = version("umf-core")
    try:
        reader = cast(Callable[[str, str], Any], sdk.read_json_value)
        raw: object = reader(text, "json")
    except ValueError:
        return ReaderRefusal("umf-core", installed_version)
    registry_factory = cast(OfficialRegistryFactory, sdk.Registry)
    validator = cast(OfficialValidator, sdk.validate_document)
    result = validator(raw, registry_factory())
    diagnostics = tuple(
        EngineDiagnostic(
            item.code,
            item.path,
            item.message,
            item.severity,
        )
        for item in result.diagnostics
    )
    return EngineResult("umf-core", installed_version, result.valid, result.complete, diagnostics)


def read_typed_snapshot(text: str) -> object:
    """Read a post-validation document through the official typed reader.

    The caller is responsible for admitting this exact text first. Returning only an
    `exclude_unset` model dump keeps the mutable official model inside this bridge while
    preserving which optional fields were explicitly supplied.
    """
    sdk = cast(Any, import_module("umf"))
    reader = cast(Callable[[str, str], Any], sdk.read_document)
    document = reader(text, "json")
    return document.model_dump(mode="python", exclude_unset=True)
