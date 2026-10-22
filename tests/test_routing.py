# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Which backend serves a statement: the named module's placement and the consistency level
(CONTRACT-001, Query language). Arras never reads the statement.

The module check (an unreadable or unknown module is `unknown_type` before anything else), `latest`
from the record store, `bulk` through the replicas in placement order with `Unsupported` falling
through and everything else raised, the wait for `at_least` before each `query`, and an unconfigured
reader. The backends are memory backends whose `query` can be scripted to raise, and each logs what
it was asked, in order."""

from typing import Any

import pytest

from arras import (
    Arras,
    Invalid,
    NotYetCurrent,
    Placement,
    Principal,
    Refused,
    Statement,
    Unavailable,
    Unsupported,
    Violation,
)
from arras.fakes import FakeAccess, MemoryReplica, MemoryStore
from arras.fakes_weft import ENTITY, WEFT
from arras.results import BackendInfo, WeftSupport
from test_core import doc

SQL = "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
COUNT = "SELECT u.name, COUNT(*) FROM catalog.UseCase u GROUP BY u.name ORDER BY u.name LIMIT 100"


class Scripted:
    """`query` raises `script` when it is set; every call is logged as (operation, backend)."""

    log: list[tuple[str, str]]
    reached_for: list[Principal]
    script: Exception | None = None
    unreadable: frozenset[str] = frozenset()  # types it declares `read=False` for

    def query(self, principal: Principal, module: str, statement: Any, **kw: Any) -> Any:
        self.log.append(("query", self.name))  # type: ignore[attr-defined]
        if self.script is not None:
            raise self.script
        return super().query(principal, module, statement, **kw)  # type: ignore[misc]

    def reached(self, principal: Principal, token: str) -> bool:
        self.log.append(("reached", self.name))  # type: ignore[attr-defined]
        self.reached_for.append(principal)  # type: ignore[attr-defined]
        return super().reached(principal, token)  # type: ignore[misc]

    def describe(self) -> BackendInfo:
        info: BackendInfo = super().describe()  # type: ignore[misc]
        for t in self.unreadable:
            info.capabilities[t] = type(info.capabilities[t])(read=False)
        return info


class Store(Scripted, MemoryStore):
    pass


class Replica(Scripted, MemoryReplica):
    pass


class Rig:
    """A record store `primary` and replicas `first` and `second`, fed, with one use case."""

    def __init__(self, **kw: Any) -> None:
        self.log: list[tuple[str, str]] = []
        self.reached_for: list[Principal] = []
        self.access = FakeAccess()
        self.primary = Store(self.access, "primary")
        self.first = Replica(self.primary, self.access, "first")
        self.second = Replica(self.primary, self.access, "second")
        for b in (self.primary, self.first, self.second):
            b.log = self.log
            b.reached_for = self.reached_for
        self.root = self.access.grant("root", "*", "read", "write", "schema", admin=True)
        self.alice = self.access.grant("alice", "catalog", "read", "write")
        kw.setdefault("default_placement", Placement("primary", ("first", "second")))
        self.backends = {"primary": self.primary, "first": self.first, "second": self.second}
        self.h = Arras.start(self.backends, admin=self.root, **kw)
        self.h.session(self.root).registry().register(doc())
        self.o = self.h.session(self.alice)
        self.receipt = self.o.invoke("catalog.AddUseCase", {"code": "a", "name": "A"})
        self.feed()
        self.log.clear()

    def feed(self) -> None:
        self.first.feed()
        self.second.feed()

    def asked(self, op: str = "query") -> list[str]:
        return [name for o, name in self.log if o == op]


@pytest.fixture
def rig() -> Rig:
    return Rig()


# -- the module the caller names


def test_latest_is_the_record_store_and_bulk_the_first_replica(rig: Rig) -> None:
    ans = rig.o.query("catalog", SQL)
    assert ans.freshness.backend == "primary" and [r["code"] for r in ans.rows] == ["a"]
    assert rig.asked() == ["primary"]  # one backend asked, once
    bulk = rig.o.query("catalog", SQL, consistency="bulk")
    assert bulk.freshness.backend == "first" and bulk.revision["primary"] == 1
    assert rig.asked() == ["primary", "first"]


@pytest.mark.parametrize("module", ["nomodule", "other"])
def test_a_module_that_does_not_exist_is_unknown_and_no_backend_runs_it(
    rig: Rig, module: str
) -> None:
    with pytest.raises(Invalid) as e:
        rig.o.query(module, SQL)
    assert [(v.path, v.code) for v in e.value.violations] == [("module", "unknown_type")]
    assert rig.asked() == []


def test_a_module_the_principal_may_not_read_is_unknown_not_refused(rig: Rig) -> None:
    """`unknown_type` comes before a refusal that depends on the type, so an unreadable module
    never answers `Unsupported` and its existence is not revealed."""
    for b in (rig.primary, rig.first, rig.second):
        b.weft = WeftSupport(WEFT.version, (ENTITY,))  # counts are refused everywhere
    zed = rig.access.grant("zed", "other", "read")
    for consistency in ("latest", "bulk"):
        with pytest.raises(Invalid) as e:
            rig.h.session(zed).query("catalog", COUNT, consistency=consistency)
        assert [v.code for v in e.value.violations] == ["unknown_type"]
    assert rig.asked() == []
    with pytest.raises(Invalid) as e:  # and the backend says the same when it is asked directly
        rig.primary.query(zed, "catalog", Statement(COUNT), limit=5)
    assert e.value.violations[0].code == "unknown_type"


def test_a_statement_reading_outside_the_named_module_is_the_backends_unsupported(
    rig: Rig,
) -> None:
    with pytest.raises(Unsupported) as e:
        rig.o.query("catalog", "SELECT t.code FROM other.Thing t ORDER BY t.code LIMIT 100")
    assert "outside module catalog" in e.value.construct
    assert rig.asked() == ["primary"]


def test_a_statement_or_parameter_fault_is_raised_from_the_serving_backend(rig: Rig) -> None:
    with pytest.raises(Invalid) as e:
        rig.o.query(
            "catalog",
            "SELECT u.code FROM catalog.UseCase u WHERE u.code = :k ORDER BY u.code LIMIT 100",
        )
    assert e.value.violations[0].code == "missing_param"
    rig.first.script = Invalid([Violation("params.k", "missing_param", "no value for :k")])
    with pytest.raises(Invalid):  # in bulk too: only Unsupported falls through
        rig.o.query("catalog", SQL, consistency="bulk")
    assert rig.asked() == ["primary", "first"]


def test_a_refused_token_is_raised(rig: Rig) -> None:
    rig.first.script = Refused("first", "query", "token_expired")
    with pytest.raises(Refused) as e:
        rig.o.query("catalog", SQL, consistency="bulk")
    assert e.value.reason == "token_expired" and rig.asked() == ["first"]
    rig.first.script = None
    rig.access.expire(rig.alice.token)  # the real thing: the backends refuse the token
    with pytest.raises(Refused):
        rig.o.query("catalog", SQL)


# -- outages


def test_bulk_reaches_a_replica_while_the_record_store_is_down(rig: Rig) -> None:
    rig.primary.available = False
    ans = rig.o.query("catalog", SQL, consistency="bulk")
    assert ans.freshness.backend == "first" and [r["code"] for r in ans.rows] == ["a"]
    with pytest.raises(Unavailable) as e:  # latest with the record store down names it
        rig.o.query("catalog", SQL)
    assert e.value.backend == "primary"


def test_bulk_raises_a_replica_outage_rather_than_skipping_it(rig: Rig) -> None:
    rig.first.available = False
    with pytest.raises(Unavailable) as e:
        rig.o.query("catalog", SQL, consistency="bulk")
    assert e.value.backend == "first"
    assert "second" not in rig.asked() and "primary" not in rig.asked()


def test_a_reader_the_host_did_not_configure_is_unavailable() -> None:
    rig = Rig()
    rig.h.default_placement = Placement("primary", ("ghost", "first"))  # the host changed it
    assert rig.o.query("catalog", SQL).freshness.backend == "primary"  # latest does not ask it
    with pytest.raises(Unavailable) as e:
        rig.o.query("catalog", SQL, consistency="bulk")
    assert (e.value.backend, e.value.reason) == ("ghost", "not_configured")
    rig.h.placements["catalog"] = Placement("nowhere", ("first",))
    with pytest.raises(Unavailable) as e:  # latest from a record store the host did not configure
        rig.o.query("catalog", SQL)
    assert (e.value.backend, e.value.reason) == ("nowhere", "not_configured")


# -- bulk: which replica


def test_a_replica_that_answers_unsupported_falls_through_to_the_next(rig: Rig) -> None:
    rig.first.script = Unsupported("profile", ["x"])
    assert rig.o.query("catalog", SQL, consistency="bulk").freshness.backend == "second"
    rig.second.script = Unsupported("profile", ["x"])
    ans = rig.o.query("catalog", SQL, consistency="bulk")  # no replica serves it: the record store
    assert (ans.freshness.backend, ans.freshness.consistency) == ("primary", "bulk")
    assert rig.asked() == ["first", "second", "first", "second", "primary"]


def test_unsupported_from_the_record_store_is_raised(rig: Rig) -> None:
    rig.primary.script = Unsupported("JOIN", ["primary serves no joins"])
    with pytest.raises(Unsupported) as e:
        rig.o.query("catalog", SQL)
    assert e.value.supported == ["primary serves no joins"]


def test_bulk_passes_over_a_replica_that_reads_none_of_the_modules_types(rig: Rig) -> None:
    rig.first.unreadable = frozenset({t.name for t in rig.primary.modules["catalog"].entity_types})
    assert rig.o.query("catalog", SQL, consistency="bulk").freshness.backend == "second"
    assert rig.asked() == ["second"]  # it was not asked to run the statement
    rig.first.modules.clear()  # and one that holds no types of the module at all
    rig.first.unreadable = frozenset()
    assert rig.o.query("catalog", SQL, consistency="bulk").freshness.backend == "second"


def test_a_replica_that_declares_fewer_profiles_refuses_and_the_next_serves(rig: Rig) -> None:
    for r in (rig.first, rig.second):
        r.weft = WeftSupport(WEFT.version, (ENTITY,))
    ans = rig.o.query("catalog", COUNT, consistency="bulk")
    assert ans.freshness.backend == "primary" and ans.rows == ({"name": "A", "count": 1},)
    assert rig.o.query("catalog", SQL, consistency="bulk").freshness.backend == "first"


def test_no_backend_declares_counts_so_a_count_is_unsupported(rig: Rig) -> None:
    for b in (rig.primary, rig.first, rig.second):
        b.weft = WeftSupport(WEFT.version, (ENTITY,))
    for consistency in ("latest", "bulk"):
        with pytest.raises(Unsupported) as e:
            rig.o.query("catalog", COUNT, consistency=consistency)
        assert e.value.construct == "profile count-summary"


# -- at_least: the wait runs on each backend before it is asked


def test_reached_is_asked_as_the_reading_person() -> None:
    rig = Rig()
    rig.o.query("catalog", SQL, consistency="bulk", at_least=rig.receipt.token)
    assert rig.reached_for and all(p.user == "alice" for p in rig.reached_for)


def test_at_least_waits_on_the_chosen_backend_then_queries() -> None:
    rig = Rig(wait_bound=0.0)
    token = rig.o.invoke("catalog.AddUseCase", {"code": "b", "name": "B"}).token
    rig.log.clear()
    with pytest.raises(NotYetCurrent) as e:  # first has not reached it; it is not passed over
        rig.o.query("catalog", SQL, consistency="bulk", at_least=token)
    assert e.value.backend == "first"
    assert rig.log == [("reached", "first")]
    rig.feed()
    rig.log.clear()
    ans = rig.o.query("catalog", SQL, consistency="bulk", at_least=token)
    assert [r["code"] for r in ans.rows] == ["a", "b"]
    assert rig.log == [("reached", "first"), ("query", "first")]


def test_a_fall_through_waits_again_on_the_next_backend(rig: Rig) -> None:
    rig.first.script = Unsupported("profile", ["x"])
    rig.o.query("catalog", SQL, consistency="bulk", at_least=rig.receipt.token)
    assert rig.log == [
        ("reached", "first"),
        ("query", "first"),
        ("reached", "second"),
        ("query", "second"),
    ]


def test_a_replica_that_holds_the_module_but_not_the_type_falls_through(rig: Rig) -> None:
    """CONTRACT-004: a module the backend holds with a type it does not hold is `Unsupported`, not
    `Invalid`, so `bulk` passes to the next reader."""
    from dataclasses import replace

    held = rig.first.modules["catalog"]
    rig.first.modules["catalog"] = replace(
        held, entity_types=tuple(t for t in held.entity_types if t.local_name != "Solution")
    )
    sql = "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 5"
    with pytest.raises(Unsupported) as e:
        rig.first.query(rig.alice, "catalog", Statement(sql), limit=5)
    assert "catalog.Solution" in e.value.construct
    rig.log.clear()
    assert rig.o.query("catalog", sql, consistency="bulk").freshness.backend == "second"
    assert rig.asked() == ["first", "second"]
