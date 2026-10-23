# SPDX-License-Identifier: MIT OR Apache-2.0
"""The memory backend's explicit metadata-only profile behavior."""

from __future__ import annotations

import copy
import importlib.util
import os
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import overload

import pytest

from arras import Arras, Placement
from arras.actions import Plan
from arras.errors import Invalid, Refused, Unsupported
from arras.fakes import FakeAccess, MemoryReplica, MemoryStore
from arras.model import ModuleInfo
from arras.policy import PolicyBackend, PolicyDecision
from arras.results import BackendInfo, BatchReceipt, Receipt
from arras.types import Principal, Statement
from arras.umf_admission import project_document

SOURCE = Path(__file__).parent / "fixtures/umf-core-metadata/primary-string-record.json"
DOCUMENT = SOURCE.read_bytes()
PROFILE = "umf-core-metadata/1"


@pytest.fixture(scope="module")
def metadata_module() -> ModuleInfo:
    if importlib.util.find_spec("umf") is None:
        if os.environ.get("ARRAS_REQUIRE_UMF") == "1":
            pytest.fail("ARRAS_REQUIRE_UMF=1 but the selected UMF engine is unavailable")
        pytest.skip("install the optional arras[umf] dependency for metadata-profile tests")
    projection = project_document(DOCUMENT)
    assert projection.supported and projection.module is not None
    return projection.module


class _Clock:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return datetime(2026, 10, 22, tzinfo=UTC)


class _GuardedPlans(Sequence[Plan]):
    """Permit the first plan only; every attempt to inspect the tail is a test failure."""

    def __init__(self, first: Plan) -> None:
        self.first = first
        self.reads: list[int] = []

    def __len__(self) -> int:
        return 2

    @overload
    def __getitem__(self, index: int) -> Plan: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[Plan]: ...

    def __getitem__(self, index: int | slice) -> Plan | Sequence[Plan]:
        if not isinstance(index, int):
            raise AssertionError("metadata-only batch inspected a slice of plans")
        self.reads.append(index)
        if index != 0:
            raise AssertionError("metadata-only batch inspected a later plan")
        return self.first

    def __iter__(self) -> Iterator[Plan]:
        raise AssertionError("metadata-only batch iterated its plans")


class _GuardedRecords(Sequence[Mapping[str, object]]):
    def __len__(self) -> int:
        return 1

    @overload
    def __getitem__(self, index: int) -> Mapping[str, object]: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[Mapping[str, object]]: ...

    def __getitem__(
        self, index: int | slice
    ) -> Mapping[str, object] | Sequence[Mapping[str, object]]:
        raise AssertionError(f"metadata-only import inspected record index {index}")

    def __iter__(self) -> Iterator[Mapping[str, object]]:
        raise AssertionError("metadata-only import iterated records")


def _world(module: ModuleInfo) -> tuple[MemoryStore, FakeAccess, Principal, Principal, _Clock]:
    access = FakeAccess()
    clock = _Clock()
    store = MemoryStore(access, "memory", clock)
    writer = access.grant("writer", "m", "read", "write", "schema", admin=True)
    reader = access.grant("reader", "m", "read")
    store.register(writer, DOCUMENT, module, unknown_endpoint="reject")
    clock.calls = 0
    return store, access, writer, reader, clock


def _snapshot(store: MemoryStore, clock: _Clock) -> tuple[object, ...]:
    return (
        copy.deepcopy(store.state),
        store.position(),
        dict(store.modules),
        dict(store.documents),
        store.catalog_revision,
        dict(store.origin_actor),
        copy.deepcopy(store._journal),  # pyright: ignore[reportPrivateUsage]
        clock.calls,
    )


def test_memory_advertises_profile_and_keeps_registration_and_empty_reads(
    metadata_module: ModuleInfo,
) -> None:
    store, _, writer, reader, _ = _world(metadata_module)

    info = store.describe()
    assert info.metadata_profiles == ("legacy-arras/1", PROFILE)
    assert info.capabilities["m.Order"].mutable is False
    assert store.document(reader, "m").text.encode("utf-8") == DOCUMENT
    answer = store.query(
        reader,
        "m",
        Statement('SELECT o.id FROM m."Order" o ORDER BY o.id LIMIT 5'),
        limit=5,
    )
    assert answer.rows == ()
    assert store.modules["m"].metadata_profile == PROFILE

    replica_access = FakeAccess()
    replica_reader = replica_access.grant("replica-reader", "m", "read")
    replica = MemoryReplica(store, replica_access, clock=_Clock())
    replica.feed()
    replica_info = replica.describe()
    assert replica_info.metadata_profiles == ("legacy-arras/1", PROFILE)
    assert replica_info.capabilities["m.Order"].mutable is False
    assert replica.modules["m"].metadata_profile == PROFILE
    assert (
        replica.query(
            replica_reader,
            "m",
            Statement('SELECT o.id FROM m."Order" o ORDER BY o.id LIMIT 5'),
            limit=5,
        ).rows
        == ()
    )

    wrapped = PolicyBackend(store, lambda request: PolicyDecision(True))
    assert wrapped.describe().metadata_profiles == info.metadata_profiles
    assert store.access.authenticated(writer)


def test_public_host_registers_core_metadata_and_reads_original_bytes(
    metadata_module: ModuleInfo,
) -> None:
    access = FakeAccess()
    admin = access.grant("admin", "m", "read", "write", "schema", admin=True)
    reader = access.grant("reader", "m", "read")
    store = MemoryStore(access, "primary")
    host = Arras.start(
        {"primary": store},
        admin=admin,
        default_placement=Placement("primary"),
        metadata_profile=PROFILE,
    )

    registration = host.session(admin).registry().register(DOCUMENT)
    assert registration.module == "m"
    read_session = host.session(reader)
    assert read_session.document("m").text.encode("utf-8") == DOCUMENT
    [description] = read_session.describe("m")
    assert description.metadata_profile == PROFILE
    order = description.entity_type("Order")
    assert order is not None
    assert order.capabilities["primary"].mutable is False
    assert read_session.query("m", 'SELECT o.id FROM m."Order" o ORDER BY o.id LIMIT 5').rows == ()


@pytest.mark.parametrize("dry_run", [False, True])
def test_apply_refuses_metadata_only_after_write_auth_and_before_replay_or_effects(
    dry_run: bool, metadata_module: ModuleInfo
) -> None:
    store, _, writer, reader, clock = _world(metadata_module)
    plan = Plan("m.Create", (), ())
    key = "cached"
    digest = store._digest([plan])  # pyright: ignore[reportPrivateUsage]
    store._journal[(plan.action, key)] = (  # pyright: ignore[reportPrivateUsage]
        digest,
        Receipt(plan.action, (), 0, 0, 0, 0, 0, "cached-token"),
    )
    before = _snapshot(store, clock)

    with pytest.raises(Unsupported, match="metadata-only profile"):
        store.apply(writer, plan, idempotency_key=key, dry_run=dry_run)
    assert _snapshot(store, clock) == before

    with pytest.raises(Refused):
        store.apply(reader, plan, idempotency_key=key, dry_run=dry_run)
    assert _snapshot(store, clock) == before


@pytest.mark.parametrize("atomic", [False, True])
def test_batch_refuses_before_replay_or_inspecting_any_later_plan(
    atomic: bool, metadata_module: ModuleInfo
) -> None:
    store, _, writer, reader, clock = _world(metadata_module)
    plan = Plan("m.Create", (), ())
    sequence = _GuardedPlans(plan)
    key = "cached-batch"
    digest = store._digest([plan, plan])  # pyright: ignore[reportPrivateUsage]
    store._journal[("m.Create#atomic", key)] = (  # pyright: ignore[reportPrivateUsage]
        digest,
        BatchReceipt("m.Create", True, (), 0, 0, None),
    )
    before = _snapshot(store, clock)

    with pytest.raises(Unsupported, match="metadata-only profile"):
        store.apply_batch(writer, sequence, atomic=atomic, idempotency_key=key)
    assert sequence.reads == [0]
    assert _snapshot(store, clock) == before

    unauthorized = _GuardedPlans(plan)
    with pytest.raises(Refused):
        store.apply_batch(reader, unauthorized, atomic=atomic, idempotency_key=key)
    assert unauthorized.reads == [0]
    assert _snapshot(store, clock) == before


def test_import_checks_auth_and_attribution_then_refuses_before_records_or_clock(
    metadata_module: ModuleInfo,
) -> None:
    store, _, writer, reader, clock = _world(metadata_module)
    records = _GuardedRecords()
    before = _snapshot(store, clock)

    with pytest.raises(Unsupported, match="metadata-only profile"):
        store.import_records(writer, "m", records, load_id="load", initiated_by="writer")
    assert _snapshot(store, clock) == before

    with pytest.raises(Refused):
        store.import_records(reader, "m", records, load_id="load", initiated_by="reader")
    assert _snapshot(store, clock) == before

    with pytest.raises(Invalid) as error:
        store.import_records(writer, "m", records, load_id="load", initiated_by="other")
    assert [(item.path, item.code) for item in error.value.violations] == [
        ("initiated_by", "attribution")
    ]
    assert _snapshot(store, clock) == before


def test_write_profile_guard_refuses_even_without_raw_document(metadata_module: ModuleInfo) -> None:
    store, _, writer, _, _ = _world(metadata_module)
    del store.documents["m"]
    with pytest.raises(Unsupported, match="metadata-only profile"):
        store.apply(writer, Plan("m.Create", (), ()), idempotency_key=None)
    assert store.modules["m"].metadata_profile == PROFILE


def test_backend_profile_default_remains_legacy_only() -> None:
    assert BackendInfo("custom", ("reader",)).metadata_profiles == ("legacy-arras/1",)
