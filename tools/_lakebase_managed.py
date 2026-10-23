# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned managed-target cases over public Arras and Truss APIs.

The fixture supplies connection sources and provider controls only. Results are
derived here from public calls and independent PostgreSQL observations.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from _lakebase_managed_access import _run_acl, _run_custody
from _lakebase_managed_common import (
    MANAGED_CASES,
)
from _lakebase_managed_common import (
    SAFE_CODE as _SAFE_CODE,
)
from _lakebase_managed_common import (
    Blocked as _Blocked,
)
from _lakebase_managed_common import (
    Failed as _Failed,
)
from _lakebase_managed_common import (
    allowed as _allowed,
)
from _lakebase_managed_common import (
    digest as _digest,
)
from _lakebase_managed_common import (
    is_authorized as _is_authorized,
)
from _lakebase_managed_feed_cases import _run_mp04
from _lakebase_managed_identity import (
    _MP06_REQUIREMENTS_SHA256,
    _MP06_RUNTIME_MANIFEST_SHA256,
    _MP06_SOURCE_INVENTORY_SHA256,
    _run_mp03,
    _run_mp06,
)
from _lakebase_managed_lifecycle import (
    _run_commit_fault,
    _run_mp05,
    _run_restart,
    _run_session_lease,
)

_CONTROL_KEYS = frozenset(
    {
        "restart_compute",
        "terminate_session",
        "fault_person_connection_source",
        "fault_events",
        "open_feed_destination",
        "observe_settings",
        "required_extension_provenance",
    }
)
_MODULE = "lakebase_qualification"
_DOCUMENT_ID = "arras-lakebase-qualification-v1"
_QUERY = "SELECT p.code, p.value FROM lakebase_qualification.Probe p ORDER BY p.code"


def _row(case: str, status: str, code: str) -> dict[str, str]:
    if status not in {"passed", "blocked", "failed"} or not _SAFE_CODE.fullmatch(code):
        raise ValueError("invalid managed-case projection")
    return {"case": case, "status": status, "code": code}


def _controls(fixture_module: Any) -> dict[str, Any]:
    factory = getattr(fixture_module, "managed_controls", None)
    if not callable(factory):
        return {}
    try:
        raw = factory()
    except Exception:
        return {}
    if type(raw) is not dict or raw.get("interface_version") != 1:
        return {}
    if set(raw) - (_CONTROL_KEYS | {"interface_version"}):
        return {}
    return {key: raw.get(key) for key in _CONTROL_KEYS}


_OBSERVATION_FIELDS: dict[str, frozenset[str]] = {
    "LB-CUSTODY": frozenset(
        {
            "caller_identity_sha256",
            "caller_prework_count",
            "caller_savepoint_restored",
            "public_query_row_count",
            "public_refusal_type",
            "native_before_sha256",
            "native_after_sha256",
        }
    ),
    "LB-SETTLEMENT": frozenset(
        {
            "fault_mode",
            "transport_event_count",
            "transport_phases",
            "public_initial_outcome_type",
            "idempotency_retry_receipt_type",
            "exactly_one_public_object",
            "original_request_receipt_sha256",
            "native_before_sha256",
            "native_after_sha256",
        }
    ),
    "LB-ACL": frozenset(
        {
            "before_acl_sha256",
            "after_acl_sha256",
            "ordinary_actor_count",
            "membership_fact_count",
            "ordinary_object_grant_count",
            "denied_catalog_refused",
            "selected_public_write_readback",
            "person_lifecycle_facts_available",
            "person_membership_lifecycle_verified",
            "person_revoke_operation_sha256",
            "person_restore_operation_sha256",
            "person_memberships_sha256",
            "person_state_sha256",
        }
    ),
    "MP-01": frozenset(
        {
            "operation_sha256",
            "generation_before_sha256",
            "generation_after_sha256",
            "backend_pid_changed",
            "public_object_count",
            "native_inventory_sha256",
            "feed",
        }
    ),
    "MP-02": frozenset(
        {
            "ended_backend_pid",
            "termination_operation_sha256",
            "old_handle_refused",
            "new_session_row_count",
            "old_handle_rebound",
        }
    ),
    "MP-03": frozenset(
        {
            "ordinary_role_count",
            "direct_membership_count",
            "effective_membership_count",
            "elevated_membership_count",
            "truss_table_privilege_count",
            "allowed_query_row_count",
            "allowed_query_succeeded",
            "ordinary_attributes_safe",
            "denied_catalog_refused",
            "snapshot_sha256",
        }
    ),
    "MP-04": frozenset(
        {
            "consumer_id_sha256",
            "feed_page_sha256",
            "feed_page_count",
            "transaction_page_count",
            "empty_interval_drained",
            "source_ack_reconciled",
            "destination_receipt_sha256",
            "destination_reopened_equal",
            "destination_replay_equal",
            "restart_operation_sha256",
            "generation_before_sha256",
            "generation_after_sha256",
            "native_after_restart_sha256",
        }
    ),
    "MP-05": frozenset(
        {
            "server_version_num",
            "configured_statement_timeout_ms",
            "configured_lock_timeout_ms",
            "bounded_timeout_sqlstate",
            "transaction_aborted_then_rolled_back",
            "genuine_commit_fault",
        }
    ),
    "MP-06": frozenset(
        {
            "runtime_manifest_sha256",
            "source_inventory_sha256",
            "required_extension_count",
            "dependency_count",
            "callable_count",
            "ordinary_execute_count",
            "ordinary_language_usage_count",
            "ordinary_principal_count",
            "bounded_vacuous_inventory",
            "requirements_declaration_sha256",
            "observed_extensions_sha256",
        }
    ),
}
_DIGEST_FIELDS: dict[str, frozenset[str]] = {
    "LB-CUSTODY": frozenset(
        {"caller_identity_sha256", "native_before_sha256", "native_after_sha256"}
    ),
    "LB-SETTLEMENT": frozenset(
        {"original_request_receipt_sha256", "native_before_sha256", "native_after_sha256"}
    ),
    "LB-ACL": frozenset(
        {
            "before_acl_sha256",
            "after_acl_sha256",
            "person_revoke_operation_sha256",
            "person_restore_operation_sha256",
            "person_memberships_sha256",
            "person_state_sha256",
        }
    ),
    "MP-01": frozenset(
        {
            "operation_sha256",
            "generation_before_sha256",
            "generation_after_sha256",
            "native_inventory_sha256",
        }
    ),
    "MP-02": frozenset({"termination_operation_sha256"}),
    "MP-03": frozenset({"snapshot_sha256"}),
    "MP-04": frozenset(
        {
            "consumer_id_sha256",
            "feed_page_sha256",
            "destination_receipt_sha256",
            "restart_operation_sha256",
            "generation_before_sha256",
            "generation_after_sha256",
            "native_after_restart_sha256",
        }
    ),
    "MP-05": frozenset(),
    "MP-06": frozenset(
        {
            "runtime_manifest_sha256",
            "source_inventory_sha256",
            "requirements_declaration_sha256",
            "observed_extensions_sha256",
        }
    ),
}
_COUNT_FIELDS: dict[str, frozenset[str]] = {
    "LB-CUSTODY": frozenset({"caller_prework_count", "public_query_row_count"}),
    "LB-SETTLEMENT": frozenset({"transport_event_count"}),
    "LB-ACL": frozenset(
        {"ordinary_actor_count", "membership_fact_count", "ordinary_object_grant_count"}
    ),
    "MP-01": frozenset({"public_object_count"}),
    "MP-02": frozenset({"ended_backend_pid", "new_session_row_count"}),
    "MP-03": frozenset(
        {
            "ordinary_role_count",
            "direct_membership_count",
            "effective_membership_count",
            "elevated_membership_count",
            "truss_table_privilege_count",
            "allowed_query_row_count",
        }
    ),
    "MP-04": frozenset({"feed_page_count", "transaction_page_count"}),
    "MP-05": frozenset({"configured_statement_timeout_ms", "configured_lock_timeout_ms"}),
    "MP-06": frozenset(
        {
            "required_extension_count",
            "dependency_count",
            "callable_count",
            "ordinary_execute_count",
            "ordinary_language_usage_count",
            "ordinary_principal_count",
        }
    ),
}
_BOOLEAN_FIELDS: dict[str, frozenset[str]] = {
    "LB-CUSTODY": frozenset({"caller_savepoint_restored"}),
    "LB-SETTLEMENT": frozenset({"exactly_one_public_object"}),
    "LB-ACL": frozenset(
        {
            "denied_catalog_refused",
            "selected_public_write_readback",
            "person_lifecycle_facts_available",
            "person_membership_lifecycle_verified",
        }
    ),
    "MP-01": frozenset({"backend_pid_changed"}),
    "MP-02": frozenset({"old_handle_refused", "old_handle_rebound"}),
    "MP-03": frozenset(
        {"allowed_query_succeeded", "ordinary_attributes_safe", "denied_catalog_refused"}
    ),
    "MP-04": frozenset(
        {"destination_reopened_equal", "destination_replay_equal", "empty_interval_drained"}
    ),
    "MP-05": frozenset({"transaction_aborted_then_rolled_back"}),
    "MP-06": frozenset({"bounded_vacuous_inventory"}),
}


def _validate_settlement(value: dict[str, Any], modes: set[str]) -> None:
    valid_phases = {
        "commit_entered",
        "ack_entered",
        "transport_interrupted",
        "provider_restart_completed",
        "driver_returned",
        "driver_error",
        "connection_closed",
    }
    if (
        value["fault_mode"] not in modes
        or value["public_initial_outcome_type"] not in {"CommitUnknown", "Receipt"}
        or value["exactly_one_public_object"] is not True
        or value["idempotency_retry_receipt_type"] not in {"Receipt", "BatchReceipt"}
        or type(value["transport_phases"]) not in {tuple, list}
        or not {"commit_entered", "transport_interrupted"}.issubset(value["transport_phases"])
        or set(value["transport_phases"]) - valid_phases
    ):
        raise ValueError("managed settlement observation is invalid")
    phases = tuple(value["transport_phases"])
    try:
        entered = phases.index("commit_entered")
        interrupted = phases.index("transport_interrupted")
        outcome = next(
            index
            for index, phase in enumerate(phases)
            if phase in {"driver_returned", "driver_error"}
        )
        closed = phases.index("connection_closed")
    except (StopIteration, ValueError):
        raise ValueError("managed settlement phase sequence is incomplete") from None
    if not entered < interrupted < outcome < closed:
        raise ValueError("managed settlement phase sequence is invalid")


def _validate_restart_feed(feed: Any) -> None:
    required = {
        "consumer_id_sha256",
        "feed_page_sha256",
        "feed_page_count",
        "transaction_page_count",
        "empty_interval_drained",
        "unacknowledged_replay_equal",
        "destination_receipt_sha256",
        "source_ack_reconciled",
        "destination_reopened_equal",
        "destination_replay_equal",
    }
    if type(feed) is not dict or set(feed) != required:
        raise ValueError("managed restart feed evidence is invalid")
    for key in {"consumer_id_sha256", "feed_page_sha256", "destination_receipt_sha256"}:
        _digest(feed[key], "managed_feed_digest_invalid")
    if (
        type(feed["feed_page_count"]) is not int
        or feed["feed_page_count"] < 2
        or type(feed["transaction_page_count"]) is not int
        or feed["transaction_page_count"] < 1
        or feed["feed_page_count"] != feed["transaction_page_count"] + 1
        or feed["empty_interval_drained"] is not True
        or feed["unacknowledged_replay_equal"] is not True
        or feed["source_ack_reconciled"] != "matched"
        or feed["destination_reopened_equal"] is not True
        or feed["destination_replay_equal"] is not True
    ):
        raise ValueError("managed restart feed postcondition is invalid")


def _safe_facts(
    case: str, value: Any, *, settlement_modes: set[str] | None = None
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _OBSERVATION_FIELDS[case]:
        raise ValueError("managed observation has an unexpected field set")
    safe = dict(value)
    for key in _DIGEST_FIELDS[case]:
        _digest(safe[key], "managed_observation_digest_invalid")
    for key in _COUNT_FIELDS[case]:
        if type(safe[key]) is not int or safe[key] < 0:
            raise ValueError("managed observation count is invalid")
    for key in _BOOLEAN_FIELDS[case]:
        if type(safe[key]) is not bool:
            raise ValueError("managed observation boolean is invalid")
    _validate_case_postconditions(case, safe, settlement_modes)
    return safe


def _validate_case_postconditions(
    case: str, safe: dict[str, Any], settlement_modes: set[str] | None
) -> None:
    if case == "LB-CUSTODY" and (
        safe["public_refusal_type"] != "QueryRefused"
        or safe["caller_savepoint_restored"] is not True
        or safe["caller_prework_count"] < 1
        or safe["native_before_sha256"] != safe["native_after_sha256"]
    ):
        raise ValueError("managed caller custody observation is invalid")
    if case == "LB-SETTLEMENT":
        _validate_settlement(safe, settlement_modes or {"cut_transport_during_commit"})
    if case == "LB-ACL" and any(
        safe[key] is not True
        for key in (
            "denied_catalog_refused",
            "selected_public_write_readback",
            "person_lifecycle_facts_available",
            "person_membership_lifecycle_verified",
        )
    ):
        raise ValueError("managed activation observation is invalid")
    if case == "MP-01":
        if (
            safe["backend_pid_changed"] is not True
            or safe["generation_before_sha256"] == safe["generation_after_sha256"]
            or safe["public_object_count"] < 2
        ):
            raise ValueError("managed restart evidence is incomplete")
        _validate_restart_feed(safe["feed"])
    if case == "MP-02" and (
        safe["old_handle_refused"] is not True or safe["old_handle_rebound"] is not False
    ):
        raise ValueError("managed ended-session observation is invalid")
    if case == "MP-04" and (
        safe["source_ack_reconciled"] != "matched"
        or safe["destination_reopened_equal"] is not True
        or safe["destination_replay_equal"] is not True
        or safe["empty_interval_drained"] is not True
        or safe["feed_page_count"] < 1
        or safe["transaction_page_count"] < 1
        or safe["feed_page_count"] != safe["transaction_page_count"] + 1
    ):
        raise ValueError("managed feed durability observation is invalid")
    if case == "MP-03" and (
        safe["ordinary_role_count"] != 4
        or safe["elevated_membership_count"] != 0
        or safe["ordinary_attributes_safe"] is not True
        or safe["allowed_query_succeeded"] is not True
        or safe["denied_catalog_refused"] is not True
    ):
        raise ValueError("managed identity observation is incomplete")
    if case == "MP-06" and (
        safe["runtime_manifest_sha256"] != _MP06_RUNTIME_MANIFEST_SHA256
        or safe["source_inventory_sha256"] != _MP06_SOURCE_INVENTORY_SHA256
        or safe["requirements_declaration_sha256"] != _MP06_REQUIREMENTS_SHA256
        or safe["required_extension_count"] != 1
        or safe["dependency_count"] != 4
        or safe["callable_count"] != 3
        or safe["ordinary_principal_count"] != 4
        or safe["ordinary_language_usage_count"] > safe["ordinary_principal_count"]
        or safe["ordinary_execute_count"]
        > safe["callable_count"] * safe["ordinary_principal_count"]
        or safe["bounded_vacuous_inventory"] is not False
    ):
        raise ValueError("managed extension observation is incomplete")
    if case == "MP-05":
        fault = safe["genuine_commit_fault"]
        if (
            type(safe["server_version_num"]) is not str
            or safe["bounded_timeout_sqlstate"] != "57014"
            or safe["transaction_aborted_then_rolled_back"] is not True
        ):
            raise ValueError("managed timeout observation is invalid")
        safe["genuine_commit_fault"] = _safe_facts(
            "LB-SETTLEMENT",
            fault,
            settlement_modes={"cut_transport_during_commit"},
        )


def safe_managed_observations(value: Any) -> dict[str, Any]:
    """Return a closed, redacted observation map suitable for a public receipt."""
    if type(value) is not dict or set(value) - set(MANAGED_CASES):
        raise ValueError("managed observations contain an invalid case set")
    return {case: _safe_facts(case, facts) for case, facts in value.items()}


def _execute_case(
    case: str,
    inputs: Any,
    controls: Mapping[str, Any],
    sources: Mapping[str, Any],
    backend: Any,
    principals: Mapping[str, Any],
    baseline_observed: Any,
) -> dict[str, Any]:
    _allowed(inputs, case)
    if case == "LB-CUSTODY":
        return _run_custody(inputs, sources, principals)
    if case == "LB-SETTLEMENT":
        return _run_commit_fault(
            case, "cut_transport_during_commit", inputs, controls, sources, principals, backend
        )
    if case == "LB-ACL":
        return _run_acl(inputs, controls, sources, principals, backend, baseline_observed)
    if case == "MP-01":
        return _run_restart(inputs, controls, sources, principals, backend)
    if case == "MP-02":
        return _run_session_lease(inputs, controls, sources, principals, backend)
    if case == "MP-03":
        return _run_mp03(inputs, sources, principals, backend)
    if case == "MP-04":
        return _run_mp04(inputs, controls, sources, principals, backend)
    if case == "MP-05":
        return _run_mp05(inputs, controls, sources, principals, backend)
    if case == "MP-06":
        return _run_mp06(inputs, controls, sources, principals)
    raise _Blocked("control_unavailable")


def run_managed(
    *,
    inputs: Any,
    fixture_module: Any,
    sources: Mapping[str, Any],
    backend: Any,
    principals: Mapping[str, Any],
    installed: Any,
    baseline_observed: Any,
) -> dict[str, Any]:
    """Execute the managed case tranche without rerunning baseline or cleanup."""
    del installed
    required_cases = tuple(case for case in MANAGED_CASES if case in inputs.required_cases)
    if not required_cases:
        return {"cases": [], "observed": {}}
    rows: list[dict[str, str]] = []
    observed: dict[str, Any] = {}
    allowed_cases = tuple(case for case in required_cases if _is_authorized(inputs, case))
    control_cases = {"LB-SETTLEMENT", "LB-ACL", "MP-01", "MP-02", "MP-04", "MP-05", "MP-06"}
    controls = (
        _controls(fixture_module) if any(case in control_cases for case in allowed_cases) else {}
    )
    for index, case in enumerate(required_cases):
        try:
            facts = _execute_case(
                case,
                inputs,
                controls,
                sources,
                backend,
                principals,
                baseline_observed,
            )
            observed[case] = facts
            rows.append(_row(case, "passed", "managed_postconditions_verified"))
        except _Blocked as blocked:
            rows.append(_row(case, "blocked", blocked.code))
        except _Failed as failed:
            rows.append(_row(case, "failed", failed.code))
        except (KeyboardInterrupt, SystemExit):
            rows.append(_row(case, "failed", "operation_interrupted"))
            rows.extend(
                _row(remaining, "blocked", "operation_interrupted")
                for remaining in required_cases[index + 1 :]
            )
            break
        except Exception:
            rows.append(_row(case, "failed", "managed_operation_failed"))
    return {"cases": rows, "observed": observed}
