# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independent identity and credential-lifecycle checks for the Lakebase harness.

Fixture callbacks provide provider observations and bounded controls only. This module derives
case outcomes from those facts, fresh PostgreSQL connections, and the public Arras API.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
from typing import Any, cast

from arras.errors import Invalid, Refused
from arras.types import Principal

if __package__:
    from ._lakebase_operations import HARNESS_MODULE_DOCUMENT, _case_row
else:
    from _lakebase_operations import HARNESS_MODULE_DOCUMENT, _case_row

_ACTORS = ("registrar", "writer", "reader", "denied")
_OAUTH_PROFILES = frozenset({"human-oauth", "nonhuman-oauth"})
_PROFILES = frozenset({"native-password", *_OAUTH_PROFILES})
_METHODS = frozenset(
    {
        "provider-identity-api",
        "provider-issued-credential-binding",
        "cryptographically-verified-oauth",
        "native-role-authority",
    }
)
_IDENTITY_KEYS = {
    "auth_profile",
    "subject_kind",
    "subject_reference_sha256",
    "sql_role_sha256",
    "provider_resource_sha256",
    "provider_observation_sha256",
    "credential_generation",
    "credential_expires_at",
    "provenance_method",
}
_PERSON_REQUIRED_OPERATIONS = frozenset(
    {"read", "apply", "refresh", "revoke_owned_memberships", "expire_owned_login"}
)
_EXPECTED_SNAPSHOT_COMPARISONS = 4
_VALIDATION_ALLOCATOR_SEQUENCES = frozenset(
    {
        "id_seq",
        "key_storage_row_seq",
        "journal_seq",
        "request_receipt_row_seq",
        "runtime_feed_reservation_seq",
        "runtime_object_transition_seq",
    }
)
_VALIDATION_ALLOCATOR_TRUSS_VERSION = "0.0.50"
_VALIDATION_ALLOCATOR_WHEEL_SHA256 = (
    "7b0483bb0c624c98515cf38ec30bbbf1ca43c1250e8880e5d00d520b4b7eec00"
)
_VALIDATION_ALLOCATOR_NATIVE_SHA256 = (
    "288801f7177338328441b5d3ce9328af31740ebf513f04ea45e30ae316a9f3a4"
)
_VALIDATION_ALLOCATOR_SOURCE_SHA256 = {
    "feed.sql": "ebfa70c3b91221aff15c953130c437667f3c40748a6e76a9467a55e1d76c4787",
    "groups.sql": "dcdc317ce1d3844f1d16853576b21c6238de3fe752b4d86fe44d13b2a9f3df22",
    "layout.sql": "fc2cdc8dfc80aef7f630a21ee9587751b9b026d9491832c0cdbb89c4a72feaa3",
    "operations.sql": "1ecbfecc7642fdb2b21a7180bf4c7c7394587493061e71a9d87977a416cc7ffd",
}


class PersonFailure(Exception):
    """A person-control postcondition was not independently established."""

    def __init__(self, code: str) -> None:
        self.code = code


_FAILURE_CODES = frozenset(
    {
        "credential_refusal_failed",
        "expired_credential_accepted",
        "registrar_authority_mismatch",
        "writer_operation_refused",
        "denied_actor_authorized",
        "membership_revoke_mismatch",
        "revoked_writer_authorized",
        "membership_restore_mismatch",
        "person_state_changed",
        "credential_refresh_mismatch",
    }
)


def _digest(value: object, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _profile_map(target: Mapping[str, Any]) -> dict[str, str]:
    auth = target.get("actor_auth_profiles")
    if type(auth) is not dict or set(auth) != set(_ACTORS):
        raise ValueError("actor authentication map is malformed")
    if any(type(auth[label]) is not str or auth[label] not in _PROFILES for label in _ACTORS):
        raise ValueError("actor authentication profile is invalid")
    if target.get("schema_version") == 2 and (
        target.get("auth_profile") != "mixed"
        or target.get("human_actor") != "writer"
        or auth["writer"] != "human-oauth"
    ):
        raise ValueError("schema-2 human writer authorization is not exact")
    return dict(auth)


def _identity_fact(
    raw: object,
    *,
    label: str,
    principal: Principal,
    target: Mapping[str, Any],
    provider_observation_sha256: str,
    now: int,
) -> dict[str, Any]:
    profiles = _profile_map(target)
    if type(raw) is not dict or set(raw) != _IDENTITY_KEYS:
        raise ValueError("person identity observation has an unexpected shape")
    profile = profiles[label]
    expected_kind = {
        "native-password": "native-role",
        "human-oauth": "human",
        "nonhuman-oauth": "nonhuman",
    }[profile]
    expected_method = raw["provenance_method"]
    if type(expected_method) is not str or expected_method not in _METHODS:
        raise ValueError("person identity provenance method is invalid")
    if expected_method == "native-role-authority" and profile != "native-password":
        raise ValueError("native role authority cannot establish an OAuth subject")
    if (
        raw["auth_profile"] != profile
        or raw["subject_kind"] != expected_kind
        or raw["sql_role_sha256"] != hashlib.sha256(principal.user.encode("utf-8")).hexdigest()
        or raw["provider_resource_sha256"]
        != hashlib.sha256(target["provider_resource_id"].encode("utf-8")).hexdigest()
        or raw["provider_observation_sha256"] != provider_observation_sha256
    ):
        raise ValueError("person identity observation is not bound to its authorized actor")
    _digest(raw["subject_reference_sha256"], "subject reference")
    _digest(raw["sql_role_sha256"], "SQL role")
    _digest(raw["provider_resource_sha256"], "provider resource")
    _digest(raw["provider_observation_sha256"], "provider observation")
    generation = _digest(raw["credential_generation"], "credential generation")
    expires = raw["credential_expires_at"]
    if profile in _OAUTH_PROFILES:
        if type(expires) is not int or expires <= now:
            raise ValueError("OAuth credential is expired or has an invalid expiry")
    elif expires is not None and (type(expires) is not int or expires <= now):
        raise ValueError("native credential expiry is invalid")
    return {
        "auth_profile": profile,
        "subject_kind": expected_kind,
        "subject_reference_sha256": raw["subject_reference_sha256"],
        "sql_role_sha256": raw["sql_role_sha256"],
        "provider_resource_sha256": raw["provider_resource_sha256"],
        "provider_observation_sha256": raw["provider_observation_sha256"],
        "credential_generation": generation,
        "credential_expires_at": expires,
        "provenance_method": expected_method,
    }


def safe_person_observations(
    value: object,
    *,
    target: Mapping[str, Any] | None = None,
    authorization: Mapping[str, Any] | None = None,
    provider_observation_sha256: str | None = None,
    role_sha256_by_actor: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Validate and project the closed, non-secret person observation receipt."""
    if type(value) is not dict or set(value) != _PERSON_OBSERVATION_KEYS:
        raise ValueError("person observation object has an unexpected shape")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("person observation schema version is invalid")
    actors, profiles = _safe_actor_facts(
        value["actors"], target, provider_observation_sha256, role_sha256_by_actor
    )
    if profiles.get("writer") != "human-oauth":
        raise ValueError("human writer identity was not observed")
    if authorization is not None and (
        authorization.get("schema_version") != 2
        or authorization.get("human_actor") != "writer"
        or authorization.get("actor_auth_profiles") != profiles
        or authorization.get("auth_profile") != "mixed"
    ):
        raise ValueError("authorization does not bind the human writer")
    controls = _safe_membership_facts(value["membership_control"])
    if target is not None:
        resources = target["resources"]
        actor_roles = resources["ordinary_role_names"]
        access = resources["module_access"]
        writer_role = actor_roles[_ACTORS.index("writer")]
        expected_memberships = _membership_sha256(
            (
                (writer_role, access["reader_role"]),
                (writer_role, access["writer_role"]),
            )
        )
        if controls["revoked_membership_sha256"] != expected_memberships:
            raise ValueError("membership receipt is not bound to the authorized role pairs")
    expiry = _safe_expiry_facts(value["expiry_control"])
    writer_expiry = actors["writer"]["before"]["credential_expires_at"]
    refreshed_expiry = actors["writer"]["after_refresh"]["credential_expires_at"]
    if (
        expiry["effective_at_unix"] != writer_expiry
        or type(refreshed_expiry) is not int
        or refreshed_expiry <= expiry["effective_at_unix"]
    ):
        raise ValueError("credential expiry receipt differs from observed writer credentials")
    state = _safe_state_facts(value["state"])
    _validate_person_lifecycle(value["refresh"], controls, expiry, state)
    return {
        "schema_version": 1,
        "actors": actors,
        "refresh": dict(value["refresh"]),
        "membership_control": controls,
        "expiry_control": expiry,
        "state": state,
    }


_PERSON_OBSERVATION_KEYS = {
    "schema_version",
    "actors",
    "refresh",
    "membership_control",
    "expiry_control",
    "state",
}


def _safe_actor_facts(
    value: object,
    target: Mapping[str, Any] | None,
    provider_digest: str | None,
    role_digests: Mapping[str, str] | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    if type(value) is not dict or set(value) != set(_ACTORS):
        raise ValueError("person actor observation set is incomplete")
    if role_digests is not None and set(role_digests) != set(_ACTORS):
        raise ValueError("person role binding is incomplete")
    expected_profiles = _profile_map(target) if target is not None else None
    actors: dict[str, Any] = {}
    profiles: dict[str, str] = {}
    for label in _ACTORS:
        actor = value[label]
        if type(actor) is not dict or set(actor) != {"before", "after_refresh", "sql"}:
            raise ValueError("person actor observation is malformed")
        before = _safe_identity_projection(actor["before"])
        profile = before["auth_profile"]
        profiles[label] = profile
        if expected_profiles is not None and expected_profiles[label] != profile:
            raise ValueError("person actor profile differs from authorization")
        if (
            target is not None
            and before["provider_resource_sha256"]
            != hashlib.sha256(target["provider_resource_id"].encode("utf-8")).hexdigest()
        ):
            raise ValueError("person identity is bound to a different provider resource")
        if provider_digest is not None and before["provider_observation_sha256"] != provider_digest:
            raise ValueError("person identity is not bound to current provider observation")
        if role_digests is not None and before["sql_role_sha256"] != role_digests[label]:
            raise ValueError("person identity SQL role differs from baseline role")
        after = _safe_identity_projection(actor["after_refresh"]) if label == "writer" else None
        if label == "writer":
            if (
                after["auth_profile"] != profile
                or after["subject_reference_sha256"] != before["subject_reference_sha256"]
                or after["sql_role_sha256"] != before["sql_role_sha256"]
                or after["credential_generation"] == before["credential_generation"]
                or provider_digest is not None
                and after["provider_observation_sha256"] != provider_digest
                or role_digests is not None
                and after["sql_role_sha256"] != role_digests[label]
            ):
                raise ValueError("writer refresh did not preserve identity and rotate generation")
            if (
                target is not None
                and after["provider_resource_sha256"]
                != hashlib.sha256(target["provider_resource_id"].encode("utf-8")).hexdigest()
            ):
                raise ValueError("refreshed writer is bound to a different provider resource")
        elif actor["after_refresh"] is not None:
            raise ValueError("non-writer actor unexpectedly has refresh evidence")
        sql = _safe_sql_facts(actor["sql"], before["sql_role_sha256"])
        actors[label] = {"before": before, "after_refresh": after, "sql": sql}
    if len({item["before"]["provider_resource_sha256"] for item in actors.values()}) != 1:
        raise ValueError("person actors are bound to different provider resources")
    if len({item["before"]["provider_observation_sha256"] for item in actors.values()}) != 1:
        raise ValueError("person actors are bound to different provider observations")
    return actors, profiles


def _safe_sql_facts(value: object, role_digest: str) -> dict[str, Any]:
    expected = {
        "initial_connection_verified",
        "current_user_sha256",
        "session_user_sha256",
        "tls_verified",
    }
    if type(value) is not dict or set(value) != expected:
        raise ValueError("person SQL identity observation is malformed")
    if value["initial_connection_verified"] is not True or value["tls_verified"] is not True:
        raise ValueError("person SQL identity was not verified")
    if any(type(value[key]) is not bool for key in ("initial_connection_verified", "tls_verified")):
        raise ValueError("person SQL flags must be booleans")
    for key in ("current_user_sha256", "session_user_sha256"):
        _digest(value[key], f"person SQL {key}")
    if value["current_user_sha256"] != role_digest or value["session_user_sha256"] != role_digest:
        raise ValueError("person SQL identity differs from provider identity binding")
    return dict(value)


def _safe_membership_facts(value: object) -> dict[str, Any]:
    keys = {
        "revoke_operation_sha256",
        "restore_operation_sha256",
        "revoked_membership_sha256",
        "restored_membership_sha256",
        "fresh_connection_denied",
        "existing_session_denied",
        "restoration_verified",
    }
    if type(value) is not dict or set(value) != keys:
        raise ValueError("membership control observation is malformed")
    for key in (
        "revoke_operation_sha256",
        "restore_operation_sha256",
        "revoked_membership_sha256",
        "restored_membership_sha256",
    ):
        _digest(value[key], f"membership {key}")
    if value["revoked_membership_sha256"] != value["restored_membership_sha256"]:
        raise ValueError("membership restore set differs from the revoked set")
    for key in ("fresh_connection_denied", "existing_session_denied", "restoration_verified"):
        if type(value[key]) is not bool:
            raise ValueError("membership control result is invalid")
    return dict(value)


def _safe_expiry_facts(value: object) -> dict[str, Any]:
    keys = {
        "operation_sha256",
        "mechanism",
        "effective_at_unix",
        "expired_connection_denied",
        "refreshed_connection_verified",
    }
    if type(value) is not dict or set(value) != keys:
        raise ValueError("credential expiry observation is malformed")
    _digest(value["operation_sha256"], "credential expiry operation")
    if value["mechanism"] not in {"provider-credential-expiry", "native-role-valid-until"}:
        raise ValueError("credential expiry mechanism is invalid")
    if type(value["effective_at_unix"]) is not int:
        raise ValueError("credential expiry time is invalid")
    for key in ("expired_connection_denied", "refreshed_connection_verified"):
        if type(value[key]) is not bool:
            raise ValueError("credential expiry result is invalid")
    return dict(value)


def _safe_state_facts(value: object) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {
        "before_sha256",
        "after_sha256",
        "unchanged",
        "sequence_allocations",
    }:
        raise ValueError("person state observation is malformed")
    for key in ("before_sha256", "after_sha256"):
        _digest(value[key], f"person state {key}")
    if type(value["unchanged"]) is not bool:
        raise ValueError("person state comparison is invalid")
    sequence_allocations = value["sequence_allocations"]
    if type(sequence_allocations) is not dict or set(sequence_allocations) != {
        "comparison_count",
        "sha256",
    }:
        raise ValueError("person sequence allocation observation is malformed")
    if (
        type(sequence_allocations["comparison_count"]) is not int
        or sequence_allocations["comparison_count"] != _EXPECTED_SNAPSHOT_COMPARISONS
    ):
        raise ValueError("person sequence allocation count is invalid")
    _digest(sequence_allocations["sha256"], "person sequence allocation digest")
    return dict(value)


def _validate_person_lifecycle(
    refresh: object,
    controls: Mapping[str, Any],
    expiry: Mapping[str, Any],
    state: Mapping[str, Any],
) -> None:
    if (
        type(refresh) is not dict
        or set(refresh)
        != {
            "credential_changed",
            "invalid_credential_refused",
            "other_person_credential_refused",
        }
        or any(type(item) is not bool or not item for item in refresh.values())
    ):
        raise ValueError("writer refresh credential change is unverified")
    if any(
        controls[key] is not True
        for key in ("fresh_connection_denied", "existing_session_denied", "restoration_verified")
    ):
        raise ValueError("membership lifecycle did not independently verify")
    if state["before_sha256"] != state["after_sha256"] or state["unchanged"] is not True:
        raise ValueError("person lifecycle changed the authorized state")
    if (
        expiry["mechanism"] != "provider-credential-expiry"
        or expiry["expired_connection_denied"] is not True
        or expiry["refreshed_connection_verified"] is not True
    ):
        raise ValueError("credential expiry and refresh were not independently verified")


def _safe_identity_projection(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _IDENTITY_KEYS:
        raise ValueError("person identity fact has an unexpected shape")
    profile = value["auth_profile"]
    if (
        type(profile) is not str
        or profile not in _PROFILES
        or value["subject_kind"]
        != {
            "native-password": "native-role",
            "human-oauth": "human",
            "nonhuman-oauth": "nonhuman",
        }[profile]
    ):
        raise ValueError("identity fact profile and subject kind differ")
    if type(value["provenance_method"]) is not str or value["provenance_method"] not in _METHODS:
        raise ValueError("identity provenance method is invalid")
    if value["provenance_method"] == "native-role-authority" and profile != "native-password":
        raise ValueError("native role authority cannot establish an OAuth subject")
    for key in (
        "subject_reference_sha256",
        "sql_role_sha256",
        "provider_resource_sha256",
        "provider_observation_sha256",
        "credential_generation",
    ):
        _digest(value[key], key)
    expiry = value["credential_expires_at"]
    if profile in _OAUTH_PROFILES:
        if type(expiry) is not int:
            raise ValueError("OAuth expiry must be an integer Unix timestamp")
    elif expiry is not None and type(expiry) is not int:
        raise ValueError("native expiry must be null or an integer Unix timestamp")
    return {key: value[key] for key in _IDENTITY_KEYS}


def run_person_lifecycle(
    *,
    inputs: Any,
    fixture_module: Any,
    sources: Mapping[str, Any],
    backend: Any,
    principals: dict[str, Principal],
    installed: Any,
    baseline_observed: Mapping[str, Any],
    provider_observation_sha256: str | None = None,
    baseline_roles: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute checks against the genuine ``backend.migrate()`` result and live principals.

    Authorization and capability checks finish before any fixture callback or connection. Fixture
    callbacks provide factual observations and controls only; they never provide case verdicts.
    """
    allowed_cases = inputs.authorization["allowed_cases"]
    allowed_operations = inputs.authorization["allowed_operations"]
    if "LB-PERSON" not in allowed_cases:
        return {
            "cases": [_case_row("LB-PERSON", "blocked", "case_not_authorized")],
            "observed": None,
        }
    if not _PERSON_REQUIRED_OPERATIONS.issubset(allowed_operations):
        return {
            "cases": [_case_row("LB-PERSON", "blocked", "required_operation_not_authorized")],
            "observed": None,
        }
    target = inputs.target
    auth = _profile_map(target)
    if target.get("schema_version") != 2 or target.get("human_actor") != "writer":
        return {
            "cases": [_case_row("LB-PERSON", "blocked", "mixed_human_writer_profile_required")],
            "observed": None,
        }
    required_callbacks = (
        "observe_person_identity",
        "revoke_owned_memberships",
        "restore_owned_memberships",
        "expire_person_credential",
    )
    if any(not callable(getattr(fixture_module, name, None)) for name in required_callbacks):
        return {
            "cases": [
                _case_row("LB-PERSON", "blocked", "identity_and_lifecycle_controls_unavailable")
            ],
            "observed": None,
        }
    if not callable(sources.get("refresh_principal")):
        return {
            "cases": [_case_row("LB-PERSON", "blocked", "credential_refresh_unavailable")],
            "observed": None,
        }
    # Full service execution is intentionally isolated behind a trusted, owner-authorized fixture.
    # The implementation below validates every callback response and derives each outcome from
    # the fresh connections and public API calls it performs.
    return _run_person_controls(
        inputs=inputs,
        fixture_module=fixture_module,
        sources=sources,
        backend=backend,
        principals=principals,
        installed=installed,
        baseline_observed=baseline_observed,
        provider_observation_sha256=provider_observation_sha256,
        baseline_roles=baseline_roles,
        auth=auth,
    )


def _run_person_controls(**context: Any) -> dict[str, Any]:
    """Run actual identity, membership, and credential lifecycle observations."""
    try:
        context["sequence_deltas"] = []
        facts = _person_context_facts(context)
        before_negative_snapshot = _native_snapshot(context["sources"])
        negative_credentials = _person_wrong_credential_checks(context)
        if not all(negative_credentials.values()):
            raise PersonFailure("credential_refusal_failed")
        after_negative_snapshot = _native_snapshot(context["sources"])
        if not _record_snapshot_pair(context, before_negative_snapshot, after_negative_snapshot):
            raise PersonFailure("person_state_changed")
        refreshed = _person_expiry_and_refresh(context, facts)
        active_principals = context["principals"]
        _handoff_refreshed_writer(active_principals, refreshed["new_principal"])
        active_context = dict(context)
        active_context["principals"] = active_principals
        host, writer, reader, public_state = _person_public_api_checks(active_context)
        membership = _person_membership_cycle(active_context, host, writer, reader, public_state)
        observed = _person_observation_document(context, facts, membership, refreshed)
        observed["refresh"].update(negative_credentials)
        safe = safe_person_observations(
            observed,
            target=context["inputs"].target,
            authorization=context["inputs"].authorization,
            provider_observation_sha256=facts["provider_digest"],
            role_sha256_by_actor=facts["role_sha"],
        )
        return {
            "cases": [_case_row("LB-PERSON", "passed", "human_identity_lifecycle_verified")],
            "observed": safe,
        }
    except PersonFailure as failure:
        return {
            "cases": [_case_row("LB-PERSON", "failed", failure.code)],
            "observed": None,
        }
    except Exception:
        return {
            "cases": [
                _case_row("LB-PERSON", "blocked", "identity_lifecycle_postcondition_unverified")
            ],
            "observed": None,
        }


def _handoff_refreshed_writer(principals: dict[str, Principal], refreshed: Principal) -> None:
    if (
        type(principals) is not dict
        or type(refreshed) is not Principal
        or type(refreshed.user) is not str
        or type(refreshed.token) is not str
        or not refreshed.token
    ):
        raise ValueError("refreshed writer principal is invalid")
    prior = principals.get("writer")
    if (
        type(prior) is not Principal
        or prior.user != refreshed.user
        or prior.token == refreshed.token
    ):
        raise PersonFailure("credential_refresh_mismatch")
    principals["writer"] = refreshed


def _person_context_facts(context: Mapping[str, Any]) -> dict[str, Any]:
    inputs = context["inputs"]
    target = inputs.target
    principals = context["principals"]
    fixture = context["fixture_module"]
    provider_digest = context.get("provider_observation_sha256") or context.get(
        "baseline_observed", {}
    ).get("provider_observation_sha256")
    provider_digest = _digest(provider_digest, "provider observation")
    baseline_roles = context.get("baseline_roles", {})
    if set(principals) != set(_ACTORS):
        raise ValueError("person principals are incomplete")
    roles: dict[str, str] = {}
    before: dict[str, dict[str, Any]] = {}
    sql: dict[str, dict[str, Any]] = {}
    for label in _ACTORS:
        principal = principals[label]
        if (
            type(principal) is not Principal
            or type(principal.user) is not str
            or not principal.user
            or type(principal.token) is not str
            or not principal.token
        ):
            raise ValueError("authorized principal is invalid")
        role_fact = baseline_roles.get(label)
        if type(role_fact) is not dict:
            raise ValueError("baseline role observation is unavailable")
        role_fact = cast(dict[str, Any], role_fact)
        roles[label] = _digest(role_fact.get("role_sha256"), "baseline SQL role")
        if roles[label] != hashlib.sha256(principal.user.encode("utf-8")).hexdigest():
            raise ValueError("baseline SQL role differs from authorized principal")
        raw = fixture.observe_person_identity(actor_label=label, principal=principal)
        before[label] = _identity_fact(
            raw,
            label=label,
            principal=principal,
            target=target,
            provider_observation_sha256=provider_digest,
            now=int(time.time()),
        )
        with context["sources"]["person_connection_source"](principal) as connection:
            sql[label] = _observe_person_connection(connection, principal, target)
        if sql[label]["current_user_sha256"] != roles[label]:
            raise ValueError("person source connected as a different SQL role")
    return {"provider_digest": provider_digest, "role_sha": roles, "before": before, "sql": sql}


def _person_public_api_checks(context: Mapping[str, Any]) -> tuple[Any, Any, Any, tuple[str, str]]:
    from arras.core import Arras
    from arras.model import Placement

    principals = context["principals"]
    host = Arras.start(
        {"truss": context["backend"]},
        expected=("truss",),
        admin=principals["registrar"],
        default_placement=Placement("truss"),
    )
    registrar = host.session(principals["registrar"])
    if context["baseline_observed"]["operations"]["registration"] == "passed":
        _assert_administrator_document_refused(registrar, "lakebase_qualification")
    elif registrar.registry().register(HARNESS_MODULE_DOCUMENT).module != "lakebase_qualification":
        raise PersonFailure("registrar_authority_mismatch")
    reader = host.session(principals["reader"])
    reader.document("lakebase_qualification")
    writer = host.session(principals["writer"])
    draft = {"code": f"person-{uuid.uuid4().hex}", "value": "identity-control"}
    before_validate = _native_snapshot(context["sources"])
    validation = writer.validate(
        "lakebase_qualification.CreateProbe",
        draft,
    )
    after_validate = _native_snapshot(context["sources"])
    allowed_sequences = _approved_validation_sequences(context)
    if not _record_snapshot_pair(
        context,
        before_validate,
        after_validate,
        allowed_sequence_advances=allowed_sequences,
    ):
        raise PersonFailure("person_state_changed")
    if not validation.ok or len(validation.effects) != 1:
        raise PersonFailure("writer_operation_refused")
    receipt = writer.invoke(
        "lakebase_qualification.CreateProbe",
        draft,
        idempotency_key=f"lakebase-person-{uuid.uuid4().hex}",
    )
    if getattr(receipt, "created", None) != 1:
        raise PersonFailure("writer_operation_refused")
    rows = reader.query(
        "lakebase_qualification",
        "SELECT p.code, p.value FROM lakebase_qualification.Probe p WHERE p.code = $code LIMIT 1",
        params={"code": draft["code"]},
    ).rows
    if rows != ({"code": draft["code"], "value": draft["value"]},):
        raise PersonFailure("writer_operation_refused")
    public_before = _public_state_sha256(reader)
    native_before = _native_snapshot(context["sources"])
    _person_refusal_controls(host, writer, principals["denied"])
    public_after = _public_state_sha256(reader)
    native_after = _native_snapshot(context["sources"])
    if public_before != public_after or not _record_snapshot_pair(
        context, native_before, native_after
    ):
        raise PersonFailure("person_state_changed")
    return host, writer, reader, (native_before["sha256"], public_before)


def _assert_administrator_document_refused(registrar: Any, module: str) -> None:
    """Keep the named administrative principal out of the data-reading path."""
    try:
        registrar.document(module)
    except Refused as error:
        if (
            error.backend == "arras"
            and error.operation == "document"
            and error.reason == "no_access"
        ):
            return
        raise PersonFailure("registrar_authority_mismatch") from None
    except Invalid:
        raise PersonFailure("registrar_authority_mismatch") from None
    raise PersonFailure("registrar_authority_mismatch")


def _person_refusal_controls(host: Any, writer: Any, denied_principal: Principal) -> None:
    try:
        writer.registry().register(HARNESS_MODULE_DOCUMENT)
    except (Refused, Invalid):
        pass
    else:
        raise PersonFailure("registrar_authority_mismatch")
    denied = host.session(denied_principal)
    try:
        denied.document("lakebase_qualification")
    except (Refused, Invalid):
        pass
    else:
        raise PersonFailure("denied_actor_authorized")
    try:
        denied.invoke(
            "lakebase_qualification.CreateProbe",
            {"code": f"denied-{uuid.uuid4().hex}", "value": "identity-control"},
            idempotency_key=f"lakebase-denied-{uuid.uuid4().hex}",
        )
    except (Refused, Invalid):
        return
    else:
        raise PersonFailure("denied_actor_authorized")


def _person_wrong_credential_checks(context: Mapping[str, Any]) -> dict[str, bool]:
    sources = context["sources"]
    principals = context["principals"]
    target = context["inputs"].target
    writer = principals["writer"]
    reader = principals["reader"]
    invalid = Principal(writer.user, f"invalid-{uuid.uuid4().hex}")
    other_person = Principal(writer.user, reader.token)
    return {
        "invalid_credential_refused": _connection_identity_refused(sources, invalid, target),
        "other_person_credential_refused": _connection_identity_refused(
            sources, other_person, target
        ),
    }


def _connection_identity_refused(
    sources: Mapping[str, Any], principal: Principal, target: Mapping[str, Any]
) -> bool:
    try:
        with sources["person_connection_source"](principal) as connection:
            endpoint = target["endpoint"]
            info = connection.info
            parameters = info.get_parameters()
            if (
                type(parameters) is not dict
                or info.host != endpoint["host"]
                or type(info.port) is not int
                or info.port != endpoint["port"]
                or info.dbname != endpoint["database"]
                or parameters.get("sslmode") != "verify-full"
                or not parameters.get("sslrootcert")
                or not connection.pgconn.ssl_in_use
            ):
                return False
            # A connection under a different identity is still successful authentication and
            # therefore an unsafe identity substitution, never evidence of refusal.
            return False
    except Exception as error:
        return _is_authentication_refusal(error)


def _is_authentication_refusal(error: BaseException) -> bool:
    sqlstate = getattr(error, "sqlstate", None)
    return type(sqlstate) is str and sqlstate.startswith("28")


def _person_membership_cycle(
    context: Mapping[str, Any],
    host: Any,
    writer: Any,
    reader: Any,
    public_state: tuple[str, str],
) -> dict[str, Any]:
    fixture = context["fixture_module"]
    inputs = context["inputs"]
    sources = context["sources"]
    principal = context["principals"]["writer"]
    access = inputs.target["resources"]["module_access"]
    pairs = _membership_pairs(
        ((principal.user, access["reader_role"]), (principal.user, access["writer_role"]))
    )
    native_before = _native_snapshot(sources)
    if _observe_memberships(sources, pairs) != {pair: True for pair in pairs}:
        raise ValueError("writer memberships differ from authorized precondition")
    revoke: str | None = None
    restore: str | None = None
    restore_verified = False
    revoke_state = {"started": False}
    primary_error: BaseException | None = None
    primary_traceback = None
    cleanup_error: BaseException | None = None
    try:
        revoke = _revoke_and_probe(
            context,
            host,
            writer,
            principal,
            pairs,
            lambda: revoke_state.__setitem__("started", True),
        )
    except BaseException as error:
        primary_error = error
        primary_traceback = error.__traceback__
    finally:
        if revoke_state["started"]:
            restore, restore_verified, cleanup_error = _restore_memberships(fixture, sources, pairs)
    if primary_error is not None:
        if revoke_state["started"] and (not restore_verified or cleanup_error is not None):
            primary_error.add_note(
                "authorized membership restoration cleanup did not complete cleanly "
                f"(membership_state_verified={restore_verified})"
            )
        raise primary_error.with_traceback(primary_traceback)
    if cleanup_error is not None:
        raise cleanup_error
    if not revoke_state["started"] or revoke is None:
        raise ValueError("membership revocation was not independently observed")
    if not restore_verified or restore is None:
        raise PersonFailure("membership_restore_mismatch")
    digest = _membership_sha256(pairs)
    native_after = _native_snapshot(sources)
    if not _record_snapshot_pair(context, native_before, native_after):
        raise PersonFailure("person_state_changed")
    state_before = _combined_state_sha256(_durable_snapshot_sha256(native_before), public_state[1])
    state_after = _combined_state_sha256(_durable_snapshot_sha256(native_after), public_state[1])
    return {
        "revoke": revoke,
        "restore": restore,
        "memberships_sha256": digest,
        "restored": restore_verified,
        "before_state_sha256": state_before,
        "after_state_sha256": state_after,
    }


def _revoke_and_probe(
    context: Mapping[str, Any],
    host: Any,
    writer: Any,
    principal: Principal,
    pairs: tuple[tuple[str, str], ...],
    mark_started: Callable[[], None],
) -> str:
    fixture = context["fixture_module"]
    sources = context["sources"]
    # Keep a real SQL connection open across revocation. A separate public Truss backend is
    # restricted to this exact principal and adopts only that held connection.
    with sources["person_connection_source"](principal) as held_connection:
        _observe_person_connection(held_connection, principal, context["inputs"].target)
        held_connection.rollback()
        _, held_writer = _held_connection_writer(context, principal, held_connection)
        mark_started()
        result = _validate_control_result(
            fixture.revoke_owned_memberships(actor_label="writer", memberships=pairs), pairs
        )
        if any(_observe_memberships(sources, pairs).values()):
            raise PersonFailure("membership_revoke_mismatch")
        _must_refuse(lambda: host.session(principal).document("lakebase_qualification"))
        _must_refuse(lambda: held_writer.document("lakebase_qualification"))
        return result


def _restore_memberships(
    fixture: Any, sources: Mapping[str, Any], pairs: tuple[tuple[str, str], ...]
) -> tuple[str | None, bool, BaseException | None]:
    restore: str | None = None
    cleanup_error: BaseException | None = None
    try:
        restore = _validate_control_result(
            fixture.restore_owned_memberships(actor_label="writer", memberships=pairs), pairs
        )
    except BaseException as error:
        cleanup_error = error
    try:
        verified = _observe_memberships(sources, pairs) == {pair: True for pair in pairs}
    except BaseException as error:
        cleanup_error = cleanup_error or error
        verified = False
    return restore, verified, cleanup_error


def _held_connection_writer(
    context: Mapping[str, Any], principal: Principal, connection: Any
) -> tuple[Any, Any]:
    """Create a public Arras session whose source can yield only the held writer connection."""
    from arras.adapters.truss import ModuleAccess, create_backend
    from arras.core import Arras
    from arras.model import Placement

    inputs = context["inputs"]
    resources = inputs.target["resources"]
    raw_access = resources["module_access"]
    access = ModuleAccess(
        document_id=raw_access["document_id"],
        reader_role=raw_access["reader_role"],
        writer_role=raw_access["writer_role"],
        auditor_role=raw_access.get("auditor_role"),
    )

    def held_source(requested: Principal):
        if (
            type(requested) is not Principal
            or requested.user != principal.user
            or requested.token != principal.token
        ):
            raise PermissionError("held connection is restricted to its authenticated principal")
        return nullcontext(connection)

    backend = create_backend(
        "truss",
        held_source,
        context["sources"]["installer_connection_source"],
        module_access={"lakebase_qualification": access},
        tolerated_grantees=tuple(resources["tolerated_grantees"]),
    )
    registrar = context["principals"]["registrar"]
    host = Arras.start(
        {"truss": backend},
        expected=("truss",),
        admin=registrar,
        default_placement=Placement("truss"),
    )
    return host, host.session(principal)


def _native_snapshot(sources: Mapping[str, Any]) -> dict[str, Any]:
    module_name = (
        f"{__package__}._lakebase_managed_native" if __package__ else "_lakebase_managed_native"
    )
    observer = getattr(importlib.import_module(module_name), "_observer_snapshot", None)
    if not callable(observer):
        raise ValueError("native observer snapshot is unavailable")
    snapshot = observer(sources)
    if type(snapshot) is not dict:
        raise ValueError("native observer returned an invalid snapshot")
    return cast(dict[str, Any], snapshot)


def _record_snapshot_pair(
    context: Mapping[str, Any],
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    allowed_sequence_advances: frozenset[str] = frozenset(),
) -> bool:
    """Compare state, allowing only source-bound sequence gaps in a successful dry run."""
    before_relations = before.get("relations")
    after_relations = after.get("relations")
    if type(before_relations) not in {list, tuple} or type(after_relations) not in {list, tuple}:
        raise ValueError("native snapshot relation inventory is malformed")
    before_sequences = _sequence_states(cast(Sequence[Any], before_relations))
    after_sequences = _sequence_states(cast(Sequence[Any], after_relations))
    if set(before_sequences) != set(after_sequences):
        return False
    changes: list[tuple[str, tuple[int, bool], tuple[int, bool]]] = []
    for name in sorted(before_sequences):
        old = before_sequences[name]
        new = after_sequences[name]
        if old != new and name not in allowed_sequence_advances:
            return False
        if new[0] < old[0] or (old[1] and not new[1]):
            return False
        if old != new:
            changes.append((name, old, new))
    durable_equal = _durable_snapshot_sha256(
        before, allowed_sequence_advances
    ) == _durable_snapshot_sha256(after, allowed_sequence_advances)
    digest = hashlib.sha256(json.dumps(changes, separators=(",", ":")).encode("utf-8")).hexdigest()
    context["sequence_deltas"].append({"count": len(changes), "sha256": digest})
    return durable_equal


def _sequence_states(relations: Sequence[Any]) -> dict[str, tuple[int, bool]]:
    result: dict[str, tuple[int, bool]] = {}
    for relation in relations:
        if type(relation) is not dict:
            raise ValueError("native relation entry is malformed")
        relation = cast(dict[str, Any], relation)
        if relation.get("kind") != "S":
            continue
        raw_state = relation.get("sequence_state")
        name = relation.get("name")
        if type(name) is not str or type(raw_state) not in {list, tuple} or name in result:
            raise ValueError("native sequence inventory is malformed")
        state = cast(Sequence[Any], raw_state)
        if len(state) != 2 or type(state[0]) is not int or type(state[1]) is not bool:
            raise ValueError("native sequence inventory is malformed")
        result[name] = (state[0], state[1])
    return result


def _durable_snapshot_sha256(
    snapshot: Mapping[str, Any], normalized_sequences: frozenset[str] = frozenset()
) -> str:
    payload = dict(snapshot)
    payload.pop("sha256", None)
    relations = payload.get("relations")
    if type(relations) not in {list, tuple}:
        raise ValueError("native snapshot relation inventory is malformed")
    normalized: list[dict[str, Any]] = []
    for relation in cast(Sequence[dict[str, Any]], relations):
        item = dict(relation)
        if item.get("kind") == "S" and item.get("name") in normalized_sequences:
            item.pop("sequence_state", None)
        normalized.append(item)
    payload["relations"] = tuple(normalized)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _approved_validation_sequences(context: Mapping[str, Any]) -> frozenset[str]:
    inputs = context["inputs"]
    expected = inputs.target["expected"]
    artifacts = context["baseline_observed"]["artifacts"]
    if (
        expected.get("truss_version") != _VALIDATION_ALLOCATOR_TRUSS_VERSION
        or expected.get("truss_wheel_sha256") != _VALIDATION_ALLOCATOR_WHEEL_SHA256
        or expected.get("native_manifest_sha256") != _VALIDATION_ALLOCATOR_NATIVE_SHA256
    ):
        raise ValueError("dry-run allocator exception is not approved for this Truss source")
    if any(
        artifacts.get(key) != expected.get(key)
        for key in (
            "truss_version",
            "truss_wheel_sha256",
            "native_manifest_sha256",
            "migration_manifest_sha256",
        )
    ):
        raise ValueError("dry-run allocator exception is not bound to the selected Truss source")
    from importlib.resources import files

    runtime = files("truss").joinpath("_catalog_runtime")
    for name, expected_digest in _VALIDATION_ALLOCATOR_SOURCE_SHA256.items():
        source_digest = hashlib.sha256(runtime.joinpath(name).read_bytes()).hexdigest()
        if source_digest != expected_digest:
            raise ValueError("dry-run allocator source differs from its reviewed source member")
    return _VALIDATION_ALLOCATOR_SEQUENCES


def _sequence_delta_summary(context: Mapping[str, Any]) -> dict[str, Any]:
    deltas = context.get("sequence_deltas", [])
    if type(deltas) is not list:
        raise ValueError("sequence delta inventory is malformed")
    deltas = cast(list[dict[str, Any]], deltas)
    payload = json.dumps(deltas, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"comparison_count": len(deltas), "sha256": hashlib.sha256(payload).hexdigest()}


def _must_refuse(operation: Any) -> None:
    try:
        operation()
    except (Refused, Invalid):
        return
    raise PersonFailure("revoked_writer_authorized")


def _person_expiry_and_refresh(
    context: Mapping[str, Any], facts: Mapping[str, Any]
) -> dict[str, Any]:
    fixture = context["fixture_module"]
    inputs = context["inputs"]
    sources = context["sources"]
    old = context["principals"]["writer"]
    expire = _validate_expiry_result(
        fixture.expire_person_credential(actor_label="writer", principal=old),
        context["auth"]["writer"],
    )
    if expire["effective_at_unix"] != facts["before"]["writer"]["credential_expires_at"]:
        raise ValueError("expiry control differs from observed issuer expiry")
    delay = expire["effective_at_unix"] - int(time.time())
    if delay > 300:
        raise ValueError("credential expiry exceeds bounded wait")
    if delay > 0:
        time.sleep(delay)
    try:
        with sources["person_connection_source"](old) as connection:
            _observe_person_connection(connection, old, inputs.target)
    except Exception as error:
        expired_denied = _is_authentication_refusal(error)
        if not expired_denied:
            raise ValueError(
                "expired credential refusal was not an authentication denial"
            ) from None
    else:
        raise PersonFailure("expired_credential_accepted")
    new = sources["refresh_principal"]("writer")
    if (
        type(new) is not Principal
        or type(new.token) is not str
        or not new.token
        or new.token == old.token
    ):
        raise PersonFailure("credential_refresh_mismatch")
    raw = fixture.observe_person_identity(actor_label="writer", principal=new)
    new_fact = _identity_fact(
        raw,
        label="writer",
        principal=new,
        target=inputs.target,
        provider_observation_sha256=facts["provider_digest"],
        now=int(time.time()),
    )
    old_fact = facts["before"]["writer"]
    if (
        new_fact["subject_reference_sha256"] != old_fact["subject_reference_sha256"]
        or new_fact["credential_generation"] == old_fact["credential_generation"]
    ):
        raise PersonFailure("credential_refresh_mismatch")
    with sources["person_connection_source"](new) as connection:
        sql = _observe_person_connection(connection, new, inputs.target)
    if sql["current_user_sha256"] != facts["role_sha"]["writer"]:
        raise PersonFailure("credential_refresh_mismatch")
    return {
        "expiry": expire,
        "expired_denied": expired_denied,
        "new_fact": new_fact,
        "new_principal": new,
    }


def _person_observation_document(
    context: Mapping[str, Any],
    facts: Mapping[str, Any],
    membership: Mapping[str, Any],
    refreshed: Mapping[str, Any],
) -> dict[str, Any]:
    principals = context["principals"]
    if refreshed["new_principal"].user != principals["writer"].user:
        raise ValueError("refreshed principal changed SQL role name")
    before_state = membership["before_state_sha256"]
    after_state = membership["after_state_sha256"]
    return {
        "schema_version": 1,
        "actors": {
            label: {
                "before": facts["before"][label],
                "after_refresh": refreshed["new_fact"] if label == "writer" else None,
                "sql": facts["sql"][label],
            }
            for label in _ACTORS
        },
        "refresh": {
            "credential_changed": True,
            "invalid_credential_refused": True,
            "other_person_credential_refused": True,
        },
        "membership_control": {
            "revoke_operation_sha256": membership["revoke"],
            "restore_operation_sha256": membership["restore"],
            "revoked_membership_sha256": membership["memberships_sha256"],
            "restored_membership_sha256": membership["memberships_sha256"],
            "fresh_connection_denied": True,
            "existing_session_denied": True,
            "restoration_verified": membership["restored"],
        },
        "expiry_control": {
            **refreshed["expiry"],
            "expired_connection_denied": refreshed["expired_denied"],
            "refreshed_connection_verified": True,
        },
        "state": {
            "before_sha256": before_state,
            "after_sha256": after_state,
            "unchanged": before_state == after_state,
            "sequence_allocations": _sequence_delta_summary(context),
        },
    }


def _observe_person_connection(
    connection: Any, principal: Principal, target: Mapping[str, Any]
) -> dict[str, Any]:
    endpoint = target["endpoint"]
    info = connection.info
    parameters = info.get_parameters()
    if (
        type(parameters) is not dict
        or info.host != endpoint["host"]
        or type(info.port) is not int
        or info.port != endpoint["port"]
        or info.dbname != endpoint["database"]
        or parameters.get("sslmode") != "verify-full"
        or not parameters.get("sslrootcert")
        or not connection.pgconn.ssl_in_use
    ):
        raise ValueError("person connection did not use the authorized verify-full endpoint")
    row = connection.execute(
        "SELECT current_user, session_user, s.ssl, s.version, s.cipher, r.rolcanlogin, "
        "r.rolsuper, r.rolcreaterole, r.rolcreatedb, r.rolbypassrls "
        "FROM pg_roles AS r JOIN pg_stat_ssl AS s ON s.pid = pg_backend_pid() "
        "WHERE r.rolname = current_user"
    ).fetchone()
    if row is None or len(row) != 10:
        raise ValueError("person connection identity or TLS could not be observed")
    (
        user,
        session_user,
        ssl,
        tls_version,
        cipher,
        can_login,
        superuser,
        create_roles,
        create_db,
        bypass,
    ) = row
    role_hash = hashlib.sha256(principal.user.encode("utf-8")).hexdigest()
    if (
        user != principal.user
        or session_user != principal.user
        or ssl is not True
        or not can_login
        or superuser
        or create_roles
        or create_db
        or bypass
        or type(tls_version) is not str
        or not tls_version.startswith("TLSv")
        or type(cipher) is not str
        or not cipher
    ):
        raise ValueError("person connection identity or TLS differs from the authorized role")
    return {
        "initial_connection_verified": True,
        "current_user_sha256": role_hash,
        "session_user_sha256": hashlib.sha256(session_user.encode("utf-8")).hexdigest(),
        "tls_verified": True,
    }


def _membership_pairs(value: object) -> tuple[tuple[str, str], ...]:
    if type(value) not in (tuple, list) or not value:
        raise ValueError("membership set must be a nonempty sequence")
    pairs: list[tuple[str, str]] = []
    for pair in value:
        if (
            type(pair) not in (tuple, list)
            or len(pair) != 2
            or any(type(item) is not str or not item for item in pair)
        ):
            raise ValueError("membership pair is malformed")
        pairs.append((pair[0], pair[1]))
    if len(set(pairs)) != len(pairs):
        raise ValueError("membership set contains duplicates")
    return tuple(pairs)


def _validate_control_result(value: object, expected: tuple[tuple[str, str], ...]) -> str:
    if type(value) is not dict or set(value) != {"operation_sha256", "memberships"}:
        raise ValueError("membership control result has an unexpected shape")
    digest = _digest(value["operation_sha256"], "membership operation")
    if _membership_pairs(value["memberships"]) != expected:
        raise ValueError("membership control attempted a different set")
    return digest


def _observe_memberships(
    sources: Mapping[str, Any], pairs: tuple[tuple[str, str], ...]
) -> dict[tuple[str, str], bool]:
    with sources["installer_connection_source"]() as connection:
        result: dict[tuple[str, str], bool] = {}
        for member, role in pairs:
            row = connection.execute(
                "SELECT pg_catalog.pg_has_role(%s, %s, 'MEMBER')", (member, role)
            ).fetchone()
            if row is None or len(row) != 1 or type(row[0]) is not bool:
                raise ValueError("membership state could not be observed")
            result[(member, role)] = row[0]
        return result


def _membership_sha256(pairs: tuple[tuple[str, str], ...]) -> str:
    wire = "\n".join("\0".join(pair) for pair in sorted(pairs)).encode("utf-8")
    return hashlib.sha256(wire).hexdigest()


def _validate_expiry_result(value: object, profile: str) -> dict[str, Any]:
    keys = {"operation_sha256", "mechanism", "effective_at_unix"}
    if type(value) is not dict or set(value) != keys:
        raise ValueError("credential expiry control has an unexpected shape")
    operation = _digest(value["operation_sha256"], "credential expiry operation")
    mechanism = value["mechanism"]
    if mechanism not in {"provider-credential-expiry", "native-role-valid-until"}:
        raise ValueError("credential expiry mechanism is invalid")
    if profile in _OAUTH_PROFILES and mechanism != "provider-credential-expiry":
        raise ValueError("native login validity cannot expire OAuth credentials")
    effective = value["effective_at_unix"]
    if type(effective) is not int:
        raise ValueError("credential expiry timestamp is invalid")
    return {"operation_sha256": operation, "mechanism": mechanism, "effective_at_unix": effective}


def _installed_state_sha256(
    installed: Any,
    sources: Mapping[str, Any],
    principals: Mapping[str, Principal],
    target: Mapping[str, Any],
) -> str:
    if not getattr(installed, "ran", False):
        raise ValueError("module installation was not independently observed")
    if type(installed.owner_role) is not str or type(installed.registrar_role) is not str:
        raise ValueError("installed role identities are unavailable")
    access = target["resources"]["module_access"]
    actors = tuple(principals[label].user for label in _ACTORS)
    roles = (
        installed.owner_role,
        installed.registrar_role,
        access["reader_role"],
        access["writer_role"],
        *((access["auditor_role"],) if access.get("auditor_role") is not None else ()),
    )
    direct = (
        (principals["registrar"].user, installed.registrar_role),
        (principals["registrar"].user, access["reader_role"]),
        (principals["writer"].user, access["reader_role"]),
        (principals["writer"].user, access["writer_role"]),
        (principals["reader"].user, access["reader_role"]),
    )
    if __package__:
        from ._lakebase_native import _role_acl_snapshot
    else:
        from _lakebase_native import _role_acl_snapshot
    with sources["installer_connection_source"]() as connection:
        digest, valid = _role_acl_snapshot(connection, actors, roles, frozenset(direct))
    if not valid:
        raise ValueError("installed person ACL differs from its authorized state")
    return digest


def _public_state_sha256(reader: Any) -> str:
    result = reader.query(
        "lakebase_qualification",
        "SELECT p.code, p.value FROM lakebase_qualification.Probe p ORDER BY p.code LIMIT 100",
    )
    if result.truncated:
        raise ValueError("public person state snapshot was truncated")
    payload = {
        "rows": [dict(row) for row in result.rows],
        "revision": dict(result.revision.by_backend),
        "backend": result.freshness.backend,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(canonical).hexdigest()


def _combined_state_sha256(acl_digest: str, public_digest: str) -> str:
    _digest(acl_digest, "ACL snapshot")
    _digest(public_digest, "public state snapshot")
    return hashlib.sha256(f"{acl_digest}:{public_digest}".encode()).hexdigest()
