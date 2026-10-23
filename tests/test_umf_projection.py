# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounds for the released UMF core metadata projection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from arras.errors import Unsupported
from arras.gqlschema import build_module_schema
from arras.umf_admission import ProjectionReport, admit_document, project_document

ROOT = Path(__file__).parent
FIXTURE = ROOT / "fixtures/umf-core-metadata/primary-string-record.json"
REFERENCE = ROOT / "fixtures/umf-core-reference/current-conformance.json"


def _document() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _source(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _report(value: object) -> ProjectionReport:
    return project_document(_source(value))


def _rename_module(value: dict[str, Any], name: str) -> None:
    module = value["modules"][0]
    module["id"] = name
    for element in module["elements"]:
        for member in element.get("members", []):
            member["module"] = name
        for key in element.get("keys", []):
            for field in key.get("fields", []):
                field["module"] = name


def _invalid_record_name(value: dict[str, Any]) -> None:
    value["modules"][0]["elements"][0]["id"] = "OrderList"


def _invalid_module_name(value: dict[str, Any]) -> None:
    _rename_module(value, "not-valid")


def test_official_derived_core_record_projects_without_renaming_or_losing_source() -> None:
    original = FIXTURE.read_bytes()
    result = project_document(original)

    assert result.supported is True
    assert result.issues == ()
    assert result.admission.source == original
    assert result.admission.valid is True
    assert result.admission.complete is True
    assert result.module is not None
    assert result.module.name == "m"
    assert result.module.metadata_profile == "umf-core-metadata/1"
    assert result.module.entity_types[0].name == "m.Order"
    assert result.module.entity_types[0].key == "id"
    build_module_schema(result.module)
    assert [
        (item.name, item.type, item.cardinality)
        for item in result.module.entity_types[0].properties
    ] == [
        ("id", "string", "one"),
        ("number", "string", "one"),
    ]


def test_projection_is_fresh_and_source_metadata_does_not_replace_identity() -> None:
    first = project_document(FIXTURE.read_bytes())
    second = project_document(FIXTURE.read_bytes())

    assert first.module is not second.module
    assert first.module is not None
    assert first.module.entity_types[0].name == "m.Order"
    assert first.module.entity_types[0].key == "id"
    assert first.module.entity_types[0].property(first.module.entity_types[0].key) is not None
    build_module_schema(first.module)


def test_unknown_incomplete_document_preserves_official_diagnostic_without_typed_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = json.loads(REFERENCE.read_text(encoding="utf-8"))
    original = next(
        case["document"] for case in corpus["cases"] if case["id"] == "keys/primary-and-alternate"
    )
    expected = admit_document(_source(original))
    assert expected.valid is True and expected.complete is False

    def forbidden_read(_: str) -> object:
        raise AssertionError("typed read must not follow incomplete admission")

    monkeypatch.setattr("arras._umf_engine.read_typed_snapshot", forbidden_read, raising=False)
    result = _report(original)

    assert result.admission.diagnostics == expected.diagnostics
    assert result.admission.valid is True
    assert result.admission.complete is False
    assert result.supported is False
    assert result.module is None
    assert result.issues[0].code == "incomplete_interpretation"


def test_nonstring_primary_key_is_officially_valid_but_refused_by_profile() -> None:
    corpus = json.loads(REFERENCE.read_text(encoding="utf-8"))
    value = next(
        case["document"] for case in corpus["cases"] if case["id"] == "keys/primary-and-alternate"
    )
    value.pop("extensions")
    value["vocabularies"] = {}
    record = value["modules"][0]["elements"][0]
    record["keys"] = record["keys"][:1]

    result = _report(value)

    assert result.admission.valid is True
    assert result.admission.complete is True
    assert result.supported is False
    assert result.issues[0].code == "unsupported_projection"
    assert result.issues[0].path == "/modules/0/elements/1"


def test_missing_primary_key_is_profile_issue_when_official_core_accepts_document() -> None:
    value = _document()
    value["modules"][0]["elements"][0].pop("keys")

    result = _report(value)

    assert result.admission.valid is True
    assert result.admission.complete is True
    assert result.supported is False
    assert any(issue.code == "missing_key" for issue in result.issues)
    assert result.module is None


def test_alternate_key_is_officially_complete_but_outside_single_key_profile() -> None:
    corpus = json.loads(REFERENCE.read_text(encoding="utf-8"))
    original = next(
        case["document"] for case in corpus["cases"] if case["id"] == "keys/primary-and-alternate"
    )
    value = _document()
    alternate = original["modules"][0]["elements"][0]["keys"][1]
    value["modules"][0]["elements"][0]["keys"].append(alternate)

    result = _report(value)

    assert result.admission.valid is True
    assert result.admission.complete is True
    assert result.supported is False
    assert result.issues[0].path == "/modules/0/elements/0/keys"
    assert result.issues[0].code == "unsupported_projection"
    assert result.module is None


@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        (
            _invalid_record_name,
            "/modules/0/elements/0/id",
        ),
        (_invalid_module_name, "/modules/0/id"),
    ],
)
def test_name_incompatible_identifiers_are_refused_without_echoing_source(
    mutate: Any, expected_path: str
) -> None:
    value = _document()
    mutate(value)

    result = _report(value)

    assert result.admission.valid is True
    assert result.admission.complete is True
    issue = next(issue for issue in result.issues if issue.code == "invalid_name")
    assert issue.path == expected_path
    assert "OrderList" not in issue.message
    assert "not-valid" not in issue.message
    assert result.module is None


def test_casefold_name_collision_is_refused_before_metadata_is_advertised() -> None:
    value = _document()
    value["modules"][0]["elements"][2]["id"] = "ID"
    value["modules"][0]["elements"][0]["members"][1]["element"] = "ID"

    result = _report(value)

    assert result.admission.valid is True
    assert result.admission.complete is True
    assert result.supported is False
    assert any(
        issue.code == "invalid_name" and issue.path == "/modules/0/elements/2/id"
        for issue in result.issues
    )


@pytest.mark.parametrize(
    ("slot", "value", "valid"),
    [
        ("default", None, False),
        ("allowedValues", [], False),
        ("facets", {"minLength": 1}, True),
        ("semanticTypes", [{"vocabulary": "x", "version": "1.0", "term": "x"}], True),
        ("itemType", {"module": "m", "element": "Order"}, False),
    ],
)
def test_official_incomplete_semantics_are_not_reinterpreted_by_projection(
    slot: str, value: object, valid: bool
) -> None:
    source = _document()
    source["modules"][0]["elements"][1][slot] = value

    result = _report(source)

    assert result.admission.valid is valid
    assert result.admission.complete is False
    assert result.supported is False
    assert result.issues[0].code == "incomplete_interpretation"
    assert result.admission.diagnostics


def test_unsupported_projection_messages_are_static_and_report_repr_hides_source() -> None:
    value = _document()
    value["description"] = "private sentinel description 7f63b"
    value["modules"][0]["actions"] = [{"id": "sentinel-secret-action"}]
    result = _report(value)

    assert result.supported is False
    assert "private sentinel description 7f63b" not in repr(result)
    assert "sentinel-secret-action" not in " ".join(issue.message for issue in result.issues)


def test_valid_metadata_title_is_preserved_only_in_source_not_nested_repr() -> None:
    value = _document()
    value["title"] = "private valid-title sentinel 2cf16"
    result = _report(value)

    assert result.supported is True
    assert result.admission.source == _source(value)
    assert "private valid-title sentinel 2cf16" not in repr(result)
    assert "private valid-title sentinel 2cf16" not in repr(result.admission)
    assert result.module is not None
    assert "private valid-title sentinel 2cf16" not in repr(result.module)


def test_missing_engine_never_falls_back_to_legacy_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_: str) -> object:
        raise ModuleNotFoundError("no module named umf", name="umf")

    monkeypatch.setattr("arras._umf_engine.read_and_validate", missing)

    with pytest.raises(Unsupported):
        project_document(FIXTURE.read_bytes())
