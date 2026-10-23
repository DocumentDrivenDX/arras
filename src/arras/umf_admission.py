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
from arras.model import (
    UNPLACED,
    EntityTypeInfo,
    ModuleInfo,
    PropertyInfo,
)
from arras.types import Revision

_ENGINE_DISTRIBUTION = "umf-core"
_ENGINE_VERSION = "0.10.0"
_PROFILE = "umf-core-empty-registry/1"
_METADATA_PROFILE = "umf-core-metadata/1"
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


@dataclass(frozen=True, slots=True)
class ProjectionIssue:
    """A safe Arras profile refusal at a source location."""

    path: str
    code: Literal[
        "invalid_name", "missing_key", "incomplete_interpretation", "unsupported_projection"
    ]
    message: str

    def __post_init__(self) -> None:
        if type(self.path) is not str or type(self.message) is not str:
            raise TypeError("projection issue fields must be strings")
        if self.code not in (
            "invalid_name",
            "missing_key",
            "incomplete_interpretation",
            "unsupported_projection",
        ):
            raise ValueError("projection issue code is not recognized")


@dataclass(frozen=True, slots=True)
class ProjectionReport:
    """Official admission plus a bounded, explicit Arras metadata summary."""

    admission: AdmissionReport
    profile: str
    supported: bool
    issues: tuple[ProjectionIssue, ...]
    module: ModuleInfo | None

    def __post_init__(self) -> None:
        if type(self.admission) is not AdmissionReport:
            raise TypeError("admission must be an AdmissionReport")
        if self.profile != _METADATA_PROFILE:
            raise ValueError("projection profile is not recognized")
        if type(self.supported) is not bool:
            raise TypeError("supported must be bool")
        if type(self.issues) is not tuple or any(
            type(issue) is not ProjectionIssue for issue in self.issues
        ):
            raise TypeError("issues must be an immutable tuple of ProjectionIssue")
        if self.supported:
            if self.module is None or self.issues:
                raise ValueError("a supported projection requires a module and no issues")
            if (
                self.admission.validation_status != "completed"
                or self.admission.valid is not True
                or self.admission.complete is not True
            ):
                raise ValueError("a supported projection requires complete official admission")
            if self.module.metadata_profile != _METADATA_PROFILE:
                raise ValueError("projected module must carry the metadata profile")
        elif self.module is not None or not self.issues:
            raise ValueError("an unsupported projection requires issues and no module")


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


def project_document(document: bytes | str) -> ProjectionReport:
    """Admit source afresh, then summarize only the declared core metadata profile."""
    admission = admit_document(document)
    if (
        admission.validation_status != "completed"
        or admission.valid is not True
        or admission.complete is not True
    ):
        issue = ProjectionIssue(
            "document",
            "incomplete_interpretation",
            "official source admission did not establish a complete valid document",
        )
        return ProjectionReport(admission, _METADATA_PROFILE, False, (issue,), None)

    text = admission.source.decode("utf-8", errors="strict")
    from arras._umf_engine import read_typed_snapshot
    from arras._umf_projection import project_snapshot

    result = project_snapshot(read_typed_snapshot(text))
    if result.issues:
        return ProjectionReport(
            admission,
            _METADATA_PROFILE,
            False,
            tuple(
                ProjectionIssue(issue.path, issue.code, issue.message) for issue in result.issues
            ),
            None,
        )
    assert result.module_name is not None
    assert result.type_name is not None
    assert result.key_name is not None
    entity = EntityTypeInfo(
        result.type_name,
        result.key_name,
        tuple(
            PropertyInfo(item.name, item.scalar_type, True, item.cardinality)
            for item in result.properties
        ),
    )
    module = ModuleInfo(
        result.module_name,
        UNPLACED,
        Revision(),
        (entity,),
        metadata_profile=_METADATA_PROFILE,
    )
    return ProjectionReport(admission, _METADATA_PROFILE, True, (), module)


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
