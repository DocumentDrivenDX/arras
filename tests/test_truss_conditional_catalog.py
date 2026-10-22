# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The conditional reader catalog (Truss 0.0.44, plan B8): the adapter keeps each person's last
snapshot with Truss's validator and asks Truss whether it changed, so an unchanged catalog costs no
payload, while access is answered by Truss as the person on every call.

The unit tests script Truss's answers; the Truss-marked ones revoke a role while the person's
snapshot and validator are cached and check that the very next call is refused.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from arras import Arras, Invalid, Placement
from arras.conformance import load_corpus
from arras.types import Principal
from arras.umf import parse_module
from test_truss_harness import cluster  # noqa: F401
from test_truss_registry import (
    ALICE,
    CatalogRefused,
    ReaderCatalog,
    Rig,
    entry,
    ok,
)
from truss_harness import TrussHarness

DAVE = Principal("dave", "dave-token")
MODULE_TEXT = load_corpus()["_module_text"]
LIST = "SELECT u.code, u.name FROM catalog.UseCase u ORDER BY u.code LIMIT 100"


def test_the_second_read_of_a_person_presents_the_validator_of_the_first() -> None:
    rig = Rig()
    backend = rig.backend()
    backend.catalog(ALICE)
    backend.catalog(ALICE)
    first, second = rig.assembly.validators
    assert first is None and second is not None
    assert rig.assembly.log.count("catalog") == 2  # Truss is asked every time


def test_a_validator_is_one_persons_and_is_never_presented_for_another() -> None:
    rig = Rig()
    backend = rig.backend()
    backend.catalog(ALICE)
    backend.catalog(DAVE)
    assert rig.assembly.validators == [None, None]


def test_an_unchanged_answer_serves_the_snapshot_and_reads_no_document() -> None:
    rig = Rig()
    backend = rig.backend()
    first = backend.catalog(ALICE)
    rig.assembly.log.clear()
    assert backend.catalog(ALICE) == first
    assert rig.assembly.log == ["catalog"]  # no accepted-document read either


def test_a_changed_catalog_replaces_the_snapshot() -> None:
    rig = Rig()
    backend = rig.backend()
    backend.catalog(ALICE)
    rig.assembly.catalog = ok(ReaderCatalog(4, (entry(),)))
    backend.catalog(ALICE)
    rig.assembly.log.clear()
    backend.catalog(ALICE)
    assert rig.assembly.validators[-1] == rig.assembly.validators[-1] is not None
    assert rig.assembly.log == ["catalog"]


def test_a_refusal_with_a_cached_snapshot_is_refused_and_the_snapshot_is_dropped() -> None:
    rig = Rig()
    backend = rig.backend()
    assert backend.catalog(ALICE)
    assert backend.cache.snapshot("alice", True) is not None
    rig.assembly.catalog = ok(CatalogRefused())  # the role was revoked
    assert backend.catalog(ALICE) == {}  # the very next call, whatever was cached
    assert backend.cache.snapshot("alice", True) is None
    rig.assembly.catalog = ok(ReaderCatalog(3, (entry(),)))
    assert backend.catalog(ALICE)
    assert rig.assembly.validators[-1] is None  # the old validator is not presented again


def test_the_snapshots_kept_are_bounded() -> None:
    from arras.adapters.truss import cache

    held = cache.CatalogCache()
    for i in range(cache.CATALOG_HOLDERS + 5):
        held.keep_snapshot(f"p{i}", True, object(), "v")
    assert held.snapshot("p0", True) is None
    assert held.snapshot(f"p{cache.CATALOG_HOLDERS + 4}", True)


def test_a_read_only_and_a_read_write_view_are_kept_apart_and_a_refusal_drops_both() -> None:
    """Truss's validator names the view of the transaction it was given in, so a validator of a
    read-only call is no validator of a write call."""
    from arras.adapters.truss import cache

    held = cache.CatalogCache()
    held.keep_snapshot("alice", True, "read catalog", "v-read")
    held.keep_snapshot("alice", False, "write catalog", "v-write")
    assert held.snapshot("alice", True) == ("read catalog", "v-read")
    assert held.snapshot("alice", False) == ("write catalog", "v-write")
    held.drop_snapshot("alice")
    assert held.snapshot("alice", True) is None and held.snapshot("alice", False) is None


class Truss:
    """One Truss with the corpus module, a reader (`carol`), and the host over it."""

    def __init__(self, cluster: Any) -> None:  # noqa: F811
        h = TrussHarness(cluster)
        h.install(parse_module(MODULE_TEXT), MODULE_TEXT.encode())
        h.grant("carol", {"catalog": ["read"]}, False)
        h.grant("dave", {}, False)
        self.h = h
        self.backend: Any = h.backend()
        self.host = Arras.start({"truss": self.backend}, default_placement=Placement("truss", ()))

    def revoke(self, user: str) -> None:
        role = self.h.world.reader_role("catalog")
        self.h.world.cluster.su.execute(f'REVOKE "{role}" FROM "{user}"')


@pytest.fixture
def truss(cluster: Any) -> Iterator[Truss]:  # noqa: F811
    t = Truss(cluster)
    try:
        yield t
    finally:
        t.h.world.cluster.end_world()


@pytest.mark.truss
def test_a_revoked_role_is_refused_on_its_very_next_call_with_a_cached_snapshot(
    truss: Truss,
) -> None:
    carol = truss.h.principal("carol")
    assert "catalog" in truss.backend.catalog(carol)
    assert truss.backend.catalog(carol)  # the second call presents the validator and is `unchanged`
    assert truss.backend.cache.snapshot("carol", True) is not None
    truss.revoke("carol")
    assert truss.backend.catalog(carol) == {}
    assert truss.backend.cache.snapshot("carol", True) is None
    session = truss.host.session(carol)
    with pytest.raises(Invalid) as raised:
        session.query("catalog", LIST)
    assert raised.value.violations[0].code == "unknown_type"


@pytest.mark.truss
def test_a_snapshot_of_one_person_never_answers_for_another(truss: Truss) -> None:
    carol, dave = truss.h.principal("carol"), truss.h.principal("dave")
    assert truss.backend.catalog(carol)
    assert truss.backend.catalog(dave) == {}
    assert truss.backend.cache.snapshot("dave", True) is None


@pytest.mark.truss
def test_an_unchanged_catalog_costs_less_than_a_changed_one(truss: Truss) -> None:
    """The conditional answer is a payload-free `unchanged`: what comes back is not the catalog."""
    carol = truss.h.principal("carol")
    truss.backend.catalog(carol)
    held = truss.backend.cache.snapshot("carol", True)
    assert held is not None and held[1]
    truss.backend.catalog(carol)
    again = truss.backend.cache.snapshot("carol", True)
    assert again is not None and again[0] is held[0]  # the very snapshot object, served as is


@pytest.mark.truss
def test_a_registration_changes_the_validator_and_the_new_catalog_is_served(truss: Truss) -> None:
    from arras.conformance import _edited

    truss.h.grant("alice", {"catalog": ["read", "write", "schema"]}, True)
    registrar = truss.h.principal("alice")
    kinds = len(truss.backend.catalog(registrar)["catalog"].entity_types)
    before = truss.backend.cache.snapshot("alice", True)
    assert before is not None
    new = _edited(MODULE_TEXT, "add-record-type").encode()
    truss.backend.register(registrar, new, parse_module(new), unknown_endpoint="reject")
    assert len(truss.backend.catalog(registrar)["catalog"].entity_types) == kinds + 1
    after = truss.backend.cache.snapshot("alice", True)
    assert after is not None and after[1] != before[1]


@pytest.mark.truss
def test_a_write_after_a_write_is_answered_unchanged_though_a_read_came_between(
    truss: Truss, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read-only call and a read-write call each present the validator they were given in their own
    kind of transaction, so neither keeps the other from being answered `unchanged`."""
    import truss.catalog_runtime as runtime

    answers: list[tuple[bool, str]] = []
    real = runtime.CatalogReferenceAssembly.reader_catalog_if_changed_in_transaction

    def spy(self: Any, tx: Any, **kw: Any) -> Any:
        out = real(self, tx, **kw)
        answers.append((kw.get("validator") is not None, type(getattr(out, "value", out)).__name__))
        return out

    monkeypatch.setattr(
        runtime.CatalogReferenceAssembly, "reader_catalog_if_changed_in_transaction", spy
    )
    truss.h.grant("bob", {"catalog": ["read", "write"]}, False)
    bob = truss.h.principal("bob")
    from arras.actions import Create, Plan, Ref

    def write(key: str) -> None:
        plan = Plan("catalog.AddUseCase", (), (Create(Ref("catalog.UseCase", key), {"name": "N"}),))
        truss.backend.apply(bob, plan, idempotency_key=None)

    truss.backend.catalog(bob)  # a read-only call
    write("w0")  # a read-write call: its own first view (the validator of the read is not its own)
    answers.clear()
    truss.backend.catalog(bob)
    write("w1")
    truss.backend.catalog(bob)
    write("w2")
    assert answers == [(True, "ReaderCatalogUnchanged")] * 4


@pytest.mark.truss
def test_truss_answers_another_kinds_validator_with_a_new_snapshot_and_its_own_as_unchanged(
    truss: Truss,
) -> None:
    from truss_harness import transaction

    carol = truss.h.principal("carol")

    def ask(read_only: bool, validator: str | None) -> Any:
        with truss.h.world.connection_source(carol) as conn:
            with transaction(conn, read_only=read_only) as (assembly, handle):
                return assembly.reader_catalog_if_changed_in_transaction(
                    handle, validator=validator
                ).value

    read, write = ask(True, None), ask(False, None)
    assert read.validator != write.validator
    assert type(ask(False, read.validator)).__name__ == "ReaderCatalogSnapshot"
    assert type(ask(True, read.validator)).__name__ == "ReaderCatalogUnchanged"
    assert type(ask(False, write.validator)).__name__ == "ReaderCatalogUnchanged"
