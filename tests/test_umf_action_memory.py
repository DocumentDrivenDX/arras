# SPDX-License-Identifier: MIT OR Apache-2.0
"""Controlled bridge-double controls for the opted-in memory host path."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, NoReturn, cast

import pytest

from arras import Arras, Conflict, Invalid, Principal, Refused, Unsupported, Violation, _umf_actions
from arras._action_types import AdmittedRecord, AdmittedSet, PreparedSetModule, SetBinding
from arras.actions import ActionInfo, InputSpec, Ref
from arras.fakes import FakeAccess, MemoryReplica, MemoryStore
from arras.fakes_state import Entity
from arras.model import UNPLACED, EntityTypeInfo, ModuleInfo, Placement, PropertyInfo
from arras.results import Receipt, Validation
from arras.testing import InMemory
from arras.types import Revision

SOURCE = b"controlled action bridge fixture"
MODULE = "example"
RECORD = "example.Probe"
ACTION = "example.write_item"
KEY_FIELD = "item_id"
VALUE_FIELD = "label_value"


def _store(world: InMemory) -> MemoryStore:
    return cast(MemoryStore, cast(Any, world)._store)


def _access(world: InMemory) -> FakeAccess:
    return cast(FakeAccess, cast(Any, world)._access)


def _replica(world: InMemory) -> MemoryReplica:
    return cast(MemoryReplica, cast(Any, world)._replica)


def _runtime_available() -> bool:
    return True


def _record_prepare_call(called: list[bool]) -> Callable[[bytes], PreparedSetModule]:
    def record(source: bytes) -> PreparedSetModule:
        called.append(True)
        return _prepared(source)

    return record


def _prepare_second(source: bytes) -> PreparedSetModule:
    return _prepared(source, "other")


def _admit_initial(prepared: PreparedSetModule, row: Mapping[str, object]) -> AdmittedRecord:
    del prepared, row
    return AdmittedRecord(Ref(RECORD, "probe-1"), {KEY_FIELD: "probe-1", VALUE_FIELD: "Initial"})


def _reject_record(prepared: PreparedSetModule, row: Mapping[str, object]) -> NoReturn:
    del prepared, row
    raise Invalid([Violation("record", "invalid", "safe")])


def _materialize_changed(prepared: PreparedSetModule, request: Mapping[str, object]) -> AdmittedSet:
    del prepared, request
    return AdmittedSet(Ref(RECORD, "probe-1"), {VALUE_FIELD: "Changed"}, "a" * 64)


def _validate_values(prepared: PreparedSetModule, values: Mapping[str, str]) -> None:
    del prepared, values


def _prepared(source: bytes = SOURCE, module_name: str = MODULE) -> PreparedSetModule:
    record_name = f"{module_name}.Probe"
    action_name = f"{module_name}.write_item"
    record = EntityTypeInfo(
        record_name,
        KEY_FIELD,
        (
            PropertyInfo(KEY_FIELD, "string", True, "one"),
            PropertyInfo(VALUE_FIELD, "string", True, "one"),
        ),
    )
    module = ModuleInfo(
        module_name,
        UNPLACED,
        Revision(),
        (record,),
        actions=(
            ActionInfo(
                action_name,
                "",
                (
                    InputSpec("item", record_name, "ref", "one"),
                    InputSpec("label", "string", "scalar", "one"),
                ),
                (),
                (),
            ),
        ),
        metadata_profile="arras-umf-set/1",
    )
    digest = hashlib.sha256(source).hexdigest()
    return PreparedSetModule(
        source,
        digest,
        module,
        "controlled-document",
        f"sha256:{digest}",
        module_name,
        "Probe",
        action_name,
        "write_item",
        KEY_FIELD,
        KEY_FIELD,
        "item",
        (SetBinding("label", VALUE_FIELD, VALUE_FIELD),),
        ("write_frame",),
        "arras.module-write/1",
        ("write_frame",),
    )


def _enable_controlled_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_umf_actions, "runtime_available", _runtime_available)
    monkeypatch.setattr(_umf_actions, "prepare", _prepared)


def _registered_world(monkeypatch: pytest.MonkeyPatch) -> InMemory:
    _enable_controlled_bridge(monkeypatch)
    world = InMemory(action_profile="arras-umf-set/1")
    assert set(world.backends) == {"memory"}
    world.register(SOURCE)
    return world


def _lock_is_held_elsewhere(lock: Any) -> bool:
    acquired = lock.acquire(blocking=False)
    if acquired:
        lock.release()
    return not acquired


def _release_and_join(
    release: threading.Event,
    action_thread: threading.Thread,
    expiry_thread: threading.Thread | None,
) -> None:
    release.set()
    action_thread.join(timeout=5)
    if expiry_thread is not None:
        expiry_thread.join(timeout=5)


def _run_action_expiration_race(
    world: InMemory,
    store: MemoryStore,
    writer: Principal,
    request: Mapping[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[Mapping[str, object]], list[BaseException], list[bool]]:
    validation_entered = threading.Event()
    release_validation = threading.Event()
    expiry_started = threading.Event()
    expiry_finished = threading.Event()
    action_results: list[Mapping[str, object]] = []
    action_errors: list[BaseException] = []
    action_admissions: list[bool] = []
    original_expire = store.access.expire

    def materialize(prepared: PreparedSetModule, raw: Mapping[str, object]) -> AdmittedSet:
        action_admissions.append(True)
        return _materialize_changed(prepared, raw)

    def block_validation(prepared: PreparedSetModule, values: Mapping[str, str]) -> None:
        validation_entered.set()
        if not release_validation.wait(timeout=5):
            raise AssertionError("test did not release action validation")
        _validate_values(prepared, values)

    def expire(token: str) -> None:
        expiry_started.set()
        original_expire(token)
        expiry_finished.set()

    monkeypatch.setattr(_umf_actions, "materialize", materialize)
    monkeypatch.setattr(_umf_actions, "validate_candidate", block_validation)
    monkeypatch.setattr(store.access, "expire", expire)

    def perform_action() -> None:
        try:
            action_results.append(world.arras.session(writer).execute(request))
        except BaseException as exc:
            action_errors.append(exc)

    action_thread = threading.Thread(target=perform_action)
    expiry_thread: threading.Thread | None = None
    try:
        action_thread.start()
        assert validation_entered.wait(timeout=5)
        assert _lock_is_held_elsewhere(store.access.serialization_lock())
        expiry_thread = threading.Thread(target=store.access.expire, args=(writer.token,))
        expiry_thread.start()
        assert expiry_started.wait(timeout=5)
        assert not expiry_finished.wait(timeout=0.05)
    finally:
        _release_and_join(release_validation, action_thread, expiry_thread)

    assert (
        not action_thread.is_alive() and expiry_thread is not None and not expiry_thread.is_alive()
    )
    return action_results, action_errors, action_admissions


def test_candidate_store_registration_is_byte_owned_and_store_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _registered_world(monkeypatch)
    held = _store(world).documents[MODULE]
    owner = _store(world).action_source_owners[MODULE]
    assert owner == world.admin.user
    assert held == SOURCE

    repeated = world.arras.session(world.admin).registry().register(SOURCE)
    assert repeated.changed is False
    assert _store(world).documents[MODULE] == SOURCE

    other = _access(world).grant("other", MODULE, "schema", admin=True)
    other_host = Arras.start(
        {"memory": _store(world)},
        admin=other,
        default_placement=Placement("memory"),
        metadata_profile="arras-umf-set/1",
    )
    with pytest.raises(Refused):
        other_host.session(other).registry().register(SOURCE)
    called: list[bool] = []
    monkeypatch.setattr(_umf_actions, "prepare", _record_prepare_call(called))
    with pytest.raises(Refused):
        _store(world).register(
            other,
            SOURCE + b" malformed replacement",
            _store(world).modules[MODULE],
            unknown_endpoint="reject",
            expected_revision=Revision({"memory": 999}),
        )
    assert called == []
    assert _store(world).action_source_owners[MODULE] == world.admin.user
    monkeypatch.setattr(_umf_actions, "prepare", _prepared)

    with pytest.raises(Unsupported):
        world.arras.session(world.admin).registry().register(SOURCE + b" ")
    assert _store(world).documents[MODULE] == SOURCE


def test_selected_store_advertises_only_the_runtime_it_can_accept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = FakeAccess()
    selected = MemoryStore(access, action_profile="arras-umf-set/1")
    legacy = MemoryStore(access)
    monkeypatch.setattr(_umf_actions, "runtime_available", lambda: False)

    unavailable = selected.describe()
    assert unavailable.metadata_profiles == ()
    assert unavailable.action_profiles == ()
    assert legacy.describe().metadata_profiles == ("legacy-arras/1", "umf-core-metadata/1")

    monkeypatch.setattr(_umf_actions, "runtime_available", _runtime_available)
    available = selected.describe()
    assert available.metadata_profiles == ("arras-umf-set/1",)
    assert available.action_profiles == ("arras-umf-set/1",)


def test_rejected_candidate_seed_shape_does_not_read_the_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _registered_world(monkeypatch)
    clock_calls: list[bool] = []

    def clock() -> datetime:
        clock_calls.append(True)
        return datetime.now(UTC)

    _store(world).clock = clock
    with pytest.raises(Unsupported):
        world.import_records(
            MODULE,
            [
                {"type": "Probe", "key": "one", "properties": {VALUE_FIELD: "A"}},
                {"type": "Probe", "key": "two", "properties": {VALUE_FIELD: "B"}},
            ],
        )
    assert clock_calls == []


def test_malformed_current_action_capability_stops_before_provider_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    world = _registered_world(monkeypatch)
    store = _store(world)
    writer = world.person("writer", MODULE, "read", "write")
    base = store.describe()
    monkeypatch.setattr(
        store,
        "describe",
        lambda: replace(base, action_profiles=cast(Any, "arras-umf-set/1")),
    )
    dispatched: list[bool] = []

    def apply(principal: object, module: str, request: Mapping[str, object]) -> object:
        del principal, module, request
        dispatched.append(True)
        return object()

    monkeypatch.setattr(store, "apply_declared_action", apply)
    request: dict[str, object] = {
        "contract": "umf.access/1",
        "schema": hashlib.sha256(SOURCE).hexdigest(),
        "kind": "apply",
        "action": ACTION,
        "inputs": {"item": {KEY_FIELD: "probe-1"}, "label": "Changed"},
        "idempotency_key": "malformed-capability",
    }

    response = world.arras.session(writer).execute(request)

    assert response == {"schema": request["schema"], "error": {"code": "UNSUPPORTED"}}
    assert dispatched == []


def test_candidate_store_rejects_legacy_mixed_module_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _registered_world(monkeypatch)
    other_source = b"another controlled module"
    second = _prepared(other_source, "other")
    second_module = second.module.__class__(
        second.module.name,
        Placement("memory"),
        second.module.revision,
        second.module.entity_types,
        actions=second.module.actions,
        metadata_profile="arras-umf-set/1",
    )
    monkeypatch.setattr(_umf_actions, "prepare", _prepare_second)
    with pytest.raises(Unsupported):
        _store(world).register(
            world.admin,
            other_source,
            second_module,
            unknown_endpoint="reject",
        )
    assert set(_store(world).documents) == {MODULE}


def test_candidate_profile_refuses_legacy_write_routes_before_any_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from arras.actions import Plan

    world = _registered_world(monkeypatch)
    store = _store(world)
    writer = world.person("writer", MODULE, "read", "write")
    session = world.arras.session(writer)
    inputs: dict[str, object] = {
        "item": {KEY_FIELD: "probe-1"},
        "label": "Changed",
    }
    plan = Plan(ACTION, (), ())
    state = store.state
    clock_calls: list[bool] = []
    store.clock = lambda: (clock_calls.append(True), datetime.now(UTC))[1]
    provider_calls: list[bool] = []

    def record_dispatch(
        principal: Principal, module: str, request: Mapping[str, object]
    ) -> Receipt | Validation:
        del principal, module, request
        provider_calls.append(True)
        raise AssertionError("legacy write path must not dispatch the declared action")

    monkeypatch.setattr(store, "apply_declared_action", record_dispatch)
    operations: tuple[Callable[[], object], ...] = (
        lambda: session.validate(ACTION, inputs),
        lambda: session.invoke(ACTION, inputs),
        lambda: session.invoke_batch(ACTION, [inputs]),
        lambda: store.apply(writer, plan, idempotency_key=None, dry_run=True),
        lambda: store.apply(writer, plan, idempotency_key=None, dry_run=False),
        lambda: store.apply_batch(writer, [plan], atomic=False, idempotency_key=None),
    )

    for operation in operations:
        with pytest.raises(Unsupported):
            operation()

    assert store.state is state
    assert store.state.seq == 0
    assert clock_calls == []
    assert provider_calls == []


def test_public_admin_import_is_officially_admitted_and_atomic_on_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _registered_world(monkeypatch)
    monkeypatch.setattr(_umf_actions, "admit_record", _admit_initial)
    result = world.import_records(
        MODULE,
        [{"type": "Probe", "key": "probe-1", "properties": {VALUE_FIELD: "Initial"}}],
    )
    assert result.created == 1 and result.skipped == 0 and not result.rejected
    entity = _store(world).state.entities[Ref(RECORD, "probe-1")]
    assert entity.props == {KEY_FIELD: "probe-1", VALUE_FIELD: "Initial"}

    before = _store(world).state
    monkeypatch.setattr(_umf_actions, "admit_record", _reject_record)
    with pytest.raises(Invalid):
        world.import_records(
            MODULE,
            [{"type": "Probe", "key": "probe-2", "properties": {VALUE_FIELD: "Bad"}}],
        )
    assert _store(world).state is before


def test_candidate_action_refuses_extra_stored_properties_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _registered_world(monkeypatch)
    entity_ref = Ref(RECORD, "probe-1")
    _store(world).state.entities[entity_ref] = Entity(
        {KEY_FIELD: entity_ref.key, VALUE_FIELD: "Initial", "unexpected": "value"},
        1,
        "admin",
        datetime.now(UTC),
        "admin",
        datetime.now(UTC),
    )
    writer = world.person("writer", MODULE, "read", "write")
    monkeypatch.setattr(_umf_actions, "materialize", _materialize_changed)
    monkeypatch.setattr(_umf_actions, "validate_candidate", _validate_values)

    before = _store(world).state
    request: dict[str, object] = {
        "contract": "umf.access/1",
        "schema": hashlib.sha256(SOURCE).hexdigest(),
        "kind": "apply",
        "action": ACTION,
        "inputs": {"item": {KEY_FIELD: entity_ref.key}, "label": "Changed"},
        "idempotency_key": "extra-property",
    }
    response = world.arras.session(writer).execute(request)
    assert response == {
        "schema": hashlib.sha256(SOURCE).hexdigest(),
        "error": {"code": "UNSUPPORTED"},
    }
    assert _store(world).state is before


def test_provider_refusals_are_acknowledged_but_postpublish_uncertainty_is_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from arras.results import Receipt, RefVersion

    world = _registered_world(monkeypatch)
    store = _store(world)
    writer = world.person("writer", MODULE, "read", "write")
    request: dict[str, object] = {
        "contract": "umf.access/1",
        "schema": hashlib.sha256(SOURCE).hexdigest(),
        "kind": "apply",
        "action": ACTION,
        "inputs": {"item": {KEY_FIELD: "probe-1"}, "label": "Changed"},
        "idempotency_key": "known-refusal",
    }

    def refuse(principal: object, module: str, raw_request: Mapping[str, object]) -> Receipt:
        del principal, module, raw_request
        raise Invalid([Violation("schema", "schema_mismatch", "private source detail")])

    monkeypatch.setattr(store, "apply_declared_action", refuse)
    response = world.arras.session(writer).execute(request)
    assert response == {"schema": request["schema"], "error": {"code": "SCHEMA_MISMATCH"}}
    assert "private source detail" not in repr(response)

    before = store.state.seq

    def published_then_lost(
        principal: object, module: str, raw_request: Mapping[str, object]
    ) -> Receipt:
        del principal, module, raw_request
        store.state.seq += 1
        raise RuntimeError("post-publish outcome is uncertain")

    monkeypatch.setattr(store, "apply_declared_action", published_then_lost)
    with pytest.raises(RuntimeError, match="post-publish outcome is uncertain"):
        world.arras.session(writer).execute(request)
    assert store.state.seq == before + 1

    def malformed_receipt(
        principal: object, module: str, raw_request: Mapping[str, object]
    ) -> Receipt:
        del principal, module, raw_request
        store.state.seq += 1
        return Receipt("wrong.action", (RefVersion(RECORD, "probe-1", 1),), 0, 1, 0, 0, 0, "")

    monkeypatch.setattr(store, "apply_declared_action", malformed_receipt)
    with pytest.raises(Unsupported, match="action receipt shape"):
        world.arras.session(writer).execute(request)
    assert store.state.seq == before + 2


def test_work_copy_failure_before_publish_keeps_rows_tokens_and_replays_atomic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _registered_world(monkeypatch)
    store = _store(world)
    monkeypatch.setattr(_umf_actions, "admit_record", _admit_initial)
    world.import_records(
        MODULE,
        [{"type": "Probe", "key": "probe-1", "properties": {VALUE_FIELD: "Initial"}}],
    )
    writer = world.person("writer", MODULE, "read", "write")
    monkeypatch.setattr(_umf_actions, "materialize", _materialize_changed)
    monkeypatch.setattr(_umf_actions, "validate_candidate", _validate_values)
    request: dict[str, object] = {
        "contract": "umf.access/1",
        "schema": hashlib.sha256(SOURCE).hexdigest(),
        "kind": "apply",
        "action": ACTION,
        "inputs": {"item": {KEY_FIELD: "probe-1"}, "label": "Changed"},
        "idempotency_key": "before-publish-fault",
    }
    before = store.state
    before_entity = dict(before.entities[Ref(RECORD, "probe-1")].props)
    before_tokens = dict(before.declared_tokens)
    before_replays = dict(before.declared_replays)
    saw_mutated_work = False

    def fail_after_work_mutation(work: Any) -> str:
        nonlocal saw_mutated_work
        entity = work.entities[Ref(RECORD, "probe-1")]
        assert entity.props[VALUE_FIELD] == "Changed"
        assert work.seq == before.seq + 1
        saw_mutated_work = True
        raise RuntimeError("injected prepublication failure")

    monkeypatch.setattr(store, "_new_declared_token", fail_after_work_mutation)
    with pytest.raises(RuntimeError, match="injected prepublication failure"):
        world.arras.session(writer).execute(request)

    assert saw_mutated_work
    assert store.state is before
    assert before.entities[Ref(RECORD, "probe-1")].props == before_entity
    assert store.state.declared_tokens == before_tokens
    assert store.state.declared_replays == before_replays
    assert store.state.seq == 1


def test_expiration_waits_for_action_lock_then_denies_replay_before_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _registered_world(monkeypatch)
    store = _store(world)
    monkeypatch.setattr(_umf_actions, "admit_record", _admit_initial)
    world.import_records(
        MODULE,
        [{"type": "Probe", "key": "probe-1", "properties": {VALUE_FIELD: "Initial"}}],
    )
    writer = world.person("writer", MODULE, "read", "write")
    request: dict[str, object] = {
        "contract": "umf.access/1",
        "schema": hashlib.sha256(SOURCE).hexdigest(),
        "kind": "apply",
        "action": ACTION,
        "inputs": {"item": {KEY_FIELD: "probe-1"}, "label": "Changed"},
        "idempotency_key": "grant-race",
    }
    action_results, action_errors, action_admissions = _run_action_expiration_race(
        world, store, writer, request, monkeypatch
    )
    assert action_errors == []
    assert len(action_results) == 1
    assert action_results[0]["status"] == "committed"
    committed_state = store.state
    assert committed_state.seq == 2
    assert len(action_admissions) == 1
    assert world.arras.session(writer).execute(request) == {
        "schema": request["schema"],
        "error": {"code": "DENIED"},
    }
    assert store.state is committed_state
    assert store.state.seq == 2
    assert len(action_admissions) == 1


@pytest.mark.parametrize("key", ["", "probe/1", "é" * 4, "x" * 129])
def test_declared_set_rejects_keys_outside_existing_physical_key_carrier(
    key: str,
) -> None:
    from arras.fakes_actions import DeclaredActions

    store = cast(DeclaredActions, object.__new__(MemoryStore))
    with pytest.raises(Unsupported):
        cast(Any, store)._check_admitted_set(
            _prepared(), AdmittedSet(Ref(RECORD, key), {VALUE_FIELD: "Value"}, "a" * 64)
        )


def test_opted_in_inmemory_sync_refuses_before_feeding(monkeypatch: pytest.MonkeyPatch) -> None:
    world = _registered_world(monkeypatch)
    fed: list[bool] = []
    monkeypatch.setattr(_replica(world), "feed", lambda: fed.append(True))

    with pytest.raises(Unsupported):
        world.sync()

    assert fed == []
    assert set(world.backends) == {"memory"}


def test_candidate_provider_preserves_revision_cas_and_unknown_endpoint_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _registered_world(monkeypatch)
    current = _store(world).modules[MODULE].revision
    before = _store(world).documents[MODULE]
    with pytest.raises(Conflict):
        _store(world).register(
            world.admin,
            SOURCE,
            _store(world).modules[MODULE],
            unknown_endpoint="reject",
            expected_revision=Revision({"memory": 999}),
        )
    with pytest.raises(Invalid):
        _store(world).register(
            world.admin,
            SOURCE,
            _store(world).modules[MODULE],
            unknown_endpoint="discover",
        )
    assert _store(world).modules[MODULE].revision == current
    assert _store(world).documents[MODULE] == before


@pytest.mark.parametrize("bad_profile", ["arras-umf-set/1 ", object()])
def test_public_candidate_profile_rejects_noncanonical_carrier_without_equality(
    bad_profile: object,
) -> None:
    class EqualityTrap(str):
        def __eq__(self, other: object) -> bool:
            raise AssertionError("profile equality callback ran")

    hostile = EqualityTrap("arras-umf-set/1") if isinstance(bad_profile, str) else bad_profile
    with pytest.raises(ValueError, match="unsupported"):
        InMemory(action_profile=cast(Any, hostile))
    with pytest.raises(ValueError, match="unsupported"):
        MemoryStore(FakeAccess(), action_profile=cast(Any, hostile))
