# SPDX-License-Identifier: MIT OR Apache-2.0
"""Closed-schema tests for the human-person receipt projection."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from arras.types import Principal


def _load_tool() -> Any:
    tools_path = Path(__file__).parents[1] / "tools"
    spec = importlib.util.spec_from_file_location(
        "lakebase_person", tools_path / "_lakebase_person.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["lakebase_person"] = module
    sys.path.insert(0, str(tools_path))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


person_tool = _load_tool()
safe_person_observations = person_tool.safe_person_observations


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _inputs() -> tuple[dict[str, Any], dict[str, Any], str, dict[str, str], dict[str, Any]]:
    profiles = {
        "registrar": "native-password",
        "writer": "human-oauth",
        "reader": "nonhuman-oauth",
        "denied": "native-password",
    }
    target = {
        "schema_version": 2,
        "auth_profile": "mixed",
        "human_actor": "writer",
        "actor_auth_profiles": profiles,
        "provider_resource_id": "resource-1",
        "resources": {
            "ordinary_role_names": ["registrar-role", "writer-role", "reader-role", "denied-role"],
            "module_access": {"reader_role": "module-reader", "writer_role": "module-writer"},
        },
    }
    authorization = {
        "schema_version": 2,
        "auth_profile": "mixed",
        "human_actor": "writer",
        "actor_auth_profiles": profiles,
    }
    provider = _sha("provider-observation")
    roles = {label: _sha(f"role:{label}") for label in profiles}
    actors: dict[str, Any] = {}
    for label, profile in profiles.items():
        kind = {
            "native-password": "native-role",
            "human-oauth": "human",
            "nonhuman-oauth": "nonhuman",
        }[profile]
        before = {
            "auth_profile": profile,
            "subject_kind": kind,
            "subject_reference_sha256": _sha(f"subject:{label}"),
            "sql_role_sha256": roles[label],
            "provider_resource_sha256": _sha("resource-1"),
            "provider_observation_sha256": provider,
            "credential_generation": _sha(f"generation:{label}:1"),
            "credential_expires_at": 1_900_000_000 if profile.endswith("oauth") else None,
            "provenance_method": (
                "provider-identity-api" if profile.endswith("oauth") else "native-role-authority"
            ),
        }
        after = None
        if label == "writer":
            after = {
                **before,
                "credential_generation": _sha("generation:writer:2"),
                "credential_expires_at": 1_900_000_100,
            }
        actors[label] = {
            "before": before,
            "after_refresh": after,
            "sql": {
                "initial_connection_verified": True,
                "current_user_sha256": roles[label],
                "session_user_sha256": roles[label],
                "tls_verified": True,
            },
        }
    facts = {
        "schema_version": 1,
        "actors": actors,
        "refresh": {
            "credential_changed": True,
            "invalid_credential_refused": True,
            "other_person_credential_refused": True,
        },
        "membership_control": {
            "revoke_operation_sha256": _sha("revoke"),
            "restore_operation_sha256": _sha("restore"),
            "revoked_membership_sha256": person_tool._membership_sha256(
                (("writer-role", "module-reader"), ("writer-role", "module-writer"))
            ),
            "restored_membership_sha256": person_tool._membership_sha256(
                (("writer-role", "module-reader"), ("writer-role", "module-writer"))
            ),
            "fresh_connection_denied": True,
            "existing_session_denied": True,
            "restoration_verified": True,
        },
        "expiry_control": {
            "operation_sha256": _sha("expire"),
            "mechanism": "provider-credential-expiry",
            "effective_at_unix": 1_900_000_000,
            "expired_connection_denied": True,
            "refreshed_connection_verified": True,
        },
        "state": {
            "before_sha256": _sha("state"),
            "after_sha256": _sha("state"),
            "unchanged": True,
            "sequence_allocations": {"comparison_count": 4, "sha256": _sha("sequence-deltas")},
        },
    }
    return target, authorization, provider, roles, facts


def _project(facts: dict[str, Any]) -> dict[str, Any]:
    target, authorization, provider, roles, _ = _inputs()
    return safe_person_observations(
        facts,
        target=target,
        authorization=authorization,
        provider_observation_sha256=provider,
        role_sha256_by_actor=roles,
    )


def test_person_projection_accepts_bound_mixed_identity_and_keeps_closed_shape() -> None:
    target, authorization, provider, roles, facts = _inputs()
    result = safe_person_observations(
        facts,
        target=target,
        authorization=authorization,
        provider_observation_sha256=provider,
        role_sha256_by_actor=roles,
    )
    assert result["actors"]["writer"]["before"]["subject_kind"] == "human"
    assert (
        result["actors"]["writer"]["after_refresh"]["credential_generation"]
        != result["actors"]["writer"]["before"]["credential_generation"]
    )
    assert set(result) == {
        "schema_version",
        "actors",
        "refresh",
        "membership_control",
        "expiry_control",
        "state",
    }
    assert "PRIVATE-TOKEN" not in json.dumps(result)


_PERSON_MUTATIONS: tuple[tuple[Callable[[dict[str, Any]], object], str], ...] = (
    (
        lambda facts: facts["actors"]["writer"]["before"].update(auth_profile="nonhuman-oauth"),
        "profile",
    ),
    (
        lambda facts: facts["actors"]["writer"]["before"].update(
            sql_role_sha256=_sha("other-role")
        ),
        "role",
    ),
    (
        lambda facts: facts["actors"]["writer"]["after_refresh"].update(
            subject_reference_sha256=_sha("other")
        ),
        "identity",
    ),
    (
        lambda facts: facts["actors"]["writer"]["after_refresh"].update(
            credential_generation=facts["actors"]["writer"]["before"]["credential_generation"]
        ),
        "generation",
    ),
    (
        lambda facts: facts["membership_control"].update(existing_session_denied=False),
        "membership",
    ),
    (
        lambda facts: facts["membership_control"].update(restored_membership_sha256=_sha("other")),
        "membership",
    ),
    (
        lambda facts: facts["refresh"].update(other_person_credential_refused=False),
        "refresh",
    ),
    (
        lambda facts: facts["expiry_control"].update(mechanism="native-role-valid-until"),
        "expiry",
    ),
    (
        lambda facts: facts["expiry_control"].update(effective_at_unix=1_899_999_999),
        "differs from observed writer credentials",
    ),
    (
        lambda facts: facts["actors"]["writer"]["after_refresh"].update(
            credential_expires_at=1_900_000_000
        ),
        "differs from observed writer credentials",
    ),
    (lambda facts: facts["state"].update(after_sha256=_sha("changed")), "state"),
    (
        lambda facts: facts["state"]["sequence_allocations"].update(comparison_count=True),
        "sequence allocation",
    ),
    (
        lambda facts: facts["actors"]["reader"]["before"].update(private_path="/private/token"),
        "shape",
    ),
    (
        lambda facts: facts["actors"]["writer"]["before"].update(token="PRIVATE-TOKEN"),
        "shape",
    ),
)


@pytest.mark.parametrize(("mutate", "message"), _PERSON_MUTATIONS)
def test_person_projection_rejects_unproven_or_private_facts(
    mutate: Callable[[dict[str, Any]], object], message: str
) -> None:
    _, _, _, _, facts = _inputs()
    candidate = copy.deepcopy(facts)
    mutate(candidate)
    with pytest.raises(ValueError, match=message):
        _project(candidate)


def test_context_free_receipt_projection_still_requires_human_writer_and_closed_facts() -> None:
    _, _, _, _, facts = _inputs()
    assert safe_person_observations(facts)["schema_version"] == 1
    candidate = copy.deepcopy(facts)
    candidate["actors"]["writer"]["before"]["auth_profile"] = "nonhuman-oauth"
    candidate["actors"]["writer"]["before"]["subject_kind"] = "nonhuman"
    candidate["actors"]["writer"]["after_refresh"]["auth_profile"] = "nonhuman-oauth"
    candidate["actors"]["writer"]["after_refresh"]["subject_kind"] = "nonhuman"
    with pytest.raises(ValueError, match="human writer"):
        safe_person_observations(candidate)


@pytest.mark.parametrize(
    ("allowed_cases", "allowed_operations", "expected"),
    [
        (
            [],
            ["read", "apply", "refresh", "revoke_owned_memberships", "expire_owned_login"],
            "case_not_authorized",
        ),
        *[
            (
                ["LB-PERSON"],
                [
                    operation
                    for operation in (
                        "read",
                        "apply",
                        "refresh",
                        "revoke_owned_memberships",
                        "expire_owned_login",
                    )
                    if operation != missing
                ],
                "required_operation_not_authorized",
            )
            for missing in (
                "read",
                "apply",
                "refresh",
                "revoke_owned_memberships",
                "expire_owned_login",
            )
        ],
    ],
)
def test_person_runner_refuses_before_any_fixture_or_connection_call(
    allowed_cases: list[str], allowed_operations: list[str], expected: str
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unapproved callback or connection was invoked")

    inputs = SimpleNamespace(
        authorization={"allowed_cases": allowed_cases, "allowed_operations": allowed_operations},
        target={},
    )
    result = person_tool.run_person_lifecycle(
        inputs=inputs,
        fixture_module=SimpleNamespace(__getattr__=forbidden),
        sources={"refresh_principal": forbidden},
        backend=forbidden,
        principals={},
        installed=None,
        baseline_observed={},
    )
    assert result["cases"] == [{"case": "LB-PERSON", "status": "blocked", "code": expected}]
    assert result["observed"] is None


def test_verified_writer_refresh_updates_only_the_private_shared_principal_context() -> None:
    principals = {"writer": Principal("human-role", "old-private-token")}
    person_tool._handoff_refreshed_writer(principals, Principal("human-role", "new-private-token"))
    assert principals["writer"].user == "human-role"
    assert principals["writer"].token == "new-private-token"
    assert "new-private-token" not in json.dumps(safe_person_observations(_inputs()[4]))


def test_held_connection_backend_is_public_and_restricted_to_exact_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from arras.adapters import truss
    from arras.core import Arras

    principal = Principal("writer-role", "held-token")
    held_connection = object()
    captured: dict[str, Any] = {}

    class Host:
        def session(self, requested: Principal) -> Principal:
            return requested

    host = Host()

    def create_backend(
        _name: str,
        source: Callable[[Principal], Any],
        _installing: Any,
        **_kwargs: Any,
    ) -> object:
        captured["source"] = source
        return object()

    monkeypatch.setattr(truss, "create_backend", create_backend)
    monkeypatch.setattr(Arras, "start", staticmethod(lambda *_args, **_kwargs: host))
    context: dict[str, Any] = {
        "inputs": SimpleNamespace(
            target={
                "resources": {
                    "module_access": {
                        "document_id": "arras-lakebase-qualification-v1",
                        "reader_role": "module-reader",
                        "writer_role": "module-writer",
                    },
                    "tolerated_grantees": ["installer-role"],
                }
            }
        ),
        "sources": {"installer_connection_source": object()},
        "principals": {"registrar": Principal("registrar-role", "admin-token")},
    }
    assert person_tool._held_connection_writer(context, principal, held_connection) == (
        host,
        principal,
    )
    with captured["source"](principal) as connection:
        assert connection is held_connection
    with pytest.raises(PermissionError):
        captured["source"](Principal("writer-role", "substituted-token"))


def test_successful_wrong_role_connection_does_not_count_as_credential_refusal() -> None:
    target = {"endpoint": {"host": "db.example", "port": 5432, "database": "db"}}

    class Connection:
        info = SimpleNamespace(
            host="db.example",
            port=5432,
            dbname="db",
            dsn_parameters={"sslmode": "verify-full", "sslrootcert": "/root.crt"},
        )
        pgconn = SimpleNamespace(ssl_in_use=True)

    @contextmanager
    def successful_source(_principal: Principal) -> Any:
        yield Connection()

    assert (
        person_tool._connection_identity_refused(
            {"person_connection_source": successful_source},
            Principal("writer-role", "other-person-token"),
            target,
        )
        is False
    )

    class AuthenticationFailure(Exception):
        sqlstate = "28P01"

    @contextmanager
    def refused_source(_principal: Principal) -> Any:
        raise AuthenticationFailure
        yield Connection()

    assert person_tool._connection_identity_refused(
        {"person_connection_source": refused_source},
        Principal("writer-role", "invalid-token"),
        target,
    )


def test_snapshot_comparison_retains_sequence_inventory_and_reports_counter_gaps() -> None:
    before = {
        "sha256": _sha("before"),
        "relations": (
            {"name": "probe_id_seq", "kind": "S", "columns": (), "sequence_state": (10, True)},
            {"name": "probe", "kind": "r", "rows": ("row",)},
        ),
        "roles": (),
    }
    after = {
        "sha256": _sha("after"),
        "relations": (
            {"name": "probe_id_seq", "kind": "S", "columns": (), "sequence_state": (11, True)},
            {"name": "probe", "kind": "r", "rows": ("row",)},
        ),
        "roles": (),
    }
    context: dict[str, Any] = {"sequence_deltas": []}
    approved = frozenset({"probe_id_seq"})
    assert person_tool._record_snapshot_pair(
        context, before, after, allowed_sequence_advances=approved
    )
    assert person_tool._sequence_delta_summary(context)["comparison_count"] == 1
    assert context["sequence_deltas"][0]["count"] == 1

    changed_row: dict[str, Any] = copy.deepcopy(after)
    changed_row["relations"] = (
        changed_row["relations"][0],
        {"name": "probe", "kind": "r", "rows": ("changed",)},
    )
    assert not person_tool._record_snapshot_pair(
        context, before, changed_row, allowed_sequence_advances=approved
    )


def test_snapshot_comparison_rejects_unapproved_sequence_advance() -> None:
    before = {
        "sha256": _sha("before"),
        "relations": ({"name": "unexpected_seq", "kind": "S", "sequence_state": (10, True)},),
    }
    after = {
        "sha256": _sha("after"),
        "relations": ({"name": "unexpected_seq", "kind": "S", "sequence_state": (11, True)},),
    }
    context: dict[str, Any] = {"sequence_deltas": []}
    assert not person_tool._record_snapshot_pair(
        context, before, after, allowed_sequence_advances=frozenset({"probe_id_seq"})
    )
    assert context["sequence_deltas"] == []


def test_snapshot_comparison_rejects_sequence_regression() -> None:
    before = {
        "sha256": _sha("before"),
        "relations": ({"name": "probe_id_seq", "kind": "S", "sequence_state": (11, True)},),
    }
    after = {
        "sha256": _sha("after"),
        "relations": ({"name": "probe_id_seq", "kind": "S", "sequence_state": (10, True)},),
    }
    assert not person_tool._record_snapshot_pair({"sequence_deltas": []}, before, after)


def test_validation_sequence_allowance_requires_actual_selected_artifact_evidence() -> None:
    artifacts = {
        "truss_version": person_tool._VALIDATION_ALLOCATOR_TRUSS_VERSION,
        "truss_wheel_sha256": person_tool._VALIDATION_ALLOCATOR_WHEEL_SHA256,
        "native_manifest_sha256": person_tool._VALIDATION_ALLOCATOR_NATIVE_SHA256,
        "migration_manifest_sha256": _sha("migrations"),
    }
    context: dict[str, Any] = {
        "inputs": SimpleNamespace(target={"expected": artifacts}),
        "baseline_observed": {"artifacts": dict(artifacts)},
    }
    assert person_tool._approved_validation_sequences(context) == frozenset(
        {
            "id_seq",
            "key_storage_row_seq",
            "journal_seq",
            "request_receipt_row_seq",
            "runtime_feed_reservation_seq",
            "runtime_object_transition_seq",
        }
    )
    context["baseline_observed"]["artifacts"]["truss_wheel_sha256"] = _sha("other-wheel")
    with pytest.raises(ValueError, match="selected Truss source"):
        person_tool._approved_validation_sequences(context)


@pytest.mark.parametrize("failure", [person_tool.PersonFailure("denied"), KeyboardInterrupt()])
@pytest.mark.parametrize("restore_failure", [False, True])
def test_membership_restoration_runs_when_revoke_or_denial_probe_raises(
    monkeypatch: pytest.MonkeyPatch, failure: BaseException, restore_failure: bool
) -> None:
    target = {
        "resources": {
            "module_access": {"reader_role": "module-reader", "writer_role": "module-writer"}
        }
    }
    principals = {"writer": Principal("writer-role", "private-token")}
    pairs = (("writer-role", "module-reader"), ("writer-role", "module-writer"))
    calls: list[str] = []

    class Fixture:
        def restore_owned_memberships(self, *, actor_label: str, memberships: Any) -> Any:
            assert actor_label == "writer"
            assert tuple(memberships) == pairs
            calls.append("restore")
            if restore_failure:
                raise RuntimeError("private restore error")
            return {"operation_sha256": _sha("restore"), "memberships": pairs}

    def fail_after_revoke(
        _context: Any,
        _host: Any,
        _writer: Any,
        _principal: Principal,
        _pairs: Any,
        mark_started: Callable[[], None],
    ) -> str:
        mark_started()
        raise failure

    def same_snapshot(_sources: Mapping[str, Any]) -> dict[str, Any]:
        return {"sha256": _sha("state"), "relations": []}

    def restored_memberships(
        _sources: Mapping[str, Any], requested: tuple[tuple[str, str], ...]
    ) -> dict[tuple[str, str], bool]:
        return {pair: True for pair in requested}

    monkeypatch.setattr(person_tool, "_native_snapshot", same_snapshot)
    monkeypatch.setattr(
        person_tool,
        "_observe_memberships",
        restored_memberships,
    )
    monkeypatch.setattr(person_tool, "_revoke_and_probe", fail_after_revoke)
    context = {
        "fixture_module": Fixture(),
        "inputs": SimpleNamespace(target=target),
        "sources": {},
        "principals": principals,
    }
    with pytest.raises(type(failure)) as raised:
        person_tool._person_membership_cycle(
            context, None, None, None, (_sha("state"), _sha("public"))
        )
    assert calls == ["restore"]
    if restore_failure:
        assert any("membership_state_verified=True" in note for note in raised.value.__notes__)


def test_observed_postcondition_violation_is_failed_not_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def contradiction(_context: Any) -> dict[str, bool]:
        return {"invalid_credential_refused": False}

    def should_not_continue(_context: Any, _facts: Any) -> Any:
        pytest.fail("the runner continued after an observed credential was accepted")

    def empty_facts(_context: dict[str, Any]) -> dict[str, Any]:
        return {}

    def same_snapshot(_sources: Any) -> dict[str, Any]:
        return {"sha256": _sha("state"), "relations": []}

    monkeypatch.setattr(person_tool, "_person_context_facts", empty_facts)
    monkeypatch.setattr(person_tool, "_native_snapshot", same_snapshot)
    monkeypatch.setattr(person_tool, "_person_wrong_credential_checks", contradiction)
    monkeypatch.setattr(person_tool, "_person_expiry_and_refresh", should_not_continue)
    result = person_tool._run_person_controls(sources={})
    assert result["cases"] == [
        {"case": "LB-PERSON", "status": "failed", "code": "credential_refusal_failed"}
    ]
