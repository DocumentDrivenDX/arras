# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
import json
from pathlib import Path
from typing import Any

import pytest

from arras import (
    Arras,
    Invalid,
    NotYetCurrent,
    PreconditionFailed,
    Principal,
    Refused,
    Unavailable,
    Unsupported,
)
from arras.actions import Create, Ref
from arras.fakes import FakeAccess, MemoryReplica, MemoryStore
from arras.model import Placement

EXAMPLE = Path(__file__).parents[1] / "docs/helix/02-design/contracts/examples/catalog.umf.json"
CONSTRAINED_TEXT = EXAMPLE.read_text()


def plain_test_document() -> dict[str, Any]:
    """Use a named, unconstrained derivative for generic CRUD tests; never rewrite source bytes."""
    d = json.loads(CONSTRAINED_TEXT)
    for element in d["modules"][0]["elements"]:
        facets = element.get("facets")
        if isinstance(facets, dict) and set(facets) == {"length"}:
            element.pop("facets")
    return d


ADD_UC = {
    "id": "AddUseCase",
    "description": "Add a use case",
    "inputs": [
        {"name": "code", "type": {"kind": "scalar", "name": "string"}},
        {"name": "name", "type": {"kind": "scalar", "name": "string"}},
    ],
    "preconditions": [
        {
            "id": "fresh",
            "reason": "already there",
            "predicate": {"op": "absent", "type": "UseCase", "key": {"input": "code"}},
        }
    ],
    "effects": [
        {
            "op": "create",
            "type": "UseCase",
            "key": {"input": "code"},
            "properties": {"name": {"input": "name"}},
        }
    ],
}
HANDLED = {
    "id": "Handled",
    "inputs": [{"name": "code", "type": {"kind": "scalar", "name": "string"}}],
    "handler": "handled",
}


def doc(**mod: Any) -> str:
    d = plain_test_document()
    d["modules"][0]["actions"] = [ADD_UC, HANDLED]
    d["modules"][0].update(mod)
    return json.dumps(d)


class World:
    def __init__(self, *, registered: bool = True, **kw: Any) -> None:
        self.access = FakeAccess()
        self.auth = MemoryStore(self.access, "primary")
        self.replica = MemoryReplica(self.auth, self.access, "mirror")
        self.root = self.access.grant("root", "catalog", "read", "write", "schema", admin=True)
        self.alice = self.access.grant("alice", "catalog", "read", "write")
        self.carol = self.access.grant("carol", "catalog", "read")
        kw.setdefault("default_placement", Placement("primary", ("mirror",)))
        self.h = Arras.start({"primary": self.auth, "mirror": self.replica}, **kw)
        self.o = self.h.session(self.alice)  # a person: reads and acts
        self.a = self.h.session(self.root)  # the administrator: registry, handlers, imports
        if registered:
            self.a.registry().register(doc())

    def read(self, sql: str, who: Principal | None = None, module: str = "catalog", **kw: Any):
        return self.h.session(who or self.carol).query(module, sql, **kw)


@pytest.fixture
def w() -> World:
    return World()


def add(w: World, code: str):
    return w.o.invoke("catalog.AddUseCase", {"code": code, "name": code.upper()})


def test_describe_states_capabilities_and_backend_status(w: World) -> None:
    [m] = w.h.session(w.carol).describe()
    assert m.name == "catalog" and m.revision["primary"] == 1
    t = m.entity_type("UseCase")
    assert t is not None
    assert set(t.capabilities) == {"primary", "mirror"}
    assert t.capabilities["primary"].mutable and not t.capabilities["mirror"].mutable
    assert m.status["primary"].available and m.status["mirror"].available
    assert [a.name for a in m.actions] == ["catalog.AddUseCase", "catalog.Handled"]
    with pytest.raises(Invalid):
        w.o.describe("nope")
    assert w.h.session(w.access.grant("zed", "other", "read")).describe() == []


def test_latest_reads_the_record_store_and_bulk_the_replica(w: World) -> None:
    r = add(w, "uc-1")
    sql = "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
    latest = w.read(sql)
    assert [x["code"] for x in latest.rows] == ["uc-1"]
    assert (latest.freshness.backend, latest.freshness.consistency) == ("primary", "latest")
    assert latest.freshness.as_of.value == r.token and latest.revision["primary"] == 1
    with pytest.raises(Unavailable) as e:  # a replica that was never fed has no position to state
        w.read(sql, consistency="bulk")
    assert e.value.backend == "mirror" and "no position" in e.value.detail
    w.replica.feed()
    w.auth.available = True
    bulk = w.read(sql, consistency="bulk")
    assert len(bulk.rows) == 1 and bulk.freshness.backend == "mirror"
    assert bulk.freshness.consistency == "bulk" and bulk.freshness.as_of.value == r.token
    add(w, "uc-2")
    assert (
        len(w.read(sql, consistency="bulk").rows) == 1
    )  # behind until it is fed again, and says so


def test_bulk_falls_to_the_record_store_when_no_replica_serves_the_type(w: World) -> None:
    add(w, "uc-1")
    w.replica.modules.clear()  # the replica holds no types
    ans = w.read(
        "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100", consistency="bulk"
    )
    assert ans.freshness.backend == "primary" and ans.freshness.consistency == "bulk"


def test_latest_never_comes_from_a_replica(w: World) -> None:
    add(w, "uc-1")
    w.replica.feed()
    w.auth.available = False
    with pytest.raises(Unavailable) as e:
        w.read("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100")
    assert e.value.backend == "primary"
    # and a replica answer is not offered when the record store is down for `latest`
    assert w.read(
        "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100", consistency="bulk"
    ).rows


def test_bulk_does_not_become_latest_when_the_replica_is_down(w: World) -> None:
    w.replica.available = False
    with pytest.raises(Unavailable) as e:
        w.read("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100", consistency="bulk")
    assert e.value.backend == "mirror"


def test_at_least_waits_then_answers_or_raises(w: World) -> None:
    r = add(w, "uc-1")
    sql = "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
    with pytest.raises(NotYetCurrent) as e:
        w.read(sql, consistency="bulk", at_least=r.token)
    assert (e.value.token, e.value.backend) == (r.token, "mirror")
    assert w.read(sql, at_least=r.token).rows  # the record store has always reached it
    slept: list[float] = []

    holder: list[World] = []

    def feed_on_sleep(s: float) -> None:
        slept.append(s)
        holder[0].replica.feed()

    w2 = World(wait_bound=1.0, sleep=feed_on_sleep)
    holder.append(w2)
    r2 = add(w2, "uc-1")
    ans = w2.read(sql, consistency="bulk", at_least=r2.token)
    assert ans.rows and slept


def test_empty_refused_and_unavailable_are_three_outcomes(w: World) -> None:
    sql = "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
    assert w.read(sql).rows == ()
    stranger = w.access.grant("dave", "elsewhere", "read")
    assert w.h.session(stranger).describe() == []  # a module it cannot read is not there at all
    w.access.expire("token-carol")
    with pytest.raises(Refused):
        w.read(sql)
    w.auth.available = False
    with pytest.raises(Unavailable):
        w.read(sql, who=w.alice)


def test_no_token_is_refused_before_any_backend_call(w: World) -> None:
    calls: list[str] = []
    real = w.auth.query

    def spy(*a: Any, **k: Any):
        calls.append("query")
        return real(*a, **k)

    w.auth.query = spy  # type: ignore
    anon = w.h.session(Principal("alice", ""))
    for op in (
        lambda: anon.query(
            "catalog", "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
        ),
        lambda: anon.describe(),
        lambda: anon.invoke("catalog.AddUseCase", {}),
        lambda: anon.registry().register(doc()),
    ):
        with pytest.raises(Refused):
            op()
    assert calls == []


def test_query_bounds_and_errors(w: World) -> None:
    sql = "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
    for kw in ({"limit": 0}, {"limit": 101}, {"limit": True}, {"consistency": "soon"}):
        with pytest.raises(Invalid):
            w.read(sql, **kw)  # type: ignore
    with pytest.raises(Unsupported):
        w.read("SELECT u.code FROM catalog.UseCase u ORDER BY u.name")
    for kw, path in (({"sql": ""}, "sql"), ({"sql": 5}, "sql"), ({"params": [1]}, "params")):
        args = {"sql": "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 5", **kw}
        with pytest.raises(Invalid) as e:  # checked before any backend is asked, never a TypeError
            w.h.session(w.carol).query("catalog", args.pop("sql"), **args)  # type: ignore[arg-type]
        assert [v.path for v in e.value.violations] == [path]
    for module in ("", 5, None):  # the module the statement reads is named, as text
        with pytest.raises(Invalid) as e:
            w.read("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100", module=module)  # type: ignore[arg-type]
        assert e.value.violations[0].path == "module"
    with pytest.raises(Unsupported) as u:  # the module is held; a type it does not hold is unserved
        w.read("SELECT u.code FROM catalog.Nope u ORDER BY u.code LIMIT 100")
    assert "catalog.Nope" in u.value.construct
    with pytest.raises(Unsupported) as u:  # a page orders by the key and names a LIMIT
        w.read("SELECT u.code FROM catalog.UseCase u")
    assert "ORDER BY" in u.value.construct


def test_paging_through_the_interface(w: World) -> None:
    for i in range(3):
        add(w, f"uc-{i}")
    first = "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 2"
    following = "SELECT u.code FROM catalog.UseCase u WHERE u.code > :last ORDER BY u.code LIMIT 2"
    p1 = w.read(first)
    p2 = w.read(following, params={"last": p1.rows[-1]["code"]})
    assert [r["code"] for r in (*p1.rows, *p2.rows)] == ["uc-0", "uc-1", "uc-2"]
    capped = w.read("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100", limit=2)
    assert len(capped.rows) == 2 and capped.truncated  # the cap cut it; the statement continues
    assert not hasattr(capped, "next_cursor")


def test_actions_validate_invoke_batch_and_idempotency(w: World) -> None:
    v = w.o.validate("catalog.AddUseCase", {"code": "a", "name": "A"})
    assert v.ok and len(v.effects) == 1
    bad = w.o.validate("catalog.AddUseCase", {"code": "bad key!"})
    assert not bad.ok and {x.code for x in bad.violations} == {"required"}
    first = w.o.invoke("catalog.AddUseCase", {"code": "a", "name": "A"}, idempotency_key="k")
    again = w.o.invoke("catalog.AddUseCase", {"code": "a", "name": "A"}, idempotency_key="k")
    assert again.replayed and again.token == first.token
    b = w.o.invoke_batch(
        "catalog.AddUseCase",
        [{"code": "b", "name": "B"}, {"code": "a", "name": "A"}, {"code": "c", "name": "C"}],
    )
    assert (b.succeeded, b.failed) == (2, 1)
    with pytest.raises(Invalid) as e:
        w.o.invoke_batch("catalog.AddUseCase", [{"code": "d", "name": "D"}, {"code": "e!"}])
    assert all(v.path.startswith("items[1].") for v in e.value.violations)
    with pytest.raises(Invalid):
        w.o.invoke_batch("catalog.AddUseCase", [])
    ans = w.read("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100", at_least=b.token)
    assert [r["code"] for r in ans.rows] == ["a", "b", "c"]


def test_reader_cannot_invoke_and_unknown_actions_are_invalid(w: World) -> None:
    with pytest.raises(Refused):
        w.h.session(w.carol).invoke("catalog.AddUseCase", {"code": "a", "name": "A"})
    with pytest.raises(Invalid):
        w.o.invoke("catalog.Nope", {})
    with pytest.raises(Invalid):
        w.o.invoke("nomod.Nope", {})


def test_handlers_supply_effects_the_same_way(w: World) -> None:
    with pytest.raises(Unsupported):
        w.o.invoke("catalog.Handled", {"code": "h"})  # not bound yet

    def handled(inputs, ctx):
        assert (
            ctx.query(
                "catalog", "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
            ).rows
            == ()
        )
        return [Create(Ref("catalog.UseCase", inputs["code"]), {"name": "from handler"})]

    w.a.registry().bind_handler("catalog.Handled", handled)
    r = w.o.invoke("catalog.Handled", {"code": "h"})
    assert r.created == 1
    row = w.read(
        "SELECT u.name FROM catalog.UseCase u WHERE u.code = 'h' ORDER BY u.code LIMIT 100"
    ).rows[0]
    assert row["name"] == "from handler"


def test_registry_checks_placement_and_provider_role() -> None:
    reg = World().a.registry()
    unconfigured = World(registered=False, default_placement=Placement("mystery", ("mirror",)))
    with pytest.raises(Invalid) as e:
        unconfigured.a.registry().register(doc())
    assert e.value.violations[0].code == "invalid_placement"
    # a module whose record store is the (reader-only) replica is attached, never registered
    ro = World(registered=False, placement={"catalog": Placement("mirror")})
    with pytest.raises(Invalid) as e:
        ro.a.registry().register(doc())
    assert e.value.violations[0].code == "read_only_module"
    with pytest.raises(Invalid):
        reg.attach(doc())  # a module the record store provides for is registered


def test_read_only_modules_have_no_actions_or_imports() -> None:
    access = FakeAccess()
    auth = MemoryStore(access, "primary")
    replica = MemoryReplica(auth, access, name="mirror")
    alice = access.grant("alice", "catalog", "read", "write")
    root = access.grant("root", "catalog", "read", "write", "schema", admin=True)
    h = Arras.start(
        {"primary": auth, "mirror": replica}, placement={"catalog": Placement("mirror")}
    )
    o = h.session(alice)
    admin = h.session(root)
    d = json.loads(doc())
    d["modules"][0]["actions"] = []
    admin.registry().attach(json.dumps(d))
    assert [m.name for m in o.describe()] == ["catalog"]
    with pytest.raises(Invalid):
        o.invoke("catalog.AddUseCase", {})
    with pytest.raises(Unsupported):
        admin.import_records("catalog", [], load_id="L")


def test_status_never_raises_and_reports_each_backend(w: World) -> None:
    assert all(s.available for s in w.h.status().values())
    w.replica.outage = "migration_failed"
    s = w.h.refresh()
    assert not s["mirror"].available and s["mirror"].reason == "migration_failed"
    w.auth.available = False
    assert w.h.status()["primary"].reason == "unreachable"
    lonely = Arras.start({})
    assert lonely.status() == {} and lonely.migrate().ran is False


def test_import_through_the_session(w: World) -> None:
    r = w.a.import_records(
        "catalog", [{"type": "UseCase", "key": "u1", "properties": {"name": "x"}}], load_id="L1"
    )
    assert r.created == 1
    with pytest.raises(Refused):
        w.h.session(w.carol).import_records("catalog", [], load_id="L2")


def test_an_outage_is_never_reported_as_absence() -> None:
    w = World(placement={"solo": Placement("primary")})
    w.access.grant("alice", "solo", "read", "write")
    w.access.grant("root", "solo", "read", "write", "schema", admin=True)
    w.a.registry().register(doc(id="solo").replace('"catalog"', '"solo"'))
    w.auth.available = False
    s = w.h.session(w.alice)
    for op in (
        lambda: s.query("solo", "SELECT u.code FROM solo.UseCase u ORDER BY u.code LIMIT 100"),
        lambda: s.describe("solo"),
        lambda: s.invoke("solo.AddUseCase", {"code": "a", "name": "A"}),
        lambda: w.a.import_records("solo", [], load_id="L"),
    ):
        with pytest.raises(Unavailable) as e:
            op()
        assert e.value.backend == "primary"
    shown = s.describe()  # what the replica holds; the status says the record store is down
    assert [m.name for m in shown] == ["catalog"] and not shown[0].status["primary"].available


def test_refused_wins_over_unavailable_when_both_are_reported() -> None:
    w = World()
    w.access.expire("token-carol")
    w.replica.available = False
    with pytest.raises(Refused):
        w.read("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100")


def test_a_faulty_replica_does_not_break_latest_but_stops_bulk() -> None:
    w = World()
    w.replica.available = False
    assert (
        w.read("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100").freshness.backend
        == "primary"
    )
    with pytest.raises(Unavailable) as e:
        w.read("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100", consistency="bulk")
    assert e.value.backend == "mirror"
    assert [m.name for m in w.h.session(w.carol).describe()] == ["catalog"]  # still describes


def test_a_replica_that_refuses_the_statement_does_not_serve_it() -> None:
    from arras import Statement
    from arras.fakes_weft import ENTITY, WEFT
    from arras.results import WeftSupport

    w = World()
    w.replica.weft = WeftSupport(WEFT.version, (ENTITY,))  # it declares no counts
    count = (
        "SELECT u.name, COUNT(*) FROM catalog.UseCase u GROUP BY u.name ORDER BY u.name LIMIT 100"
    )
    w.replica.feed()
    with pytest.raises(Unsupported):  # the refusal comes from the replica's own `query`
        w.replica.query(w.carol, "catalog", Statement(count), limit=5)
    ans = w.read(count, consistency="bulk")
    assert ans.freshness.backend == "primary" and ans.freshness.consistency == "bulk"


def test_a_bulk_answer_states_the_revision_its_backend_holds() -> None:
    w = World()
    w.replica.feed()
    ans = w.read(
        "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100", consistency="bulk"
    )
    assert ans.freshness.backend == "mirror" and ans.revision["primary"] == 1


def test_limit_must_be_an_integer(w: World) -> None:
    with pytest.raises(Invalid):
        w.read("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100", limit="5")  # type: ignore


def test_unknown_actions_have_their_own_code(w: World) -> None:
    with pytest.raises(Invalid) as e:
        w.o.invoke("catalog.Nope", {})
    assert e.value.violations[0].code == "unknown_action"


def test_handler_effects_are_checked_like_declared_ones(w: World) -> None:
    from arras.actions import Delete, Link

    calls: list[int] = []

    def bind(effects):
        def fn(inputs, ctx):
            calls.append(1)
            return effects

        w.a.registry().bind_handler("catalog.Handled", fn)

    cases = [
        [{"op": "create"}],  # not an effect
        [Create(Ref("catalog.UseCase", "h"), {"name": 42})],  # wrong type
        [Create(Ref("catalog.UseCase", "h"), {})],  # missing name
        [Create(Ref("other.Thing", "h"), {"name": "x"})],  # outside the module
        [Create(Ref("catalog.UseCase", "bad key!"), {"name": "x"})],
        [Delete(Ref("other.Thing", "x"))],
        [Link("nope", Ref("catalog.UseCase", "a"), Ref("catalog.UseCase", "b"))],
        [Create(Ref("catalog.UseCase", f"k{i}"), {"name": "x"}) for i in range(1001)],
    ]
    for effects in cases:
        bind(effects)
        with pytest.raises(Invalid):
            w.o.invoke("catalog.Handled", {"code": "h"})
        v = w.o.validate("catalog.Handled", {"code": "h"})
        assert not v.ok and v.violations
    bind("not a list")
    with pytest.raises(Invalid):
        w.o.invoke("catalog.Handled", {"code": "h"})
    calls.clear()
    bind([])
    with pytest.raises(Invalid):  # the handler does not run when the inputs are already wrong
        w.o.invoke("catalog.Handled", {})
    assert calls == []


def test_binding_a_handler_is_checked(w: World) -> None:
    reg = w.a.registry()
    for name in ("catalog.Nope", "catalog.AddUseCase"):  # unknown; declares no handler
        with pytest.raises(Invalid):
            reg.bind_handler(name, lambda i, c: [])
    with pytest.raises(Refused):
        w.h.session(Principal("alice", "")).registry().bind_handler(
            "catalog.Handled", lambda i, c: []
        )


def test_register_reports_replicas_it_could_not_tell() -> None:
    w = World()
    bob = w.access.grant("bob", "catalog", "read", "write")  # a writer, not an administrator
    with pytest.raises(Refused):
        w.h.session(bob).registry().register(doc())  # the registry is the host's administrator's
    r = w.h.session(w.root).registry().register(doc())
    assert not r.changed  # already registered, unchanged
    w2 = World()
    w2.access.grant("bob", "catalog", "read", "write", "schema")
    changed = doc().replace('"UseCase.name"', '"UseCase.name"')
    d = json.loads(changed)
    d["modules"][0]["elements"][0]["extensions"]["umf.ddd"]["fields"]["note"] = {
        "type": {"kind": "scalar", "name": "string"},
        "cardinality": "optional",
    }
    d["modules"][0]["elements"][0]["members"].append(
        {"module": "catalog", "element": "UseCase.note"}
    )
    d["modules"][0]["elements"].append(
        {
            "id": "UseCase.note",
            "kind": "field",
            "nullability": "absent-allowed",
            "cardinality": "one",
            "scalarType": "string",
            "extensions": {},
        }
    )
    host_admin = Principal("bob", "token-bob", admin=True)  # the host says so; the replica decides
    r = w2.h.session(host_admin).registry().register(json.dumps(d))
    assert r.changed and r.revision["primary"] == 2
    assert any("replica mirror not attached" in x for x in r.report)


@pytest.mark.parametrize("declaration", [None, [], {}, {"version": "0.2.0"}, {"version": 1}])
def test_invalid_ddd_vocabulary_cannot_replace_registered_module(declaration: Any) -> None:
    w = World()
    add(w, "preserved")
    accepted_bytes = w.auth.documents["catalog"]
    accepted_revision = w.auth.catalog_revision
    accepted_rows = w.auth.state.entities.copy()

    replacement = json.loads(doc())
    replacement["vocabularies"]["umf.ddd"] = declaration
    with pytest.raises(Invalid) as e:
        w.a.registry().register(json.dumps(replacement))

    assert any(
        v.path == "vocabularies.umf.ddd.version" and v.code == "invalid_document"
        for v in e.value.violations
    )
    assert w.auth.documents["catalog"] == accepted_bytes
    assert w.auth.catalog_revision == accepted_revision
    assert w.auth.state.entities == accepted_rows


def test_register_requires_readable_modules_and_attach_has_no_actions(w: World) -> None:
    d = json.loads(doc())
    d["modules"][0]["relationships"][0]["target"][0] = {"module": "secret", "element": "T"}
    with pytest.raises(Invalid) as e:
        w.a.registry().register(json.dumps(d))
    assert e.value.violations[0].code == "unreadable_module"
    ro = World(registered=False, placement={"catalog": Placement("mirror")})
    with pytest.raises(Invalid) as e:
        ro.a.registry().register(doc())
    assert e.value.violations[0].code == "read_only_module"


def test_a_reader_is_named_once() -> None:
    w = World(registered=False, placement={"catalog": Placement("mirror", ("primary", "primary"))})
    with pytest.raises(Invalid) as e:
        w.a.registry().register(doc())
    assert any(v.code == "invalid_placement" for v in e.value.violations)


def test_batches_atomic_stop_and_bound(w: World) -> None:
    r = w.o.invoke_batch(
        "catalog.AddUseCase", [{"code": "a", "name": "A"}, {"code": "b", "name": "B"}], atomic=True
    )
    assert r.atomic and len({i.receipt.token for i in r.items if i.receipt}) == 1
    r = w.o.invoke_batch(
        "catalog.AddUseCase",
        [{"code": "a", "name": "A"}, {"code": "c", "name": "C"}],
        stop_on_error=True,
    )
    assert len(r.items) == 1 and r.failed == 1
    w.a.registry().bind_handler(
        "catalog.Handled",
        lambda i, c: [Create(Ref("catalog.UseCase", f"h{n}"), {"name": "x"}) for n in range(600)],
    )
    with pytest.raises(Invalid) as e:
        w.o.invoke_batch("catalog.Handled", [{"code": "1"}, {"code": "2"}], atomic=True)
    assert e.value.violations[0].code == "bound"


def test_status_is_total() -> None:
    from arras.errors import Unavailable as U

    class Boom:
        def status(self):
            raise OSError("socket closed")

    class Denied:
        def status(self):
            raise Refused("x", "status")

    class Busy:
        def status(self):
            raise U("x", "busy", "locked")

    s = Arras.start({"a": Boom(), "b": Denied(), "c": Busy()}).status()  # type: ignore
    assert s["a"].reason == "unreachable" and "OSError" in s["a"].detail
    assert s["b"].reason == "access_denied"
    assert s["c"].reason == "unreachable" and "busy" in s["c"].detail


def test_close_releases_what_arras_holds(w: World) -> None:
    w.h.close()
    assert w.h.status() == {}


# -- the administrative principal and the person are different (CONTRACT-005, US-049-AC3)
def test_the_administrative_principal_is_refused_for_reads_and_actions(w: World) -> None:
    for op in (
        lambda: w.a.query(
            "catalog", "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
        ),
        lambda: w.a.describe(),
        lambda: w.a.modules(),
        lambda: w.a.invoke("catalog.AddUseCase", {"code": "x", "name": "x"}),
        lambda: w.a.validate("catalog.AddUseCase", {"code": "x", "name": "x"}),
        lambda: w.a.invoke_batch("catalog.AddUseCase", [{"code": "x", "name": "x"}]),
    ):
        with pytest.raises(Refused) as e:
            op()
        assert e.value.backend == "arras"
    assert (
        w.read("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100").rows == ()
    )  # nothing was written
    with pytest.raises(Refused):  # and a person cannot do the administrator's work
        w.o.registry().register(doc())
    with pytest.raises(Refused):
        w.o.import_records("catalog", [], load_id="L")


def test_a_person_with_no_replica_token_is_refused_by_it_and_the_record_store_is_unaffected() -> (
    None
):
    store_access, replica_access = FakeAccess(), FakeAccess()
    auth = MemoryStore(store_access, "primary")
    replica = MemoryReplica(auth, replica_access, "mirror")
    root = store_access.grant("root", "catalog", "read", "write", "schema", admin=True)
    replica_access.grant("root", "catalog", "read", "write", "schema", admin=True)
    carol = store_access.grant(
        "carol", "catalog", "read"
    )  # a token for the record store, and none for the replica
    h = Arras.start(
        {"primary": auth, "mirror": replica},
        default_placement=Placement("primary", ("mirror",)),
    )
    h.session(root).registry().register(doc())
    o = h.session(carol)
    sql = "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
    with pytest.raises(Refused) as e:
        o.query("catalog", sql, consistency="bulk")
    assert e.value.backend == "mirror"
    assert o.query("catalog", sql).freshness.backend == "primary"  # the refusal does not spread
    assert [m.name for m in o.describe()] == [
        "catalog"
    ]  # describe still answers from the record store


def test_a_validation_does_not_reserve_the_state_it_saw(w: World) -> None:
    v = w.o.validate("catalog.AddUseCase", {"code": "late", "name": "L"})
    assert v.ok
    w.o.invoke("catalog.AddUseCase", {"code": "late", "name": "other"})  # state changes in between
    with pytest.raises(PreconditionFailed):
        w.o.invoke("catalog.AddUseCase", {"code": "late", "name": "L"})  # invoke checks again
    assert not w.o.validate("catalog.AddUseCase", {"code": "late", "name": "L"}).ok


def test_a_statement_built_from_describe_is_accepted_by_query(w: World) -> None:
    w.o.invoke("catalog.AddUseCase", {"code": "d1", "name": "D"})
    for m in w.o.describe():
        for t in m.entity_types:
            caps = t.capabilities["primary"]
            cols = ", ".join(f"x.{c}" for c in caps.columns)
            assert (
                w.o.query(
                    m.name, f"SELECT {cols} FROM {t.name} x ORDER BY x.{t.key} LIMIT 100"
                ).rows
                is not None
            )
            for rel in caps.relationships:
                w.o.query(
                    m.name,
                    f"SELECT x.{t.key} FROM {t.name} x WHERE HAS_RELATED(x.{rel}, KEY('none'))"
                    f" ORDER BY x.{t.key} LIMIT 100",
                )
                w.o.query(
                    m.name,
                    f"SELECT x.{t.key}, RELATED_KEYS(x.{rel}, 5) FROM {t.name} x ORDER BY x.{t.key} LIMIT 9",
                )
            if caps.count and caps.columns:
                w.o.query(
                    m.name,
                    f"SELECT x.{caps.columns[0]}, COUNT(*) FROM {t.name} x GROUP BY x.{caps.columns[0]}"
                    f" ORDER BY x.{caps.columns[0]} LIMIT 100",
                )


def test_reads_write_nothing_and_the_public_operations_are_the_known_ones(w: World) -> None:
    import inspect

    from arras.core import Ontology, Registry

    public = {
        n for n, f in inspect.getmembers(Ontology, inspect.isfunction) if not n.startswith("_")
    }
    guards = {"require_admin", "require_token", "require_user"}
    writers = {"execute", "invoke", "invoke_batch", "import_records", "registry", "schema"}
    reads = {
        "describe",
        "modules",
        "query",
        "validate",
        "changes",
        "loads",
        "document",
        "view_of",
        "search",
        "export_records",
    }
    assert public - guards == writers | reads
    registry_ops = {
        n for n, f in inspect.getmembers(Registry, inspect.isfunction) if not n.startswith("_")
    }
    assert registry_ops == {"register", "attach", "bind_handler"}
    w.o.invoke("catalog.AddUseCase", {"code": "r1", "name": "R"})
    before = (w.auth.state.seq, len(w.auth.state.entities), dict(w.auth._journal))
    w.o.describe()
    w.o.modules()
    w.o.query("catalog", "SELECT u.* FROM catalog.UseCase u ORDER BY u.code LIMIT 100")
    w.o.validate("catalog.AddUseCase", {"code": "r2", "name": "R"})
    w.o.document("catalog")
    assert (w.auth.state.seq, len(w.auth.state.entities), dict(w.auth._journal)) == before


def test_the_host_names_its_administrator_and_a_flag_is_not_trusted() -> None:
    access = FakeAccess()
    auth = MemoryStore(access, "primary")
    root = access.grant("root", "catalog", "read", "write", "schema", admin=True)
    alice = access.grant("alice", "catalog", "read", "write")
    h = Arras.start({"primary": auth}, admin=root, default_placement=Placement("primary"))
    h.session(root).registry().register(doc())
    forged = Principal("alice", alice.token, admin=True)  # a person's token with the flag set
    with pytest.raises(Refused):
        h.session(forged).registry().register(doc())
    with pytest.raises(Refused):
        h.session(forged).import_records("catalog", [], load_id="L")
    unflagged = Principal("root", root.token)  # the administrator's token, flag unset
    with pytest.raises(Refused):
        h.session(unflagged).query(
            "catalog", "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
        )
    with pytest.raises(Refused):
        h.session(unflagged).invoke("catalog.AddUseCase", {"code": "x", "name": "x"})
    other_token = Principal("root", "another-token")
    with pytest.raises(Refused):
        h.session(other_token).describe()  # the administrator's name, however it is presented
    assert (
        h.session(alice)
        .query("catalog", "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100")
        .rows
        == ()
    )


def test_a_registry_that_will_not_hold_still_is_busy(w: World) -> None:
    from dataclasses import replace

    from arras.types import Revision

    real = w.auth.describe
    n = {"i": 0}

    def churn() -> Any:
        n["i"] += 1
        mod = w.auth.modules["catalog"]
        w.auth.modules["catalog"] = replace(
            mod, revision=Revision({"primary": int(mod.revision["primary"] or 0) + 1})
        )
        return real()

    w.auth.describe = churn
    with pytest.raises(Unavailable) as e:
        w.o.describe()
    assert e.value.reason == "busy" and e.value.backend == "arras"


def test_a_handler_reads_as_the_person_and_only_the_administrator_binds_it(w: World) -> None:
    seen: list[str] = []

    def handler(inputs: Any, ctx: Any) -> Any:
        seen.append(ctx.ontology.principal.user)
        ctx.query("catalog", "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100")
        return [Create(Ref("catalog.UseCase", inputs["code"]), {"name": "h"})]

    with pytest.raises(Refused):
        w.o.registry().bind_handler("catalog.Handled", handler)  # a person cannot
    w.a.registry().bind_handler("catalog.Handled", handler)
    w.o.invoke("catalog.Handled", {"code": "hh"})
    assert seen == ["alice"]  # bound by the administrator, run as the person


# -- a provider that keeps no journal answers Unsupported to a group lookup (TR-11)
class _NoJournal(MemoryStore):
    def changes(self, *a: Any, **k: Any):
        raise Unsupported("changes", [])


def test_a_group_lookup_on_providers_that_keep_no_journal_is_unsupported() -> None:
    access = FakeAccess()
    alice = access.grant("alice", "catalog", "read", "write")
    only = Arras.start({"a": _NoJournal(access, "a"), "b": _NoJournal(access, "b")})
    with pytest.raises(Unsupported):
        only.session(alice).changes(group="g-1")  # not "no such change"
    mixed = Arras.start({"a": _NoJournal(access, "a"), "b": MemoryStore(access, "b")})
    assert mixed.session(alice).changes(group="g-1").items == ()  # b keeps one, and holds none


def test_a_group_lookup_with_no_provider_at_all_is_still_no_such_change() -> None:
    access = FakeAccess()
    alice = access.grant("alice", "catalog", "read", "write")
    replica_only = Arras.start({"r": MemoryReplica(MemoryStore(access, "p"), access, "r")})
    with pytest.raises(Invalid):
        replica_only.session(alice).changes(group="g-1")


# -- migrate (CONTRACT-005): the optional adapter call


class _Migrating:
    """A backend with a store to install: it keeps the keyword it was called with."""

    def __init__(self, *results: Any, error: Exception | None = None) -> None:
        self.results = list(results)
        self.error = error
        self.timeouts: list[float | None] = []

    def migrate(self, *, timeout: float | None = None) -> Any:
        self.timeouts.append(timeout)
        if self.error:
            raise self.error
        return self.results.pop(0)

    def status(self) -> Any:
        from arras.results import BackendStatus

        return (
            BackendStatus(False, "migration_failed", "timeout")
            if self.error
            else BackendStatus(True)
        )


def test_arras_migrate_calls_the_adapters_that_migrate_and_passes_the_role_names() -> None:
    from arras import MigrationResult

    memory = MemoryStore(FakeAccess(), "memory")
    installed = MigrationResult(True, "rel", "owner_x", "registrar_x")
    truss = _Migrating(installed, MigrationResult(False, "rel"))
    ar = Arras.start({"memory": memory, "truss": truss})  # type: ignore[dict-item]
    assert ar.migrate(timeout=2.5) == installed  # a backend with no migrate is not asked
    assert ar.migrate() == MigrationResult(False, "rel")
    assert truss.timeouts == [2.5, None]
    assert Arras.start({}).migrate() == MigrationResult(False, "none")


def test_arras_migrate_raises_the_adapters_unavailable_and_status_reports_it() -> None:
    from arras.errors import Unavailable

    failing = _Migrating(error=Unavailable("truss", "migration_failed", "timeout"))
    ar = Arras.start({"truss": failing})  # type: ignore[dict-item]
    with pytest.raises(Unavailable) as caught:
        ar.migrate(timeout=1)
    assert (caught.value.reason, caught.value.detail) == ("migration_failed", "timeout")
    assert ar.status()["truss"].reason == "migration_failed"
