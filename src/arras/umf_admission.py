# SPDX-License-Identifier: MIT OR Apache-2.0
"""Admission results from the official UMF core validator.

This module reports source admission only. A completed valid result is not an
execution, registration, or authorization capability.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal

from arras.errors import Unsupported

_ENGINE_DISTRIBUTION = "umf-core"
_ENGINE_VERSION = "0.10.0"
_PROFILE = "umf-core-empty-registry/1"
_MAX_SOURCE_BYTES = 16 * 1024 * 1024
_SourceAuthority = Literal["umf", "arras-source"]
_ValidationStatus = Literal["not_run", "completed"]


@dataclass(frozen=True, slots=True)
class UmfDiagnostic:
    """One ordered official or Arras source-boundary diagnostic."""

    authority: _SourceAuthority
    code: str
    path: str
    message: str
    severity: str

    def __post_init__(self) -> None:
        if self.authority not in ("umf", "arras-source"):
            raise ValueError("diagnostic authority is not recognized")
        if any(
            type(value) is not str for value in (self.code, self.path, self.message, self.severity)
        ):
            raise TypeError("diagnostic fields must be strings")


@dataclass(frozen=True, slots=True)
class AdmissionReport:
    """Immutable result preserving the exact admitted input bytes."""

    source: bytes = field(repr=False)
    source_sha256: str
    engine_distribution: str
    engine_version: str
    validation_profile: str
    validation_status: _ValidationStatus
    valid: bool | None
    complete: bool | None
    diagnostics: tuple[UmfDiagnostic, ...]

    def __post_init__(self) -> None:
        if type(self.source) is not bytes:
            raise TypeError("source must be immutable bytes")
        if self.source_sha256 != hashlib.sha256(self.source).hexdigest():
            raise ValueError("source_sha256 does not match source")
        if (self.engine_distribution, self.engine_version, self.validation_profile) != (
            _ENGINE_DISTRIBUTION,
            _ENGINE_VERSION,
            _PROFILE,
        ):
            raise ValueError("admission engine identity is not recognized")
        if type(self.diagnostics) is not tuple or any(
            type(item) is not UmfDiagnostic for item in self.diagnostics
        ):
            raise TypeError("diagnostics must be an immutable tuple of UmfDiagnostic")
        if self.validation_status == "not_run":
            if self.valid is not None or self.complete is not None:
                raise ValueError("not_run results cannot claim official validation fields")
            if len(self.diagnostics) != 1:
                raise ValueError("not_run results require one source diagnostic")
            diagnostic = self.diagnostics[0]
            if (
                diagnostic.authority != "arras-source"
                or diagnostic.path != "document"
                or diagnostic.code not in ("source_profile", "source_limit")
            ):
                raise ValueError("not_run diagnostic must describe the source boundary")
        elif self.validation_status == "completed":
            if type(self.valid) is not bool or type(self.complete) is not bool:
                raise ValueError("completed results require official boolean fields")
            if any(item.authority != "umf" for item in self.diagnostics):
                raise ValueError("completed diagnostics must come from UMF")
        else:
            raise ValueError("validation_status must be not_run or completed")


def admit_document(document: bytes | str) -> AdmissionReport:
    """Preserve and validate JSON source with the official empty-registry profile."""
    if type(document) is bytes:
        source = document
    elif type(document) is str:
        try:
            source = document.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raise ValueError("document text must be strictly UTF-8 encodable") from None
    else:
        raise TypeError("document must be bytes or str")

    if len(source) > _MAX_SOURCE_BYTES:
        return _not_run(source, "source_limit")
    try:
        text = source.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _not_run(source, "source_profile")

    try:
        from arras._umf_engine import ReaderRefusal, read_and_validate

        result = read_and_validate(text)
    except ModuleNotFoundError as error:
        if error.name != "umf":
            raise
        raise Unsupported("official UMF admission", ["install the arras[umf] extra"]) from None

    if result.distribution != _ENGINE_DISTRIBUTION or result.version != _ENGINE_VERSION:
        raise RuntimeError("the loaded UMF engine does not match the selected released profile")
    if isinstance(result, ReaderRefusal):
        return _not_run(source, "source_profile")
    diagnostics = tuple(
        UmfDiagnostic("umf", item.code, item.path, item.message, item.severity)
        for item in result.diagnostics
    )
    return AdmissionReport(
        source,
        hashlib.sha256(source).hexdigest(),
        result.distribution,
        result.version,
        _PROFILE,
        "completed",
        result.valid,
        result.complete,
        diagnostics,
    )


def _not_run(source: bytes, code: Literal["source_profile", "source_limit"]) -> AdmissionReport:
    diagnostic = UmfDiagnostic(
        "arras-source",
        code,
        "document",
        "source exceeds the admission profile or could not be read as strict UTF-8 JSON",
        "error",
    )
    return AdmissionReport(
        source,
        hashlib.sha256(source).hexdigest(),
        _ENGINE_DISTRIBUTION,
        _ENGINE_VERSION,
        _PROFILE,
        "not_run",
        None,
        None,
        (diagnostic,),
    )
