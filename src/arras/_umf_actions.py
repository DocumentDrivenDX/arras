# SPDX-License-Identifier: MIT OR Apache-2.0
"""Private adapter for the official, candidate UMF single-SET action runtime.

This module carries official results into Arras's small typed port. It does not evaluate
recipes, encode keys, validate values, or authorize a caller. The candidate API remains
optional and is not a release support claim.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from arras._action_types import AdmittedRecord, AdmittedSet, PreparedSetModule, SetBinding
from arras._umf_action_shapes import (
    _assignment,
    _entity_key_value,
    _field_ref,
    _invocation_shape,
    _key_ref,
    _list,
    _map,
    _nonempty,
    _prepared_shape,
    _record_shape,
)
from arras.actions import ActionInfo, InputSpec, Ref
from arras.errors import Invalid, Unsupported, Violation
from arras.model import UNPLACED, EntityTypeInfo, ModuleInfo, PropertyInfo
from arras.names import MODULE_NAME, check_name
from arras.types import Revision

_PROFILE = "arras-umf-set/1"
_POLICY = {"id": "arras.module-write", "version": "1"}
_POLICY_EVIDENCE = "arras:module-write/1"
_MAX_SOURCE = 1_048_576
_MAX_REQUEST = 4_194_304
_MAX_DEPTH = 64
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def runtime_available() -> bool:
    """Check candidate API and packaged-engine initialization, not semantic support."""
    from arras._umf_engine import action_runtime_available

    return action_runtime_available()


def prepare(source: bytes) -> PreparedSetModule:
    """Admit exact source bytes and ask the official runtime to prepare the narrow profile."""
    if type(source) is not bytes:
        raise TypeError("UMF action source must be exact bytes")
    if len(source) > _MAX_SOURCE:
        raise Invalid([Violation("document", "source_limit", "source exceeds the action profile")])
    text = _admit_source_text(source)
    snapshot = _snapshot(text)
    document_id, module_id, action_id, entity_parameter, value_input, frame_id = (
        _source_profile_ids(snapshot)
    )
    digest = hashlib.sha256(source).hexdigest()
    artifact = {"mediaType": "application/json", "utf8": text, "sha256": digest}
    model = {
        "documentId": document_id,
        "revision": f"sha256:{digest}",
        "umfVersion": "0.10.0",
        "sha256": digest,
    }
    action_pin = {
        "identity": {"module": module_id, "action": action_id},
        "documentSha256": digest,
        "invocation": {"id": "umf.actions.tx", "version": "1"},
    }
    authorization = {
        "profile": dict(_POLICY),
        "resources": [frame_id],
        "evidence": [_POLICY_EVIDENCE],
    }
    request: dict[str, object] = {
        "source": artifact,
        "model": model,
        "action": action_pin,
        "authorization": authorization,
    }
    _bounded(request)

    from arras._umf_engine import call_action_runtime

    result = call_action_runtime("prepare_single_set_action", request)
    _prepared, target, key_fields, assignments, frames = _prepared_shape(result, request)
    target_module, record_id, _key_id = _key_ref(target)
    if (
        target_module != module_id
        or len(key_fields) != 1
        or len(assignments) != 1
        or len(frames) != 1
    ):
        raise Unsupported(
            "official UMF single-SET action profile",
            ["one module, key, assignment, and write frame"],
        )
    key_module, key_field_id = _field_ref(key_fields[0])
    binding_input, binding_module, value_field_id = _assignment(assignments[0])
    frame = frames[0]
    if (
        key_module != module_id
        or binding_module != module_id
        or binding_input != value_input
        or result.get("entityParameter") != entity_parameter
        or frame["id"] != frame_id
        or frame["access"] != "write"
        or frame["entityParameter"] != entity_parameter
    ):
        raise Unsupported(
            "official UMF single-SET action profile", ["source and prepared identities must agree"]
        )
    frame_record_module, frame_record = _field_ref(frame.get("record"))
    frame_fields = _list(frame.get("fields"), "write-frame fields")
    if (
        set(frame) != {"id", "access", "record", "entityParameter", "fields"}
        or frame_record_module != module_id
        or frame_record != record_id
        or len(frame_fields) != 1
        or _field_ref(frame_fields[0]) != (module_id, value_field_id)
    ):
        raise Unsupported("official UMF single-SET action profile", ["one exact SET write frame"])

    properties = (key_field_id, value_field_id)
    if key_field_id == value_field_id:
        raise Unsupported(
            "official UMF single-SET action profile", ["key and assignment fields must be distinct"]
        )
    validate_arras_element_names(record_id, properties)
    entity = EntityTypeInfo(
        name=f"{module_id}.{record_id}",
        key=key_field_id,
        properties=tuple(PropertyInfo(name, "string", True, "one") for name in properties),
    )
    module = ModuleInfo(
        name=module_id,
        placement=UNPLACED,
        revision=Revision(),
        entity_types=(entity,),
        actions=(
            ActionInfo(
                name=f"{module_id}.{action_id}",
                description="",
                inputs=(
                    InputSpec(entity_parameter, entity.name, "ref", "one"),
                    InputSpec(value_input, "string", "scalar", "one"),
                ),
                preconditions=(),
                effects=(),
            ),
        ),
        metadata_profile=_PROFILE,
    )
    return PreparedSetModule(
        source=source,
        sha256=digest,
        module=module,
        document_id=document_id,
        source_revision=f"sha256:{digest}",
        module_id=module_id,
        record_id=record_id,
        action_id=f"{module_id}.{action_id}",
        action_local_id=action_id,
        key_field_id=key_field_id,
        key_property=key_field_id,
        entity_parameter=entity_parameter,
        bindings=(SetBinding(binding_input, value_field_id, value_field_id),),
        frames=(frame_id,),
        policy_profile="arras.module-write/1",
        resources=(frame_id,),
    )


def materialize(prepared: PreparedSetModule, request: Mapping[str, object]) -> AdmittedSet:
    """Admit one complete generated Apply or Validate envelope through UMF unchanged."""
    if type(prepared) is not PreparedSetModule or type(request) is not dict:
        raise TypeError("materialize requires prepared source and a generated request mapping")
    _require_prepared_source(prepared)
    invocation = cast(dict[str, object], request)
    _bounded(invocation)
    if invocation.get("contract") != "umf.access/1" or invocation.get("schema") != prepared.sha256:
        raise Invalid(
            [
                Violation(
                    "invocation",
                    "schema_mismatch",
                    "generated request does not match current source",
                )
            ]
        )
    if invocation.get("action") != prepared.action_id:
        raise Invalid(
            [
                Violation(
                    "invocation/action",
                    "unknown_action",
                    "generated action does not match current source",
                )
            ]
        )
    kind = invocation.get("kind")
    if kind == "apply":
        if set(invocation) != {"contract", "schema", "kind", "action", "inputs", "idempotency_key"}:
            raise Invalid(
                [
                    Violation(
                        "invocation", "shape", "generated Apply envelope has unsupported members"
                    )
                ]
            )
        key = invocation["idempotency_key"]
        if key is not None and (
            type(key) is not str or not key or len(key.encode("utf-16-le")) // 2 > 256
        ):
            raise Invalid(
                [
                    Violation(
                        "invocation/idempotency_key",
                        "invalid",
                        "idempotency key is outside the supported shape",
                    )
                ]
            )
    elif kind == "validate":
        if set(invocation) != {"contract", "schema", "kind", "action", "inputs"}:
            raise Invalid(
                [
                    Violation(
                        "invocation", "shape", "generated Validate envelope has unsupported members"
                    )
                ]
            )
    else:
        raise Unsupported("generated UMF action invocation", ["Apply or Validate"])

    envelope = _action_request(prepared)
    envelope["invocation"] = invocation
    from arras._umf_engine import call_action_runtime

    result = call_action_runtime("admit_generated_action_invocation", envelope)
    entity, assignments = _invocation_shape(result, prepared, _action_request(prepared))
    ref = Ref(f"{prepared.module_id}.{prepared.record_id}", _entity_key_value(entity, prepared))
    set_values = {binding.property: value for binding, value in assignments}
    input_digest = result.get("inputSha256")
    if type(input_digest) is not str or not _SHA256.fullmatch(input_digest):
        raise TypeError("official action runtime returned an invalid input digest")
    return AdmittedSet(ref, MappingProxyType(set_values), input_digest)


def admit_record(
    prepared: PreparedSetModule, public_import_record: Mapping[str, object]
) -> AdmittedRecord:
    """Admit a source-keyed candidate row using the official record/value callable."""
    if type(prepared) is not PreparedSetModule or type(public_import_record) is not dict:
        raise TypeError("record admission requires prepared source and a record mapping")
    _require_prepared_source(prepared)
    record = cast(dict[str, object], public_import_record)
    if any(type(field) is not str for field in record):
        raise Invalid([Violation("record", "shape", "record member names must be strings")])
    if set(record) != {"type", "key", "properties"}:
        raise Unsupported(
            "official UMF single-record import", ["a typed record, key, and field-value mapping"]
        )
    record_type = record.get("type")
    if type(record_type) is not str:
        raise Invalid([Violation("record/type", "invalid", "record type must be a string")])
    if record_type != prepared.record_id:
        raise Invalid(
            [Violation("record", "unknown_record", "record identity does not match current source")]
        )
    key = record.get("key")
    if type(key) is not str:
        raise Invalid([Violation("record/key", "invalid", "record key must be a string")])
    properties_raw = record.get("properties")
    if type(properties_raw) is not dict:
        raise Invalid(
            [Violation("record/properties", "shape", "record values must be a string mapping")]
        )
    raw_values = cast(dict[object, object], properties_raw)
    if any(type(field) is not str for field in raw_values):
        raise Invalid(
            [Violation("record/properties", "shape", "record field identifiers must be strings")]
        )
    if any(type(value) is not str for value in raw_values.values()):
        raise Invalid(
            [Violation("record/properties", "shape", "record field values must be strings")]
        )
    values = cast(dict[str, str], raw_values.copy())
    existing_key = values.get(prepared.key_field_id)
    if prepared.key_field_id in values and existing_key != key:
        raise Invalid(
            [Violation("record/key", "conflict", "record key conflicts with its key field")]
        )
    values[prepared.key_field_id] = key
    expected_fields = {prepared.key_field_id, *(binding.field_id for binding in prepared.bindings)}
    if values.keys() != expected_fields:
        raise Invalid(
            [
                Violation(
                    "record/properties",
                    "shape",
                    "record fields do not match the selected source record",
                )
            ]
        )
    digest = prepared.sha256
    request: dict[str, object] = {
        "source": {
            "mediaType": "application/json",
            "utf8": prepared.source.decode("utf-8"),
            "sha256": digest,
        },
        "model": {
            "documentId": prepared.document_id,
            "revision": prepared.source_revision,
            "umfVersion": "0.10.0",
            "sha256": digest,
        },
        "record": {"module": prepared.module_id, "element": prepared.record_id},
        "values": values,
    }
    _bounded(request)
    from arras._umf_engine import call_action_runtime

    result = call_action_runtime("admit_generated_record_values", request)
    values, entity = _record_shape(result, prepared)
    key_value = _entity_key_value(entity, prepared)
    if values.get(prepared.key_field_id) != key_value:
        raise TypeError(
            "official action runtime key component disagrees with admitted record values"
        )
    return AdmittedRecord(Ref(f"{prepared.module_id}.{prepared.record_id}", key_value), values)


def validate_candidate(prepared: PreparedSetModule, complete_values: Mapping[str, object]) -> None:
    """Use the official full-record admission path; no local constraint evaluation occurs."""
    record = {
        "type": prepared.record_id,
        "key": complete_values.get(prepared.key_field_id),
        "properties": complete_values,
    }
    admit_record(prepared, record)


def _action_request(prepared: PreparedSetModule) -> dict[str, object]:
    text = prepared.source.decode("utf-8", errors="strict")
    digest = prepared.sha256
    return {
        "source": {"mediaType": "application/json", "utf8": text, "sha256": digest},
        "model": {
            "documentId": prepared.document_id,
            "revision": prepared.source_revision,
            "umfVersion": "0.10.0",
            "sha256": digest,
        },
        "action": {
            "identity": {"module": prepared.module_id, "action": prepared.action_local_id},
            "documentSha256": digest,
            "invocation": {"id": "umf.actions.tx", "version": "1"},
        },
        "authorization": {
            "profile": dict(_POLICY),
            "resources": list(prepared.resources),
            "evidence": [_POLICY_EVIDENCE],
        },
    }


def _require_prepared_source(prepared: PreparedSetModule) -> None:
    if hashlib.sha256(prepared.source).hexdigest() != prepared.sha256:
        raise Invalid(
            [Violation("document", "source_mismatch", "prepared source identity is invalid")]
        )
    fresh = prepare(prepared.source)
    if fresh != prepared:
        raise Invalid(
            [
                Violation(
                    "document", "prepared_mismatch", "prepared profile differs from current source"
                )
            ]
        )


def _snapshot(text: str) -> dict[str, object]:
    from arras._umf_engine import read_typed_snapshot

    raw = read_typed_snapshot(text)
    if not isinstance(raw, dict):
        raise Unsupported("official UMF action source", ["one typed document object"])
    return cast(dict[str, object], raw)


def _source_ids(snapshot: Mapping[str, object]) -> tuple[str, str, str, str, str, str]:
    """Index only identity strings; all action meaning is admitted by the official SDK."""
    document_id = _nonempty(snapshot.get("id"), "document id")
    modules = _list(snapshot.get("modules"), "source modules")
    if len(modules) != 1:
        raise Unsupported("official UMF single-SET action profile", ["exactly one source module"])
    module = _map(modules[0], "source module")
    module_id = _nonempty(module.get("id"), "module id")
    extensions_raw = module.get("extensions")
    if not isinstance(extensions_raw, dict):
        raise Unsupported("official UMF single-SET action profile", ["one umf.actions extension"])
    extensions = cast(dict[str, object], extensions_raw)
    extension_raw = extensions.get("umf.actions")
    if not isinstance(extension_raw, dict):
        raise Unsupported("official UMF single-SET action profile", ["one umf.actions extension"])
    extension = cast(dict[str, object], extension_raw)
    actions = _list(extension.get("actions"), "source actions")
    if len(actions) != 1:
        raise Unsupported("official UMF single-SET action profile", ["exactly one action"])
    action = _map(actions[0], "source action")
    action_id = _nonempty(action.get("id"), "action id")
    parameters = _list(action.get("parameters"), "source parameters")
    rows = [_map(row, "source parameter") for row in parameters]
    entities = [row for row in rows if row.get("kind") == "entity"]
    values = [row for row in rows if row.get("kind") == "value"]
    writes = _list(action.get("writes"), "source writes")
    if len(entities) != 1 or len(values) != 1 or len(writes) != 1:
        raise Unsupported(
            "official UMF single-SET action profile", ["one entity, value, and write frame"]
        )
    entity = entities[0]
    value = values[0]
    frame = _map(writes[0], "source write frame")
    return (
        document_id,
        module_id,
        action_id,
        _nonempty(entity.get("id"), "entity parameter id"),
        _nonempty(value.get("id"), "value parameter id"),
        _nonempty(frame.get("id"), "write frame id"),
    )


def _admit_source_text(source: bytes) -> str:
    try:
        text = source.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise Invalid(
            [Violation("document", "source_profile", "source must be strict UTF-8")]
        ) from None
    from arras.umf_admission import admit_document

    admission = admit_document(source)
    if admission.validation_status != "completed":
        raise Unsupported("official UMF single-SET action profile", ["complete valid UMF source"])
    if admission.valid is False:
        raise Invalid(
            [Violation("document", "invalid_document", "official UMF validation rejected source")]
        )
    if admission.valid is not True:
        raise Unsupported("official UMF single-SET action profile", ["complete valid UMF source"])
    return text


def _source_profile_ids(snapshot: Mapping[str, object]) -> tuple[str, str, str, str, str, str]:
    identifiers = _source_ids(snapshot)
    _, module_id, action_id, entity_parameter, value_input, frame_id = identifiers
    validate_arras_profile_names(module_id, action_id, entity_parameter, value_input, frame_id)
    return identifiers


def validate_arras_profile_names(
    module_id: str,
    action_id: str,
    entity_parameter: str,
    value_input: str,
    frame_id: str,
) -> None:
    if MODULE_NAME.fullmatch(module_id) is None:
        raise Invalid([Violation("module/id", "invalid_name", "module identifier is unsupported")])
    for path, name in (
        ("action/id", action_id),
        ("action/entity_parameter", entity_parameter),
        ("action/value_input", value_input),
    ):
        if check_name(name, path) is not None:
            raise Invalid([Violation(path, "invalid_name", "identifier is unsupported")])
    if entity_parameter.casefold() == value_input.casefold():
        raise Invalid(
            [Violation("action/inputs", "invalid_name", "input identifiers are not distinct")]
        )
    if (
        not frame_id
        or not frame_id.isascii()
        or len(frame_id) > 256
        or any(ord(char) < 0x20 for char in frame_id)
    ):
        raise Invalid(
            [Violation("action/frame", "invalid_name", "write-frame identifier is unsupported")]
        )


def validate_arras_element_names(record_id: str, property_ids: tuple[str, ...]) -> None:
    if check_name(record_id, "record/id", entity_type=True) is not None:
        raise Invalid([Violation("record/id", "invalid_name", "record identifier is unsupported")])
    seen: set[str] = set()
    for property_id in property_ids:
        if check_name(property_id, "record/property") is not None:
            raise Invalid(
                [Violation("record/property", "invalid_name", "property identifier is unsupported")]
            )
        folded = property_id.lower()
        if folded in seen:
            raise Invalid(
                [
                    Violation(
                        "record/properties", "invalid_name", "property identifiers are not distinct"
                    )
                ]
            )
        seen.add(folded)


def _bounded(value: object, depth: int = 0) -> None:
    if depth > _MAX_DEPTH:
        raise Invalid([Violation("request", "depth_limit", "action request exceeds nesting limit")])
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        for key, item in mapping.items():
            if type(key) is not str:
                raise Invalid([Violation("request", "shape", "request keys must be strings")])
            _bounded(item, depth + 1)
    elif type(value) is list:
        for item in cast(list[object], value):
            _bounded(item, depth + 1)
    elif value is None or type(value) in (str, int, float, bool):
        return
    else:
        raise Invalid([Violation("request", "shape", "request must contain plain JSON values")])
    if depth == 0:
        try:
            encoded = json.dumps(
                value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeEncodeError):
            raise Invalid(
                [Violation("request", "shape", "request is not valid JSON data")]
            ) from None
        if len(encoded) > _MAX_REQUEST:
            raise Invalid(
                [
                    Violation(
                        "request", "size_limit", "request exceeds the action profile size limit"
                    )
                ]
            )
