# SPDX-License-Identifier: MIT OR Apache-2.0
"""Conformance and source-boundary tests for official UMF admission."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from arras.errors import Unsupported
from arras.umf_admission import AdmissionReport, UmfDiagnostic, admit_document

_FIXTURE = Path(__file__).parent / "fixtures/umf-core-reference/current-conformance.json"


def _engine() -> tuple[Any, Any, Any, Any, Any]:
    try:
        sdk = importlib.import_module("umf")
    except ModuleNotFoundError as error:
        if error.name != "umf":
            raise
        if os.environ.get("ARRAS_REQUIRE_UMF") == "1":
            pytest.fail("ARRAS_REQUIRE_UMF=1 but the selected UMF engine is unavailable")
        pytest.skip("install the optional arras[umf] dependency for official-engine tests")
    return (
        sdk.Diagnostic,
        sdk.Extension,
        sdk.Registry,
        sdk.read_json_value,
        sdk.validate_document,
    )


def _valid_document_with_title(title: str) -> bytes:
    corpus = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    document = next(
        case["document"] for case in corpus["cases"] if case["id"] == "schema-properties/valid"
    )
    document["title"] = title
    return json.dumps(document, ensure_ascii=True).encode("utf-8")


def test_source_is_preserved_and_reports_official_result() -> None:
    _engine()
    source = _valid_document_with_title("PRIVATE-ADMISSION-SENTINEL-ONLY")
    report = admit_document(source)

    assert report.source == source
    assert report.source_sha256 == hashlib.sha256(source).hexdigest()
    assert report.validation_status == "completed"
    assert report.valid is True
    assert report.complete is True
    assert report.diagnostics == ()
    assert "source=" not in repr(report)
    assert "PRIVATE-ADMISSION-SENTINEL-ONLY" not in repr(report)
    assert "PRIVATE-ADMISSION-SENTINEL-ONLY" not in repr([report])
    with pytest.raises(AttributeError):
        report.valid = True  # type: ignore[misc]

    text_report = admit_document(source.decode("utf-8"))
    assert text_report.source == source
    assert text_report.diagnostics == report.diagnostics


def test_each_admission_uses_a_distinct_empty_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _engine()
    import arras._umf_engine as engine

    sdk = cast(Any, importlib.import_module("umf"))
    created: list[Any] = []

    def new_registry() -> Any:
        registry = sdk.Registry()
        created.append(registry)
        return registry

    bridge = SimpleNamespace(
        Registry=new_registry,
        read_json_value=sdk.read_json_value,
        validate_document=sdk.validate_document,
    )

    def load_bridge(name: str) -> Any:
        assert name == "umf"
        return bridge

    monkeypatch.setattr(engine, "import_module", load_bridge)
    source = _valid_document_with_title("Registry isolation")

    assert admit_document(source).valid is True
    assert admit_document(source).valid is True
    assert len(created) == 2
    assert created[0] is not created[1]
    assert created[0]._entries == {}
    assert created[1]._entries == {}


@pytest.mark.parametrize(
    ("source", "code"),
    [
        (b"\xff", "source_profile"),
        (b"{", "source_profile"),
        (b'{"x":1,"x":2}', "source_profile"),
        (b" " * (16 * 1024 * 1024 + 1), "source_limit"),
    ],
)
def test_reader_refusal_is_not_reported_as_official_invalidity(source: bytes, code: str) -> None:
    _engine()
    report = admit_document(source)
    assert report.source == source
    assert report.validation_status == "not_run"
    assert report.valid is None
    assert report.complete is None
    assert len(report.diagnostics) == 1
    diagnostic = report.diagnostics[0]
    assert (diagnostic.authority, diagnostic.code, diagnostic.path) == (
        "arras-source",
        code,
        "document",
    )
    assert "duplicate" not in diagnostic.message
    assert "source=" not in repr(report)


def test_input_types_and_unencodable_text_fail_before_a_report() -> None:
    with pytest.raises(TypeError, match="bytes or str"):
        admit_document({"umf": "0.10.0"})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="strictly UTF-8"):
        admit_document("\ud800")


def test_lexically_valid_non_object_is_officially_invalid() -> None:
    _engine()
    report = admit_document(b"null")
    assert report.validation_status == "completed"
    assert report.valid is False
    assert report.complete is False
    assert report.diagnostics
    assert all(item.authority == "umf" for item in report.diagnostics)


def test_report_rejects_forged_inconsistent_state() -> None:
    source = b"{}"
    digest = hashlib.sha256(source).hexdigest()
    source_diagnostic = UmfDiagnostic(
        "arras-source", "source_profile", "document", "refused", "error"
    )
    with pytest.raises(ValueError, match="cannot claim"):
        AdmissionReport(
            source,
            digest,
            "umf-core",
            "0.10.0",
            "umf-core-empty-registry/1",
            "not_run",
            False,
            None,
            (source_diagnostic,),
        )
    with pytest.raises(ValueError, match="source_sha256"):
        AdmissionReport(
            source,
            "0" * 64,
            "umf-core",
            "0.10.0",
            "umf-core-empty-registry/1",
            "completed",
            False,
            False,
            (),
        )
    with pytest.raises(ValueError, match="must come from UMF"):
        AdmissionReport(
            source,
            digest,
            "umf-core",
            "0.10.0",
            "umf-core-empty-registry/1",
            "completed",
            True,
            True,
            (source_diagnostic,),
        )


def test_unexpected_validator_failure_is_not_fabricated_as_a_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _engine()
    import arras._umf_engine as engine

    def fail(_: str) -> Any:
        raise RuntimeError("validator failure")

    monkeypatch.setattr(engine, "read_and_validate", fail)
    with pytest.raises(RuntimeError, match="validator failure"):
        admit_document(b"{}")


def test_official_current_conformance_vectors_and_empty_registry_admission() -> None:
    Diagnostic, Extension, Registry, read_json_value, validate_document = _engine()
    corpus = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert corpus["profile"] == "umf.current-conformance/1"
    assert corpus["currentVersion"] == "0.10.0"
    assert len(corpus["cases"]) == 139

    for case in corpus["cases"]:
        registry = Registry()
        spec = case.get("registry")
        if spec is not None:

            def validate(payload: Any, context: dict[str, Any]) -> list[Any]:
                return [
                    Diagnostic(
                        "BASELINE_CALLBACK",
                        context["path"],
                        f"{context['document']['id']}:{context['scope']}:{payload['kind']}",
                        "warning",
                    )
                ]

            registry.register(
                Extension(spec["id"], spec["version"], (spec["scope"],), True, validate)
            )
        # Escaped surrogates are valid JSON source bytes; ensure_ascii avoids
        # putting an unencodable Python surrogate directly into the UTF-8 input.
        source = json.dumps(case["document"], ensure_ascii=True)
        official = validate_document(read_json_value(source), registry)
        assert official.valid is case["valid"], case["id"]
        assert official.complete is case["complete"], case["id"]
        assert [
            (item.code, item.path, item.message, item.severity) for item in official.diagnostics
        ] == [
            (item["code"], item["path"], item["message"], item["severity"])
            for item in case["diagnostics"]
        ], case["id"]

        # The production admission path always has a separate empty registry.
        admitted = admit_document(source)
        empty = validate_document(read_json_value(source), Registry())
        assert admitted.validation_status == "completed", case["id"]
        assert admitted.valid is empty.valid, case["id"]
        assert admitted.complete is empty.complete, case["id"]
        assert [
            (item.code, item.path, item.message, item.severity) for item in admitted.diagnostics
        ] == [(item.code, item.path, item.message, item.severity) for item in empty.diagnostics], (
            case["id"]
        )


def test_missing_engine_is_an_explicit_unsupported_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arras._umf_engine as engine

    def without_umf(_: str) -> Any:
        raise ModuleNotFoundError("no UMF engine", name="umf")

    monkeypatch.setattr(engine, "import_module", without_umf)
    with pytest.raises(Unsupported, match="official UMF admission"):
        admit_document(b"{}")
