# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Properties of the action and read contracts, checked against a small executable model.

The model is the contract's own rules, written as plain Python over a dict (CONTRACT-001, 003,
004). A `hypothesis` state machine drives the in-memory backends with random sequences of
invocations, validations, batches, replica feeds and outages, and after every step compares what
the interface says with what the model says. The same machine is the acceptance test an adapter
runs against, when the conformance corpus is run over a real backend (docs/helix/03-test).
"""

from __future__ import annotations

import traceback
from dataclasses import replace
from typing import Any

import pytest
from hypothesis import HealthCheck, Phase, settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    invariant,
    precondition,
    rule,
    run_state_machine_as_test,
)

from arras import ArrasError, Conflict, NotYetCurrent, PreconditionFailed, Unavailable
from arras.errors import Failure
from arras.fakes import MemoryReplica, MemoryStore
from arras.results import ItemResult
from arras.routing import Router
from test_core import World

ADD = "catalog.AddUseCase"
LIST = "SELECT u.code, u.name FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
CODES = st.sampled_from(["a", "b", "c", "d"])
NAMES = st.sampled_from(["A", "B"])
KEYS = st.sampled_from(["k1", "k2"])
ITEMS = st.lists(st.tuples(CODES, NAMES), min_size=1, max_size=4)


def inputs(code: str, name: str) -> dict[str, str]:
    return {"code": code, "name": name}


class Ontology(RuleBasedStateMachine):
    """The interface against the model: use cases by code, the keys held, what the replica holds."""

    def world(self) -> Any:
        """What the machine drives: a person's session (`o`), a reader's `read`, and the record
        store's `auth.available`. The Truss adapter's run supplies its own (test_truss_properties)."""
        w = World()
        w.access.grants["alice"].add(("catalog", "journal"))
        return w

    def __init__(self) -> None:
        super().__init__()
        self.w = self.world()
        self.applied: dict[str, str] = {}  # the record store's use cases: code -> name
        self.held: dict[str, tuple[tuple[str, str], Any]] = {}  # key -> (inputs, receipt token)
        self.issued: list[Any] = []  # tokens in the order the record store issued them
        self.replica: dict[str, str] = {}  # what the replica holds after its last feed
        self.reached = 0  # tokens the replica has reached: issued[:reached]
        self.fed = False
        self.groups: list[str] = []  # one group per applied change, oldest first
        self.created: list[list[str]] = []  # the codes each of those changes created
        self.group_of: dict[str, str] = {}  # key -> the group its change committed in

    # -- the model's one step: an invocation of AddUseCase

    def model_add(self, key: str | None, code: str, name: str) -> str:
        """The model's outcome of one invocation, applied to the model: `applied`, `replayed`,
        `precondition` (the use case exists) or `conflict` (the key was used with other inputs)."""
        if key is not None and key in self.held:
            return "replayed" if self.held[key][0] == (code, name) else "conflict"
        if code in self.applied:
            return "precondition"
        self.applied[code] = name
        return "applied"

    def issue(self, key: str | None, code: str, name: str, token: Any, group: str) -> None:
        self.issued.append(token)
        self.groups.append(group)
        self.created.append([code])
        if key is not None:
            self.held[key] = ((code, name), token)
            self.group_of[key] = group

    # -- rules

    @precondition(lambda self: self.w.auth.available)
    @rule(code=CODES, name=NAMES, key=st.none() | KEYS)
    def invoke(self, code: str, name: str, key: str | None) -> None:
        expected = self.model_add(key, code, name)
        try:
            r = self.w.o.invoke(ADD, inputs(code, name), idempotency_key=key)
        except PreconditionFailed:
            assert expected == "precondition"
            WITNESSES.add("precondition")
            return
        except Conflict as e:
            assert expected == "conflict" and e.reason == "idempotency_key_reused"
            WITNESSES.add("conflict")
            return
        WITNESSES.add(expected)
        if expected == "replayed":  # applied once: the original receipt, no new change
            assert r.replayed and key is not None and r.token == self.held[key][1]
            assert r.group == self.group_of[key]  # a replay is the original group
        else:
            assert expected == "applied" and not r.replayed
            self.issue(key, code, name, r.token, r.group)

    @precondition(lambda self: self.w.auth.available and bool(self.held))
    @rule(data=st.data())
    def retry_a_keyed_invocation(self, data: st.DataObject) -> None:
        """A client that did not see the answer sends the same request again: the change applies
        once, whatever happened in between (CONTRACT-003, idempotency)."""
        key = data.draw(st.sampled_from(sorted(self.held)))
        (code, name), token = self.held[key]
        if "#" in key:  # a batch item's key is only meaningful inside its batch
            return
        before = dict(self.applied)
        r = self.w.o.invoke(ADD, inputs(code, name), idempotency_key=key)
        assert r.replayed and r.token == token and self.applied == before
        WITNESSES.add("replayed")

    @precondition(lambda self: self.w.auth.available)
    @rule(code=CODES, name=NAMES, key=KEYS)
    def validate(self, code: str, name: str, key: str) -> None:
        """Advisory: it applies nothing and costs the key nothing, so the invariants below stay
        those of the model, which this rule does not touch."""
        v = self.w.o.validate(ADD, inputs(code, name), idempotency_key=key)
        if key in self.held:
            assert v.replay is not None or self.held[key][0] != (code, name)
        else:
            assert v.ok == (code not in self.applied) and v.replay is None
            WITNESSES.add("validate_ok" if v.ok else "validate_refused")

    @precondition(lambda self: self.w.auth.available)
    @rule(items=ITEMS, key=st.none() | KEYS)
    def batch_independently(self, items: list[tuple[str, str]], key: str | None) -> None:
        """Each item is its own invocation, and under a key it is idempotent as `key#index`."""
        got = self.w.o.invoke_batch(ADD, [inputs(c, n) for c, n in items], idempotency_key=key)
        assert len(got.items) == len(items)
        ok = 0
        for i, ((c, n), item) in enumerate(zip(items, got.items, strict=True)):
            item_key = None if key is None else f"{key}#{i}"
            expected = self.model_add(item_key, c, n)
            if expected in ("precondition", "conflict"):
                assert item.refusal is not None and item.receipt is None
                continue
            assert item.receipt is not None and item.receipt.replayed == (expected == "replayed")
            ok += 1
            if expected == "applied":
                self.issue(item_key, c, n, item.receipt.token, item.receipt.group)
            elif item_key is not None:
                assert item.receipt.group == self.group_of[item_key]
        assert (got.succeeded, got.failed) == (ok, len(items) - ok)
        if 0 < ok < len(items):
            WITNESSES.add("batch_partly_applied")

    @precondition(lambda self: self.w.auth.available)
    @rule(items=ITEMS)
    def batch_atomically(self, items: list[tuple[str, str]]) -> None:
        """All of it applies, under one token, or none of it does."""
        codes = [c for c, _ in items]
        fits = len(set(codes)) == len(codes) and not set(codes) & set(self.applied)
        if fits:
            got = self.w.o.invoke_batch(ADD, [inputs(c, n) for c, n in items], atomic=True)
            assert got.atomic and got.succeeded == len(items) and got.failed == 0
            assert len({i.receipt.token for i in got.items if i.receipt}) == 1
            [group] = {i.receipt.group for i in got.items if i.receipt}  # one group
            self.applied.update(dict(items))
            self.issued.append(got.token)
            self.groups.append(group)
            self.created.append(codes)
            WITNESSES.add("atomic_applied")
        else:
            with pytest.raises((PreconditionFailed, Conflict)):
                self.w.o.invoke_batch(ADD, [inputs(c, n) for c, n in items], atomic=True)
            WITNESSES.add("atomic_refused")

    @precondition(lambda self: self.w.auth.available)
    @rule()
    def feed_the_replica(self) -> None:
        self.w.replica.feed()
        self.fed, self.replica, self.reached = True, dict(self.applied), len(self.issued)
        WITNESSES.add("fed")

    @rule(up=st.booleans())
    def record_store_availability(self, up: bool) -> None:
        self.w.auth.available = up

    @precondition(lambda self: not self.w.auth.available)
    @rule(code=CODES, name=NAMES)
    def an_outage_is_not_a_refusal_or_an_empty_answer(self, code: str, name: str) -> None:
        """With the record store down a change and a `latest` read say `Unavailable`; they are never
        applied, never refused as a precondition and never an empty list (CONTRACT-004)."""
        with pytest.raises(Unavailable) as e:
            self.w.o.invoke(ADD, inputs(code, name))
        assert e.value.backend == "primary"
        with pytest.raises(Unavailable):
            self.w.read(LIST)
        WITNESSES.add("outage_refused")

    @precondition(lambda self: self.fed and bool(self.issued))
    @rule(data=st.data())
    def read_your_writes(self, data: st.DataObject) -> None:
        """`at_least=token` on the replica answers once it has reached the token, with the state
        it holds, and otherwise says `NotYetCurrent`. It never answers from before the token."""
        i = data.draw(st.integers(0, len(self.issued) - 1))
        try:
            ans = self.w.read(LIST, consistency="bulk", at_least=self.issued[i])
        except NotYetCurrent as e:
            assert i >= self.reached and e.token == self.issued[i]
            WITNESSES.add("read_at_token_not_yet_current")
            return
        WITNESSES.add("read_at_token_answered")
        assert i < self.reached
        assert {r["code"]: r["name"] for r in ans.rows} == self.replica

    # -- after every step

    @invariant()
    def latest_is_the_model(self) -> None:
        if not self.w.auth.available:
            return
        ans = self.w.read(LIST)
        assert {r["code"]: r["name"] for r in ans.rows} == self.applied
        assert ans.freshness.backend == "primary" and ans.freshness.consistency == "latest"

    @invariant()
    def the_journal_is_the_model(self) -> None:
        """Each applied change is one record, newest first; replays, validations, refusals and
        failed groups add none (CONTRACT-001, Audit reads)."""
        if not self.w.auth.available:
            return
        page = self.w.o.changes("catalog", limit=100)
        assert [c.group for c in page.items] == self.groups[::-1]
        for c, codes in zip(page.items, self.created[::-1], strict=True):
            assert (c.by, c.action, c.module, c.backend) == ("alice", ADD, "catalog", "primary")
            want = [
                {"kind": "create", "type": "catalog.UseCase", "key": k, "version": 1} for k in codes
            ]
            assert list(c.ops) == want  # what was created, in order, and no input value

    @invariant()
    def the_journal_pages_to_the_same_sequence(self) -> None:
        """Read a page at a time, the journal is the same rows in the same order (CONTRACT-001,
        cursors): none skipped, none repeated, and the last page names no next one."""
        if not self.w.auth.available:
            return
        whole = [c.group for c in self.w.o.changes("catalog", limit=100).items]
        for size in (1, 3):
            got: list[str] = []
            after = None
            while True:
                page = self.w.o.changes("catalog", limit=size, after=after)
                got += [c.group for c in page.items]
                after = page.next_cursor
                if after is None:
                    break
                assert len(page.items) == size
            assert got == whole
        if len(whole) > 3:
            WITNESSES.add("journal_paged")

    @invariant()
    def bulk_is_what_the_replica_last_held(self) -> None:
        if not self.fed:
            return
        ans = self.w.read(LIST, consistency="bulk")
        assert {r["code"]: r["name"] for r in ans.rows} == self.replica
        assert ans.freshness.backend == "mirror" and ans.freshness.consistency == "bulk"


TestOntology = Ontology.TestCase
TestOntology.settings = settings(
    max_examples=60,
    stateful_step_count=25,
    deadline=None,
    derandomize=True,  # a failure here is reproducible, as with the controls below
    suppress_health_check=[HealthCheck.too_slow],
)


# However a broken rule surfaces: a failed assertion, `pytest.raises` finding nothing to catch, or
# an interface error the model did not predict. A setup or tooling error is none of these.
BROKEN = (AssertionError, pytest.fail.Exception, ArrasError, BaseExceptionGroup)

# The cases the machine has been seen to reach (P-W1). A rule that holds only because its
# interesting case never happens would pass the machine and prove nothing.
WITNESSES: set[str] = set()
REQUIRED_WITNESSES = frozenset(
    {
        "applied", "replayed", "conflict", "precondition",
        "validate_ok", "validate_refused",
        "batch_partly_applied",
        "atomic_applied", "atomic_refused",
        "fed", "read_at_token_answered", "read_at_token_not_yet_current",
        "outage_refused",
        "journal_paged",
    }
)  # fmt: skip


def run_machine() -> None:
    run_state_machine_as_test(
        Ontology,
        settings=settings(
            max_examples=200,  # margin: the search is derandomized, so this is fixed, not luck
            stateful_step_count=20,
            deadline=None,
            database=None,
            derandomize=True,
            phases=[Phase.generate],  # a counterexample is enough; it need not be the shortest
            report_multiple_bugs=False,
        ),
    )


def test_the_machine_fails_when_an_idempotency_key_is_forgotten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MemoryStore, "_held", lambda self, action, key, digest: None)
    with pytest.raises(BROKEN):
        run_machine()


def test_the_machine_fails_when_a_replica_answers_before_it_reached_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MemoryReplica, "_reached", lambda self, seq: True)
    with pytest.raises(BROKEN):
        run_machine()


def test_the_machine_fails_when_an_outage_reads_as_an_empty_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MemoryStore, "down", lambda self, op: None)
    with pytest.raises(BROKEN):
        run_machine()


def test_the_machine_fails_when_a_change_is_recorded_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arras.fakes as fakes

    real = fakes.record_change

    def twice(*a: Any, **k: Any) -> None:
        real(*a, **k)
        real(*a, **k)

    monkeypatch.setattr(fakes, "record_change", twice)
    with pytest.raises(BROKEN):
        run_machine()


def test_the_machine_fails_when_a_validation_leaves_a_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    from arras.results import Change

    real = MemoryStore._validate

    def leaky(self: MemoryStore, *a: Any, **k: Any) -> Any:
        self.state.changes.append(
            Change("leak", datetime.now(UTC), "x", "a.B", "catalog", (), "primary")
        )
        return real(self, *a, **k)

    monkeypatch.setattr(MemoryStore, "_validate", leaky)
    with pytest.raises(BROKEN):
        run_machine()


def test_the_machine_fails_when_a_change_names_another_person(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arras.fakes as fakes

    real = fakes.record_change

    def as_someone(*a: Any, **k: Any) -> None:
        real(*a, **{**k, "by": "someone"})

    monkeypatch.setattr(fakes, "record_change", as_someone)
    with pytest.raises(BROKEN):
        run_machine()


def test_the_machine_fails_when_a_cursor_skips_a_row(monkeypatch: pytest.MonkeyPatch) -> None:
    import arras.fakes_journal as journal

    def skipping(rows: list[Any], limit: int, after: str | None) -> Any:
        start = int(after) if after else 0
        end = start + limit
        return tuple(rows[start:end]), (str(end + 1) if end < len(rows) else None)

    monkeypatch.setattr(journal, "_page", skipping)
    with pytest.raises(BROKEN):
        run_machine()


def machine_fails_in(*rules: str) -> None:
    """The machine must fail, and in one of `rules` of the model, as a broken assertion or an
    expectation that found nothing: not as a setup error, an interface error or a tooling one."""
    with pytest.raises((AssertionError, pytest.fail.Exception)) as caught:
        run_machine()
    here = [f for f in traceback.extract_tb(caught.value.__traceback__) if f.filename == __file__]
    assert here and here[-1].name in rules, (
        f"failed in {here[-1].name if here else 'no rule'}: {caught.value!r}"
    )


def test_the_machine_fails_when_validate_spends_the_key_and_applies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validate = MemoryStore._validate

    def applying(self: MemoryStore, principal: Any, plan: Any, mod: Any, key: Any) -> Any:
        v = validate(self, principal, plan, mod, key)
        try:
            self.apply(principal, plan, idempotency_key=key)
        except ArrasError:
            pass
        return v

    monkeypatch.setattr(MemoryStore, "_validate", applying)
    machine_fails_in("validate", "invoke", "latest_is_the_model", "retry_a_keyed_invocation")


def test_the_machine_fails_when_batch_items_share_one_key(monkeypatch: pytest.MonkeyPatch) -> None:
    apply = MemoryStore._apply_scoped

    def one_key(
        self: MemoryStore, principal: Any, plan: Any, key: Any, dry: Any, scope: Any
    ) -> Any:
        return apply(self, principal, plan, key, dry, None)

    monkeypatch.setattr(MemoryStore, "_apply_scoped", one_key)
    # The poisoned key is caught by the batch rule, or, if the search reaches it first, by the
    # validate rule that finds the key held for other inputs.
    machine_fails_in("batch_independently", "validate")


def test_the_machine_fails_when_one_failed_item_refuses_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply_batch = MemoryStore.apply_batch

    def contagious(self: MemoryStore, *a: Any, **kw: Any) -> Any:
        got = apply_batch(self, *a, **kw)
        items, refused = [], False
        for it in got.items:
            refused = refused or it.refusal is not None
            if refused and it.refusal is None:
                it = ItemResult(it.index, refusal=PreconditionFailed([Failure("_x", "after one")]))
            items.append(it)
        ok = sum(1 for it in items if it.receipt is not None)
        return replace(got, items=tuple(items), succeeded=ok, failed=len(items) - ok)

    monkeypatch.setattr(MemoryStore, "apply_batch", contagious)
    machine_fails_in("batch_independently")


def test_the_machine_fails_when_an_atomic_batch_applies_item_by_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply_batch = MemoryStore.apply_batch

    def piecemeal(self: MemoryStore, principal: Any, plans: Any, **kw: Any) -> Any:
        if not kw.get("atomic"):
            return apply_batch(self, principal, plans, **kw)
        return replace(apply_batch(self, principal, plans, **{**kw, "atomic": False}), atomic=True)

    monkeypatch.setattr(MemoryStore, "apply_batch", piecemeal)
    machine_fails_in("batch_atomically")


def test_the_machine_fails_when_a_latest_read_is_served_by_the_replica(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve = Router.serve

    def replica_once_fed(self: Router, consistency: Any) -> Any:
        replicas = self.module.placement.replicas  # one never fed has no state to serve
        fed = bool(replicas) and getattr(self._backend(replicas[0]), "fed", False)
        return serve(self, "bulk" if fed else consistency)

    monkeypatch.setattr(Router, "serve", replica_once_fed)
    machine_fails_in("latest_is_the_model", "read_your_writes")


def test_the_machine_fails_when_a_bulk_read_is_served_by_the_record_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve = Router.serve
    monkeypatch.setattr(Router, "serve", lambda self, consistency: serve(self, "latest"))
    machine_fails_in("bulk_is_what_the_replica_last_held", "read_your_writes")


def test_the_machine_reaches_every_case_it_claims_to_check() -> None:
    WITNESSES.clear()
    run_state_machine_as_test(
        Ontology,
        settings=settings(
            max_examples=60, stateful_step_count=25, deadline=None, database=None, derandomize=True
        ),
    )
    assert REQUIRED_WITNESSES - WITNESSES == set()
