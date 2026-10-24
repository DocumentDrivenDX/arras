# SPDX-License-Identifier: MIT OR Apache-2.0
"""Closed `umf.access/1` request and response shapes for the single-SET host route."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import cast

from arras import telemetry
from arras._catalogs import Catalogs
from arras.actions import ActionInfo
from arras.backend import Backend, DeclaredActionProvider
from arras.errors import (
    Conflict,
    Invalid,
    PreconditionFailed,
    Refused,
    Unavailable,
    Unsupported,
    Violation,
)
from arras.model import ModuleInfo
from arras.results import BackendInfo, Receipt, Validation
from arras.types import Principal

CONTRACT = "umf.access/1"
MAX_ACTION_INPUTS = 2
MAX_ACTION_TEXT = 4_096
MAX_ACTION_TEXT_TOTAL = 8_192


def request_kind(request: Mapping[str, object]) -> tuple[str, str, Mapping[str, object]]:
    """Check only the closed transport envelope; the SDK owns input semantics."""
    if type(request) is not dict:
        raise Invalid([Violation("request", "type", "an exact object is required")])
    exact = cast(dict[str, object], request)
    if any(type(key) is not str for key in exact):
        raise Invalid([Violation("request", "type", "exact string member names are required")])
    kind: object = exact.get("kind")
    action: object = exact.get("action")
    inputs: object = exact.get("inputs")
    if type(kind) is not str:
        raise Invalid([Violation("kind", "type", "apply or validate is required")])
    expected: set[str] = {"contract", "schema", "kind", "action", "inputs"}
    if kind == "apply":
        expected.add("idempotency_key")
    if set(exact) != expected:
        raise Invalid([Violation("request", "shape", "the generated action envelope is required")])
    raw_contract = exact.get("contract")
    if type(raw_contract) is not str:
        raise Invalid([Violation("contract", "type", "an exact contract identifier is required")])
    if raw_contract != CONTRACT:
        raise Unsupported("action contract", [CONTRACT])
    raw_schema = exact.get("schema")
    if type(raw_schema) is not str:
        raise Invalid([Violation("schema", "type", "a nonempty schema digest is required")])
    schema = raw_schema
    if len(schema) != 64 or any(char not in "0123456789abcdef" for char in schema):
        raise Invalid([Violation("schema", "type", "a nonempty schema digest is required")])
    if kind not in ("apply", "validate"):
        raise Unsupported("action request kind", ["apply", "validate"])
    if type(action) is not str or not action or len(action) > 256:
        raise Invalid([Violation("action", "type", "a qualified action identifier is required")])
    if type(inputs) is not dict:
        raise Invalid([Violation("inputs", "type", "an exact object keyed by input identifiers")])
    input_object = cast(dict[str, object], inputs)
    if any(type(key) is not str for key in input_object):
        raise Invalid([Violation("inputs", "type", "an exact object keyed by input identifiers")])
    if (
        kind == "apply"
        and exact["idempotency_key"] is not None
        and (
            type(exact["idempotency_key"]) is not str
            or not exact["idempotency_key"]
            or len(exact["idempotency_key"]) > 256
        )
    ):
        raise Invalid([Violation("idempotency_key", "type", "a nonempty string or null")])
    return kind, action, input_object


def validate_response(schema: str, validation: Validation) -> Mapping[str, object]:
    if not validation.ok:
        raise Unsupported(
            "a negative action validation response",
            ["the selected generated client accepts only a valid response"],
        )
    return {"schema": schema, "valid": True}


def apply_response(
    schema: str,
    action: ActionInfo,
    inputs: Mapping[str, object],
    receipt: Receipt,
) -> Mapping[str, object]:
    """Serialize the supported one-record SET receipt, without inferring wire IDs from dots."""
    refs = receipt.refs
    targets = [spec for spec in action.inputs if spec.kind == "ref"]
    no_op = (
        not refs
        and receipt.created == 0
        and receipt.updated == 0
        and receipt.deleted == 0
        and receipt.linked == 0
        and receipt.unlinked == 0
    )
    changed = (
        len(refs) == 1
        and receipt.created == 0
        and receipt.updated == 1
        and receipt.deleted == 0
        and receipt.linked == 0
        and receipt.unlinked == 0
    )
    if (
        receipt.action != action.name
        or len(targets) != 1
        or not (no_op or changed)
        or not receipt.token
    ):
        raise Unsupported(
            "action receipt shape", ["one changed record or an acknowledged no-op SET"]
        )
    target = targets[0]
    key = inputs.get(target.name)
    if type(key) is not dict:
        raise Unsupported("action receipt identity", ["the admitted single string key"])
    key_object = cast(dict[str, object], key)
    if len(key_object) != 1:
        raise Unsupported("action receipt identity", ["the admitted single string key"])
    if any(type(field) is not str or type(value) is not str for field, value in key_object.items()):
        raise Unsupported("action receipt identity", ["the admitted single string key"])
    if not no_op and (
        target.type != refs[0].type or next(iter(key_object.values())) != refs[0].key
    ):
        raise Unsupported("action receipt identity", ["the admitted single string key"])
    if no_op and (target.type == "" or not key_object):
        raise Unsupported("action receipt identity", ["the admitted single string key"])
    return {
        "schema": schema,
        "status": "committed",
        "created": [],
        "changed": [] if no_op else [{"record": target.type, "key": dict(key_object)}],
        "counts": {
            "created": receipt.created,
            "updated": receipt.updated,
            "deleted": receipt.deleted,
            "linked": receipt.linked,
            "unlinked": receipt.unlinked,
        },
        "consistency_token": receipt.token,
    }


def snapshot_request(request: Mapping[str, object]) -> dict[str, object]:
    """Copy only the bounded JSON carrier used by the selected one-SET wire profile."""
    if type(request) is not dict:
        raise Invalid([Violation("request", "shape", "a bounded exact object is required")])
    request_object = cast(dict[str, object], request)
    if len(request_object) > 6 or any(type(key) is not str for key in request_object):
        raise Invalid([Violation("request", "shape", "a bounded exact object is required")])
    snapshot = dict(request_object)
    raw_inputs = snapshot.get("inputs")
    if type(raw_inputs) is not dict:
        raise Invalid([Violation("inputs", "bound", "at most two generated inputs are supported")])
    input_object = cast(dict[str, object], raw_inputs)
    if len(input_object) > MAX_ACTION_INPUTS:
        raise Invalid([Violation("inputs", "bound", "at most two generated inputs are supported")])
    copied: dict[str, object] = {}
    text_total = 0
    for key, value in input_object.items():
        if type(key) is not str or not key or len(key) > 256:
            raise Invalid([Violation("inputs", "type", "bounded input identifiers are required")])
        text_total += len(key)
        if type(value) is str:
            if len(value) > MAX_ACTION_TEXT:
                raise Invalid([Violation("inputs", "bound", "generated string input is too long")])
            copied[key] = value
            text_total += len(value)
        elif type(value) is dict:
            pair = cast(dict[str, object], value)
            if len(pair) != 1:
                raise Invalid([Violation("inputs", "type", "one string key is supported")])
            field, field_value = next(iter(pair.items()))
            if type(field) is not str or not field or len(field) > 256:
                raise Invalid(
                    [Violation("inputs", "type", "bounded key field identifiers are required")]
                )
            if type(field_value) is not str or len(field_value) > MAX_ACTION_TEXT:
                raise Invalid([Violation("inputs", "type", "a bounded string key is required")])
            copied[key] = {field: field_value}
            text_total += len(field) + len(field_value)
        else:
            raise Invalid(
                [Violation("inputs", "type", "only generated string inputs are supported")]
            )
        if text_total > MAX_ACTION_TEXT_TOTAL:
            raise Invalid(
                [Violation("inputs", "bound", "generated string inputs exceed the transport bound")]
            )
    snapshot["inputs"] = copied
    return snapshot


def execute(
    principal: Principal,
    request: Mapping[str, object],
    *,
    require_user: Callable[[str], None],
    backends: Mapping[str, Backend],
    collect: Callable[[str], Catalogs],
    backend_for: Callable[[str], Backend],
) -> Mapping[str, object]:
    """Run a generated request after auth; encode only bounded known no-effect refusals."""
    try:
        require_user("execute")
    except Refused as error:
        return _known_error_or_raise(request, error)

    try:
        if not backends:
            raise Unavailable("arras", "not_configured", "no backend is configured")
        catalogs = collect("execute")
        # A refusal wins before request inspection only when no readable catalog answered.
        if not catalogs.names() and (failure := catalogs.failure()) is not None:
            raise failure
        snapshot = snapshot_request(request)
        kind, action_name, inputs = request_kind(snapshot)
        schema = cast(str, snapshot["schema"])
        matches: list[tuple[ModuleInfo, ActionInfo]] = [
            (module, action)
            for name in catalogs.names()
            if (module := catalogs.module(name)) is not None
            for action in module.actions
            if action.name == action_name
        ]
        if not matches:
            raise Invalid([Violation("action", "unknown_action", "no such action is readable")])
        if len(matches) != 1:
            raise Invalid([Violation("action", "ambiguous", "the qualified action is not unique")])
        mod, action = matches[0]
        if mod.metadata_profile != "arras-umf-set/1":
            raise Unsupported("action profile", ["arras-umf-set/1"])
        backend = backend_for(mod.placement.provider_of(action.name))
        info: BackendInfo = backend.describe()
        profiles = info.action_profiles
        if (
            type(profiles) is not tuple
            or any(type(profile) is not str for profile in profiles)
            or "arras-umf-set/1" not in profiles
        ):
            raise Unsupported("action provider", ["arras-umf-set/1"])
        apply_declared = getattr(backend, "apply_declared_action", None)
        if not callable(apply_declared):
            raise Unsupported("action provider", ["DeclaredActionProvider"])
        provider = cast(DeclaredActionProvider, backend)
    except (Conflict, Invalid, PreconditionFailed, Refused, Unavailable, Unsupported) as error:
        return _known_error_or_raise(request, error)

    # The provider contract guarantees these typed refusals occur before its atomic publish.
    # Unexpected exceptions and malformed success results stay errors, so the generated client
    # correctly reports write outcome unknown rather than a fabricated refusal.
    try:
        result = provider.apply_declared_action(principal, mod.name, snapshot)
    except (Conflict, Invalid, PreconditionFailed, Refused, Unsupported) as error:
        return _known_error_or_raise(snapshot, error, action)
    if kind == "validate":
        if not isinstance(result, Validation):
            raise TypeError("a provider answers validation with Validation")
        if not result.ok:
            return _error_response(schema, "UNSUPPORTED")
        return validate_response(schema, result)
    if not isinstance(result, Receipt):
        raise TypeError("a provider answers apply with Receipt")
    return apply_response(schema, action, inputs, result)


def _request_schema(request: Mapping[str, object]) -> str | None:
    """Read only the exact outer schema field, after authentication, for error correlation."""
    if type(request) is not dict:
        return None
    exact = cast(dict[object, object], request)
    if len(exact) > 6:
        return None
    if any(type(key) is not str for key in exact):
        return None
    value = exact.get("schema")
    if type(value) is not str or len(value) != 64:
        return None
    return value if all(char in "0123456789abcdef" for char in value) else None


def _known_error_or_raise(
    request: Mapping[str, object],
    error: Conflict | Invalid | PreconditionFailed | Refused | Unavailable | Unsupported,
    action: ActionInfo | None = None,
) -> Mapping[str, object]:
    schema = _request_schema(request)
    response = _error_for(schema, error, action)
    if response is None:
        raise error
    payload: object = response.get("error")
    if type(payload) is dict:
        code: object = cast(dict[str, object], payload).get("code")
        if type(code) is str:
            telemetry.record_refusal(code)
    return response


def _error_for(
    schema: str | None,
    error: Conflict | Invalid | PreconditionFailed | Refused | Unavailable | Unsupported,
    action: ActionInfo | None = None,
) -> Mapping[str, object] | None:
    if schema is None:
        return None
    code = "INVALID"
    detail: dict[str, str] = {}
    if isinstance(error, Refused):
        code = "DENIED"
    elif isinstance(error, Conflict):
        code = "CONFLICT"
    elif isinstance(error, PreconditionFailed):
        code = "PRECONDITION_FAILED"
        known: set[str] = set()
        if action is not None:
            known.update(item.id for item in action.preconditions)
        if len(error.failures) == 1 and error.failures[0].id in known:
            detail["precondition"] = error.failures[0].id
    elif isinstance(error, Unsupported):
        code = "UNSUPPORTED"
    elif isinstance(error, Unavailable):
        code = "BUSY"
    else:
        codes = {item.code for item in error.violations}
        if "schema_mismatch" in codes:
            code = "SCHEMA_MISMATCH"
        elif "limit_exceeded" in codes:
            code = "LIMIT_EXCEEDED"
    return {"schema": schema, "error": {"code": code, **detail}}


def _error_response(schema: str, code: str) -> Mapping[str, object]:
    telemetry.record_refusal(code)
    return {"schema": schema, "error": {"code": code}}
