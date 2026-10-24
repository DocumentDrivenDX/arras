# SPDX-License-Identifier: MIT OR Apache-2.0
"""Authentication ordering at the generated action transport boundary."""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from typing import Any, cast

import pytest
from _pytest.logging import LogCaptureFixture

from arras import Arras, Principal, Refused
from arras.fakes import FakeAccess, MemoryStore


class _UnreadableInputs(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise AssertionError("request inputs must not be read before catalog authorization")

    def __iter__(self) -> Iterator[str]:
        raise AssertionError("request inputs must not be iterated before catalog authorization")

    def __len__(self) -> int:
        raise AssertionError("request inputs must not be measured before catalog authorization")


def test_expired_nonempty_token_refuses_before_request_inputs_are_consumed(
    caplog: LogCaptureFixture,
) -> None:
    from arras import telemetry

    caplog.set_level(logging.DEBUG)
    access = FakeAccess()
    person = access.grant("alice", "catalog", "read")
    backend = MemoryStore(access)
    arras = Arras.start({"memory": backend})
    access.expire(person.token)

    request: dict[str, object] = {
        "contract": "umf.access/1",
        "schema": "0" * 64,
        "kind": "validate",
        "action": "catalog.SetName",
        "inputs": _UnreadableInputs(),
    }
    response = arras.session(Principal(person.user, "stale-but-nonempty")).execute(request)

    assert response == {"schema": "0" * 64, "error": {"code": "DENIED"}}
    event = cast(
        Any,
        next(
            record
            for record in caplog.records
            if getattr(record, "arras_event", None) == "arras.execute"
        ),
    )
    assert event.arras_attrs["outcome"] == "refused"
    assert event.arras_attrs["reason"] == "denied"
    assert "stale-but-nonempty" not in str(event.arras_attrs)
    assert "arras.execute" in telemetry.EVENTS


def test_expired_token_does_not_compare_hostile_outer_keys() -> None:
    class EqualityTrap(str):
        enabled = False

        def __hash__(self) -> int:
            return hash("schema")

        def __eq__(self, other: object) -> bool:
            if self.enabled:
                raise AssertionError("outer key equality callback ran")
            return False

    access = FakeAccess()
    person = access.grant("alice", "catalog", "read")
    backend = MemoryStore(access)
    arras = Arras.start({"memory": backend})
    access.expire(person.token)
    key = EqualityTrap("foreign")
    request: dict[object, object] = {key: "value"}
    request["schema"] = "a" * 64
    key.enabled = True

    with pytest.raises(Refused):
        arras.session(Principal(person.user, "stale-but-nonempty")).execute(
            cast(Mapping[str, object], request)
        )


def test_negative_validation_response_marks_execute_refused(caplog: LogCaptureFixture) -> None:
    from arras import telemetry
    from arras._action_transport import _error_response  # pyright: ignore[reportPrivateUsage]

    caplog.set_level(logging.DEBUG)
    with telemetry.operation("arras.execute"):
        response = _error_response("a" * 64, "UNSUPPORTED")

    assert response == {"schema": "a" * 64, "error": {"code": "UNSUPPORTED"}}
    event = cast(
        Any,
        next(
            record
            for record in caplog.records
            if getattr(record, "arras_event", None) == "arras.execute"
        ),
    )
    assert event.arras_attrs["outcome"] == "refused"
    assert event.arras_attrs["reason"] == "unsupported"


def test_auth_refusal_does_not_echo_an_unvalidated_schema_value() -> None:
    access = FakeAccess()
    person = access.grant("alice", "catalog", "read")
    arras = Arras.start({"memory": MemoryStore(access)})
    access.expire(person.token)
    request: dict[str, object] = {
        "schema": "private-not-a-digest",
        "inputs": _UnreadableInputs(),
    }

    with pytest.raises(Refused):
        arras.session(Principal(person.user, "stale-but-nonempty")).execute(request)


def test_noop_set_receipt_serializes_as_committed_without_inventing_a_change() -> None:
    from arras._action_transport import apply_response
    from arras.actions import ActionInfo, InputSpec
    from arras.results import Receipt

    action = ActionInfo(
        "catalog.SetName", "", (InputSpec("entity", "catalog.UseCase", "ref", "one"),), (), ()
    )
    receipt = Receipt("catalog.SetName", (), 0, 0, 0, 0, 0, "arras-set-opaque")

    response = apply_response(
        "a" * 64,
        action,
        {"entity": {"UseCase.code": "use-1"}},
        receipt,
    )

    assert response == {
        "schema": "a" * 64,
        "status": "committed",
        "created": [],
        "changed": [],
        "counts": {"created": 0, "updated": 0, "deleted": 0, "linked": 0, "unlinked": 0},
        "consistency_token": "arras-set-opaque",
    }


def test_declared_positions_authorize_read_before_resolving_any_token() -> None:
    import hashlib
    from types import SimpleNamespace
    from typing import cast

    from arras.fakes_state import State
    from arras.model import ModuleInfo

    access = FakeAccess()
    reader = access.grant("alice", "one", "read")
    outsider = access.grant("bob", "other", "read")
    store = MemoryStore(access, action_profile="arras-umf-set/1")
    store.modules["one"] = cast(ModuleInfo, SimpleNamespace(metadata_profile="arras-umf-set/1"))
    store.documents["one"] = b"source"
    store.action_source_owners["one"] = "alice"
    store.state = State()
    store.state.declared_tokens["arras-set-known"] = (
        "one",
        "sha256:" + hashlib.sha256(b"source").hexdigest(),
        0,
    )

    assert store.reached(reader, "arras-set-known") is True
    assert store.reached(reader, "arras-set-foreign") is False
    with pytest.raises(Refused) as known:
        store.reached(outsider, "arras-set-known")
    with pytest.raises(Refused) as unknown:
        store.reached(outsider, "arras-set-foreign")
    assert known.value.reason == unknown.value.reason == "no_access"


def test_action_transport_snapshots_only_bounded_string_carriers() -> None:
    from arras import Invalid
    from arras._action_transport import snapshot_request

    inputs: dict[str, object] = {"entity": {"catalog.UseCase.code": "one"}, "name": "First"}
    request: dict[str, object] = {
        "contract": "umf.access/1",
        "schema": "a" * 64,
        "kind": "apply",
        "action": "catalog.SetName",
        "inputs": inputs,
        "idempotency_key": "request-1",
    }
    snapshot = snapshot_request(request)
    inputs["name"] = "Changed after snapshot"
    assert snapshot["inputs"] == {"entity": {"catalog.UseCase.code": "one"}, "name": "First"}

    request["inputs"] = {f"input-{index}": "x" for index in range(3)}
    with pytest.raises(Invalid):
        snapshot_request(request)


def test_known_refusals_are_matching_schema_without_driver_prose() -> None:
    from arras._action_transport import _error_for  # pyright: ignore[reportPrivateUsage]
    from arras.actions import ActionInfo, PreconditionDecl
    from arras.errors import Conflict, Failure, Invalid, PreconditionFailed, Unsupported, Violation

    assert _error_for("a" * 64, Unsupported("raw sdk detail", ["secret detail"])) == {
        "schema": "a" * 64,
        "error": {"code": "UNSUPPORTED"},
    }
    assert _error_for("b" * 64, Invalid([Violation("schema", "schema_mismatch", "detail")])) == {
        "schema": "b" * 64,
        "error": {"code": "SCHEMA_MISMATCH"},
    }
    action = ActionInfo(
        "catalog.SetName",
        "",
        (),
        (PreconditionDecl("current", "", "exists", {}),),
        (),
    )
    assert _error_for(
        "c" * 64, PreconditionFailed([Failure("current", "private detail")]), action
    ) == {"schema": "c" * 64, "error": {"code": "PRECONDITION_FAILED", "precondition": "current"}}
    assert _error_for("d" * 64, Conflict("revision", "private detail")) == {
        "schema": "d" * 64,
        "error": {"code": "CONFLICT"},
    }


@pytest.mark.parametrize("member", ["contract", "schema", "kind", "action", "idempotency_key"])
def test_exact_wire_scalar_types_are_checked_without_invoking_value_equality(member: str) -> None:
    from arras import Invalid
    from arras._action_transport import request_kind

    class EqualityTrap:
        def __eq__(self, other: object) -> bool:
            raise AssertionError("untrusted equality callback ran")

    request: dict[str, object] = {
        "contract": "umf.access/1",
        "schema": "a" * 64,
        "kind": "apply",
        "action": "catalog.SetName",
        "inputs": {},
        "idempotency_key": "request-1",
    }
    request[member] = EqualityTrap()
    with pytest.raises(Invalid):
        request_kind(request)
