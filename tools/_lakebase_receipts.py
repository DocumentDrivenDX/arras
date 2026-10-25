# SPDX-License-Identifier: MIT OR Apache-2.0
"""Closed projections for factual Lakebase operation receipts."""

from __future__ import annotations

import re
from typing import Any

from _lakebase_acceptance import CASE_IDS, AdmissionError

_MANAGED_CASE_IDS = frozenset(CASE_IDS) - {"LB-ADMISSION", "LB-INSTALL", "LB-PERSON"}


def _require_digest(value: object, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AdmissionError(f"{label} is not a lowercase SHA-256 digest")
    return value


def _safe_artifacts(artifacts: object) -> dict[str, Any]:
    artifact_keys = {
        "truss_version",
        "truss_wheel_sha256",
        "native_manifest_sha256",
        "migration_manifest_sha256",
        "evidence_codes",
    }
    if type(artifacts) is not dict or set(artifacts) != artifact_keys:
        raise AdmissionError("operation runner artifact observations have an unexpected shape")
    safe_artifacts: dict[str, Any] = {}
    for key in artifact_keys - {"evidence_codes"}:
        item = artifacts[key]
        if (
            item is not None
            and key == "truss_version"
            and (
                type(item) is not str
                or re.fullmatch(r"[0-9]+(?:\.[0-9A-Za-z_-]+){1,3}", item) is None
            )
        ):
            raise AdmissionError("operation runner version observation is invalid")
        if item is not None and key != "truss_version":
            _require_digest(item, f"operation runner {key}")
        safe_artifacts[key] = item
    codes = artifacts["evidence_codes"]
    if (
        type(codes) is not list
        or len(codes) > 16
        or any(
            type(code) is not str or re.fullmatch(r"[a-z][a-z0-9_.-]{0,79}", code) is None
            for code in codes
        )
    ):
        raise AdmissionError("operation runner evidence codes are invalid")
    safe_artifacts["evidence_codes"] = codes

    return safe_artifacts


def _safe_preconditions(preconditions: object) -> dict[str, Any]:
    if type(preconditions) is not dict or set(preconditions) != {
        "truss_schema_absent",
        "status_reason",
        "status_detail",
    }:
        raise AdmissionError("operation runner preconditions have an unexpected shape")
    if (
        preconditions["truss_schema_absent"] is not None
        and type(preconditions["truss_schema_absent"]) is not bool
    ):
        raise AdmissionError("operation runner schema observation is invalid")
    if type(preconditions["status_reason"]) not in {str, type(None)} or preconditions[
        "status_reason"
    ] not in {None, "not_configured", "unavailable", "unsupported_version", "migration_failed"}:
        raise AdmissionError("operation runner status reason is invalid")
    if type(preconditions["status_detail"]) not in {str, type(None)} or preconditions[
        "status_detail"
    ] not in {None, "not_installed", "other"}:
        raise AdmissionError("operation runner status detail is invalid")
    return dict(preconditions)


def _safe_operations(operations: object) -> dict[str, Any]:
    operation_keys = {
        "installation_ran",
        "registration",
        "access_configuration",
        "write",
        "read",
        "denial",
        "refreshed_connection",
    }
    if type(operations) is not dict or set(operations) != operation_keys:
        raise AdmissionError("operation runner outcomes have an unexpected shape")
    if (
        operations["installation_ran"] is not None
        and type(operations["installation_ran"]) is not bool
    ):
        raise AdmissionError("operation runner installation fact is invalid")
    outcomes = {"passed", "blocked", "failed", "not_run"}
    if any(
        type(operations[key]) is not str or operations[key] not in outcomes
        for key in operation_keys - {"installation_ran"}
    ):
        raise AdmissionError("operation runner outcome is invalid")
    return dict(operations)


def _safe_acl(acl: object) -> dict[str, Any]:
    if type(acl) is not dict or set(acl) != {
        "snapshot_before_sha256",
        "snapshot_after_sha256",
        "intended_memberships_match",
    }:
        raise AdmissionError("operation runner ACL observations have an unexpected shape")
    for key in ("snapshot_before_sha256", "snapshot_after_sha256"):
        if acl[key] is not None:
            _require_digest(acl[key], f"operation runner {key}")
    if (
        acl["intended_memberships_match"] is not None
        and type(acl["intended_memberships_match"]) is not bool
    ):
        raise AdmissionError("operation runner membership observation is invalid")
    return dict(acl)


def _safe_strict_probe(strict_probe: object) -> dict[str, Any]:
    strict_keys = {
        "outcome",
        "object_class",
        "phase",
        "selected_role_sha256",
        "role_selected",
        "caller_state_unchanged",
        "native_state_unchanged",
    }
    if type(strict_probe) is not dict or set(strict_probe) != strict_keys:
        raise AdmissionError("strict install probe has an unexpected shape")
    if type(strict_probe["outcome"]) is not str or strict_probe["outcome"] not in {
        "not_run",
        "typed_refusal",
        "unexpected_success",
        "other_refusal",
    }:
        raise AdmissionError("strict install probe outcome is invalid")
    if type(strict_probe["object_class"]) not in {str, type(None)} or strict_probe[
        "object_class"
    ] not in {
        None,
        "schema",
        "relation",
        "sequence",
        "routine",
        "type",
        "column",
    }:
        raise AdmissionError("strict install probe object class is invalid")
    if type(strict_probe["phase"]) not in {str, type(None)} or strict_probe["phase"] not in {
        None,
        "pre_ownership",
        "post_installation",
    }:
        raise AdmissionError("strict install probe phase is invalid")
    if strict_probe["selected_role_sha256"] is not None:
        _require_digest(strict_probe["selected_role_sha256"], "strict install role identity")
    if any(
        value is not None and type(value) is not bool
        for value in (
            strict_probe["role_selected"],
            strict_probe["caller_state_unchanged"],
            strict_probe["native_state_unchanged"],
        )
    ):
        raise AdmissionError("strict install probe observation is invalid")
    if strict_probe["outcome"] == "typed_refusal" and (
        strict_probe["object_class"] is None
        or strict_probe["phase"] is None
        or strict_probe["selected_role_sha256"] is None
        or strict_probe["role_selected"] is not True
        or strict_probe["caller_state_unchanged"] is not True
        or strict_probe["native_state_unchanged"] is not True
    ):
        raise AdmissionError(
            "typed install refusal lacks matched role and unchanged-state evidence"
        )
    return dict(strict_probe)


def _safe_operation_observations(value: object) -> dict[str, Any]:
    keys = {"artifacts", "preconditions", "operations", "acl", "strict_probe"}
    if (
        type(value) is not dict
        or not keys.issubset(value)
        or set(value) - keys - {"person", "managed"}
    ):
        raise AdmissionError("operation runner observations have an unexpected shape")
    projected = {
        "artifacts": _safe_artifacts(value["artifacts"]),
        "preconditions": _safe_preconditions(value["preconditions"]),
        "operations": _safe_operations(value["operations"]),
        "acl": _safe_acl(value["acl"]),
        "strict_probe": _safe_strict_probe(value["strict_probe"]),
    }
    for key in ("person", "managed"):
        if key in value:
            projected[key] = _safe_follow_up(key, value[key])
    return projected


def _safe_follow_up(key: str, value: object) -> Any:
    if value is None:
        return None
    if key == "person":
        if __package__:
            from ._lakebase_person import safe_person_observations
        else:
            from _lakebase_person import safe_person_observations

        return safe_person_observations(value)
    if key == "managed":
        if __package__:
            from ._lakebase_managed import safe_managed_observations
        else:
            from _lakebase_managed import safe_managed_observations

        return safe_managed_observations(value)
    raise AdmissionError("unknown follow-up observation source")


def validate_managed_case_evidence(rows: list[dict[str, str]], observations: object) -> None:
    """Each managed pass needs its own closed factual observation, independently of merge."""
    passed = {
        row["case"]
        for row in rows
        if row["case"] in _MANAGED_CASE_IDS and row["status"] == "passed"
    }
    if observations is None and not passed:
        return
    if type(observations) is not dict or set(observations) != passed:
        raise AdmissionError("managed case pass inventory lacks matching original observations")
