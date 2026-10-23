# SPDX-License-Identifier: MIT OR Apache-2.0
"""Private, inert bridge to the selected official UMF Python engine."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import version
from time import monotonic_ns
from typing import TYPE_CHECKING, Any, cast

from arras.errors import Invalid, Unsupported, Violation

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


_ACTION_RUNTIME_CALLS = (
    "create_action_engine",
    "prepare_single_set_action",
    "admit_generated_action_invocation",
    "admit_generated_record_values",
)
# Candidate-2 meter probes observed a 72,551,564-unit peak; this per-closure
# ceiling leaves bounded headroom and must be remeasured for a new SDK packet.
_ACTION_RUNTIME_MAX_WORK = 100_000_000
_ACTION_RUNTIME_DEADLINE_MS = 5_000
_SAFE_ACTION_ERROR_PATH = re.compile(r"(?:/[A-Za-z0-9_-][A-Za-z0-9_.:-]{0,127}){1,16}\Z")
_ACTION_ERROR_PATH_SEGMENTS = frozenset(
    {
        "action",
        "authorization",
        "contract",
        "entityParameter",
        "idempotency_key",
        "inputs",
        "invocation",
        "keyFields",
        "kind",
        "model",
        "profile",
        "record",
        "resources",
        "schema",
        "source",
        "target",
        "values",
    }
)


def _new_action_engine(runtime: Any) -> Any:
    def now() -> int:
        return monotonic_ns() // 1_000_000

    return runtime.create_action_engine(
        profile="cooperative",
        max_work=_ACTION_RUNTIME_MAX_WORK,
        now=now,
        deadline_ms=now() + _ACTION_RUNTIME_DEADLINE_MS,
    )


def _load_action_runtime() -> Any | None:
    """Load the optional candidate runtime only when the opted-in profile asks for it."""
    try:
        runtime = import_module("umf.action_runtime")
    except ModuleNotFoundError as exc:
        if exc.name in ("umf", "umf.action_runtime"):
            return None
        raise
    if any(not callable(getattr(runtime, name, None)) for name in _ACTION_RUNTIME_CALLS):
        return None
    return runtime


def action_runtime_available() -> bool:
    """Report whether the official packaged engine and candidate entrypoints can initialize.

    This does not establish that any action is compatible, complete, or executable.
    """
    runtime = _load_action_runtime()
    if runtime is None:
        return False
    try:
        engine = _new_action_engine(runtime)
    except Exception as error:
        if not _is_official_action_error(error):
            raise
        code = getattr(error, "code", None)
        if code == "ACTION_RUNTIME_UNSUPPORTED":
            return False
        translated = translate_action_error(code, getattr(error, "path", None))
        if translated is None:
            raise
        raise translated from None
    return engine is not None


def call_action_runtime(operation: str, request: dict[str, object]) -> dict[str, object]:
    """Invoke one named official action-runtime operation with packaged resources.

    No fallback engine, source-tree resource lookup, or local semantic implementation is
    provided. Native SDK exceptions deliberately propagate with their original typed meaning.
    """
    if operation not in _ACTION_RUNTIME_CALLS[1:]:
        raise ValueError("unknown official action-runtime operation")
    runtime = _load_action_runtime()
    if runtime is None:
        raise Unsupported(
            "official UMF single-SET runtime",
            ["install the separately qualified optional UMF action-runtime candidate"],
        )
    try:
        engine = _new_action_engine(runtime)
        result = getattr(runtime, operation)(engine, request)
    except Exception as error:
        if not _is_official_action_error(error):
            raise
        translated = translate_action_error(
            getattr(error, "code", None), getattr(error, "path", None)
        )
        if translated is None:
            raise
        raise translated from None
    if type(result) is not dict:
        raise TypeError("official UMF action runtime returned a non-object result")
    return cast(dict[str, object], result)


def _is_official_action_error(error: Exception) -> bool:
    """Match only typed errors actually defined by the official binding, if importable."""
    try:
        error_module = import_module("umf.rust_codegen")
    except ImportError:
        return False
    error_types = tuple(
        error_type
        for class_name in ("UmfCodegenError", "UmfCoreError")
        if isinstance((error_type := getattr(error_module, class_name, None)), type)
    )
    return bool(error_types) and isinstance(error, error_types)


def translate_action_error(code: object, path: object) -> Invalid | Unsupported | None:
    """Map documented SDK error identifiers without exposing SDK prose or input values."""
    if type(code) is not str:
        return None
    safe_path = (
        path
        if type(path) is str
        and len(path) <= 512
        and _SAFE_ACTION_ERROR_PATH.fullmatch(path) is not None
        and all(part not in (".", "..") for part in path.split("/")[1:])
        and all(part in _ACTION_ERROR_PATH_SEGMENTS for part in path.split("/")[1:])
        else "action"
    )
    if code == "ACTION_RUNTIME_INTEGRITY":
        return Invalid(
            [
                Violation(
                    "schema", "schema_mismatch", "the official runtime rejected its source pins"
                )
            ]
        )
    if code in {"ACTION_RUNTIME_UNSUPPORTED", "RESOURCE_PROFILE_UNAVAILABLE"}:
        return Unsupported("official UMF single-SET profile", ["single string SET actions"])
    if code in {
        "ACTION_RUNTIME_INVALID",
        "REQUEST",
        "WIRE_FORMAT",
        "NON_JSON",
        "UNSUPPORTED_KEY",
        "UNSUPPORTED_VALUE",
        "NUMBER",
        "DUPLICATE_KEY",
    }:
        return Invalid(
            [Violation(safe_path, "umf_invalid", "the official runtime rejected the request")]
        )
    if code in {"LIMIT", "RESOURCE_LIMIT", "DEADLINE", "CANCELLED"}:
        return Invalid(
            [Violation(safe_path, "limit_exceeded", "the official runtime reached a bounded limit")]
        )
    return None
