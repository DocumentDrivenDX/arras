# SPDX-License-Identifier: MIT OR Apache-2.0
"""Public Arras/Truss operation sequence for the separately admitted Lakebase target.

This module is deliberately separate from the offline admission gate. It is imported only after
the caller has validated and explicitly authorized a target and fixture.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from types import ModuleType
from typing import Any

if __package__:
    from ._lakebase_native import (
        _artifact_facts,
        _digest_name,
        _role_acl_snapshot,
        _role_attributes,
        _strict_default_probe,
    )
else:
    from _lakebase_native import (
        _artifact_facts,
        _digest_name,
        _role_acl_snapshot,
        _role_attributes,
        _strict_default_probe,
    )

HARNESS_MODULE_DOCUMENT = b"""{
  "umf": "0.10.0",
  "id": "arras-lakebase-qualification-v1",
  "vocabularies": {"umf.ddd": {"version": "0.1.0"}},
  "extensions": {},
  "modules": [{
    "id": "lakebase_qualification",
    "namespace": "lakebase_qualification",
    "extensions": {"umf.ddd": {"kind": "bounded-context", "terms": []}},
    "elements": [
      {
        "id": "Probe",
        "name": "Probe",
        "kind": "record",
        "members": [
          {"module": "lakebase_qualification", "element": "Probe.code"},
          {"module": "lakebase_qualification", "element": "Probe.value"}
        ],
        "extensions": {"umf.ddd": {
          "kind": "entity",
          "fields": {
            "code": {"type": {"kind": "scalar", "name": "string"}, "cardinality": "one"},
            "value": {"type": {"kind": "scalar", "name": "string"}, "cardinality": "one"}
          },
          "identity": {"fields": ["code"], "scope": "context"}
        }},
        "keys": [{
          "id": "identity",
          "name": "Identity",
          "fields": [{"module": "lakebase_qualification", "element": "Probe.code"}],
          "primary": true
        }]
      },
      {"id": "Probe.code", "name": "code", "kind": "field", "nullability": "required", "cardinality": "one", "scalarType": "string", "extensions": {}},
      {"id": "Probe.value", "name": "value", "kind": "field", "nullability": "required", "cardinality": "one", "scalarType": "string", "extensions": {}}
    ],
    "actions": [{
      "id": "CreateProbe",
      "inputs": [
        {"name": "code", "type": {"kind": "scalar", "name": "string"}, "cardinality": "one"},
        {"name": "value", "type": {"kind": "scalar", "name": "string"}, "cardinality": "one"}
      ],
      "preconditions": [{
        "id": "fresh",
        "reason": "a probe with that code is absent",
        "predicate": {"op": "absent", "type": "Probe", "key": {"input": "code"}}
      }],
      "effects": [{
        "op": "create", "as": "probe", "type": "Probe", "key": {"input": "code"},
        "properties": {"value": {"input": "value"}}
      }]
    }]
  }]
}"""
HARNESS_MODULE_SHA256 = hashlib.sha256(HARNESS_MODULE_DOCUMENT).hexdigest()

_CASE_OPERATIONS: dict[str, frozenset[str]] = {
    "LB-INSTALL": frozenset({"read", "install", "cleanup"}),
    "LB-PERSON": frozenset(
        {"read", "apply", "refresh", "revoke_owned_memberships", "expire_owned_login"}
    ),
    "LB-CUSTODY": frozenset({"read", "apply"}),
    "LB-SETTLEMENT": frozenset({"read", "apply", "fault"}),
    "LB-ACL": frozenset(
        {
            "read",
            "install",
            "configure",
            "provision_module_roles",
            "prepare_owned_access_roles",
            "grant_owned_memberships",
            "revoke_owned_memberships",
        }
    ),
    "MP-01": frozenset({"read", "apply", "feed", "refresh", "restart"}),
    "MP-02": frozenset({"read", "refresh"}),
    "MP-03": frozenset({"read", "install"}),
    "MP-04": frozenset({"read", "feed", "refresh", "restart"}),
    "MP-05": frozenset({"read", "apply", "fault"}),
    "MP-06": frozenset({"read", "install", "configure"}),
}
_CASE_CODES = {
    "LB-INSTALL": "strict_install_probe_not_run",
    "LB-PERSON": "identity_and_lifecycle_controls_unavailable",
    "LB-CUSTODY": "caller_savepoint_control_unavailable",
    "LB-SETTLEMENT": "commit_outcome_fault_control_unavailable",
    "LB-ACL": "owned_module_role_setup_not_authorized",
    "MP-01": "compute_restart_control_unavailable",
    "MP-02": "session_lease_control_unavailable",
    "MP-03": "managed_privilege_observation_unavailable",
    "MP-04": "feed_restart_control_unavailable",
    "MP-05": "native_setting_and_fault_control_unavailable",
    "MP-06": "required_extension_observation_unavailable",
}
_RESOURCE_KINDS = frozenset({"schema", "role"})


def _case_row(case: str, status: str, code: str) -> dict[str, str]:
    return {"case": case, "status": status, "code": code}


def _baseline_receipt(
    required: tuple[str, ...],
    results: Mapping[str, Any],
    observed: dict[str, Any],
    cleanup: dict[str, Any],
) -> dict[str, Any]:
    return {
        "cases": [results[case] for case in required],
        "observed": observed,
        "cleanup": cleanup,
        "module_document_sha256": HARNESS_MODULE_SHA256,
    }


class _ObservedFailure(Exception):
    """An independently observed operation contradicts its expected postcondition."""

    def __init__(self, case: str, code: str) -> None:
        self.case = case
        self.code = code


class _OwnershipUncertain(Exception):
    """A fixture callback may have partially changed resources without proving custody."""

    def __init__(self, *, interrupted: bool = False) -> None:
        self.interrupted = interrupted


@dataclass
class _InstallState:
    migrated: Any | None
    expected_names: set[tuple[str, str]]
    mutation_started: bool


def _fresh_install_preconditions(
    sources: Mapping[str, Any], backend: Any, observed: dict[str, Any], results: dict[str, Any]
) -> bool:
    with sources["installer_connection_source"]() as connection:
        schema_absent = connection.execute(
            "SELECT pg_catalog.to_regnamespace('truss') IS NULL"
        ).fetchone()
    if schema_absent != (True,):
        results["LB-INSTALL"] = _case_row(
            "LB-INSTALL", "blocked", "installation_namespace_not_empty"
        )
        return False
    observed["preconditions"]["truss_schema_absent"] = True
    status = backend.status()
    if (
        status.available
        or status.reason != "not_configured"
        or status.detail != "Truss is not installed here"
    ):
        observed["preconditions"]["status_reason"] = (
            status.reason
            if status.reason
            in {"not_configured", "unsupported_version", "migration_failed", "unavailable"}
            else "unavailable"
        )
        observed["preconditions"]["status_detail"] = "other"
        results["LB-INSTALL"] = _case_row(
            "LB-INSTALL", "blocked", "truss_installation_state_not_fresh"
        )
        return False
    observed["preconditions"]["status_reason"] = "not_configured"
    observed["preconditions"]["status_detail"] = "not_installed"
    return True


def _attempt_selected_install(
    backend: Any,
    sources: Mapping[str, Any],
    tolerated: tuple[str, ...],
    observed: dict[str, Any],
    results: dict[str, Any],
) -> _InstallState | None:
    strict = _strict_default_probe(sources, tolerated)
    observed["strict_probe"].update(
        {
            "outcome": strict.outcome,
            "object_class": strict.object_class,
            "phase": strict.phase,
            "selected_role_sha256": strict.selected_role_sha256,
            "role_selected": strict.role_selected,
            "caller_state_unchanged": strict.caller_state_unchanged,
            "native_state_unchanged": strict.native_state_unchanged,
        }
    )
    if strict.outcome == "unexpected_success":
        observed["operations"]["installation_ran"] = True
        owned = (
            type(strict.owner_role) is str
            and type(strict.registrar_role) is str
            and strict.caller_state_unchanged is True
            and strict.native_state_unchanged is False
        )
        names: set[tuple[str, str]] = set()
        if owned:
            names.update(
                {
                    ("schema", "truss"),
                    ("role", strict.owner_role),
                    ("role", strict.registrar_role),
                }
            )
        results["LB-INSTALL"] = _case_row(
            "LB-INSTALL", "blocked", "strict_policy_unexpectedly_succeeded"
        )
        return _InstallState(None, names, owned)
    contained = (
        strict.outcome == "typed_refusal"
        and strict.object_class in {"schema", "relation", "sequence", "routine", "type", "column"}
        and strict.phase in {"pre_ownership", "post_installation"}
        and strict.role_selected is True
        and strict.caller_state_unchanged is True
        and strict.native_state_unchanged is True
    )
    if not contained:
        results["LB-INSTALL"] = _case_row(
            "LB-INSTALL", "blocked", "strict_refusal_not_contained_and_verified"
        )
        return None
    migrated = backend.migrate()
    observed["operations"]["installation_ran"] = bool(migrated.ran)
    if not migrated.ran or not migrated.registrar_role or not migrated.owner_role:
        results["LB-INSTALL"] = _case_row(
            "LB-INSTALL", "blocked", "installation_result_not_owned_by_this_run"
        )
        return _InstallState(migrated, set(), False)
    names = {
        ("schema", "truss"),
        ("role", migrated.owner_role),
        ("role", migrated.registrar_role),
    }
    results["LB-INSTALL"] = _case_row(
        "LB-INSTALL", "passed", "typed_strict_refusal_then_selected_install"
    )
    return _InstallState(migrated, names, True)


def _cleanup_entries(raw_resources: object) -> tuple[list[dict[str, object]], bool]:
    resources: list[dict[str, object]] = []
    if type(raw_resources) not in (list, tuple):
        return resources, False
    for item in raw_resources:
        if (
            type(item) is not dict
            or set(item) != {"resource_kind", "name_or_opaque_id", "removed"}
            or item["resource_kind"] not in _RESOURCE_KINDS
            or type(item["name_or_opaque_id"]) is not str
            or type(item["removed"]) is not bool
        ):
            return resources, False
        resources.append(
            {
                "resource_kind": item["resource_kind"],
                "name_or_opaque_id": _digest_name(item["name_or_opaque_id"]),
                "removed": item["removed"],
            }
        )
    return resources, True


def _independent_absence(
    sources: Mapping[str, Any], expected_names: set[tuple[str, str]]
) -> tuple[bool | None, bool | None]:
    try:
        with sources["installer_connection_source"]() as connection:
            schema_row = connection.execute(
                "SELECT pg_catalog.to_regnamespace('truss') IS NULL"
            ).fetchone()
            absent_schema = schema_row == (True,)
            names = tuple(name for kind, name in expected_names if kind == "role")
            if names:
                role_row = connection.execute(
                    "SELECT count(*) FROM pg_catalog.pg_roles WHERE rolname = ANY(%s)",
                    (list(names),),
                ).fetchone()
                return absent_schema, role_row == (0,)
            return absent_schema, None
    except Exception:
        return None, None


def _cleanup_owned_run(
    fixture_module: ModuleType,
    sources: Mapping[str, Any],
    expected_names: set[tuple[str, str]],
    *,
    mutation_started: bool,
    cleanup_authorized: bool,
) -> dict[str, Any]:
    cleanup: dict[str, Any] = {
        "status": "blocked",
        "resources": [],
        "independent_absence": {
            "truss_schema_absent": None,
            "generated_roles_absent": None,
        },
    }
    if not mutation_started or not cleanup_authorized:
        return cleanup
    callback = getattr(fixture_module, "cleanup_owned", None)
    raw_resources: object = None
    if callable(callback):
        try:
            raw_resources = callback()
        except Exception:
            pass
    resources, valid = _cleanup_entries(raw_resources)
    absent_schema, absent_roles = _independent_absence(sources, expected_names)
    expected = {(kind, _digest_name(name)) for kind, name in expected_names}
    actual = {
        (row["resource_kind"], row["name_or_opaque_id"])
        for row in resources
        if type(row["resource_kind"]) is str and type(row["name_or_opaque_id"]) is str
    }
    complete = (
        valid
        and actual == expected
        and all(row["removed"] is True for row in resources)
        and absent_schema is True
        and absent_roles is True
    )
    return {
        "status": "passed" if complete else "blocked",
        "resources": resources,
        "independent_absence": {
            "truss_schema_absent": absent_schema,
            "generated_roles_absent": absent_roles,
        },
    }


@dataclass(frozen=True)
class _AccessPlan:
    actors: tuple[str, ...]
    roles: tuple[str, ...]
    direct: frozenset[tuple[str, str]]


def _prepare_access_roles(
    fixture_module: ModuleType,
    sources: Mapping[str, Any],
    principals: Mapping[str, Any],
    access: Any,
    migrated: Any,
    expected_names: set[tuple[str, str]],
) -> _AccessPlan | None:
    prepare = getattr(fixture_module, "prepare_owned_access_roles", None)
    grant = getattr(fixture_module, "grant_owned_memberships", None)
    if not callable(prepare) or not callable(grant):
        return None
    module_roles = tuple(
        dict.fromkeys(
            [access.reader_role, access.writer_role]
            + ([access.auditor_role] if access.auditor_role is not None else [])
        )
    )
    with sources["installer_connection_source"]() as connection:
        existing = _role_attributes(connection, module_roles)
        install_attributes = _role_attributes(
            connection, (migrated.owner_role, migrated.registrar_role)
        )
    if any(
        install_attributes.get(name) != (False, False, False, False)
        for name in (migrated.owner_role, migrated.registrar_role)
    ):
        raise _ObservedFailure("LB-ACL", "installation_role_attributes_mismatch")
    if existing:
        raise RuntimeError("bound module group custody is not fresh")
    role_specs = tuple({"name": role, "login": False} for role in module_roles)
    try:
        created = prepare(role_specs)
    except (KeyboardInterrupt, SystemExit) as exc:
        raise _OwnershipUncertain(interrupted=True) from exc
    except Exception as exc:
        raise _OwnershipUncertain from exc
    if type(created) not in (tuple, list) or tuple(created) != module_roles:
        raise _OwnershipUncertain()
    expected_names.update(("role", role) for role in module_roles)
    assignments = (
        (principals["registrar"].user, migrated.registrar_role),
        (principals["registrar"].user, access.reader_role),
        (principals["writer"].user, access.reader_role),
        (principals["writer"].user, access.writer_role),
        (principals["reader"].user, access.reader_role),
    )
    try:
        granted = grant(assignments)
    except (KeyboardInterrupt, SystemExit) as exc:
        raise _OwnershipUncertain(interrupted=True) from exc
    except Exception as exc:
        raise _OwnershipUncertain from exc
    valid = (
        type(granted) in (tuple, list)
        and all(type(pair) in (tuple, list) and len(pair) == 2 for pair in granted)
        and all(type(value) is str for pair in granted for value in pair)
        and len(set(tuple(pair) for pair in granted)) == len(granted)
        and set(tuple(pair) for pair in granted).issubset(assignments)
    )
    if not valid:
        raise _OwnershipUncertain()
    actors = tuple(principals[label].user for label in ("registrar", "writer", "reader", "denied"))
    roles = (
        migrated.owner_role,
        migrated.registrar_role,
        access.reader_role,
        access.writer_role,
        *((access.auditor_role,) if access.auditor_role is not None else ()),
    )
    return _AccessPlan(actors, roles, frozenset(assignments))


def _exercise_public_write(
    writer: Any, reader: Any, initial: Any, observed: dict[str, Any]
) -> None:
    code = f"probe-{uuid.uuid4().hex}"
    draft = {"code": code, "value": "arras-lakebase-qualification"}
    validation = writer.validate("lakebase_qualification.CreateProbe", draft)
    if not validation.ok or len(validation.effects) != 1:
        raise _ObservedFailure("LB-PERSON", "dry_run_result_mismatch")
    after_dry_run = reader.query(
        "lakebase_qualification",
        "SELECT p.code FROM lakebase_qualification.Probe p ORDER BY p.code LIMIT 10",
    ).rows
    if after_dry_run != initial:
        raise _ObservedFailure("LB-PERSON", "dry_run_changed_records")
    if initial != ():
        raise _ObservedFailure("LB-PERSON", "initial_records_not_empty")
    receipt = writer.invoke(
        "lakebase_qualification.CreateProbe",
        draft,
        idempotency_key=f"lakebase-qualification-{uuid.uuid4().hex}",
    )
    if getattr(receipt, "created", None) != 1:
        raise _ObservedFailure("LB-PERSON", "write_result_mismatch")
    observed["operations"]["write"] = "passed"
    rows = reader.query(
        "lakebase_qualification",
        "SELECT p.code, p.value FROM lakebase_qualification.Probe p ORDER BY p.code LIMIT 10",
    ).rows
    if rows != ({"code": code, "value": "arras-lakebase-qualification"},):
        raise _ObservedFailure("LB-PERSON", "readback_mismatch")


def _run_public_access(
    backend: Any,
    sources: Mapping[str, Any],
    principals: Mapping[str, Any],
    access_plan: _AccessPlan,
    observed: dict[str, Any],
    results: dict[str, Any],
    *,
    person_write_allowed: bool,
) -> None:
    from arras.core import Arras
    from arras.errors import Invalid, Refused
    from arras.model import Placement

    with sources["installer_connection_source"]() as connection:
        before_hash, before_ok = _role_acl_snapshot(
            connection, access_plan.actors, access_plan.roles, access_plan.direct
        )
    observed["acl"]["snapshot_before_sha256"] = before_hash
    if not before_ok:
        results["LB-ACL"] = _case_row("LB-ACL", "blocked", "module_acl_precondition_mismatch")
        return
    host = Arras.start(
        {"truss": backend},
        expected=("truss",),
        admin=principals["registrar"],
        default_placement=Placement("truss"),
    )
    registered = host.session(principals["registrar"]).registry().register(HARNESS_MODULE_DOCUMENT)
    if registered.module != "lakebase_qualification":
        raise _ObservedFailure("LB-ACL", "registration_result_mismatch")
    observed["operations"]["registration"] = "passed"
    backend.configure_access(("lakebase_qualification",))
    observed["operations"]["access_configuration"] = "passed"
    reader = host.session(principals["reader"])
    initial = reader.query(
        "lakebase_qualification",
        "SELECT p.code FROM lakebase_qualification.Probe p ORDER BY p.code LIMIT 10",
    )
    if initial.rows != ():
        raise _ObservedFailure("LB-ACL", "initial_records_not_empty")
    observed["operations"]["read"] = "passed"
    if person_write_allowed:
        _exercise_public_write(host.session(principals["writer"]), reader, initial.rows, observed)
    try:
        host.session(principals["denied"]).document("lakebase_qualification")
    except (Refused, Invalid):
        observed["operations"]["denial"] = "passed"
    else:
        raise _ObservedFailure("LB-ACL", "denied_actor_read_succeeded")
    with sources["installer_connection_source"]() as connection:
        after_hash, after_ok = _role_acl_snapshot(
            connection, access_plan.actors, access_plan.roles, access_plan.direct
        )
    observed["acl"]["snapshot_after_sha256"] = after_hash
    observed["acl"]["intended_memberships_match"] = after_ok
    if not after_ok:
        raise _ObservedFailure("LB-ACL", "acl_postcondition_mismatch")
    if person_write_allowed and observed["operations"]["read"] == "passed":
        results["LB-ACL"] = _case_row(
            "LB-ACL", "blocked", "native_acl_and_activation_controls_unavailable"
        )


def _run_authorized_access(
    backend: Any,
    fixture_module: ModuleType,
    sources: Mapping[str, Any],
    principals: Mapping[str, Any],
    access: Any,
    migrated: Any,
    expected_resource_names: set[tuple[str, str]],
    allowed_ops: frozenset[str],
    case_allowlist: frozenset[str],
    results: dict[str, Any],
    observed: dict[str, Any],
) -> None:
    callback_ops = _CASE_OPERATIONS["LB-ACL"]
    if "LB-ACL" not in case_allowlist or not callback_ops.issubset(allowed_ops):
        results["LB-ACL"] = _case_row(
            "LB-ACL", "blocked", "role_and_membership_changes_not_authorized"
        )
        return
    access_plan = _prepare_access_roles(
        fixture_module,
        sources,
        principals,
        access,
        migrated,
        expected_resource_names,
    )
    if access_plan is None:
        results["LB-ACL"] = _case_row(
            "LB-ACL", "blocked", "role_and_membership_changes_not_authorized"
        )
        return
    _run_public_access(
        backend,
        sources,
        principals,
        access_plan,
        observed,
        results,
        person_write_allowed=("LB-PERSON" in case_allowlist and "apply" in allowed_ops),
    )


def _baseline_initial(
    inputs: Any,
) -> tuple[
    tuple[str, ...],
    Any,
    frozenset[str],
    frozenset[str],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    required = tuple(case for case in inputs.required_cases if case != "LB-ADMISSION")
    target = inputs.target
    authorization = inputs.authorization
    allowed_ops = frozenset(authorization["allowed_operations"])
    case_allowlist = frozenset(authorization["allowed_cases"])
    results = {
        case: _case_row(case, "blocked", _CASE_CODES.get(case, "control_unavailable"))
        for case in required
    }
    for case in required:
        if case not in case_allowlist:
            results[case] = _case_row(case, "blocked", "case_not_authorized")
        elif _CASE_OPERATIONS.get(case, frozenset()).difference(allowed_ops):
            results[case] = _case_row(case, "blocked", "required_operation_not_authorized")
    if target_auth := inputs.target.get("auth_profile"):
        if target_auth in {"human-oauth", "nonhuman-oauth"}:
            for case in ("LB-PERSON", "LB-CUSTODY", "LB-SETTLEMENT", "LB-ACL"):
                if case in results:
                    results[case] = _case_row(case, "blocked", "oauth_subject_evidence_unavailable")

    observed: dict[str, Any] = {
        "artifacts": _artifact_facts(),
        "preconditions": {
            "truss_schema_absent": None,
            "status_reason": None,
            "status_detail": None,
        },
        "operations": {
            "installation_ran": None,
            "registration": "not_run",
            "access_configuration": "not_run",
            "write": "not_run",
            "read": "not_run",
            "denial": "not_run",
            "refreshed_connection": "not_run",
        },
        "acl": {
            "snapshot_before_sha256": None,
            "snapshot_after_sha256": None,
            "intended_memberships_match": None,
        },
        "strict_probe": {
            "outcome": "not_run",
            "object_class": None,
            "phase": None,
            "selected_role_sha256": None,
            "role_selected": None,
            "caller_state_unchanged": None,
            "native_state_unchanged": None,
        },
    }
    cleanup: dict[str, Any] = {
        "status": "blocked",
        "resources": [],
        "independent_absence": {
            "truss_schema_absent": None,
            "generated_roles_absent": None,
        },
    }

    return required, target, allowed_ops, case_allowlist, results, observed, cleanup


def _prepare_baseline(
    inputs: Any,
    fixture_module: ModuleType,
    sources: Mapping[str, Any],
    required: tuple[str, ...],
    target: Any,
    allowed_ops: frozenset[str],
    case_allowlist: frozenset[str],
    results: dict[str, Any],
    observed: dict[str, Any],
) -> tuple[Any, Any, dict[str, Any]] | None:
    from arras.adapters.truss import ModuleAccess, create_backend
    from arras.types import Principal

    # One target cannot prove strict-default refusal on a clean resource and selected install on a
    # second clean resource. Still run selected installation only when its exact scope is authorized.
    install_ops = _CASE_OPERATIONS["LB-INSTALL"]
    if (
        "LB-INSTALL" not in case_allowlist
        or not install_ops.issubset(allowed_ops)
        or not callable(getattr(fixture_module, "cleanup_owned", None))
        or not callable(sources.get("installer_connection_source"))
        or not callable(sources.get("person_connection_source"))
    ):
        return None

    artifact_expected = target["expected"]
    observed_artifacts = observed["artifacts"]
    artifact_ok = (
        observed_artifacts["truss_version"] == artifact_expected["truss_version"]
        and (
            observed_artifacts["truss_wheel_sha256"] is None
            or observed_artifacts["truss_wheel_sha256"] == artifact_expected["truss_wheel_sha256"]
        )
        and observed_artifacts["native_manifest_sha256"]
        == artifact_expected["native_manifest_sha256"]
        and observed_artifacts["migration_manifest_sha256"]
        == artifact_expected["migration_manifest_sha256"]
    )
    if not artifact_ok:
        results["LB-INSTALL"] = _case_row(
            "LB-INSTALL", "blocked", "installed_artifact_evidence_incomplete"
        )
        return None

    module_access_raw = target["resources"]["module_access"]
    if (
        type(module_access_raw) is not dict
        or module_access_raw.get("document_id") != "arras-lakebase-qualification-v1"
        or module_access_raw.get("source_sha256") != HARNESS_MODULE_SHA256
    ):
        results["LB-INSTALL"] = _case_row("LB-INSTALL", "blocked", "module_access_binding_mismatch")
        return None

    role_names = target["resources"]["ordinary_role_names"]
    principals: dict[str, Principal] = {}
    try:
        for label, role in zip(
            ("registrar", "writer", "reader", "denied"), role_names, strict=True
        ):
            principal = sources["principal_for"](label)
            if (
                type(principal) is not Principal
                or principal.user != role
                or type(principal.token) is not str
                or not principal.token
            ):
                raise ValueError("principal mismatch")
            principals[label] = principal
    except Exception:
        results["LB-INSTALL"] = _case_row(
            "LB-INSTALL", "blocked", "authorized_principals_unavailable"
        )
        return None

    access = ModuleAccess(
        document_id="arras-lakebase-qualification-v1",
        reader_role=module_access_raw["reader_role"],
        writer_role=module_access_raw["writer_role"],
        auditor_role=module_access_raw.get("auditor_role"),
    )
    backend = create_backend(
        "truss",
        sources["person_connection_source"],
        sources["installer_connection_source"],
        module_access={"lakebase_qualification": access},
        tolerated_grantees=tuple(target["resources"]["tolerated_grantees"]),
    )
    return access, backend, principals


def run_baseline(
    inputs: Any, fixture_module: ModuleType, sources: Mapping[str, Any]
) -> dict[str, Any]:
    """Run authorized, independently observable public Arras/Truss baseline operations.

    Missing controls block only their corresponding case. The fixture supplies connections and
    factual cleanup actions; it never supplies case verdicts. Service mutation is possible only
    after the admission CLI has authorized execution and the per-operation authorization below.
    """
    required, target, allowed_ops, case_allowlist, results, observed, cleanup = _baseline_initial(
        inputs
    )

    prepared = _prepare_baseline(
        inputs,
        fixture_module,
        sources,
        required,
        target,
        allowed_ops,
        case_allowlist,
        results,
        observed,
    )
    if prepared is None:
        return _baseline_receipt(required, results, observed, cleanup)
    access, backend, principals = prepared

    expected_resource_names: set[tuple[str, str]] = set()
    mutation_started = False
    cleanup_safe = True
    active_case = "LB-INSTALL"
    try:
        if not _fresh_install_preconditions(sources, backend, observed, results):
            return _baseline_receipt(required, results, observed, cleanup)
        state = _attempt_selected_install(
            backend,
            sources,
            tuple(target["resources"]["tolerated_grantees"]),
            observed,
            results,
        )
        if state is None:
            return _baseline_receipt(required, results, observed, cleanup)
        expected_resource_names.update(state.expected_names)
        mutation_started = state.mutation_started
        if state.migrated is not None and mutation_started:
            active_case = "LB-ACL"
            _run_authorized_access(
                backend,
                fixture_module,
                sources,
                principals,
                access,
                state.migrated,
                expected_resource_names,
                allowed_ops,
                case_allowlist,
                results,
                observed,
            )
    except _ObservedFailure as failure:
        results[failure.case] = _case_row(failure.case, "failed", failure.code)
    except _OwnershipUncertain as ownership:
        cleanup_safe = False
        results[active_case] = _case_row(
            active_case,
            "failed" if ownership.interrupted else "blocked",
            "operation_interrupted" if ownership.interrupted else "owned_resource_state_uncertain",
        )
    except (KeyboardInterrupt, SystemExit):
        results[active_case] = _case_row(active_case, "failed", "operation_interrupted")
    except Exception:
        # Errors are deliberately not copied into safe receipts; cleanup still runs in finally.
        results[active_case] = _case_row(
            active_case, "blocked", "authorized_public_operation_unavailable"
        )
    finally:
        try:
            cleanup = _cleanup_owned_run(
                fixture_module,
                sources,
                expected_resource_names,
                mutation_started=mutation_started,
                cleanup_authorized=("cleanup" in allowed_ops and cleanup_safe),
            )
        except (KeyboardInterrupt, SystemExit):
            cleanup = {
                "status": "blocked",
                "resources": [],
                "independent_absence": {
                    "truss_schema_absent": None,
                    "generated_roles_absent": None,
                },
            }
            if results[active_case]["status"] != "failed":
                results[active_case] = _case_row(active_case, "failed", "cleanup_interrupted")

    return _baseline_receipt(required, results, observed, cleanup)
