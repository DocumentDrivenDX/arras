# SPDX-License-Identifier: MIT OR Apache-2.0
"""Immutable request and report values for the offline compatibility doctor."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

from arras.distribution import DistributionConfig, TelemetryNames

_MAX_ITEMS = 32


class DistributionInvalid(ValueError):
    """A structurally valid distribution request violates its typed value constraints."""


def _telemetry_fields(value: object) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
    """The closed JSON shape for typed telemetry names; semantic validation stays shared."""
    if type(value) is not dict:
        raise ValueError("telemetry must be an object")
    fields = cast(dict[str, Any], value)
    if set(fields) - set(TelemetryNames.__dataclass_fields__) or not all(
        isinstance(item, str) or (key == "service_name" and item is None)
        for key, item in fields.items()
    ):
        raise ValueError("telemetry fields have invalid shape")
    return fields


def pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def load_json_object(raw: bytes) -> dict[str, Any]:
    value: object = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return cast(dict[str, Any], value)


def _is_instance(value: object, kind: type[object]) -> bool:
    return isinstance(value, kind)


def _validate_request(request: DoctorRequest) -> None:
    raw_maps: tuple[tuple[str, object], ...] = (
        ("expected_packages", request.expected_packages),
        ("expected_contracts", request.expected_contracts),
        ("required_python_exports", request.required_python_exports),
        ("required_npm_exports", request.required_npm_exports),
    )
    for name, raw in raw_maps:
        if not _is_instance(raw, Mapping):
            raise ValueError(f"{name}: mapping required")
    raw_tuples: tuple[tuple[str, object], ...] = (
        ("required_role_tokens", request.required_role_tokens),
        ("env_names", request.env_names),
        ("config_files", request.config_files),
        ("module_documents", request.module_documents),
    )
    for name, raw in raw_tuples:
        if not _is_instance(raw, tuple):
            raise ValueError(f"{name}: tuple required")
    _validate_request_maps(request)
    if any(
        not isinstance(item, str) for item in cast(tuple[object, ...], request.required_role_tokens)
    ):
        raise ValueError("required_role_tokens: string values required")
    if any(not isinstance(item, str) for item in cast(tuple[object, ...], request.env_names)):
        raise ValueError("env_names: string values required")
    if any(not isinstance(item, Path) for item in cast(tuple[object, ...], request.config_files)):
        raise ValueError("config_files: Path values required")
    if any(
        not isinstance(item, Path) for item in cast(tuple[object, ...], request.module_documents)
    ):
        raise ValueError("module_documents: Path values required")
    object.__setattr__(
        request, "expected_packages", MappingProxyType(dict(request.expected_packages))
    )
    object.__setattr__(
        request, "expected_contracts", MappingProxyType(dict(request.expected_contracts))
    )
    object.__setattr__(
        request,
        "required_python_exports",
        MappingProxyType({k: tuple(v) for k, v in request.required_python_exports.items()}),
    )
    object.__setattr__(
        request,
        "required_npm_exports",
        MappingProxyType({k: tuple(v) for k, v in request.required_npm_exports.items()}),
    )
    object.__setattr__(request, "required_role_tokens", tuple(request.required_role_tokens))
    object.__setattr__(request, "env_names", tuple(request.env_names))
    object.__setattr__(request, "config_files", tuple(request.config_files))
    object.__setattr__(request, "module_documents", tuple(request.module_documents))
    if request.module_profile is not None and not isinstance(
        cast(object, request.module_profile), str
    ):
        raise ValueError("module_profile must be a string")
    if request.distribution is not None and not isinstance(
        cast(object, request.distribution), DistributionConfig
    ):
        raise ValueError("distribution must be a DistributionConfig")
    if request.asset_manifest is not None and not isinstance(
        cast(object, request.asset_manifest), Path
    ):
        raise ValueError("asset_manifest must be a Path")
    if request.theme_manifest is not None and not isinstance(
        cast(object, request.theme_manifest), Path
    ):
        raise ValueError("theme_manifest must be a Path")
    paths = (*request.config_files, *request.module_documents)
    if len(paths) > _MAX_ITEMS:
        raise ValueError("config_files and module_documents: at most 32 paths")


def _validate_request_maps(request: DoctorRequest) -> None:
    for package, version in request.expected_packages.items():
        if (
            not _is_instance(package, str)
            or not _is_instance(version, str)
            or not package.strip()
            or not version.strip()
        ):
            raise ValueError("expected_packages: nonempty package names and versions required")
    for key, version in cast(Mapping[object, object], request.expected_contracts).items():
        if not isinstance(key, str) or type(version) is not int or version < 1:
            raise ValueError("expected_contracts: names and positive integer versions required")
    for name in ("required_python_exports", "required_npm_exports"):
        mapping = getattr(request, name)
        for key, names in cast(Mapping[object, object], mapping).items():
            if (
                not isinstance(key, str)
                or not isinstance(names, tuple)
                or any(not isinstance(item, str) for item in cast(tuple[object, ...], names))
            ):
                raise ValueError(f"{name}: string keys and tuple of names required")


@dataclass(frozen=True, slots=True)
class DoctorRequest:
    expected_packages: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    expected_contracts: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))
    required_python_exports: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    required_npm_exports: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    required_role_tokens: tuple[str, ...] = ()
    distribution: DistributionConfig | None = None
    env_names: tuple[str, ...] = ()
    config_files: tuple[Path, ...] = ()
    asset_manifest: Path | None = None
    theme_manifest: Path | None = None
    module_documents: tuple[Path, ...] = ()
    module_profile: str | None = None

    def __post_init__(self) -> None:
        _validate_request(self)


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: Literal["error", "unsupported", "warning", "info"]
    surface: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    ok: bool
    complete: bool
    observed: Mapping[str, object]
    diagnostics: tuple[Diagnostic, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed", _freeze(self.observed))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "ok": self.ok,
            "complete": self.complete,
            "observed": _json_value(self.observed),
            "diagnostics": [
                {
                    "code": d.code,
                    "severity": d.severity,
                    "surface": d.surface,
                    "path": d.path,
                    "message": d.message,
                }
                for d in self.diagnostics
            ],
        }


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        entries = cast(Mapping[object, object], value)
        return MappingProxyType({str(k): _freeze(v) for k, v in entries.items()})
    if isinstance(value, tuple | list):
        items = cast(tuple[object, ...] | list[object], value)
        return tuple(_freeze(v) for v in items)
    return value


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        entries = cast(Mapping[object, object], value)
        return {str(k): _json_value(v) for k, v in entries.items()}
    if isinstance(value, tuple | list):
        items = cast(tuple[object, ...] | list[object], value)
        return [_json_value(v) for v in items]
    return value


def request_error_report() -> DoctorReport:
    return DoctorReport(
        False,
        True,
        MappingProxyType({"provenance": "request rejected"}),
        (
            Diagnostic(
                "request_invalid", "error", "request", "request", "request is invalid or unsafe"
            ),
        ),
    )


def distribution_error_report() -> DoctorReport:
    return DoctorReport(
        False,
        True,
        MappingProxyType({"provenance": "request rejected"}),
        (
            Diagnostic(
                "distribution_invalid",
                "error",
                "distribution",
                "distribution",
                "distribution settings violate Brand or launcher constraints",
            ),
        ),
    )
