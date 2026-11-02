# SPDX-License-Identifier: MIT OR Apache-2.0
"""Closed validators for official UMF action result envelopes.

This module contains only inert shape validation; SDK calls and source preparation
remain in ``_umf_actions``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import cast

from arras._action_types import PreparedSetModule, SetBinding
from arras.errors import Unsupported

_PREPARED_PROFILE = "umf.actions.single-set-prepared/1"
_INVOCATION_PROFILE = "umf.actions.single-set-invocation/1"
_RECORD_PROFILE = "umf.actions.single-record-values/1"
_EXECUTOR_OBLIGATION_KINDS = ("authorization", "attribution", "atomicity", "idempotency", "result")
_SUPPORTED_OBLIGATION_KINDS = frozenset(
    {
        "authorization",
        "attribution",
        "atomicity",
        "binding",
        "effect",
        "frame",
        "idempotency",
        "key",
        "model",
        "result",
        "selector",
        "value",
    }
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _prepared_shape(
    result: Mapping[str, object], request: Mapping[str, object]
) -> tuple[
    dict[str, object], dict[str, object], list[object], list[object], list[dict[str, object]]
]:
    expected_keys = {
        "profile",
        "source",
        "model",
        "action",
        "wireAction",
        "entityParameter",
        "target",
        "keyFields",
        "assignments",
        "frames",
        "obligations",
        "authorization",
        "requiredExecutorObligations",
        "executionVerified",
    }
    if set(result) != expected_keys:
        raise TypeError("official action runtime returned an unexpected preparation shape")
    if result.get("profile") != _PREPARED_PROFILE or result.get("executionVerified") is not False:
        raise TypeError("official action runtime returned an unrecognized preparation profile")
    action_pin = _map(request.get("action"), "action pin")
    identity = _map(action_pin.get("identity"), "action identity")
    wire_action = f"{_nonempty(identity.get('module'), 'action module')}.{_nonempty(identity.get('action'), 'action id')}"
    if (
        result.get("source") != request["source"]
        or result.get("model") != request["model"]
        or result.get("action") != request["action"]
        or result.get("wireAction") != wire_action
    ):
        raise TypeError("official action runtime preparation does not bind the exact source pins")
    target, key_fields, assignments, frames = validate_official_prepared_inventory(result, request)
    prepared = dict(result)
    return prepared, target, key_fields, assignments, frames


def validate_official_prepared_inventory(
    result: Mapping[str, object], request: Mapping[str, object]
) -> tuple[dict[str, object], list[object], list[object], list[dict[str, object]]]:
    if type(result.get("entityParameter")) is not str:
        raise TypeError("official action runtime returned an invalid entity parameter")
    module_name, record_name, _key_name = _key_ref(_map(result.get("target"), "target"))
    if not module_name or not record_name:
        raise TypeError("official action runtime returned an invalid target")
    key_fields = _list(result.get("keyFields"), "key fields")
    assignments = _list(result.get("assignments"), "assignments")
    frames = [_map(item, "frame") for item in _list(result.get("frames"), "frames")]
    if len(key_fields) != 1 or len(assignments) != 1 or len(frames) != 1:
        raise TypeError("official action runtime returned a profile outside single-SET scope")
    key_field = _field_ref(key_fields[0])
    assignment_input, assignment_module, assignment_field = _assignment(assignments[0])
    frame = frames[0]
    frame_record = _field_ref(frame.get("record"))
    frame_fields = _list(frame.get("fields"), "write frame fields")
    if (
        assignment_module != module_name
        or frame_record != (module_name, record_name)
        or len(frame_fields) != 1
        or _field_ref(frame_fields[0]) != (assignment_module, assignment_field)
        or frame.get("access") != "write"
        or frame.get("entityParameter") != result.get("entityParameter")
        or type(frame.get("id")) is not str
        or not frame.get("id")
        or not assignment_input
        or key_field[0] != module_name
    ):
        raise TypeError("official action runtime returned inconsistent single-SET identities")
    auth_request = _map(request.get("authorization"), "request authorization")
    request_profile = _map(auth_request.get("profile"), "request authorization profile")
    request_resources = _list(auth_request.get("resources"), "request authorization resources")
    request_evidence = _list(auth_request.get("evidence"), "request authorization evidence")
    auth_obligation_id = _validate_obligation_inventory(result)
    authorization = _map(result.get("authorization"), "authorization assessment")
    if (
        set(authorization) != {"obligation", "profile", "resources", "status", "evidence"}
        or authorization.get("profile") != request_profile
        or authorization.get("resources") != request_resources
        or authorization.get("evidence") != request_evidence
        or authorization.get("status") != "supported"
        or authorization.get("obligation") != auth_obligation_id
    ):
        raise TypeError(
            "official action runtime returned an inconsistent host obligation assessment"
        )
    return _map(result.get("target"), "target"), key_fields, assignments, frames


def _validate_obligation_inventory(result: Mapping[str, object]) -> str:
    obligations = [
        _map(item, "obligation") for item in _list(result.get("obligations"), "obligations")
    ]
    counts: dict[str, int] = {}
    obligation_ids: list[str] = []
    authorization_id: str | None = None
    expected_executor_ids: list[str] = []
    for obligation in obligations:
        identifier = obligation.get("id")
        kind = obligation.get("kind")
        status = obligation.get("status")
        if (
            set(obligation) != {"id", "path", "kind", "status"}
            or type(identifier) is not str
            or not identifier
            or obligation.get("path") != identifier
            or type(kind) is not str
            or kind not in _SUPPORTED_OBLIGATION_KINDS
            or type(status) is not str
            or status != ("unchecked" if kind == "authorization" else "checked")
        ):
            raise TypeError("official action runtime returned an invalid obligation inventory")
        obligation_ids.append(identifier)
        counts[kind] = counts.get(kind, 0) + 1
        if kind in _EXECUTOR_OBLIGATION_KINDS:
            expected_executor_ids.append(identifier)
        if kind == "authorization":
            authorization_id = identifier
    if len(set(obligation_ids)) != len(obligation_ids) or any(
        counts.get(kind) != 1 for kind in _EXECUTOR_OBLIGATION_KINDS
    ):
        raise TypeError("official action runtime returned incomplete host obligations")
    raw_executor_ids = _list(result.get("requiredExecutorObligations"), "executor obligations")
    if (
        any(type(item) is not str for item in raw_executor_ids)
        or cast(list[str], raw_executor_ids) != expected_executor_ids
        or authorization_id is None
    ):
        raise TypeError("official action runtime returned invalid executor obligations")
    return authorization_id


def _key_ref(value: Mapping[str, object]) -> tuple[str, str, str]:
    if set(value) != {"module", "element", "key"}:
        raise TypeError("official runtime returned an invalid KeyRef")
    return (
        _nonempty(value.get("module"), "KeyRef module"),
        _nonempty(value.get("element"), "KeyRef element"),
        _nonempty(value.get("key"), "KeyRef key"),
    )


def _field_ref(value: object) -> tuple[str, str]:
    field = _map(value, "FieldRef")
    if set(field) != {"module", "element"}:
        raise TypeError("official runtime returned an invalid FieldRef")
    return (
        _nonempty(field.get("module"), "FieldRef module"),
        _nonempty(field.get("element"), "FieldRef element"),
    )


def _assignment(value: object) -> tuple[str, str, str]:
    assignment = _map(value, "assignment")
    if set(assignment) != {"input", "field"}:
        raise TypeError("official runtime returned an invalid assignment")
    module, field = _field_ref(assignment.get("field"))
    return (_nonempty(assignment.get("input"), "assignment input"), module, field)


def _invocation_shape(
    result: Mapping[str, object],
    prepared: PreparedSetModule,
    action_request: Mapping[str, object],
) -> tuple[dict[str, object], list[tuple[SetBinding, str]]]:
    expected_keys = {
        "profile",
        "preparation",
        "inputs",
        "entity",
        "assignments",
        "inputSha256Profile",
        "inputSha256",
        "executionVerified",
    }
    if set(result) != expected_keys:
        raise TypeError("official action runtime returned an unexpected invocation shape")
    if result.get("profile") != _INVOCATION_PROFILE or result.get("executionVerified") is not False:
        raise TypeError("official action runtime returned an unrecognized invocation profile")
    preparation = _map(result.get("preparation"), "preparation")
    entity = _map(result.get("entity"), "entity")
    _, target, key_fields, source_assignments, source_frames = _prepared_shape(
        preparation, action_request
    )
    module_name, record_name, _key_name = _key_ref(target)
    if (
        module_name != prepared.module_id
        or record_name != prepared.record_id
        or len(key_fields) != 1
        or _field_ref(key_fields[0]) != (prepared.module_id, prepared.key_field_id)
        or len(source_assignments) != len(prepared.bindings)
        or len(source_frames) != 1
        or source_frames[0].get("id") != prepared.frames[0]
        or target != _map(entity.get("key"), "entity key")
    ):
        raise TypeError("official action runtime invocation preparation differs from source")
    for raw_assignment, binding in zip(source_assignments, prepared.bindings, strict=True):
        input_id, module_name, field_id = _assignment(raw_assignment)
        if (input_id, module_name, field_id) != (
            binding.input_id,
            prepared.module_id,
            binding.field_id,
        ):
            raise TypeError("official action runtime invocation assignments differ from source")
    if result.get("inputSha256Profile") != "umf.actions.generated-invocation/1":
        raise TypeError("official action runtime returned an unknown input digest profile")
    if entity.get("profile") != "umf-key-tuple-v1":
        raise TypeError("official action runtime returned an unrecognized key profile")
    module, record, _key = _key_ref(_map(entity.get("key"), "entity key"))
    if (
        module != prepared.module_id
        or record != prepared.record_id
        or entity.get("parameter") != prepared.entity_parameter
    ):
        raise TypeError("official action runtime invocation identity does not match source")
    tuple_hex = _nonempty(entity.get("tupleHex"), "tupleHex")
    if len(tuple_hex) % 2 or any(char not in "0123456789abcdef" for char in tuple_hex):
        raise TypeError("official action runtime returned an invalid key tuple")
    key_fields = _list(entity.get("fields"), "entity key fields")
    components = _list(entity.get("components"), "entity key components")
    if (
        len(key_fields) != 1
        or len(components) != 1
        or _field_ref(key_fields[0]) != (prepared.module_id, prepared.key_field_id)
    ):
        raise TypeError("official action runtime returned a key outside the selected profile")
    if result.get("inputs") is None or not isinstance(result.get("inputs"), Mapping):
        raise TypeError("official action runtime returned invalid admitted inputs")
    raw_assignments = _list(result.get("assignments"), "admitted assignments")
    if len(raw_assignments) != len(prepared.bindings):
        raise TypeError("official action runtime returned an incomplete SET")
    accepted: list[tuple[SetBinding, str]] = []
    for binding, raw in zip(prepared.bindings, raw_assignments, strict=True):
        item = _map(raw, "admitted assignment")
        module_name, field_name = _field_ref(item.get("field"))
        literal = _map(item.get("literal"), "CoreLiteral")
        native = item.get("native")
        if (
            module_name != prepared.module_id
            or field_name != binding.field_id
            or item.get("input") != binding.input_id
            or set(literal) != {"string"}
            or type(literal.get("string")) is not str
            or type(native) is not str
            or literal["string"] != native
        ):
            raise TypeError("official action runtime returned an inconsistent SET value")
        accepted.append((binding, native))
    return entity, accepted


def _record_shape(
    result: Mapping[str, object], prepared: PreparedSetModule
) -> tuple[dict[str, str], dict[str, object]]:
    expected_keys = {
        "profile",
        "source",
        "model",
        "record",
        "values",
        "entity",
        "executionVerified",
    }
    if set(result) != expected_keys:
        raise TypeError("official action runtime returned an unexpected record shape")
    if result.get("profile") != _RECORD_PROFILE or result.get("executionVerified") is not False:
        raise TypeError("official action runtime returned an unrecognized record profile")
    digest = prepared.sha256
    if (
        result.get("source")
        != {
            "mediaType": "application/json",
            "utf8": prepared.source.decode("utf-8"),
            "sha256": digest,
        }
        or result.get("model")
        != {
            "documentId": prepared.document_id,
            "revision": prepared.source_revision,
            "umfVersion": "0.10.0",
            "sha256": digest,
        }
        or result.get("record") != {"module": prepared.module_id, "element": prepared.record_id}
    ):
        raise TypeError("official action runtime record admission is not source-bound")
    values = _list(result.get("values"), "record values")
    expected = {prepared.key_field_id, *(binding.field_id for binding in prepared.bindings)}
    decoded: dict[str, str] = {}
    if len(values) != len(expected):
        raise TypeError("official action runtime returned duplicate or extra record values")
    for value in values:
        item = _map(value, "record value")
        module, field = _field_ref(item.get("field"))
        literal = _map(item.get("literal"), "record CoreLiteral")
        native = item.get("native")
        if (
            module != prepared.module_id
            or set(literal) != {"string"}
            or type(literal.get("string")) is not str
            or type(native) is not str
            or native != literal["string"]
        ):
            raise TypeError("official action runtime returned an inconsistent record value")
        if field in decoded:
            raise TypeError("official action runtime returned a duplicate record field")
        decoded[field] = native
    if decoded.keys() != expected:
        raise TypeError("official action runtime returned incomplete record values")
    entity = _map(result.get("entity"), "record key")
    if entity.get("profile") != "umf-key-tuple-v1":
        raise TypeError("official action runtime returned an unrecognized key profile")
    key_module, key_record, _key_id = _key_ref(_map(entity.get("key"), "record key reference"))
    if key_module != prepared.module_id or key_record != prepared.record_id:
        raise TypeError("official action runtime record key does not match source")
    tuple_hex = _nonempty(entity.get("tupleHex"), "tupleHex")
    if len(tuple_hex) % 2 or any(char not in "0123456789abcdef" for char in tuple_hex):
        raise TypeError("official action runtime returned an invalid key tuple")
    key_fields = _list(entity.get("fields"), "record key fields")
    components = _list(entity.get("components"), "record key components")
    if (
        len(key_fields) != 1
        or len(components) != 1
        or _field_ref(key_fields[0]) != (prepared.module_id, prepared.key_field_id)
    ):
        raise TypeError("official action runtime returned a key outside the selected profile")
    return decoded, entity


def _entity_key_value(entity: Mapping[str, object], prepared: PreparedSetModule) -> str:
    if _field_ref(_list(entity.get("fields"), "entity key fields")[0]) != (
        prepared.module_id,
        prepared.key_field_id,
    ):
        raise TypeError("official action runtime key field does not match source")
    components = _list(entity.get("components"), "entity key components")
    if len(components) != 1:
        raise TypeError("official action runtime returned a non-singleton key")
    literal = _map(components[0], "key literal")
    if set(literal) != {"string"} or type(literal.get("string")) is not str:
        raise TypeError("official action runtime returned a non-string key")
    value = cast(str, literal["string"])
    from arras.actions import KEY_VALUE

    if KEY_VALUE.fullmatch(value) is None:
        raise Unsupported(
            "official UMF action key carrier", ["the Arras physical string-key range"]
        )
    return value


def _map(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"official action runtime returned an invalid {label}")
    if any(type(key) is not str for key in cast(dict[object, object], value)):
        raise TypeError(f"official action runtime returned an invalid {label}")
    return cast(dict[str, object], value)


def _list(value: object, label: str) -> list[object]:
    if type(value) is not list:
        raise TypeError(f"official action runtime returned invalid {label}")
    return cast(list[object], value)


def _nonempty(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise TypeError(f"official action runtime/source contains invalid {label}")
    return value


__all__ = [
    "_assignment",
    "_entity_key_value",
    "_field_ref",
    "_invocation_shape",
    "_key_ref",
    "_list",
    "_map",
    "_nonempty",
    "_prepared_shape",
    "_record_shape",
    "_validate_obligation_inventory",
    "validate_official_prepared_inventory",
]
