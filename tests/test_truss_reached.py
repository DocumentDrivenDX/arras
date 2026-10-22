# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
# ruff: noqa: F811
"""The Truss adapter's `reached` (TR-10): a position token asked of the store, mapped without ever
turning an answer Truss cannot give into `False`.

The unit tests are always on: a scripted fake of Truss's assembly behind the connection layer's
`Toolkit` seam, with results named as Truss names them. The Truss-marked tests run the freshness corpus
cases and the plan's gate checks against a real Truss on PostgreSQL 18.6.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from arras.actions import Create, Plan, Ref
from arras.adapters.truss import reach
from arras.errors import Invalid, Refused, Unavailable
from arras.types import Principal
from test_truss_harness import _world, cluster  # noqa: F401
from test_truss_registry import ALICE, FakeAssembly, Rig, error, fake_truss, ok  # noqa: F401
from truss_harness import foreign_token

# -- results as Truss names them


@dataclass(frozen=True)
class ReceiptIncluded:
    included: bool
    comparison_profile: str = "profile"


@dataclass(frozen=True)
class ReceiptVisibilityUnavailable:
    reason: str


class ReachAssembly(FakeAssembly):
    def __init__(self) -> None:
        super().__init__()
        self.answer: Any = ok(ReceiptIncluded(True))
        self.calls: list[tuple[Any, ...]] = []
        self.kwargs: list[dict[str, Any]] = []

    def reached_in_transaction(self, tx: Any, token: Any, **kw: Any) -> Any:
        self.log.append("reached")
        self.calls.append((tx, token))
        self.kwargs.append(kw)
        return self.answer


@dataclass
class ReachRig(Rig):
    assembly: ReachAssembly = field(default_factory=ReachAssembly)  # type: ignore[assignment]


def rig(answer: Any) -> ReachRig:
    r = ReachRig()
    r.assembly.answer = answer
    return r


def unavailable(reason: str) -> Any:
    return ok(ReceiptVisibilityUnavailable(reason))


TOKEN = "a-token-the-adapter-never-reads"


# -- the call


@pytest.mark.parametrize("included", [True, False])
def test_included_is_the_answer(included: bool) -> None:
    r = rig(ok(ReceiptIncluded(included)))
    assert r.backend().reached(ALICE, TOKEN) is included


def test_it_is_one_read_only_call_that_is_rolled_back_and_names_no_consumer() -> None:
    r = rig(ok(ReceiptIncluded(True)))
    r.backend().reached(ALICE, TOKEN)
    [conn] = r.conns
    assert conn.log[0].endswith("READ ONLY") and conn.log[-1] == "rollback"
    assert r.assembly.log == ["reached"]
    assert r.assembly.calls == [("tx", TOKEN)]
    assert r.assembly.kwargs == [{}]  # no consumer_id, no bound of its own


def test_a_call_with_no_token_never_connects() -> None:
    r = rig(ok(ReceiptIncluded(True)))
    with pytest.raises(Refused) as raised:
        r.backend().reached(Principal("anon", ""), TOKEN)
    assert (raised.value.reason, r.conns) == ("token_expired", [])


def test_with_no_connections_it_is_not_configured() -> None:
    from arras.adapters.truss import TrussBackend

    with pytest.raises(Unavailable) as raised:
        TrussBackend("truss").reached(ALICE, TOKEN)
    assert raised.value.reason == "not_configured"


# -- the map


def test_a_token_truss_cannot_read_is_invalid() -> None:
    r = rig(unavailable("invalid_token"))
    with pytest.raises(Invalid) as raised:
        r.backend().reached(ALICE, "garbage")
    assert [v.code for v in raised.value.violations] == ["malformed"]


def test_a_token_over_the_bound_is_invalid_and_a_resource_inside_it_is_unavailable() -> None:
    big = "x" * (reach.TOKEN_BOUND + 1)
    with pytest.raises(Invalid):
        rig(unavailable("resource")).backend().reached(ALICE, big)
    with pytest.raises(Unavailable) as raised:
        rig(unavailable("resource")).backend().reached(ALICE, "x" * reach.TOKEN_BOUND)
    assert raised.value.reason == "resource"


def test_the_token_bound_is_16384_characters_and_one_more_is_invalid() -> None:
    assert reach.TOKEN_BOUND == 16_384
    with pytest.raises(Unavailable):  # at the bound the token is asked of Truss
        rig(unavailable("resource")).backend().reached(ALICE, "x" * 16_384)
    with pytest.raises(Invalid):
        rig(unavailable("resource")).backend().reached(ALICE, "x" * 16_385)


def test_a_non_member_is_refused() -> None:
    with pytest.raises(Refused) as raised:
        rig(unavailable("authorization")).backend().reached(ALICE, TOKEN)
    assert (raised.value.operation, raised.value.reason) == ("reached", "no_access")


@pytest.mark.parametrize(
    "reason", ["epoch_profile", "retention", "observation_integrity", "invalid_consumer", "other"]
)
def test_every_other_reason_is_unavailable_never_false(reason: str) -> None:
    with pytest.raises(Unavailable) as raised:
        rig(unavailable(reason)).backend().reached(ALICE, TOKEN)
    assert raised.value.reason == "unreachable" and reason in (raised.value.detail or "")


def test_an_answer_of_no_known_kind_is_unavailable_not_false() -> None:
    with pytest.raises(Unavailable):
        rig(ok(object())).backend().reached(ALICE, TOKEN)
    with pytest.raises(Unavailable):
        rig(ok(ReceiptIncluded("yes"))).backend().reached(ALICE, TOKEN)  # type: ignore[arg-type]


def test_a_failed_call_goes_through_the_failure_map_and_quarantines_the_connection() -> None:
    r = rig(error("transaction_unusable"))
    with pytest.raises(Unavailable):
        r.backend().reached(ALICE, TOKEN)
    assert r.conns[0].closed
    with pytest.raises(Refused):
        rig(error("execution_obligation", sql_state="42501")).backend().reached(ALICE, TOKEN)


def test_no_error_carries_the_token() -> None:
    for answer in (unavailable("epoch_profile"), unavailable("authorization"), error("retry")):
        with pytest.raises(Exception) as raised:
            rig(answer).backend().reached(ALICE, TOKEN)
        assert TOKEN not in repr(raised.value) and TOKEN not in str(raised.value)


# -- against a real Truss


def _plan(key: str) -> Plan:
    return Plan(
        "catalog.AddUseCase",
        (),
        (Create(Ref("catalog.UseCase", key), {"name": "N"}),),
    )


@pytest.mark.truss
def test_a_written_token_is_reached_by_every_member_and_garbage_is_invalid(cluster: Any) -> None:
    h = _world(cluster, "basic")
    backend = h.backend()
    mine = backend.apply(h.principal("alice"), _plan("uc-9"), idempotency_key=None)
    later = backend.apply(h.principal("alice"), _plan("uc-10"), idempotency_key=None)
    for user in ("carol", "bob", "alice"):
        who = h.principal(user)
        assert backend.reached(who, mine.token) is True
        assert backend.reached(who, later.token) is True  # earlier tokens stay reached
    carol = h.principal("carol")
    for bad in ("garbage", "", "fake:999999", "not base64!!", "café"):
        with pytest.raises(Invalid):
            backend.reached(carol, bad)
    with pytest.raises(Invalid):
        backend.reached(carol, "x" * (reach.TOKEN_BOUND + 1))
    with pytest.raises(Unavailable) as raised:  # another installation's token cannot be told
        backend.reached(carol, foreign_token())
    assert "epoch_profile" in (raised.value.detail or "")
    with pytest.raises(Refused):
        backend.reached(h.principal("dave"), mine.token)


@pytest.mark.truss
def test_a_non_member_with_a_garbage_token_is_invalid_on_truss_and_refused_on_memory(
    cluster: Any,
) -> None:
    """The order of refusal and classification is the adapter's own (CONTRACT-004, `reached`): Truss
    decodes a token before it authorizes, so a person who is a member of nothing is told the token is
    malformed; the memory adapter authenticates and refuses the non-member first. A well-formed
    token of a non-member is `Refused` on both."""
    from test_truss_query import _memory

    h = _world(cluster, "basic")
    truss = h.backend()
    mine = truss.apply(h.principal("alice"), _plan("uc-13"), idempotency_key=None).token
    memory = _memory("basic")
    store = memory.backend()
    held = store.apply(memory.principal("alice"), _plan("uc-99"), idempotency_key=None).token
    for bad in ("garbage", "", "x" * (reach.TOKEN_BOUND + 1)):
        with pytest.raises(Invalid):
            truss.reached(h.principal("dave"), bad)
        with pytest.raises(Refused):
            store.reached(memory.principal("dave"), bad)
    with pytest.raises(Refused):
        truss.reached(h.principal("dave"), mine)
    with pytest.raises(Refused):
        store.reached(memory.principal("dave"), held)


@pytest.mark.truss
def test_an_unissued_token_of_this_installation_is_unavailable_until_truss_tells_it_apart(
    cluster: Any,
) -> None:
    """Truss 0.0.44 answers a well-formed token whose receipt row does not exist `not_yet`, the reason
    it gives for a receipt whose transaction is not visible yet, so the adapter raises `Unavailable`.
    If Truss makes it `invalid_token`, this test changes to `Invalid`."""
    h = _world(cluster, "basic")
    backend = h.backend()
    alice = h.principal("alice")
    real = backend.apply(alice, _plan("uc-12"), idempotency_key=None).token
    body = json.loads(base64.urlsafe_b64decode(real + "=" * (-len(real) % 4)))
    body["receiptStorageRowId"] = "999999999"
    unissued = (
        base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode())
        .rstrip(b"=")
        .decode()
    )
    with pytest.raises(Unavailable) as raised:
        backend.reached(alice, unissued)
    assert "not_yet" in (raised.value.detail or "")


@pytest.mark.truss
def test_reached_runs_as_the_person(cluster: Any) -> None:
    h = _world(cluster, "basic")
    seen: list[str] = []
    source = h.world.connection_source

    from contextlib import contextmanager

    @contextmanager
    def watching(principal: Principal) -> Any:
        with source(principal) as conn:
            yield conn
            seen.append(conn.execute("select session_user").fetchone()[0])

    from arras.adapters.truss import Connections, TrussBackend

    backend = TrussBackend("truss", Connections("truss", watching))
    token = h.backend().apply(h.principal("alice"), _plan("uc-11"), idempotency_key=None).token
    assert backend.reached(h.principal("carol"), token) is True
    assert seen == ["carol"]
