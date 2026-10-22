# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
# ruff: noqa: F811
"""The ADR-020 model against the Truss adapter (TR-12): the same state machine as
`tests/test_properties.py`, driven through the interface over a real Truss on PostgreSQL 18.6.

The model (use cases by code, the keys held, one group per change) is the one the in-memory
backends are held to. What Truss is not has no rule here: it has no replica (so no replica feed,
read-your-writes or mirror). Its journal is its audit pages, read under an audit grant of their own,
so the journal rules read them as `aud` (who reads and holds the audit grant but writes nothing) and add one: a writer with no
audit grant is `Refused`; every change has its own group. The machine acts as `bob`, a writer who is not an administrator (an administrative
principal is refused reads and actions). Each example builds a world of its own, about half a
second, and a step costs a second or two, so the budget is small and fixed (the search is
derandomized); the cases it must reach are checked, and each control breaks one rule of the
adapter and must fail the machine.
"""

from __future__ import annotations

import traceback
from typing import Any

import pytest
from hypothesis import HealthCheck, Phase, settings
from hypothesis import strategies as st
from hypothesis.stateful import invariant, precondition, rule, run_state_machine_as_test

import test_properties as memory
from arras import Arras, ArrasError, Conflict, Placement, Refused, Unavailable
from arras.conformance import load_corpus
from arras.umf import parse_module
from test_properties import ADD, CODES, LIST, NAMES, Ontology, inputs
from test_truss_harness import cluster  # noqa: F401
from truss_harness import Cluster, TrussHarness

MODULE_TEXT = load_corpus()["_module_text"]
HOST = "truss"  # the name the host registers the backend under
CLUSTER: list[Cluster] = []  # the module's cluster, for the machine that cannot take a fixture


class _Record:
    """The record store's availability, as the machine sets it: an outage cuts the sessions."""

    def __init__(self, harness: TrussHarness) -> None:
        self._harness = harness
        self._up = True

    @property
    def available(self) -> bool:
        return self._up

    @available.setter
    def available(self, up: bool) -> None:
        self._harness.outage(None if up else "unreachable")
        self._up = up


class TrussWorld:
    """One Truss installation with the corpus module, a writer (`bob`) and a reader (`carol`)."""

    def __init__(self, cluster: Cluster) -> None:
        h = TrussHarness(cluster)
        h.install(parse_module(MODULE_TEXT), MODULE_TEXT.encode())
        h.grant("bob", {"catalog": ["read", "write"]}, False)
        h.grant("carol", {"catalog": ["read"]}, False)
        # an auditor who writes nothing; she reads the module because `Arras` names a module from the
        # person's own catalog (the adapter itself serves an auditor who reads none: test_truss_audit)
        h.grant("aud", {"catalog": ["read", "journal"]}, False)
        self.harness = h
        self.auth = _Record(h)
        self.h = Arras.start({HOST: h.backend()}, default_placement=Placement(HOST, ()))
        self.o = self.h.session(h.principal("bob"))
        self.audit = self.h.session(h.principal("aud"))

    def read(self, sql: str, module: str = "catalog", **kw: Any) -> Any:
        return self.h.session(self.harness.principal("carol")).query(module, sql, **kw)


class TrussOntology(Ontology):
    def world(self) -> Any:
        return TrussWorld(CLUSTER[0])

    # no replica on Truss
    feed_the_replica = None  # type: ignore[assignment]
    read_your_writes = None  # type: ignore[assignment]
    bulk_is_what_the_replica_last_held = None  # type: ignore[assignment]
    record_store_availability = None  # type: ignore[assignment]

    @precondition(lambda self: self.w.auth.available)
    @rule()
    def the_record_store_goes_down(self) -> None:
        """Truss cuts off, then (in the rule below, the only one that can run) comes back: a step
        costs seconds here, so an outage lasts the one step that checks it."""
        self.w.auth.available = False

    @precondition(lambda self: self.w.auth.available and any("#" not in k for k in self.held))
    @rule(data=st.data())
    def a_held_key_with_other_inputs_is_a_conflict(self, data: st.DataObject) -> None:
        """Truss holds a request for its input: the same key with other inputs is a conflict, never
        applied and never a replay (the search alone rarely reaches it)."""
        key = data.draw(st.sampled_from(sorted(k for k in self.held if "#" not in k)))
        (code, name), _ = self.held[key]
        with pytest.raises(Conflict) as e:
            self.w.o.invoke(ADD, inputs(code, "B" if name == "A" else "A"), idempotency_key=key)
        assert e.value.reason == "idempotency_key_reused"
        memory.WITNESSES.add("conflict")

    @precondition(lambda self: not self.w.auth.available)
    @rule(code=CODES, name=NAMES)
    def an_outage_is_not_a_refusal_or_an_empty_answer(self, code: str, name: str) -> None:
        """With Truss unreachable a change and a `latest` read say `Unavailable`, naming the backend
        the host registered; they are never applied, refused or empty (CONTRACT-004)."""
        with pytest.raises(Unavailable) as e:
            self.w.o.invoke(ADD, inputs(code, name))
        assert e.value.backend == HOST
        with pytest.raises(Unavailable):
            self.w.read(LIST)
        memory.WITNESSES.add("outage_refused")
        self.w.auth.available = True  # and it recovers: nothing was applied or lost

    @invariant()
    def latest_is_the_model(self) -> None:
        if not self.w.auth.available:
            return
        ans = self.w.read(LIST)
        assert {r["code"]: r["name"] for r in ans.rows} == self.applied
        assert ans.freshness.backend == HOST and ans.freshness.consistency == "latest"

    @invariant()
    def each_change_has_its_own_group_and_the_journal_needs_its_grant(self) -> None:
        """A group names one change, so no two applied changes share one (a replay names its
        original, which is no new change); and a writer with no audit grant is refused the journal,
        never given an empty page."""
        assert len(set(self.groups)) == len(self.groups)
        if not self.w.auth.available:  # the module is listed by the record store, which is down
            return
        with pytest.raises(Refused):
            self.w.o.changes("catalog", limit=1)
        memory.WITNESSES.add("journal_refused_without_grant")

    @invariant()
    def the_journal_is_the_model(self) -> None:
        """Each applied change is one record, newest first, as the auditor reads it (Truss states no
        key or version); replays, validations, refusals and failed groups add none."""
        if not self.w.auth.available:
            return
        page = self.w.audit.changes("catalog", limit=100)
        assert [c.group for c in page.items] == self.groups[::-1]
        for c, codes in zip(page.items, self.created[::-1], strict=True):
            assert (c.by, c.action, c.module, c.backend) == ("bob", ADD, "catalog", HOST)
            assert [(o["kind"], o["type"]) for o in c.ops] == [("create", "catalog.UseCase")] * len(
                codes
            )
            assert all(o["key"] is None and o["version"] is None for o in c.ops)

    @invariant()
    def the_journal_pages_to_the_same_sequence(self) -> None:
        """Read a page at a time, the journal is the same rows in the same order: none skipped, none
        repeated, and the last page names no next one."""
        if not self.w.auth.available or len(self.groups) <= 3:
            return
        whole = [c.group for c in self.w.audit.changes("catalog", limit=100).items]
        got: list[str] = []
        after = None
        while True:
            page = self.w.audit.changes("catalog", limit=3, after=after)
            got += [c.group for c in page.items]
            after = page.next_cursor
            if after is None:
                break
            assert len(page.items) == 3
        assert got == whole
        memory.WITNESSES.add("journal_paged")


REQUIRED = frozenset(
    {
        "applied", "replayed", "conflict", "precondition",
        "validate_ok", "validate_refused",
        "batch_partly_applied",
        "atomic_applied", "atomic_refused",
        "outage_refused", "journal_refused_without_grant",
    }
)  # fmt: skip

BUDGET = settings(
    max_examples=12,
    stateful_step_count=16,
    deadline=None,
    database=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


@pytest.fixture
def truss(cluster: Cluster, monkeypatch: pytest.MonkeyPatch) -> Any:  # noqa: F811
    CLUSTER[:] = [cluster]
    seen: set[str] = set()
    monkeypatch.setattr(memory, "WITNESSES", seen)
    yield seen
    CLUSTER.clear()


def run_machine() -> None:
    run_state_machine_as_test(
        TrussOntology,
        settings=settings(
            BUDGET,
            max_examples=40,  # a control fails early; the margin is for a rule that fails late
            phases=[
                Phase.generate
            ],  # a counterexample is enough: shrinking would cost a world each
            report_multiple_bugs=False,
        ),
    )


def machine_fails_in(*rules: str) -> None:
    """The machine must fail in one of `rules` of the model: as a broken assertion, or as an answer
    the model did not predict (a retry refused as a precondition); not as a setup or tooling error."""
    with pytest.raises((AssertionError, pytest.fail.Exception, ArrasError)) as caught:
        run_machine()
    ours = {__file__, memory.__file__}
    here = [f for f in traceback.extract_tb(caught.value.__traceback__) if f.filename in ours]
    assert here and here[-1].name in rules, (
        f"failed in {here[-1].name if here else 'no rule'}: {caught.value!r}"
    )


@pytest.mark.truss
def test_the_machine_agrees_with_truss_and_reaches_every_case_it_claims(truss: Any) -> None:
    run_state_machine_as_test(TrussOntology, settings=BUDGET)
    assert REQUIRED - truss == set(), sorted(truss)


@pytest.mark.truss
def test_the_machine_fails_when_a_retried_key_is_a_new_request(
    truss: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import uuid

    import arras.adapters.truss.apply as apply

    monkeypatch.setattr(apply, "request_id", lambda action, key: str(uuid.uuid4()))
    machine_fails_in(
        "invoke",
        "retry_a_keyed_invocation",
        "batch_independently",
        "validate",
        "a_held_key_with_other_inputs_is_a_conflict",
    )


@pytest.mark.truss
def test_the_machine_fails_when_batch_items_share_one_request(
    truss: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import arras.adapters.truss.apply as apply

    real = apply.request_id
    monkeypatch.setattr(apply, "request_id", lambda action, key: real(action.split("#")[0], key))
    machine_fails_in("batch_independently", "validate", "invoke", "retry_a_keyed_invocation")


@pytest.mark.truss
def test_the_machine_fails_when_every_change_names_one_group(
    truss: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import arras.adapters.truss.outcome as outcome

    monkeypatch.setattr(outcome, "group_of", lambda semantic, request: "one-group")
    machine_fails_in(
        "each_change_has_its_own_group_and_the_journal_needs_its_grant", "the_journal_is_the_model"
    )
