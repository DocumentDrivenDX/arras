# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
import asyncio
import json
import threading
from collections.abc import Mapping
from datetime import UTC
from typing import Any

import pytest

from arras import Arras, Principal
from arras.console import MAX_BODY, create_app, measure
from arras.gqlschema import build_module_schema
from arras.sandbox import Sandbox


class Client:
    def __init__(self, base_path: str = "", box: Any = None) -> None:
        self.box = box or Sandbox().seed()
        self.h = self.box.arras
        self.base = base_path
        self.app = create_app(self.h, principal_for_request=self.who, base_path=base_path)

    def who(self, request) -> Principal | None:
        name = request.headers.get("x-user")
        if name is None:
            return None
        return self.box.principal(name)

    def call(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        user: str | None = "carol",
        ctype: str = "application/json",
        raw: bytes | None = None,
        query: str = "",
        extra: Mapping[str, str | list[str]] | None = None,
    ) -> Any:
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
        headers = [(b"content-type", ctype.encode())]
        if user is not None:
            headers.append((b"x-user", user.encode()))
        for k, v in (extra or {}).items():
            headers += [(k.encode(), x.encode()) for x in ([v] if isinstance(v, str) else v)]
        scope = {
            "type": "http",
            "method": method,
            "path": self.base + path,
            "query_string": query.encode(),
            "headers": headers,
        }
        sent: list[dict] = []

        async def receive() -> dict:
            return {"type": "http.request", "body": data, "more_body": False}

        async def send(msg: dict) -> None:
            sent.append(msg)

        asyncio.run(self.app(scope, receive, send))
        status = sent[0]["status"]
        hdrs = {k.decode(): v.decode() for k, v in sent[0]["headers"]}
        out = sent[1]["body"]
        return (
            status,
            (
                json.loads(out)
                if hdrs.get("content-type", "").startswith("application/json")
                else out.decode()
            ),
            hdrs,
        )

    def gql(self, query: str, path: str = "/graphql/catalog", **kw: Any):
        return self.call("POST", path, {"query": query}, **kw)


@pytest.fixture
def c() -> Client:
    return Client()


def test_meta_schema_lists_what_the_viewer_may_read(c: Client) -> None:
    status, r, _ = c.gql(
        "{ modules { name record replicas revision entityTypes { name key capabilities } actions { name } } status { backend available } }",
        "/graphql",
    )
    assert status == 200 and "errors" not in r
    [m] = r["data"]["modules"]
    assert (m["name"], m["record"], m["replicas"]) == ("catalog", "memory", ["memory_replica"])
    assert m["revision"]["memory"] == 1
    assert {t["name"] for t in m["entityTypes"]} == {"catalog.UseCase", "catalog.Solution"}
    assert {s["backend"] for s in r["data"]["status"]} == {"memory", "memory_replica"}
    _, dave, _ = c.gql("{ modules { name } }", "/graphql", user="dave")
    assert dave["data"]["modules"] == []


def test_entity_by_key_with_relationships_and_freshness(c: Client) -> None:
    q = """{ useCase(key: "uc-pipeline") { key type version code name workArea addressedBy { type key }
             freshness { backend asOf at consistency } } }"""
    status, r, _ = c.gql(q)
    assert status == 200 and "errors" not in r, r
    u = r["data"]["useCase"]
    assert (u["key"], u["type"], u["version"], u["code"]) == (
        "uc-pipeline",
        "catalog.UseCase",
        "1",
        "uc-pipeline",
    )
    assert u["addressedBy"] == [{"type": "catalog.Solution", "key": "sol-1"}]
    assert u["freshness"]["backend"] == "memory" and u["freshness"]["consistency"] == "LATEST"
    assert r["extensions"]["revision"]["memory"] == 1  # the revision the request ran under


def test_absent_entity_is_null_not_an_error(c: Client) -> None:
    status, r, _ = c.gql('{ useCase(key: "nope") { key } }')
    assert status == 200 and r["data"]["useCase"] is None and "errors" not in r


def test_lists_page_filter_and_cost_one_query_per_page(c: Client) -> None:
    status, r, _ = c.gql(
        "{ useCaseList(limit: 1) { items { key } truncated freshness { backend } } }"
    )
    page = r["data"]["useCaseList"]
    assert [i["key"] for i in page["items"]] == ["uc-alerts"] and page[
        "truncated"
    ]  # the cap cut it
    _, r2, _ = c.gql("{ useCaseList(limit: 2) { items { key } truncated } }")
    assert [i["key"] for i in r2["data"]["useCaseList"]["items"]] == ["uc-alerts", "uc-pipeline"]
    assert r2["data"]["useCaseList"]["truncated"] is False
    _, gone, _ = c.gql('{ useCaseList(limit: 1, after: "x") { items { key } } }')
    assert gone["errors"]  # a page is one statement: there is no cursor to pass
    _, nc, _ = c.gql("{ useCaseList(limit: 1) { nextCursor } }")
    assert nc["errors"]
    _, f, _ = c.gql('{ useCaseList(filter: {name: "Alert review"}) { items { key } } }')
    assert [i["key"] for i in f["data"]["useCaseList"]["items"]] == ["uc-alerts"]
    _, f, _ = c.gql('{ useCaseList(filter: {addressedBy: "sol-1"}) { items { key } } }')
    assert [i["key"] for i in f["data"]["useCaseList"]["items"]] == ["uc-pipeline"]
    _, bad, _ = c.gql("{ useCaseList(filter: {bogus: 1}) { items { key } } }")
    assert bad["errors"][0]["extensions"]["code"] == "BAD_QUERY"
    assert bad["data"] == {"useCaseList": None}  # only that field failed


def test_a_relationship_filter_is_sent_as_weft_has_related(c: Client) -> None:
    sent: list[Any] = []
    real = c.box.store.query

    def spy(principal, module, statement, **k):
        sent.append(statement)
        return real(principal, module, statement, **k)

    c.box.store.query = spy
    c.gql('{ useCaseList(filter: {addressedBy: "sol-1", name: "Pipeline"}) { items { key } } }')
    [s] = sent
    # every generated name is a Weft quoted identifier, so a reserved word reads as a name
    assert 'HAS_RELATED(x."addressedBy", KEY(:p0))' in s.sql and 'x."name" = :p1' in s.sql
    assert s.sql.startswith('SELECT x."code" FROM "catalog"."UseCase" x')  # only the key asked for
    assert dict(s.params) == {"p0": "sol-1", "p1": "Pipeline"}
    sent.clear()
    c.gql("{ useCaseList { items { key name addressedBy { key } } } }")
    assert sent[0].sql.startswith('SELECT x."code", x."name", RELATED_KEYS(x."addressedBy", 100)')
    assert 'AS "_addressedBy" FROM "catalog"."UseCase" x' in sent[0].sql  # the keys, in the row
    sent.clear()
    c.gql("{ useCaseList { items { key version } } }")  # a fact: the whole entity
    assert sent[0].sql.startswith(
        'SELECT x.*, RELATED_KEYS(x."addressedBy", 100) AS "_addressedBy"'
    )


def test_a_relationship_field_is_bounded_at_a_hundred_keys(c: Client) -> None:
    """CONTRACT-006: a relationship field holds the first 100 keys in key order; more are read with
    the client's own query."""
    recs: list[dict[str, Any]] = [
        {"type": "Solution", "key": f"s{i:03}", "properties": {"name": "n"}} for i in range(101)
    ]
    recs += [
        {"relationship": "addresses", "source": f"s{i:03}", "target": "uc-alerts"}
        for i in range(101)
    ]
    c.box.store.import_records(
        c.box.people["root"], "catalog", recs, load_id="L", initiated_by="root"
    )
    _, r, _ = c.gql('{ useCase(key: "uc-alerts") { addressedBy { key } } }')
    keys = [x["key"] for x in r["data"]["useCase"]["addressedBy"]]
    assert len(keys) == 100 and keys == sorted(keys) and keys[0] == "s000" and "s100" not in keys


def test_relationships_come_from_the_same_row_not_one_query_per_entity(c: Client) -> None:
    calls: list[str] = []
    real = c.box.store.query

    def spy(*a, **k):
        calls.append(threading.current_thread().name)
        return real(*a, **k)

    c.box.store.query = spy
    _, r, _ = c.gql("{ useCaseList { items { key addressedBy { key } } } }")
    assert len(r["data"]["useCaseList"]["items"]) == 2 and len(calls) == 1
    assert calls[0] != "MainThread"  # executed in a worker, not on the host's event loop


def test_limits(c: Client) -> None:
    for lim in (0, 101, -1):
        _, r, _ = c.gql(f"{{ useCaseList(limit: {lim}) {{ items {{ key }} }} }}")
        assert r["errors"][0]["extensions"]["code"] == "LIMIT_EXCEEDED"
    deep = "{ useCaseList { items { addressedBy { key } } } }"  # depth 4: fine
    assert "errors" not in c.gql(deep)[1]
    too_deep = "{ useCaseList { items { freshness { backend } addressedBy { type } } } }"
    assert "errors" not in c.gql(too_deep)[1]
    nested = "{ a: useCaseList { items { freshness { backend } } } }"
    assert "errors" not in c.gql(nested)[1]
    q = "query Q { useCaseList { items { ...F } } } fragment F on UseCase { addressedBy { ...G } } fragment G on Ref { key }"
    assert measure(__import__("graphql").parse(q), None) == (4, 4)
    fragment_deep = "{ useCaseList { ...A } } fragment A on UseCasePage { items { ...B } } fragment B on UseCase { freshness { ...C } } fragment C on Freshness { backend at consistency asOf }"
    assert measure(__import__("graphql").parse(fragment_deep), None)[0] == 4


def test_depth_and_field_count_are_enforced() -> None:
    import graphql

    deep = "{ a { b { c { d { e { f { g } } } } } } }"
    assert measure(graphql.parse(deep), None)[0] == 7
    many = "{ " + " ".join(f'f{i}: useCase(key: "x") {{ key }}' for i in range(26)) + " }"
    assert measure(graphql.parse(many), None) == (2, 52)


def test_depth_exceeded_and_cost_exceeded_are_answered(c: Client) -> None:
    fields = (
        "{ " + " ".join(f'f{i}: useCase(key: "uc-pipeline") {{ key }}' for i in range(26)) + " }"
    )
    status, r, _ = c.gql(fields)
    assert status == 200 and r["errors"][0]["extensions"]["code"] == "COST_EXCEEDED"
    nested = "{ a { b { c { d { e { f { g } } } } } } }"
    status, r, _ = c.gql(nested)
    assert status == 200 and r["errors"][0]["extensions"]["code"] == "DEPTH_EXCEEDED"
    within = "{ useCaseList { items { freshness { backend } addressedBy { key } } } }"
    assert "errors" not in c.gql(within)[1]


def test_entity_budget(c: Client) -> None:
    recs = [
        {"type": "UseCase", "key": f"u{i:04}", "properties": {"name": "n"}} for i in range(1100)
    ]
    c.box.store.import_records(
        c.box.people["root"], "catalog", recs, load_id="L", initiated_by="root"
    )
    ok = (
        "{ "
        + " ".join(f"p{i}: useCaseList(limit: 100) {{ items {{ key }} }}" for i in range(9))
        + " }"
    )
    assert "errors" not in c.gql(ok)[1]
    over = (
        "{ "
        + " ".join(f"p{i}: useCaseList(limit: 100) {{ items {{ key }} }}" for i in range(11))
        + " }"
    )
    _, r, _ = c.gql(over)
    assert any(e["extensions"]["code"] == "COST_EXCEEDED" for e in r["errors"])


def test_consistency_at_least_and_errors_per_field(c: Client) -> None:
    c.box.replica.feed()
    _, r, _ = c.gql(
        '{ useCase(key: "uc-pipeline", consistency: BULK) { key freshness { backend consistency } } }'
    )
    f = r["data"]["useCase"]["freshness"]
    assert (f["backend"], f["consistency"]) == ("memory_replica", "BULK")
    rec = c.box.arras.session(c.box.people["alice"]).invoke(
        "catalog.AddUseCase", {"code": "z", "name": "Z"}
    )
    _, r, _ = c.gql(
        f'{{ ok: useCase(key: "uc-pipeline") {{ key }} late: useCase(key: "z", consistency: BULK, atLeast: "{rec.token}") {{ key }} }}'
    )
    assert r["data"]["ok"]["key"] == "uc-pipeline" and r["data"]["late"] is None
    e = r["errors"][0]
    assert (
        e["extensions"]["code"] == "NOT_YET_CURRENT"
        and e["path"] == ["late"]
        and e["extensions"]["backend"] == "memory_replica"
    )


def test_unavailable_per_field_then_503_when_nothing_answers(c: Client) -> None:
    c.box.store.available = False
    _, r, _ = c.gql('{ useCase(key: "uc-pipeline") { key } }')
    assert r["errors"][0]["extensions"] == {
        "code": "UNAVAILABLE",
        "backend": "memory",
        "reason": "unreachable",
    }
    _, ok, _ = c.gql('{ useCase(key: "uc-pipeline", consistency: BULK) { key } }')
    assert ok["data"]["useCase"]["key"] == "uc-pipeline"
    c.box.replica.available = False
    status, r, _ = c.gql("{ modules { name } }", "/graphql")
    assert status == 503 and r["errors"][0]["extensions"]["code"] == "UNAVAILABLE"
    assert c.gql('{ useCase(key: "x") { key } }')[0] == 503


def test_status_codes(c: Client) -> None:
    assert c.gql("{ modules { name } }", "/graphql", user=None)[0] == 401
    assert c.gql("{ x }", "/graphql/nope")[0] == 404
    assert c.gql('{ useCase(key: "x") { key } }', user="dave")[0] == 404  # cannot read it
    assert (
        c.call("GET", "/graphql")[0] == 405
        and c.call("GET", "/graphql/catalog")[2]["allow"] == "POST"
    )
    assert c.call("POST", "/graphql", raw=b"{nope")[0] == 400
    assert c.call("POST", "/graphql", {"nothing": 1})[0] == 400
    assert c.call("POST", "/graphql", {"query": 5})[0] == 400
    assert c.call("POST", "/graphql", {"query": "{ modules { name } }", "variables": [1]})[0] == 400
    assert c.call("POST", "/graphql", raw=b'{"query": "{ x }", "variables": {"a": NaN}}')[0] == 400
    assert (
        c.call("POST", "/graphql", {"query": "{ modules { name } }"}, ctype="text/plain")[0] == 400
    )
    assert c.gql("{ modules {", "/graphql")[0] == 400
    assert c.call("POST", "/graphql", raw=b" " * (MAX_BODY + 1))[0] == 413
    assert (
        c.call("GET", "/elsewhere")[0] == 404
        and c.call("POST", "/graphql/a/b", {"query": "{x}"})[0] == 404
    )
    status, r, _ = c.gql("{ nope }", "/graphql")
    assert status == 200 and r["errors"][0]["extensions"]["code"] == "BAD_QUERY"


EXPIRED = {
    "errors": [
        {
            "message": "sign in again",
            "extensions": {"code": "REFUSED", "reason": "token_expired"},
        }
    ]
}


def test_expired_token(c: Client) -> None:
    c.box.access.expire(c.box.people["carol"].token)
    # sign in again, on both paths: not "no such module", not a 200 with an error
    assert c.gql('{ useCase(key: "x") { key } }')[:2] == (401, EXPIRED)
    assert c.gql("{ modules { name } }", "/graphql")[:2] == (401, EXPIRED)
    # a module the viewer cannot read is still answered as an unknown one
    assert c.gql('{ useCase(key: "x") { key } }', user="dave")[0] == 404


def test_a_token_that_expires_mid_request_is_a_401_too(c: Client) -> None:
    real = c.box.store.query

    def expire_then_query(principal, *a, **k):
        c.box.access.expire(principal.token)  # the token lapses between describe and the read
        return real(principal, *a, **k)

    c.box.store.query = expire_then_query
    assert c.gql('{ useCase(key: "uc-pipeline") { key } }')[:2] == (401, EXPIRED)


def test_a_no_access_refusal_on_the_meta_path_stays_a_field_error(c: Client) -> None:
    from arras import Refused

    def refuse(principal):
        raise Refused("memory", "catalog")

    c.box.store.catalog = refuse
    c.box.replica.catalog = refuse
    status, r, _ = c.gql("{ modules { name } }", "/graphql")
    assert status == 200 and r["errors"][0]["extensions"]["code"] == "REFUSED"
    assert r["errors"][0]["extensions"]["reason"] == "no_access"


def test_there_is_no_way_to_write(c: Client) -> None:
    _, r, _ = c.gql("{ __schema { mutationType { name } subscriptionType { name } } }")
    assert r["data"]["__schema"] == {"mutationType": None, "subscriptionType": None}
    _, r, _ = c.gql("{ __schema { mutationType { name } } }", "/graphql")
    assert r["data"]["__schema"]["mutationType"] is None
    _, r, _ = c.gql('mutation { addUseCase(code: "x") { key } }')
    assert r["errors"][0]["extensions"]["code"] == "BAD_QUERY"
    _, r, _ = c.gql("subscription { useCase }")
    assert "errors" in r


def test_introspection_is_exempt_from_the_limits(c: Client) -> None:
    from graphql import get_introspection_query

    status, r, _ = c.gql(get_introspection_query(), "/graphql")
    assert status == 200 and "errors" not in r
    _, r, _ = c.gql(get_introspection_query())
    names = {t["name"] for t in r["data"]["__schema"]["types"]}
    assert {
        "Entity",
        "UseCase",
        "UseCasePage",
        "Solution",
        "SolutionPage",
        "Ref",
        "Freshness",
        "Consistency",
    } <= names


def test_generated_schema_follows_the_registry() -> None:
    from arras.umf import parse_module

    mod = parse_module(__import__("arras.sandbox", fromlist=["x"]).catalog_document())
    sdl = __import__("graphql").print_schema(build_module_schema(mod))
    assert "interface Entity" in sdl and "type UseCase implements Entity" in sdl
    assert (
        "useCaseList(filter: JSON, limit: Int = 50, consistency: Consistency = LATEST, afterKey: String): UseCasePage"
        in sdl
    )
    assert "addressedBy: [Ref!]!" in sdl and "addresses: [Ref!]!" in sdl
    assert "Mutation" not in sdl and "Subscription" not in sdl
    assert "name: String!" in sdl and "workArea: String\n" in sdl  # required is non-null


def test_page_and_script(c: Client) -> None:
    status, page, hdrs = c.call("GET", "/", user=None)  # the page itself needs no viewer
    assert status == 200 and "console.js" in page and "<script>" not in page
    assert "unpkg.com/graphiql@3.7.1" in page
    status, js, _ = c.call("GET", "/console.js", user=None)
    assert status == 200 and "new URL(" in js and "location.href" in js


def test_works_under_a_path_prefix_and_with_another_asset_base() -> None:
    c = Client("/admin/console")
    assert c.call("GET", "")[0] == 308 and c.call("GET", "")[2]["location"] == "/admin/console/"
    assert c.call("GET", "/")[0] == 200
    status, r, _ = c.gql('{ useCase(key: "uc-pipeline") { key } }')
    assert status == 200 and r["data"]["useCase"]["key"] == "uc-pipeline"
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/elsewhere/graphql",
        "headers": [],
        "query_string": b"",
    }
    sent: list[dict] = []

    async def noop() -> dict:
        return {}

    async def send(m: dict) -> None:
        sent.append(m)

    asyncio.run(c.app(scope, noop, send))
    assert sent[0]["status"] == 404
    own = create_app(c.h, principal_for_request=c.who, asset_base="https://assets.example/x/")
    scope["path"] = "/"
    asyncio.run(own(scope, noop, send))
    assert b"https://assets.example/x/graphiql@3.7.1/graphiql.min.js" in sent[-1]["body"]


def test_registering_builds_the_schema_first() -> None:
    from arras.errors import Invalid

    c = Client()
    import arras.gqlschema as schema

    original = schema.build_module_schema

    def broken(mod):
        raise Invalid([__import__("arras").Violation("module", "invalid_name", "collides")])

    schema.build_module_schema = broken
    try:
        o = c.h.session(c.box.people["root"])
        from arras.sandbox import catalog_document

        with pytest.raises(Invalid) as e:
            o.registry().register(catalog_document().replace('"UseCase.name"', '"UseCase.name"'))
        assert e.value.violations[0].code == "invalid_name"
    finally:
        schema.build_module_schema = original


def test_the_viewer_is_the_principal(c: Client) -> None:
    seen: list[str] = []
    real = c.box.store.query

    def spy(principal, *a, **k):
        seen.append(principal.user)
        return real(principal, *a, **k)

    c.box.store.query = spy
    c.gql('{ useCase(key: "uc-pipeline") { key } }', user="carol")
    c.gql('{ useCase(key: "uc-pipeline") { key } }', user="bob")
    assert seen == ["carol", "bob"]
    _ = Arras


# -- hostile and awkward input
def test_fragment_chains_are_measured_in_linear_time() -> None:
    import time

    import graphql

    n = 40
    frags = " ".join(f"fragment F{i} on Freshness {{ ...F{i + 1} ...F{i + 1} }}" for i in range(n))
    doc = graphql.parse(
        "{ useCaseList { items { freshness { ...F0 } } } } "
        + frags
        + f" fragment F{n} on Freshness {{ backend }}"
    )
    start = time.monotonic()
    m = measure(doc, None)
    assert time.monotonic() - start < 1 and m[1] > 50  # counted, not walked 2**40 times


def test_exponential_fragments_are_answered_fast(c: Client) -> None:
    import time

    n = 40
    frags = " ".join(f"fragment F{i} on Freshness {{ ...F{i + 1} ...F{i + 1} }}" for i in range(n))
    q = (
        "{ useCaseList { items { freshness { ...F0 } } } } "
        + frags
        + f" fragment F{n} on Freshness {{ backend }}"
    )
    start = time.monotonic()
    status, r, _ = c.gql(q)
    assert time.monotonic() - start < 2
    assert r["errors"][0]["extensions"]["code"] == "COST_EXCEEDED"


def test_introspection_is_bounded_too(c: Client) -> None:
    level = "ofType { name kind %s }"
    deep = "kind name"
    for _ in range(8):
        deep = level % deep
    alias = " ".join(f"a{i}: type {{ {deep} }}" for i in range(40))
    q = f"{{ __schema {{ types {{ fields {{ {alias} }} }} }} }}"
    _, r, _ = c.gql(q, "/graphql")
    assert r["errors"][0]["extensions"]["code"] == "COST_EXCEEDED"
    from graphql import get_introspection_query

    assert "errors" not in c.gql(get_introspection_query(), "/graphql")[1]  # the real one fits
    assert "errors" not in c.gql("{ __typename }", "/graphql")[1]


def test_deep_nesting_is_a_400_not_a_500(c: Client) -> None:
    assert c.call("POST", "/graphql", raw=b"[" * 100000)[0] == 400
    assert c.gql("{" * 10000 + "x" + "}" * 10000)[0] == 400
    assert c.gql("{ a(b: " + "[" * 10000 + "1" + "]" * 10000 + ") }")[0] == 400


def test_null_and_wrongly_typed_arguments_are_answered(c: Client) -> None:
    _, r, _ = c.gql("{ useCaseList(limit: null) { items { key } } }")
    assert "errors" not in r and len(r["data"]["useCaseList"]["items"]) == 2
    _, r, _ = c.call(
        "POST",
        "/graphql/catalog",
        {
            "query": "query($l: Int) { useCaseList(limit: $l) { items { key } } }",
            "variables": {"l": None},
        },
    )
    assert "errors" not in r
    for flt in ('"x"', "[1]", "5"):
        _, r, _ = c.gql(f"{{ useCaseList(filter: {flt}) {{ items {{ key }} }} }}")
        assert r["errors"][0]["extensions"]["code"] == "BAD_QUERY", flt


def test_one_failing_field_keeps_the_others_data(c: Client) -> None:
    c.box.replica.available = False
    _, r, _ = c.gql(
        '{ a: useCase(key: "uc-pipeline") { key } b: useCaseList(consistency: BULK) { items { key } } c: useCaseList(limit: 0) { items { key } } }'
    )
    assert (
        r["data"]["a"]["key"] == "uc-pipeline" and r["data"]["b"] is None and r["data"]["c"] is None
    )
    assert {e["extensions"]["code"] for e in r["errors"]} == {"UNAVAILABLE", "LIMIT_EXCEEDED"}


def test_the_budget_is_reserved_before_a_query_runs(c: Client) -> None:
    calls: list[int] = []
    real = c.box.store.query

    def spy(*a, **k):
        calls.append(k["limit"])
        return real(*a, **k)

    recs = [
        {"type": "UseCase", "key": f"u{i:04}", "properties": {"name": "n"}} for i in range(1100)
    ]
    c.box.store.import_records(
        c.box.people["root"], "catalog", recs, load_id="L", initiated_by="root"
    )
    c.box.store.query = spy
    q = (
        "{ "
        + " ".join(f"p{i}: useCaseList(limit: 100) {{ items {{ key }} }}" for i in range(12))
        + " }"
    )
    _, r, _ = c.gql(q)
    assert len(calls) == 10 and sum(calls) == 1000  # the eleventh and twelfth never ran
    assert sum(e["extensions"]["code"] == "COST_EXCEEDED" for e in r["errors"]) == 2


def test_a_name_that_collides_with_a_generated_one_is_refused_at_registration() -> None:
    from arras.errors import Invalid
    from arras.sandbox import catalog_document

    c = Client()
    doc = (
        catalog_document().replace('"UseCase"', '"Consistency"').replace("UseCase.", "Consistency.")
    )
    with pytest.raises(Invalid) as e:
        c.h.session(c.box.people["root"]).registry().register(doc)
    assert e.value.violations[0].code == "invalid_name"


def test_relationships_with_several_ends_are_refused_with_a_reason() -> None:
    import json

    from arras.errors import Invalid
    from arras.sandbox import catalog_document
    from arras.umf import parse_module

    d = json.loads(catalog_document())
    d["modules"][0]["relationships"][0]["target"].append(
        {"module": "catalog", "element": "Solution"}
    )
    with pytest.raises(Invalid) as e:
        build_module_schema(parse_module(json.dumps(d)))
    assert "one type per end" in e.value.violations[0].message


def test_an_answer_under_another_revision_is_an_error_not_a_silent_mix(c: Client) -> None:
    from dataclasses import replace

    from arras.types import Revision

    real = c.box.store.query

    def other_revision(*a, **k):
        ans = real(*a, **k)
        return ans

    mod = c.box.store.modules["catalog"]
    c.box.store.modules["catalog"] = replace(mod, revision=Revision({"memory": 1}))
    _, ok, _ = c.gql('{ useCase(key: "uc-pipeline") { key } }')
    assert "errors" not in ok
    # the catalog moves between the request's snapshot and its read: simulate with a changing describe
    calls = {"n": 0}
    describe = c.h.session

    def moving(principal):
        o = describe(principal)
        real_query = o.query

        def query(*a, **k):
            rows = real_query(*a, **k)
            return replace(rows, revision=Revision({"memory": 99}))

        o.query = query
        return o

    c.h.session = moving
    _, r, _ = c.gql('{ useCase(key: "uc-pipeline") { key } }')
    assert (
        r["errors"][0]["extensions"]["code"] == "REVISION_CHANGED" and r["data"]["useCase"] is None
    )
    _ = (other_revision, calls)


def test_a_mount_that_keeps_the_prefix_in_the_path_and_the_redirect_keeps_the_query() -> None:
    c = Client("")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/praxis/console/",
        "root_path": "/praxis/console",
        "query_string": b"",
        "headers": [],
    }
    sent: list[dict] = []

    async def receive() -> dict:
        return {}

    async def send(m: dict) -> None:
        sent.append(m)

    asyncio.run(c.app(scope, receive, send))
    assert sent[0]["status"] == 200
    d = Client("/c")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/c",
        "query_string": b"module=catalog",
        "headers": [],
    }
    sent.clear()
    asyncio.run(d.app(scope, receive, send))
    assert (
        dict((k.decode(), v.decode()) for k, v in sent[0]["headers"])["location"]
        == "/c/?module=catalog"
    )


def test_chunked_bodies_disconnects_and_other_scopes() -> None:
    c = Client()
    body = json.dumps({"query": "{ modules { name } }"}).encode()
    chunks = [{"body": body[:5], "more_body": True}, {"body": body[5:], "more_body": False}]

    async def run(msgs: list[dict], scope_type: str = "http") -> list[dict]:
        sent: list[dict] = []
        it = iter(msgs)

        async def receive() -> dict:
            return next(it)

        async def send(m: dict) -> None:
            sent.append(m)

        scope = {
            "type": scope_type,
            "method": "POST",
            "path": "/graphql",
            "headers": [(b"content-type", b"application/json"), (b"x-user", b"carol")],
            "query_string": b"",
        }
        await c.app(scope, receive, send)
        return sent

    assert asyncio.run(run(chunks))[0]["status"] == 200
    assert asyncio.run(run([{"type": "http.disconnect"}]))[0]["status"] == 400
    assert asyncio.run(run([], "websocket")) == [] and asyncio.run(run([], "lifespan")) == []


def test_busy_console_says_so(c: Client) -> None:
    c.app.busy = 8
    status, r, _ = c.gql("{ modules { name } }", "/graphql")
    assert status == 503 and r["errors"][0]["extensions"]["code"] == "UNAVAILABLE"


def test_scalars_serialize_as_the_contract_says() -> None:
    import base64
    from datetime import datetime
    from decimal import Decimal

    from arras import gqlschema as s

    assert s.BigInt.serialize(2**62) == str(2**62)
    assert s.DecimalScalar.serialize(Decimal("1.50")) == "1.50"
    assert s.Base64.serialize(b"hi") == base64.b64encode(b"hi").decode()
    assert (
        s.DateTime.serialize(datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC))
        == "2026-01-02T03:04:05+00:00"
    )
    assert s.DateTime.serialize(datetime(2026, 1, 2)).endswith("+00:00")  # an offset, always


def test_responses_carry_no_internal_tags(c: Client) -> None:
    _, r, _ = c.gql("{ modules { revision } }", "/graphql")
    assert (
        "_type" not in r["data"]["modules"][0]["revision"]
        and r["data"]["modules"][0]["revision"]["memory"] == 1
    )


def test_integrity_attributes_are_added_when_given() -> None:
    c = Client()
    app = create_app(c.h, principal_for_request=c.who, integrity={"graphiql": "sha384-abc"})
    sent: list[dict] = []

    async def receive() -> dict:
        return {}

    async def send(m: dict) -> None:
        sent.append(m)

    asyncio.run(
        app(
            {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""},
            receive,
            send,
        )
    )
    page = sent[1]["body"].decode()
    assert 'integrity="sha384-abc" crossorigin="anonymous"' in page and "unpkg.com" in page


def test_a_ref_opens_its_target_as_the_viewer(c: Client) -> None:
    q = """{ useCase(key: "uc-pipeline") { addressedBy { module type key
             target { key type ... on Solution { name } freshness { backend } } } } }"""
    status, r, _ = c.gql(q)
    assert status == 200 and "errors" not in r, r
    [ref] = r["data"]["useCase"]["addressedBy"]
    assert (ref["module"], ref["type"], ref["key"]) == ("catalog", "catalog.Solution", "sol-1")
    t = ref["target"]
    assert t["key"] == "sol-1" and t["type"] == "catalog.Solution" and t["name"]
    assert t["freshness"]["backend"] == "memory"


def test_a_target_is_one_budgeted_query_and_an_absent_one_is_null(c: Client) -> None:
    calls: list[str] = []
    real = c.box.store.query

    def spy(*a, **k):
        calls.append(a[0])
        return real(*a, **k)

    c.box.store.query = spy
    _, r, _ = c.gql("{ useCaseList { items { addressedBy { target { key } } } } }")
    assert "errors" not in r and len(calls) == 1 + 1  # the page, then one lookup for the one ref
    from arras.gqlschema import RequestContext

    ctx = RequestContext(c.h.session(c.box.principal("carol")))
    ctx.targets = 100
    with pytest.raises(Exception) as e:
        ctx.reserve_target()
    assert e.value.extensions["code"] == "COST_EXCEEDED"  # type: ignore[attr-defined]


def test_an_entity_carries_its_attribution_and_an_action_its_typed_inputs(c: Client) -> None:
    status, r, _ = c.gql(
        """{ useCase(key: "uc-pipeline") { createdBy createdAt updatedBy updatedAt }
             solution(key: "sol-1") { addresses { target { createdBy updatedAt } } } }"""
    )
    assert status == 200 and "errors" not in r, r
    u = r["data"]["useCase"]
    assert (
        u["createdBy"] == "alice"
        and u["updatedBy"] == "alice"
        and u["createdAt"]
        and u["updatedAt"]
    )
    [ref] = r["data"]["solution"]["addresses"]
    assert ref["target"]["createdBy"] == "alice"  # same-module targets are attributed too
    _, m, _ = c.gql(
        "{ modules { actions { name inputSpecs { name type kind cardinality } } } }", "/graphql"
    )
    acts = {a["name"]: a for a in m["data"]["modules"][0]["actions"]}
    specs = {s["name"]: s for s in acts["catalog.AddUseCase"]["inputSpecs"]}
    assert specs["code"]["kind"] == "scalar" and specs["code"]["type"] == "string"
    assert any(s["kind"] == "ref" for a in acts.values() for s in a["inputSpecs"])


def test_a_cross_origin_post_is_refused_and_a_same_origin_one_is_not(c: Client) -> None:
    q = {"query": "{ useCaseList { items { key } } }"}
    host = {"host": "console.example"}
    status, _, _ = c.call(
        "POST", "/graphql/catalog", q, extra={**host, "origin": "https://evil.example"}
    )
    assert status == 403
    status, _, _ = c.call(
        "POST", "/graphql/catalog", q, extra={**host, "sec-fetch-site": "cross-site"}
    )
    assert status == 403
    ok, body, _ = c.call(
        "POST", "/graphql/catalog", q, extra={**host, "origin": "https://console.example"}
    )
    assert ok == 200 and "errors" not in body
    ok, _, _ = c.call("POST", "/graphql/catalog", q)  # no origin: not a browser
    assert ok == 200


# -- Ref.target, case by case (CONTRACT-006, Generated schema per module and Limits) -------------


def _ext_document() -> str:
    """A second module, `ext`, whose `about` relationship ends at `catalog.UseCase`."""
    import json

    from arras.sandbox import catalog_document

    d = json.loads(catalog_document())
    m = d["modules"][0]
    m["id"] = m["namespace"] = "ext"
    note = {
        "id": "Note",
        "kind": "record",
        "members": [{"module": "ext", "element": "Note.code"}],
        "extensions": {
            "umf.ddd": {
                "kind": "entity",
                "fields": {
                    "code": {"type": {"kind": "scalar", "name": "string"}, "cardinality": "one"}
                },
                "identity": {"fields": ["code"], "scope": "context"},
            }
        },
        "keys": [
            {
                "id": "identity",
                "name": "Identity",
                "fields": [{"module": "ext", "element": "Note.code"}],
                "primary": True,
            }
        ],
    }
    code = {
        "id": "Note.code",
        "kind": "field",
        "nullability": "required",
        "cardinality": "one",
        "scalarType": "string",
        "extensions": {},
    }
    m["elements"] = [note, code]
    m["relationships"] = [
        {
            "id": "note-about",
            "name": "about",
            "source": [{"module": "ext", "element": "Note"}],
            "target": [{"module": "catalog", "element": "UseCase", "key": "identity"}],
            "sourceMultiplicity": {"min": 0, "max": "*"},
            "targetMultiplicity": {"min": 0, "max": "*"},
            "targetLifecycle": "independent",
            "directed": True,
        }
    ]
    m["actions"] = []
    return json.dumps(d)


@pytest.fixture
def ext() -> Client:
    c = Client()
    c.box.load(_ext_document())
    root = c.h.session(c.box.people["root"])
    recs = [
        {"type": "Note", "key": "n1", "properties": {}},
        {"relationship": "about", "source": "n1", "target": "uc-pipeline"},
    ]
    assert root.import_records("ext", recs, load_id="ext").created == 2
    c.box.people["xena"] = c.box.access.grant("xena", "ext", "read")  # ext only
    return c


FOREIGN_Q = """{ note(key: "n1") { about { module type key target {
    __typename key type version createdBy createdAt updatedBy updatedAt freshness { backend } } } } }"""


def test_a_cross_module_target_is_a_foreign_entity_with_interface_fields_only(ext: Client) -> None:
    status, r, _ = ext.gql(FOREIGN_Q, "/graphql/ext")
    assert status == 200 and "errors" not in r, r
    [ref] = r["data"]["note"]["about"]
    assert (ref["module"], ref["type"], ref["key"]) == ("catalog", "catalog.UseCase", "uc-pipeline")
    assert ref["target"] == {
        "__typename": "ForeignEntity",
        "key": "uc-pipeline",
        "type": "catalog.UseCase",
        "version": "1",
        "createdBy": None,  # another module's entity is read from its own endpoint
        "createdAt": None,
        "updatedBy": None,
        "updatedAt": None,
        "freshness": {"backend": "memory"},
    }
    # the foreign type's own fields are not in this module's schema
    status, r, _ = ext.gql(
        '{ note(key: "n1") { about { target { ... on UseCase { name } } } } }', "/graphql/ext"
    )
    assert r["errors"][0]["extensions"]["code"] == "BAD_QUERY"


def test_a_target_in_a_module_the_viewer_cannot_read_is_null_and_says_nothing(ext: Client) -> None:
    calls: list[str] = []
    real = ext.box.store.query

    def spy(principal, module, statement, **k):
        calls.append(module)  # the module the statement was sent for
        return real(principal, module, statement, **k)

    ext.box.store.query = spy
    status, r, _ = ext.gql(FOREIGN_Q, "/graphql/ext", user="xena")
    assert status == 200 and "errors" not in r, r
    [ref] = r["data"]["note"]["about"]
    assert ref["key"] == "uc-pipeline" and ref["target"] is None
    assert calls == ["ext"]  # the unreadable module is never queried


def test_an_absent_target_is_null_with_no_error(c: Client) -> None:
    c.box.replica.feed()  # the replica still holds sol-1 -> uc-pipeline ...
    alice = c.h.session(c.box.people["alice"])
    alice.invoke(
        "catalog.RetireUseCase", {"useCase": "uc-pipeline"}
    )  # ... the record store does not
    q = """{ solution(key: "sol-1", consistency: BULK) {
             addresses { key target { key ... on UseCase { name } } } } }"""
    status, r, _ = c.gql(q)
    assert status == 200 and "errors" not in r, r
    assert r["data"]["solution"]["addresses"] == [{"key": "uc-pipeline", "target": None}]


def test_the_hundred_and_first_target_is_cost_exceeded_and_the_rest_keep_their_data(
    c: Client,
) -> None:
    recs: list[dict] = []
    for i in range(100):
        recs.append({"type": "UseCase", "key": f"u{i:03}", "properties": {"name": f"U{i}"}})
        recs.append({"type": "Solution", "key": f"s{i:03}", "properties": {"name": "S"}})
        recs.append({"relationship": "addresses", "source": f"s{i:03}", "target": f"u{i:03}"})
    c.box.store.import_records(
        c.box.people["root"], "catalog", recs, load_id="L", initiated_by="root"
    )
    q = """{ a: useCaseList(limit: 100) { items { key addressedBy { target { key } } } }
             b: solution(key: "sol-1") { name addresses { key target { key } } } }"""
    status, r, _ = c.gql(q)
    assert status == 200
    items = r["data"]["a"]["items"]
    assert len(items) == 100 and all(i["addressedBy"][0]["target"] for i in items)
    b = r["data"]["b"]
    assert b["name"] == "Pipeline extractor" and b["addresses"] == [
        {"key": "uc-pipeline", "target": None}
    ]
    [err] = r["errors"]
    assert err["extensions"]["code"] == "COST_EXCEEDED"
    assert err["path"] == ["b", "addresses", 0, "target"]


def test_a_target_chain_past_depth_six_is_depth_exceeded(c: Client) -> None:
    six = """{ solution(key: "sol-1") { addresses { target { ... on UseCase {
               addressedBy { target { key } } } } } } }"""
    status, r, _ = c.gql(six)
    assert status == 200 and "errors" not in r, r
    [a] = r["data"]["solution"]["addresses"]
    assert a["target"]["addressedBy"] == [{"target": {"key": "sol-1"}}]
    seven = """{ solution(key: "sol-1") { addresses { target { ... on UseCase {
                 addressedBy { target { ... on Solution { addresses { key } } } } } } } } }"""
    status, r, _ = c.gql(seven)
    assert status == 200 and r["data"] is None
    assert r["errors"][0]["extensions"]["code"] == "DEPTH_EXCEEDED"


def test_an_ipv6_loopback_origin_is_compared_with_its_brackets_and_port() -> None:
    from arras.http import post_origin_ok

    none: set = set()

    def refused(h: dict[str, str]) -> bool:
        return not post_origin_ok(h, set(), none, browser_or_host=True)

    assert not refused({"origin": "http://[::1]:8000", "host": "[::1]:8000"})
    assert not refused({"origin": "http://[::1]", "host": "[::1]:80"})
    assert refused({"origin": "http://[::1]:8000", "host": "[::1]:8001"})
    named = Client()
    app = create_app(named.h, principal_for_request=named.who, public_origin="http://[::1]:8000")
    named.app = app
    q = {"query": "{ modules { name } }"}
    ok = named.call("POST", "/graphql", q, extra={"origin": "http://[::1]:8000"})
    assert ok[0] == 200
    bad = named.call("POST", "/graphql", q, extra={"origin": "http://[::1]:8001"})
    assert bad[0] == 403


def test_the_meta_schema_states_each_relationship_with_its_ends_and_multiplicities(
    c: Client,
) -> None:
    q = """{ modules { relationships { name source target sourceMultiplicity
             targetMultiplicity lifecycle inverse } } }"""
    status, r, _ = c.gql(q, "/graphql")
    assert status == 200 and "errors" not in r, r
    [rel] = r["data"]["modules"][0]["relationships"]
    assert rel["name"] == "addresses" and rel["inverse"] == "addressedBy"
    assert (rel["source"], rel["target"]) == (["catalog.Solution"], ["catalog.UseCase"])
    assert rel["lifecycle"] == "independent"
    assert (rel["sourceMultiplicity"], rel["targetMultiplicity"]) == ("0..*", "0..*")


SENTINEL = "SENTINEL-secret-row-text"


def _assert_log_is_blind(caplog: pytest.LogCaptureFixture, *, expect: str) -> None:
    records = [r for r in caplog.records if r.name.startswith("arras.console")]
    assert records, "the failure must still reach the operator"
    for r in records:
        assert SENTINEL not in r.getMessage() and SENTINEL not in str(r.args)
        assert r.exc_info is None and r.exc_text is None
        assert SENTINEL not in (r.exc_text or "")
    assert any(expect in r.getMessage() for r in records)


def test_a_failed_request_logs_the_exception_type_only(
    c: Client, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(c.app, "handle", boom)
    with caplog.at_level("DEBUG"):
        status, r, _ = c.gql("{ modules { name } }", "/graphql")
    assert status == 500 and SENTINEL not in json.dumps(r)
    _assert_log_is_blind(caplog, expect="console request failed: RuntimeError")


def test_a_failed_execution_logs_the_exception_type_only(
    c: Client, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(c.app, "_execute", boom)
    with caplog.at_level("DEBUG"):
        status, r, _ = c.gql("{ modules { name } }", "/graphql")
    assert r["errors"][0]["extensions"]["code"] == "INTERNAL_ERROR" and SENTINEL not in json.dumps(
        r
    )
    _assert_log_is_blind(caplog, expect="console execution failed: RuntimeError")


def test_a_failed_resolver_logs_the_exception_type_only(
    c: Client, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from arras.core import Ontology

    def boom(self: Any, *a: Any, **k: Any) -> Any:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(Ontology, "query", boom)
    with caplog.at_level("DEBUG"):
        _, r, _ = c.gql('{ useCase(key: "uc-pipeline") { key } }')
    assert r["errors"][0]["extensions"]["code"] == "INTERNAL_ERROR" and SENTINEL not in json.dumps(
        r
    )
    _assert_log_is_blind(caplog, expect="resolver failed: RuntimeError")


def test_a_list_pages_after_the_last_key_with_after_key(c: Client) -> None:
    """CONTRACT-006: `afterKey` reads the entities whose key follows it, in key order; the page's last
    key is the next `afterKey`, and `truncated` says another page follows. No cursor is issued."""
    sent: list[Any] = []
    real = c.box.store.query

    def spy(principal, module, statement, **k):
        sent.append(statement)
        return real(principal, module, statement, **k)

    c.box.store.query = spy
    keys: list[str] = []
    after: str | None = None
    while True:
        arg = f', afterKey: "{after}"' if after else ""
        _, r, _ = c.gql(f"{{ useCaseList(limit: 1{arg}) {{ items {{ key }} truncated }} }}")
        page = r["data"]["useCaseList"]
        keys += [x["key"] for x in page["items"]]
        if not page["truncated"]:
            break
        after = page["items"][-1]["key"]
    assert keys == sorted(keys) and len(keys) == len(set(keys)) >= 2
    last = sent[-1]
    assert 'x."code" > :after' in last.sql and last.params["after"] == keys[-2]
    assert last.sql.endswith('ORDER BY x."code" LIMIT 2')  # one over the page: truncated
    _, bad, _ = c.gql("{ useCaseList(afterKey: 5) { items { key } } }")
    assert bad["errors"]  # a key is a string


PROXIED = {"origin": "https://app.example", "host": "internal:8000"}
GQL = {"query": "{ modules { name } }"}


@pytest.mark.parametrize("path", ["/graphql", "/graphql/catalog"])
def test_a_proxied_page_posting_to_itself_is_accepted_on_the_browsers_word(path: str) -> None:
    c = Client()
    ok = c.call("POST", path, GQL, extra={**PROXIED, "sec-fetch-site": "same-origin"})
    assert ok[0] != 403


@pytest.mark.parametrize("site", ["same-site", "cross-site", "none", None])
def test_a_proxied_origin_without_same_origin_is_refused(site: str | None) -> None:
    c = Client()
    extra = dict(PROXIED) | ({"sec-fetch-site": site} if site else {})
    status, body, _ = c.call("POST", "/graphql", GQL, extra=extra)
    assert status == 403 and body["errors"][0]["extensions"]["code"] == "REFUSED"


@pytest.mark.parametrize(
    "extra",
    [
        {**PROXIED, "sec-fetch-site": ["same-origin", "same-origin"]},
        {**PROXIED, "sec-fetch-site": ["same-origin", "cross-site"]},
        {**PROXIED, "sec-fetch-site": ["cross-site", "same-origin"]},
        {"origin": ["https://app.example", "https://app.example"], "sec-fetch-site": "same-origin"},
        {
            "origin": ["https://app.example", "https://evil.example"],
            "sec-fetch-site": "same-origin",
        },
        {"origin": ["https://a.example", "https://a.example"], "host": "a.example"},
    ],
)
def test_a_repeated_origin_or_fetch_site_is_refused(extra: dict) -> None:
    assert Client().call("POST", "/graphql", GQL, extra=extra)[0] == 403


@pytest.mark.parametrize(
    "origin", ["null", "https://app.example/path", "https://a.example, https://b.example"]
)
def test_same_origin_with_a_malformed_origin_is_refused(origin: str) -> None:
    extra = {"origin": origin, "host": "internal:8000", "sec-fetch-site": "same-origin"}
    assert Client().call("POST", "/graphql", GQL, extra=extra)[0] == 403


def test_a_non_browser_post_and_a_configured_origin_are_unchanged() -> None:
    c = Client()
    assert c.call("POST", "/graphql", GQL)[0] == 200
    named = Client()
    named.app = create_app(
        named.h, principal_for_request=named.who, public_origin="https://app.example"
    )
    assert named.call("POST", "/graphql", GQL, extra=PROXIED)[0] == 200
    other = {"origin": "https://evil.example", "host": "internal:8000"}
    assert named.call("POST", "/graphql", GQL, extra=other)[0] == 403
