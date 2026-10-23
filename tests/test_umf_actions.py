# SPDX-License-Identifier: MIT OR Apache-2.0
"""Import-boundary controls for the optional official UMF action runtime."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterator, Mapping
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from pytest import MonkeyPatch

from arras import _umf_action_shapes, _umf_actions, _umf_engine
from arras._action_types import PreparedSetModule, SetBinding
from arras.errors import Invalid, Unsupported
from arras.model import UNPLACED, EntityTypeInfo, ModuleInfo, PropertyInfo
from arras.types import Revision
from arras.umf_admission import AdmissionReport, UmfDiagnostic

_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "umf-actions-binding"
_FIXTURE_SOURCE_SHA256 = "5b79b3dba5ebc52ac9452f85a75411dab5edaa34154adda76f872a53c21d0818"
_FIXTURE_VECTORS_SHA256 = "c811eefac81c4f5ff3a7aa60cbe7f7657f7599040cd0869b2616c450931a950e"


def test_absent_candidate_runtime_is_an_explicit_capability_refusal(
    monkeypatch: MonkeyPatch,
) -> None:
    def missing(name: str) -> object:
        if name == "umf.action_runtime":
            raise ModuleNotFoundError("no action runtime", name=name)
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(_umf_engine, "import_module", missing)

    assert _umf_engine.action_runtime_available() is False
    with pytest.raises(Unsupported):
        _umf_engine.call_action_runtime("prepare_single_set_action", {})


def test_api_presence_is_not_advertised_without_packaged_engine(monkeypatch: MonkeyPatch) -> None:
    class Runtime:
        @staticmethod
        def create_action_engine(**kwargs: object) -> None:
            assert set(kwargs) == {"profile", "max_work", "now", "deadline_ms"}
            assert kwargs["profile"] == "cooperative"
            assert type(kwargs["max_work"]) is int and kwargs["max_work"] > 0
            now = kwargs["now"]
            deadline = kwargs["deadline_ms"]
            assert callable(now) and type(deadline) is int
            clock = cast(Callable[[], int], now)
            assert deadline >= clock()
            return None

        @staticmethod
        def prepare_single_set_action(*args: object, **kwargs: object) -> dict[str, object]:
            return {}

        admit_generated_action_invocation = prepare_single_set_action
        admit_generated_record_values = prepare_single_set_action

    def runtime_import(name: str) -> object:
        assert name == "umf.action_runtime"
        return Runtime()

    monkeypatch.setattr(_umf_engine, "import_module", runtime_import)
    assert _umf_engine.action_runtime_available() is False


def test_typed_unsupported_engine_capability_is_not_advertised(
    monkeypatch: MonkeyPatch,
) -> None:
    class OfficialCodegenError(ValueError):
        code = "ACTION_RUNTIME_UNSUPPORTED"
        path = "/profile"

    class OfficialCoreError(ValueError):
        pass

    class Runtime:
        @staticmethod
        def create_action_engine(**kwargs: object) -> object:
            raise OfficialCodegenError("unsupported profile detail")

        @staticmethod
        def prepare_single_set_action(*args: object, **kwargs: object) -> object:
            raise AssertionError("unsupported engine must not reach an operation")

        admit_generated_action_invocation = prepare_single_set_action
        admit_generated_record_values = prepare_single_set_action

    def runtime_import(name: str) -> object:
        if name == "umf.action_runtime":
            return Runtime()
        if name == "umf.rust_codegen":
            return SimpleNamespace(
                UmfCodegenError=OfficialCodegenError, UmfCoreError=OfficialCoreError
            )
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(_umf_engine, "import_module", runtime_import)

    assert _umf_engine.action_runtime_available() is False


@pytest.mark.parametrize(
    ("code", "expected_code"),
    [("ACTION_RUNTIME_INTEGRITY", "schema_mismatch"), ("RESOURCE_LIMIT", "limit_exceeded")],
)
def test_typed_runtime_integrity_and_budget_errors_are_not_absence(
    monkeypatch: MonkeyPatch,
    code: str,
    expected_code: str,
) -> None:
    class OfficialCodegenError(ValueError):
        pass

    class OfficialCoreError(ValueError):
        def __init__(self) -> None:
            self.code = code
            self.path = "/source"

    class Runtime:
        @staticmethod
        def create_action_engine(**kwargs: object) -> object:
            raise OfficialCoreError()

        @staticmethod
        def prepare_single_set_action(*args: object, **kwargs: object) -> object:
            raise AssertionError("factory refusal must precede runtime operation")

        admit_generated_action_invocation = prepare_single_set_action
        admit_generated_record_values = prepare_single_set_action

    def runtime_import(name: str) -> object:
        if name == "umf.action_runtime":
            return Runtime()
        if name == "umf.rust_codegen":
            return SimpleNamespace(
                UmfCodegenError=OfficialCodegenError, UmfCoreError=OfficialCoreError
            )
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(_umf_engine, "import_module", runtime_import)

    with pytest.raises(Invalid) as failure:
        _umf_engine.action_runtime_available()

    assert failure.value.violations[0].code == expected_code
    assert "official source" not in str(failure.value)


def test_runtime_api_import_dependency_failure_is_not_misreported_as_absent(
    monkeypatch: MonkeyPatch,
) -> None:
    def broken(name: str) -> object:
        assert name == "umf.action_runtime"
        raise ModuleNotFoundError("runtime dependency is broken", name="umf_codegen")

    monkeypatch.setattr(_umf_engine, "import_module", broken)

    with pytest.raises(ModuleNotFoundError, match="runtime dependency"):
        _umf_engine.action_runtime_available()


@pytest.mark.parametrize(
    ("code", "path", "expected", "violation_code"),
    [
        ("ACTION_RUNTIME_INTEGRITY", "/source", Invalid, "schema_mismatch"),
        ("ACTION_RUNTIME_INVALID", "/inputs/secret", Invalid, "umf_invalid"),
        ("CORE_SCHEMA_PROPERTIES", "", Invalid, "umf_invalid"),
        ("RESOURCE_LIMIT", "/inputs/value", Invalid, "limit_exceeded"),
        ("ACTION_RUNTIME_UNSUPPORTED", "/profile", Unsupported, None),
    ],
)
def test_official_typed_refusals_are_mapped_without_sdk_prose(
    code: str,
    path: str,
    expected: type[Exception],
    violation_code: str | None,
) -> None:
    translated = _umf_engine.translate_action_error(code, path)

    assert isinstance(translated, expected)
    assert "secret" not in str(translated)
    if isinstance(translated, Invalid):
        assert [item.code for item in translated.violations] == [violation_code]


def test_unsafe_sdk_error_path_is_replaced_with_fixed_path() -> None:
    translated = _umf_engine.translate_action_error(
        "ACTION_RUNTIME_INVALID", "/inputs/private value\nsecret"
    )

    assert isinstance(translated, Invalid)
    assert translated.violations[0].path == "action"
    assert "private value" not in str(translated)


def test_runtime_boundary_maps_only_official_typed_errors(monkeypatch: MonkeyPatch) -> None:
    class OfficialCodegenError(ValueError):
        code = "ACTION_RUNTIME_INVALID"
        path = "/inputs/value"

    class OfficialCoreError(ValueError):
        pass

    class Runtime:
        @staticmethod
        def create_action_engine(**kwargs: object) -> object:
            return object()

        @staticmethod
        def prepare_single_set_action(*args: object, **kwargs: object) -> object:
            raise OfficialCodegenError("sensitive value must not escape")

        admit_generated_action_invocation = prepare_single_set_action
        admit_generated_record_values = prepare_single_set_action

    def runtime_import(name: str) -> object:
        if name == "umf.action_runtime":
            return Runtime()
        if name == "umf.rust_codegen":
            return SimpleNamespace(
                UmfCodegenError=OfficialCodegenError, UmfCoreError=OfficialCoreError
            )
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(_umf_engine, "import_module", runtime_import)

    with pytest.raises(Invalid) as failure:
        _umf_engine.call_action_runtime("prepare_single_set_action", {})

    assert failure.value.violations[0].code == "umf_invalid"
    assert "sensitive value" not in str(failure.value)


def test_unknown_official_error_code_is_not_accepted_as_a_refusal(
    monkeypatch: MonkeyPatch,
) -> None:
    class OfficialCodegenError(ValueError):
        code = "NEW_UNMAPPED_CODE"
        path = "/input"

    class OfficialCoreError(ValueError):
        pass

    class Runtime:
        @staticmethod
        def create_action_engine(**kwargs: object) -> object:
            return object()

        @staticmethod
        def prepare_single_set_action(*args: object, **kwargs: object) -> object:
            raise OfficialCodegenError("SDK-owned detail")

        admit_generated_action_invocation = prepare_single_set_action
        admit_generated_record_values = prepare_single_set_action

    def runtime_import(name: str) -> object:
        if name == "umf.action_runtime":
            return Runtime()
        if name == "umf.rust_codegen":
            return SimpleNamespace(
                UmfCodegenError=OfficialCodegenError, UmfCoreError=OfficialCoreError
            )
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(_umf_engine, "import_module", runtime_import)

    with pytest.raises(OfficialCodegenError, match="SDK-owned detail"):
        _umf_engine.call_action_runtime("prepare_single_set_action", {})


def test_engine_factory_limit_is_mapped_at_the_official_boundary(
    monkeypatch: MonkeyPatch,
) -> None:
    class OfficialCodegenError(ValueError):
        pass

    class OfficialCoreError(ValueError):
        code = "RESOURCE_LIMIT"
        path = ""

    class Runtime:
        @staticmethod
        def create_action_engine(**kwargs: object) -> object:
            raise OfficialCoreError("bounded factory detail")

        @staticmethod
        def prepare_single_set_action(*args: object, **kwargs: object) -> object:
            raise AssertionError("factory failure must happen before operation")

        admit_generated_action_invocation = prepare_single_set_action
        admit_generated_record_values = prepare_single_set_action

    def runtime_import(name: str) -> object:
        if name == "umf.action_runtime":
            return Runtime()
        if name == "umf.rust_codegen":
            return SimpleNamespace(
                UmfCodegenError=OfficialCodegenError, UmfCoreError=OfficialCoreError
            )
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(_umf_engine, "import_module", runtime_import)

    with pytest.raises(Invalid) as failure:
        _umf_engine.call_action_runtime("prepare_single_set_action", {})

    assert failure.value.violations[0].code == "limit_exceeded"
    assert "bounded factory detail" not in str(failure.value)


def test_validate_candidate_delegates_using_public_record_carrier(
    monkeypatch: MonkeyPatch,
) -> None:
    prepared = cast(
        PreparedSetModule,
        SimpleNamespace(record_id="Probe", key_field_id="item_id", module_id="example"),
    )
    values = {"item_id": "probe-1", "label_value": "ready"}
    seen: list[tuple[PreparedSetModule, object]] = []

    def admitted(source: PreparedSetModule, row: object) -> object:
        seen.append((source, row))
        return object()

    monkeypatch.setattr(_umf_actions, "admit_record", admitted)
    _umf_actions.validate_candidate(prepared, values)

    assert seen == [
        (
            prepared,
            {"type": "Probe", "key": "probe-1", "properties": values},
        )
    ]


def test_completed_invalid_official_admission_remains_invalid_and_safe(
    monkeypatch: MonkeyPatch,
) -> None:
    source = b"{}"
    report = AdmissionReport(
        source=source,
        source_sha256=hashlib.sha256(source).hexdigest(),
        engine_distribution="umf-core",
        engine_version="0.10.0",
        validation_profile="umf-core-empty-registry/1",
        validation_status="completed",
        valid=False,
        complete=False,
        diagnostics=(
            UmfDiagnostic("umf", "invalid", "/private", "sensitive source detail", "error"),
        ),
    )

    def invalid_admission(_: bytes) -> AdmissionReport:
        return report

    def forbidden_snapshot(_: str) -> object:
        pytest.fail("invalid official admission must stop before typed projection")

    monkeypatch.setattr("arras.umf_admission.admit_document", invalid_admission)
    monkeypatch.setattr(_umf_actions, "_snapshot", forbidden_snapshot)

    with pytest.raises(Invalid) as failure:
        _umf_actions.prepare(source)

    assert failure.value.violations[0].code == "invalid_document"
    assert "sensitive source detail" not in str(failure.value)


def _prepared_for_record_guard() -> PreparedSetModule:
    source = b"{}"
    digest = hashlib.sha256(source).hexdigest()
    entity = EntityTypeInfo(
        "catalog.Probe",
        "item_id",
        (
            PropertyInfo("item_id", "string", True, "one"),
            PropertyInfo("label", "string", True, "one"),
        ),
    )
    module = ModuleInfo(
        "catalog", UNPLACED, Revision(), (entity,), metadata_profile="arras-umf-set/1"
    )
    return PreparedSetModule(
        source=source,
        sha256=digest,
        module=module,
        document_id="actions-binding-neutral-fixture",
        source_revision=f"sha256:{digest}",
        module_id="catalog",
        record_id="Probe",
        action_id="catalog.set_label",
        action_local_id="set_label",
        key_field_id="item_id",
        key_property="item_id",
        entity_parameter="item",
        bindings=(SetBinding("label_value", "label", "label"),),
        frames=("write_item",),
        policy_profile="arras.module-write/1",
        resources=("write_item",),
    )


def test_record_admission_rejects_custom_mapping_without_iterating_it(
    monkeypatch: MonkeyPatch,
) -> None:
    touched = False

    class GuardedMapping(Mapping[str, object]):
        def __getitem__(self, key: str) -> object:
            raise AssertionError("custom mapping must not be read")

        def __iter__(self) -> Iterator[str]:
            nonlocal touched
            touched = True
            raise AssertionError("custom mapping must not be traversed")

        def __len__(self) -> int:
            raise AssertionError("custom mapping must not be measured")

    def skip_source_recheck(_: PreparedSetModule) -> None:
        return None

    monkeypatch.setattr(_umf_actions, "_require_prepared_source", skip_source_recheck)
    with pytest.raises(Invalid, match="string mapping"):
        _umf_actions.admit_record(
            _prepared_for_record_guard(),
            {"type": "Probe", "key": "probe-1", "properties": GuardedMapping()},
        )
    assert touched is False


def test_record_admission_checks_scalar_types_before_key_equality(
    monkeypatch: MonkeyPatch,
) -> None:
    compared = False

    class UnsafeScalar:
        def __eq__(self, other: object) -> bool:
            nonlocal compared
            compared = True
            raise AssertionError("non-string source value must not be compared")

    def skip_source_recheck(_: PreparedSetModule) -> None:
        return None

    monkeypatch.setattr(_umf_actions, "_require_prepared_source", skip_source_recheck)
    with pytest.raises(Invalid, match="field values must be strings"):
        _umf_actions.admit_record(
            _prepared_for_record_guard(),
            {
                "type": "Probe",
                "key": "probe-1",
                "properties": {"item_id": UnsafeScalar(), "label": "ready"},
            },
        )
    assert compared is False


def _prepared_vector_for_obligation_checks() -> tuple[dict[str, object], dict[str, object]]:
    vectors = cast(
        dict[str, object],
        json.loads((_FIXTURE_ROOT / "vectors.json").read_bytes()),
    )
    expected = cast(dict[str, object], vectors["expected"])
    result = cast(dict[str, object], deepcopy(expected["prepared"]))
    authorization = cast(dict[str, object], result["authorization"])
    request_authorization = {
        "profile": deepcopy(authorization["profile"]),
        "resources": deepcopy(authorization["resources"]),
        "evidence": ["arras:module-write/1"],
    }
    authorization["evidence"] = request_authorization["evidence"]
    return result, {"authorization": request_authorization}


def test_candidate_preparation_requires_complete_host_obligations() -> None:
    result, request = _prepared_vector_for_obligation_checks()

    target, key_fields, assignments, frames = (
        _umf_action_shapes.validate_official_prepared_inventory(result, request)
    )

    assert target["element"] == "item"
    assert len(key_fields) == len(assignments) == len(frames) == 1


@pytest.mark.parametrize(
    "mutation",
    ["empty_executor", "missing_executor", "authorization_mismatch"],
)
def test_candidate_preparation_rejects_incomplete_or_mismatched_obligations(
    mutation: str,
) -> None:
    result, request = _prepared_vector_for_obligation_checks()
    executor = cast(list[object], result["requiredExecutorObligations"])
    if mutation == "empty_executor":
        result["requiredExecutorObligations"] = []
    elif mutation == "missing_executor":
        result["requiredExecutorObligations"] = executor[:-1]
    else:
        authorization = cast(dict[str, object], result["authorization"])
        authorization["obligation"] = "/unrelated"

    with pytest.raises(TypeError, match="obligation"):
        _umf_action_shapes.validate_official_prepared_inventory(result, request)


@pytest.mark.parametrize(
    ("module_id", "action_id", "entity_input", "value_input", "frame_id"),
    [
        ("Bad-Module", "set_label", "item", "label_value", "write_item"),
        ("catalog", "set-label", "item", "label_value", "write_item"),
        ("catalog", "set_label", "bad-input", "label_value", "write_item"),
        ("catalog", "set_label", "Item", "item", "write_item"),
        ("catalog", "set_label", "item", "label_value", "write\nitem"),
    ],
)
def test_source_identifiers_must_fit_safe_arras_name_profile(
    module_id: str,
    action_id: str,
    entity_input: str,
    value_input: str,
    frame_id: str,
) -> None:
    with pytest.raises(Invalid) as failure:
        _umf_actions.validate_arras_profile_names(
            module_id, action_id, entity_input, value_input, frame_id
        )

    assert failure.value.violations[0].code == "invalid_name"
    assert module_id not in str(failure.value)
    assert action_id not in str(failure.value)


@pytest.mark.parametrize(
    ("record_id", "property_ids"),
    [
        ("Item-Record", ("item_id", "label")),
        ("ItemPage", ("item_id", "label")),
        ("item", ("label-value", "label")),
        ("item", ("label", "Label")),
    ],
)
def test_projected_entity_and_property_names_are_arras_safe(
    record_id: str,
    property_ids: tuple[str, ...],
) -> None:
    with pytest.raises(Invalid) as failure:
        _umf_actions.validate_arras_element_names(record_id, property_ids)

    assert failure.value.violations[0].code == "invalid_name"
    assert record_id not in str(failure.value)


def test_candidate_fixture_bytes_match_the_frozen_vectors() -> None:
    source = (_FIXTURE_ROOT / "source.json").read_bytes()
    vectors_bytes = (_FIXTURE_ROOT / "vectors.json").read_bytes()
    vectors = cast(dict[str, object], json.loads(vectors_bytes))

    assert hashlib.sha256(source).hexdigest() == _FIXTURE_SOURCE_SHA256
    assert hashlib.sha256(vectors_bytes).hexdigest() == _FIXTURE_VECTORS_SHA256
    assert vectors["source"] == {
        "path": "source.json",
        "bytes": len(source),
        "sha256": _FIXTURE_SOURCE_SHA256,
    }


@pytest.fixture(scope="module")
def candidate_bridge_data() -> tuple[PreparedSetModule, dict[str, object]]:
    required = os.environ.get("ARRAS_REQUIRE_UMF_ACTIONS") == "1"
    if not _umf_actions.runtime_available():
        if required:
            pytest.fail("ARRAS_REQUIRE_UMF_ACTIONS=1 but candidate engine is unavailable")
        pytest.skip("candidate UMF action runtime is not installed in this environment")

    source = (_FIXTURE_ROOT / "source.json").read_bytes()
    vectors = cast(
        dict[str, object],
        json.loads((_FIXTURE_ROOT / "vectors.json").read_bytes()),
    )
    return _umf_actions.prepare(source), vectors


@pytest.fixture
def candidate_runtime_available() -> None:
    required = os.environ.get("ARRAS_REQUIRE_UMF_ACTIONS") == "1"
    if not _umf_engine.action_runtime_available():
        if required:
            pytest.fail("ARRAS_REQUIRE_UMF_ACTIONS=1 but candidate engine is unavailable")
        pytest.skip("candidate UMF action runtime is not installed in this environment")


def test_candidate_factory_work_limit_is_typed_not_absence(
    candidate_runtime_available: None, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(_umf_engine, "_ACTION_RUNTIME_MAX_WORK", 100_000)

    with pytest.raises(Invalid) as failure:
        _umf_engine.action_runtime_available()

    assert failure.value.violations[0].code == "limit_exceeded"


def test_candidate_expired_factory_deadline_is_typed_not_absence(
    candidate_runtime_available: None, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(_umf_engine, "_ACTION_RUNTIME_DEADLINE_MS", 0)

    with pytest.raises(Invalid) as failure:
        _umf_engine.action_runtime_available()

    assert failure.value.violations[0].code == "limit_exceeded"


def test_candidate_bridge_prepares_frozen_source_inventory(
    candidate_bridge_data: tuple[PreparedSetModule, dict[str, object]],
) -> None:
    prepared, vectors = candidate_bridge_data
    identity = cast(dict[str, object], vectors["identity"])

    assert prepared.sha256 == _FIXTURE_SOURCE_SHA256
    assert prepared.source_revision == f"sha256:{_FIXTURE_SOURCE_SHA256}"
    assert prepared.module_id == identity["module"]
    assert prepared.record_id == identity["record"]
    assert prepared.action_id == identity["wireAction"]
    assert prepared.action_local_id == identity["action"]
    assert prepared.key_field_id == identity["keyField"]
    assert prepared.entity_parameter == identity["entityParameter"]
    assert prepared.frames == (identity["writeFrame"],)
    assert [(binding.input_id, binding.field_id) for binding in prepared.bindings] == [
        (identity["valueParameter"], identity["valueField"])
    ]
    entity = prepared.module.entity_types[0]
    assert entity.name == f"{identity['module']}.{identity['record']}"
    assert entity.key == identity["keyField"]
    assert {prop.name for prop in entity.properties} == {
        identity["keyField"],
        identity["valueField"],
    }
    action = prepared.module.actions[0]
    assert action.name == identity["wireAction"]
    assert [(item.name, item.type, item.kind) for item in action.inputs] == [
        (identity["entityParameter"], entity.name, "ref"),
        (identity["valueParameter"], "string", "scalar"),
    ]


def test_candidate_bridge_admits_apply_validate_and_import_vectors(
    candidate_bridge_data: tuple[PreparedSetModule, dict[str, object]],
) -> None:
    prepared, vectors = candidate_bridge_data
    identity = cast(dict[str, object], vectors["identity"])

    generated = cast(dict[str, object], vectors["generatedRequests"])
    apply_request = cast(dict[str, object], generated["apply"])
    validate_request = cast(dict[str, object], generated["validate"])
    assert apply_request["idempotency_key"] == "fixture-key"
    assert "idempotency_key" not in validate_request
    apply_set = _umf_actions.materialize(prepared, apply_request)
    validate_set = _umf_actions.materialize(prepared, validate_request)
    expected_digest = cast(dict[str, object], vectors["inputSha256"])["sha256"]
    for admitted in (apply_set, validate_set):
        assert admitted.ref.type == f"{identity['module']}.{identity['record']}"
        assert admitted.ref.key == "item-1"
        assert admitted.set_values == {identity["valueField"]: "ready"}
        assert admitted.inputs_digest == expected_digest

    imported = _umf_actions.admit_record(
        prepared,
        {
            "type": identity["record"],
            "key": "item-1",
            "properties": {identity["valueField"]: "ready"},
        },
    )
    assert imported.ref == apply_set.ref
    assert dict(imported.properties) == {"item_id": "item-1", "label": "ready"}
    _umf_actions.validate_candidate(prepared, dict(imported.properties))

    with pytest.raises(Invalid) as invalid_candidate:
        _umf_actions.validate_candidate(prepared, {"item_id": "item-1", "label": "pending"})
    assert invalid_candidate.value.violations[0].code == "umf_invalid"
    assert invalid_candidate.value.violations[0].path == "action"
    assert "Literal is not an allowed value" not in str(invalid_candidate.value)
    invalid_request = dict(validate_request)
    invalid_request["inputs"] = {
        "item": {"item_id": "item-1"},
        "label_value": "pending",
    }
    with pytest.raises(Invalid):
        _umf_actions.materialize(prepared, invalid_request)
