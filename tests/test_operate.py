# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""CONTRACT-009: the operator action and audit surface, one test per rule of its tables."""

import asyncio
import json
from typing import Any

import pytest

from arras import Arras, Placement, Principal
from arras.fakes import MemoryStore
from arras.operate import create_app, openapi_document
from arras.sandbox import Sandbox

PUBLIC = "https://ops.example"
OTHER = "https://example.invalid"
ADD = {"code": "uc-x", "name": "X", "workArea": "finance"}


class Client:
    """The real operator app over the sandbox's fakes, called as an ASGI server would."""

    def __init__(self, box: Any = None, **kw: Any) -> None:
        self.box = box or Sandbox().seed()
        kw.setdefault("public_origin", PUBLIC)
        kw.setdefault("allowed_origins", (OTHER,))
        self.app = create_app(self.box.arras, principal_for_request=self.who, **kw)

    def who(self, request) -> Principal | None:
        name = request.headers.get("x-user")
        return None if name is None else self.box.principal(name)

    def call(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        user: str | None = "alice",
        origin: str | None = PUBLIC,
        extra: dict[str, str] | None = None,
        ctype: str = "application/json",
        headers: list[tuple[str, str]] | None = None,
        raw: bytes | None = None,
        messages: list[dict] | None = None,
        scope: dict[str, Any] | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        """`headers` are sent as well, repeats and all; `messages` replace the one body message
        (to send it in chunks, or a disconnect); `scope` adds to the ASGI scope."""
        hs = [(b"content-type", ctype.encode())]
        for k, v in {
            **({"x-user": user} if user else {}),
            **({"origin": origin} if origin else {}),
            **(extra or {}),
        }.items():
            hs.append((k.encode(), v.encode()))
        hs += [(k.encode(), v.encode()) for k, v in headers or []]
        data = raw if raw is not None else json.dumps(body).encode() if body is not None else b""
        sc = {"type": "http", "method": method, "path": path, "headers": hs, **(scope or {})}
        queue = list(messages or [{"type": "http.request", "body": data, "more_body": False}])
        sent: list[dict] = []

        async def receive() -> dict:
            return queue.pop(0)

        async def send(msg: dict) -> None:
            sent.append(msg)

        asyncio.run(self.app(sc, receive, send))
        hdrs = {k.decode(): v.decode() for k, v in sent[0]["headers"]}
        assert len(hdrs) == len(sent[0]["headers"]), "a response header is sent once"
        out_raw = sent[1]["body"]
        out = json.loads(out_raw) if out_raw else None
        return sent[0]["status"], out, hdrs

    def post(self, path: str, body: Any, **kw: Any):
        return self.call("POST", path, body, **kw)


@pytest.fixture
def c() -> Client:
    return Client()


INVOKE = "/actions/catalog/AddUseCase/invoke"
VALIDATE = "/actions/catalog/AddUseCase/validate"


# -- the surface describes itself -----------------------------------------------------------------


def test_version_and_openapi_are_published_without_a_principal(c: Client) -> None:
    status, r, _ = c.call("GET", "/version", user=None, origin=None)
    assert status == 200 and r["contracts"]["operate"] == 2
    status, doc, _ = c.call("GET", "/openapi.json", user=None, origin=None)
    assert status == 200 and doc["openapi"].startswith("3.1")


def test_only_declared_actions_write(c: Client) -> None:
    doc = openapi_document()
    posts = sorted(p for p, ops in doc["paths"].items() if "post" in ops)
    assert posts == [
        "/actions/{module}/{action}/batch",
        "/actions/{module}/{action}/invoke",
        "/actions/{module}/{action}/validate",
        "/audit/changes",
        "/audit/loads",
        "/export",  # a read of `export_records`: it changes nothing
        "/query",  # a read of `query`: no statement of the dialect writes
    ]
    for verb in ("put", "patch", "delete"):
        assert all(verb not in ops for ops in doc["paths"].values())
    assert c.call("DELETE", "/actions/catalog/AddUseCase/invoke")[0] == 405
    assert c.post("/sql", {"sql": "delete from x"})[0] == 404
    assert c.post("/entities/catalog.UseCase/uc-x", {})[0] == 404


# -- validate, invoke, batch ----------------------------------------------------------------------


def test_validate_shows_the_effects_and_applies_nothing(c: Client) -> None:
    before = c.post("/audit/changes", {"module": "catalog", "limit": 100})[1]["items"]
    status, v, _ = c.post(VALIDATE, {"inputs": ADD})
    assert status == 200 and v["ok"] and v["violations"] == [] and v["failures"] == []
    [e] = v["effects"]
    assert e["kind"] == "create" and e["ref"]["type"] == "catalog.UseCase"
    assert c.post("/audit/changes", {"module": "catalog", "limit": 100})[1]["items"] == before
    _, page, _ = c.post(
        "/audit/changes", {"module": "catalog", "type": "catalog.UseCase", "key": "uc-x"}
    )
    assert page["items"] == []  # nothing was applied or recorded


def test_validate_reports_violations_with_200_and_invoke_with_400(c: Client) -> None:
    bad = {"name": "no code", "workArea": 5}
    status, v, _ = c.post(VALIDATE, {"inputs": bad})
    assert status == 200 and not v["ok"] and v["violations"]
    status, e, _ = c.post(INVOKE, {"inputs": bad})
    assert status == 400 and e["error"]["type"] == "Invalid" and e["error"]["violations"]
    assert "_type" not in json.dumps(e)  # the same shape as in a Validation


def test_invoke_returns_a_receipt_with_a_group_and_replays_by_key(c: Client) -> None:
    status, r, _ = c.post(INVOKE, {"inputs": ADD, "idempotency_key": "k-1"})
    assert status == 200 and r["created"] == 1 and r["group"] and r["replayed"] is False
    assert r["refs"][0] == {"type": "catalog.UseCase", "key": "uc-x", "version": 1}
    status, again, _ = c.post(INVOKE, {"inputs": ADD, "idempotency_key": "k-1"})
    assert status == 200 and again["replayed"] and again["group"] == r["group"]
    status, e, _ = c.post(INVOKE, {"inputs": {**ADD, "name": "other"}, "idempotency_key": "k-1"})
    assert status == 409 and e["error"]["reason"] == "idempotency_key_reused"


def test_a_false_precondition_is_422_and_a_stale_revision_is_409(c: Client) -> None:
    c.post(INVOKE, {"inputs": ADD})
    status, e, _ = c.post(INVOKE, {"inputs": ADD})
    assert status == 422 and e["error"]["type"] == "PreconditionFailed" and e["error"]["failures"]
    status, e, _ = c.post(
        INVOKE, {"inputs": {**ADD, "code": "uc-y"}, "expected_revision": {"memory": 99}}
    )
    assert status == 409 and e["error"]["reason"] == "revision"
    _, m, _ = c.post(
        "/audit/changes", {"module": "catalog", "type": "catalog.UseCase", "key": "uc-y"}
    )
    assert m["items"] == []


def test_a_batch_answers_each_item_by_index(c: Client) -> None:
    items = [{**ADD, "code": f"b{i}"} for i in range(3)] + [{**ADD, "code": "uc-pipeline"}]
    status, b, _ = c.post("/actions/catalog/AddUseCase/batch", {"items": items})
    assert status == 200 and (b["succeeded"], b["failed"]) == (3, 1)
    assert b["items"][3]["index"] == 3 and b["items"][3]["refusal"]["type"] == "PreconditionFailed"
    status, e, _ = c.post("/actions/catalog/AddUseCase/batch", {"items": []})
    assert status == 400


def test_unknown_unreadable_and_unauthorized_are_answered_as_the_contract_says(c: Client) -> None:
    assert c.post("/actions/catalog/NoSuch/invoke", {"inputs": {}})[0] == 404
    assert c.post("/actions/nomodule/AddUseCase/invoke", {"inputs": {}})[0] == 404
    assert c.post(INVOKE, {"inputs": ADD}, user="dave")[0] == 404  # cannot read the module
    status, e, _ = c.post(INVOKE, {"inputs": ADD}, user="carol")  # reads, cannot write
    assert status == 403 and e["error"]["reason"] == "no_access"
    assert c.post(INVOKE, {"inputs": ADD}, user=None)[0] == 401
    c.box.access.expire(c.box.people["alice"].token)
    status, e, _ = c.post(INVOKE, {"inputs": ADD})
    assert status == 401 and e["error"]["reason"] == "token_expired"


def test_the_host_can_narrow_what_is_offered_and_the_library_is_not_called() -> None:
    seen: list[str] = []
    c = Client(authorize_action=lambda p, m, a: seen.append(a) or a != "catalog.AddUseCase")
    called: list[str] = []
    real = MemoryStore.apply
    MemoryStore.apply = lambda self, *a, **k: called.append("apply") or real(self, *a, **k)
    try:
        assert c.post(INVOKE, {"inputs": ADD})[0] == 403
        assert c.post(VALIDATE, {"inputs": ADD})[0] == 403
    finally:
        MemoryStore.apply = real
    assert seen and called == []


# -- origin, preflight, bounds --------------------------------------------------------------------


def test_a_post_needs_an_allowed_origin_or_same_origin_proof(c: Client) -> None:
    assert c.post(VALIDATE, {"inputs": ADD}, origin=None)[0] == 403  # neither
    assert c.post(VALIDATE, {"inputs": ADD}, origin="https://evil.example")[0] == 403
    assert (
        c.post(VALIDATE, {"inputs": ADD}, origin=None, extra={"sec-fetch-site": "same-origin"})[0]
        == 200
    )
    assert (
        c.post(VALIDATE, {"inputs": ADD}, origin=None, extra={"sec-fetch-site": "cross-site"})[0]
        == 403
    )
    status, _, h = c.post(VALIDATE, {"inputs": ADD}, origin=OTHER)
    assert status == 200 and h["access-control-allow-origin"] == OTHER
    assert h["access-control-allow-credentials"] == "true"


def test_preflight_is_answered_only_for_allowed_origins(c: Client) -> None:
    status, _, h = c.call("OPTIONS", INVOKE, origin=OTHER)
    assert status == 204 and "POST" in h["access-control-allow-methods"]
    assert h["access-control-allow-origin"] == OTHER
    status, _, h = c.call("OPTIONS", INVOKE, origin="https://evil.example")
    assert status == 403 and "access-control-allow-origin" not in h


def test_bodies_must_be_json_and_bounded(c: Client) -> None:
    assert c.post(VALIDATE, {"inputs": ADD}, ctype="text/plain")[0] == 400
    big = {"inputs": {"name": "x" * (300 * 1024)}}
    assert c.post(VALIDATE, big)[0] == 413
    assert c.post(VALIDATE, [1, 2])[0] == 400


def test_too_many_requests_in_flight_for_one_person_is_429(c: Client) -> None:
    c.app.inflight["alice"] = 4
    status, _, h = c.post(VALIDATE, {"inputs": ADD})
    assert status == 429 and h["retry-after"] == "1"
    assert c.post(VALIDATE, {"inputs": ADD}, user="bob")[0] == 200  # another person is not held


# -- errors are scrubbed -------------------------------------------------------------------------


def test_a_backends_text_never_reaches_the_body(c: Client, monkeypatch) -> None:
    from arras import Conflict

    def boom(self, *a, **k):
        raise Conflict("exists", "SECRET-VALUE-FROM-THE-INPUT")

    monkeypatch.setattr(MemoryStore, "apply", boom)
    status, e, _ = c.post(INVOKE, {"inputs": ADD})
    assert status == 409 and "SECRET" not in json.dumps(e)
    assert e["error"]["message"] == "conflict (exists)"


# -- audit ---------------------------------------------------------------------------------------


def test_changes_show_who_did_what_and_need_the_journal_grant(c: Client) -> None:
    _, r, _ = c.post(INVOKE, {"inputs": ADD})
    status, page, _ = c.post(
        "/audit/changes",
        {"module": "catalog", "type": "catalog.UseCase", "key": "uc-x", "limit": 20},
    )
    assert status == 200 and page["truncated"] is False and page["nextCursor"] is None
    [ch] = page["items"]
    assert (ch["by"], ch["action"], ch["group"]) == ("alice", "catalog.AddUseCase", r["group"])
    assert page["freshness"]["backend"] == "memory"
    status, one, _ = c.post("/audit/changes", {"group": r["group"]})
    assert status == 200 and one["items"][0]["group"] == r["group"]
    status, e, _ = c.post("/audit/changes", {"module": "catalog"}, user="carol")
    assert status == 403 and e["error"]["reason"] == "no_access"
    assert c.post("/audit/changes", {}, user="alice")[0] == 400  # a scope is needed
    assert c.post("/audit/changes", {"module": "catalog", "limit": 101})[0] == 400
    assert c.post("/audit/changes", {"module": "catalog", "since": "yesterday"})[0] == 400
    c.box.access.expire(c.box.people["alice"].token)
    assert c.post("/audit/changes", {"module": "catalog"})[0] == 401


def test_loads_list_the_imports(c: Client) -> None:
    root = c.box.arras.session(c.box.people["root"])
    rec = {
        "type": "catalog.UseCase",
        "key": "uc-i",
        "properties": {"name": "I", "workArea": "finance"},
    }
    root.import_records("catalog", [rec], load_id="L9")
    status, page, _ = c.post("/audit/loads", {"module": "catalog"})
    assert status == 200 and page["items"][0]["load_id"] == "L9"
    assert c.post("/audit/loads", {})[0] == 400


# -- the dev host --------------------------------------------------------------------------------


def test_the_dev_host_serves_the_apis_and_the_ui_at_one_origin_and_survives_parallel_writes(
    tmp_path,
) -> None:
    import threading

    from arras.devhost import DevHost

    (tmp_path / "index.html").write_text("<p>ui</p>")
    (tmp_path / "app.js").write_text("1")
    host = DevHost(Sandbox().seed(), port=8000, ui_dir=tmp_path)
    origin = "http://127.0.0.1:8000"

    def call(
        method: str,
        path: str,
        body: Any = None,
        user: str = "alice",
        host_header: str | None = None,
    ) -> tuple[int, bytes]:
        data = json.dumps(body).encode() if body is not None else b""
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [
                (b"content-type", b"application/json"),
                (b"x-arras-user", user.encode()),
                (b"origin", origin.encode()),
                (b"host", (host_header or "127.0.0.1:8000").encode()),
            ],
        }
        sent: list[dict] = []

        async def receive() -> dict:
            return {"type": "http.request", "body": data, "more_body": False}

        async def send(msg: dict) -> None:
            sent.append(msg)

        asyncio.run(host(scope, receive, send))
        return sent[0]["status"], sent[1]["body"]

    assert call("GET", "/") == (200, b"<p>ui</p>")
    assert call("GET", "/app.js") == (200, b"1")
    assert call("GET", "/modules/catalog") == (200, b"<p>ui</p>")  # a route of the app
    (tmp_path.parent / "secret.txt").write_text("SECRET")
    for escape in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt"):
        status, body = call("GET", escape)
        assert b"SECRET" not in body and status in (200, 404)
    assert call("GET", "/", host_header="evil.example:8000")[0] == 403  # a rebound hostname
    assert call("GET", "/missing.png")[0] == 404
    status, body = call("GET", "/api/people")
    assert status == 200 and "alice" in json.loads(body)["people"]
    status, body = call(
        "POST", "/api/console/graphql/catalog", {"query": "{ useCaseList { items { key } } }"}
    )
    assert status == 200 and json.loads(body)["data"]["useCaseList"]["items"]
    results: list[int] = []

    def add(i: int) -> None:
        results.append(
            call(
                "POST",
                "/api/operate/actions/catalog/AddUseCase/invoke",
                {"inputs": {"code": f"p{i}", "name": "P", "workArea": "finance"}},
            )[0]
        )

    threads = [threading.Thread(target=add, args=(i,)) for i in range(16)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(set(results)) == [200, 429] or results == [200] * 16
    ok = results.count(200)
    status, body = call(
        "POST",
        "/api/operate/audit/changes",
        {"module": "catalog", "action": "catalog.AddUseCase", "limit": 100},
    )
    assert status == 200 and len(json.loads(body)["items"]) == ok + 2  # the two seeded use cases
    assert (
        call(
            "POST", "/api/operate/actions/catalog/AddUseCase/invoke", {"inputs": {}}, user="nobody"
        )[0]
        == 401
    )


def test_the_uis_openapi_snapshot_matches_the_surface() -> None:
    from pathlib import Path

    snap = Path(__file__).resolve().parent.parent / "ui" / "openapi.json"
    assert json.loads(snap.read_text()) == openapi_document(), (
        "run: uv run python tests/regen_openapi.py"
    )


# -- review findings ------------------------------------------------------------------------------


def test_a_conflict_in_a_validation_is_worded_by_kind_and_never_echoes_a_key(c: Client) -> None:
    c.post(INVOKE, {"inputs": ADD, "idempotency_key": "my-secret-key"})
    status, v, _ = c.post(
        VALIDATE, {"inputs": {**ADD, "name": "other"}, "idempotency_key": "my-secret-key"}
    )
    assert status == 200 and not v["ok"]
    assert "my-secret-key" not in json.dumps(v)
    assert {
        "id": "conflict:idempotency_key_reused",
        "reason": "conflict (idempotency_key_reused)",
    } in v["failures"]
    _, v2, _ = c.post(
        "/actions/catalog/AddSolution/validate",
        {"inputs": {"code": "sol-1", "name": "N", "useCase": "uc-pipeline"}},
    )
    assert "Ref(" not in json.dumps(v2)


def test_a_time_without_an_offset_is_a_400_not_a_500(c: Client) -> None:
    for bad in ("2026-01-01T00:00:00", "2026-01-01"):
        status, e, _ = c.post("/audit/changes", {"module": "catalog", "since": bad})
        assert status == 400, bad
    assert (
        c.post("/audit/changes", {"module": "catalog", "since": "2026-01-01T00:00:00Z"})[0] == 200
    )
    import pytest as _pt

    from arras import Invalid

    with _pt.raises(Invalid):
        from datetime import datetime

        c.box.arras.session(c.box.people["alice"]).changes("catalog", since=datetime(2026, 1, 1))


def test_flags_and_revisions_are_type_checked(c: Client) -> None:
    items = [{**ADD, "code": "t1"}]
    assert (
        c.post("/actions/catalog/AddUseCase/batch", {"items": items, "atomic": "false"})[0] == 400
    )
    assert (
        c.post("/actions/catalog/AddUseCase/batch", {"items": items, "stop_on_error": 1})[0] == 400
    )
    for rev in ({"memory": True}, {"memory": 1.5}, {"memory": [1]}, {"": 1}, [1]):
        status, _, _ = c.post(INVOKE, {"inputs": ADD, "expected_revision": rev})
        assert status == 400, rev


def test_a_group_lookup_with_no_match_is_an_empty_page_for_everyone(c: Client) -> None:
    c.post(INVOKE, {"inputs": ADD})
    _, page, _ = c.post("/audit/changes", {"group": "g-1", "after": "5"})
    assert page["items"] == []
    status, none, _ = c.post("/audit/changes", {"group": "g-1"}, user="carol")  # no journal grant
    assert status == 200 and none["items"] == []  # the same answer as for a group that is not there


def test_the_host_hook_runs_before_the_library_hears_of_the_action(monkeypatch) -> None:
    from arras.core import Ontology

    seen: list[str] = []
    described: list[str | None] = []
    real = Ontology.describe

    def spy(self, module=None):
        described.append(module)
        return real(self, module)

    monkeypatch.setattr(Ontology, "describe", spy)
    allow = {"catalog.AddUseCase"}
    c = Client(authorize_action=lambda p, m, a: seen.append(a) or a in allow)
    assert c.post("/actions/catalog/NoSuchAction/invoke", {"inputs": {}})[0] == 403
    assert c.post("/actions/catalog/CorrectSolution/validate", {"inputs": {}})[0] == 403
    assert seen == ["catalog.NoSuchAction", "catalog.CorrectSolution"]
    assert described == []  # not even asked whether the action exists
    assert c.post(VALIDATE, {"inputs": ADD})[0] == 200  # the spy sees an allowed one
    assert described == ["catalog"]


def test_a_slot_is_released_when_the_work_ends_and_the_table_does_not_grow(c: Client) -> None:
    for user in ("alice", "bob", "carol"):
        c.post(VALIDATE, {"inputs": ADD}, user=user)
    assert c.app.inflight == {}  # nothing held, nothing kept for people who have gone
    c.app.inflight.update({"a": 8, "b": 8})  # the pool is full across people
    status, _, h = c.post(VALIDATE, {"inputs": ADD}, user="bob")
    assert status == 429 and h["retry-after"] == "1"


def test_a_cancelled_caller_does_not_free_the_slot_before_the_work_ends() -> None:
    import threading

    c = Client()
    gate, entered = threading.Event(), threading.Event()
    real = MemoryStore.apply

    def slow(self, *a, **k):
        entered.set()
        gate.wait(5)
        return real(self, *a, **k)

    MemoryStore.apply = slow
    try:

        async def run() -> int:
            scope = {
                "type": "http",
                "method": "POST",
                "path": INVOKE,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"x-user", b"alice"),
                    (b"origin", PUBLIC.encode()),
                ],
            }
            data = json.dumps({"inputs": ADD}).encode()

            async def receive() -> dict:
                return {"type": "http.request", "body": data, "more_body": False}

            async def send(_: dict) -> None:
                return None

            task = asyncio.ensure_future(c.app(scope, receive, send))
            while not entered.is_set():
                await asyncio.sleep(0.01)
            held = c.app.inflight.get("alice", 0)
            task.cancel()
            await asyncio.sleep(0.05)
            still = c.app.inflight.get("alice", 0)  # the work is still running
            gate.set()
            await asyncio.sleep(0.2)
            return held * 10 + still

        out = asyncio.run(run())
    finally:
        MemoryStore.apply = real
        gate.set()
    assert out == 11  # held while running, still held after the caller left
    assert c.app.inflight == {}  # and released when the work ended


def test_the_console_names_its_origins_or_compares_the_host_with_ports_and_case_normalized() -> (
    None
):
    from arras.http import parse_origin, post_origin_ok

    def _cross_origin(headers: dict, allowed: set) -> bool:
        return not post_origin_ok(headers, set(), allowed, browser_or_host=True)

    none: set = set()
    assert not _cross_origin({"origin": "https://H.example", "host": "h.example:443"}, none)
    assert not _cross_origin({"origin": "http://h.example:8000", "host": "H.EXAMPLE:8000"}, none)
    assert _cross_origin({"origin": "http://h.example", "host": "h.example:8000"}, none)
    assert _cross_origin({"origin": "null", "host": "h.example"}, none)
    origin = parse_origin("https://app.example")
    assert origin is not None
    named = {origin}
    # behind a proxy that rewrites Host, the host's own names decide
    assert not _cross_origin({"origin": "https://app.example", "host": "localhost:8000"}, named)
    assert _cross_origin({"origin": "https://localhost:8000", "host": "localhost:8000"}, named)
    assert _cross_origin({"sec-fetch-site": "cross-site"}, named)


def test_demo_seed_adds_use_cases_and_solutions() -> None:
    from arras.devhost import seed_demo

    box = seed_demo(Sandbox().seed())
    o = box.arras.session(box.people["alice"])
    cases = o.query(
        "catalog", "SELECT u.* FROM catalog.UseCase u ORDER BY u.code LIMIT 100", limit=100
    )
    sols = o.query(
        "catalog", "SELECT s.* FROM catalog.Solution s ORDER BY s.code LIMIT 100", limit=100
    )
    assert len(cases.rows) == 14  # 2 sandbox + 12 demo
    assert len(sols.rows) == 11  # 1 sandbox + 10 demo


def test_the_dev_host_can_break_and_mend_the_sandbox_for_a_test(tmp_path) -> None:
    from arras.devhost import DevHost

    host = DevHost(Sandbox().seed(), port=8000, ui_dir=tmp_path)
    origin = "http://127.0.0.1:8000"

    def call(
        path: str, body: Any, *, origin_header: str | None = origin, who: str = "alice"
    ) -> int:
        data = json.dumps(body).encode()
        hdrs = [
            (b"host", b"127.0.0.1:8000"),
            (b"content-type", b"application/json"),
            (b"x-arras-user", who.encode()),
        ]
        if origin_header:
            hdrs.append((b"origin", origin_header.encode()))
        sent: list[dict] = []

        async def receive() -> dict:
            return {"type": "http.request", "body": data, "more_body": False}

        async def send(msg: dict) -> None:
            sent.append(msg)

        asyncio.run(
            host({"type": "http", "method": "POST", "path": path, "headers": hdrs}, receive, send)
        )
        return sent[0]["status"]

    q = "/api/operate/audit/changes"
    assert call(q, {"module": "catalog"}) == 200
    assert call("/api/dev/control", {"op": "expire", "user": "alice"}) == 200
    assert call(q, {"module": "catalog"}) == 401  # an expired token is a 401 on the real surface
    assert call("/api/dev/control", {"op": "restore", "user": "alice"}) == 200
    assert call(q, {"module": "catalog"}) == 200
    assert (
        call("/api/dev/control", {"op": "outage", "backend": "memory", "reason": "unreachable"})
        == 200
    )
    assert call(q, {"module": "catalog"}) == 503
    assert call("/api/dev/control", {"op": "outage", "backend": "memory", "reason": None}) == 200
    assert call("/api/dev/control", {"op": "feed"}) == 200
    assert call("/api/dev/control", {"op": "nope"}) == 400
    assert call("/api/dev/control", {"op": "expire", "user": "nobody"}) == 400
    assert call("/api/dev/control", {"op": "feed"}, origin_header="https://evil.example") == 403


def test_the_dev_host_accepts_an_ipv6_loopback_host() -> None:
    from arras.devhost import _host_name

    assert _host_name("[::1]:8000") == "[::1]"
    assert _host_name("127.0.0.1:8000") == "127.0.0.1"
    assert _host_name("localhost") == "localhost"


# -- every error type, scrubbed (CONTRACT-009, Status codes and Error body) ---------------------

SECRET = "SECRET-7f3a"


def _noted(e: Exception) -> Exception:
    e.add_note(f"item 0 {SECRET}")
    return e


def _errors() -> dict[str, tuple[Any, int, str]]:
    """Each error a backend may raise, with the backend's text in its detail and notes: the
    status it maps to and the message the surface rebuilds from its type and reason."""
    from arras import (
        Conflict,
        NotYetCurrent,
        PreconditionFailed,
        Refused,
        Unavailable,
        Unsupported,
    )
    from arras.errors import Failure

    return {
        "Unavailable": (
            lambda: _noted(Unavailable("memory", "unreachable", SECRET)),
            503,
            "memory is unavailable (unreachable)",
        ),
        "Unsupported": (
            lambda: _noted(Unsupported("changes", ["changes"])),
            501,
            "not supported",
        ),
        "NotYetCurrent": (
            lambda: _noted(NotYetCurrent("fake:1", "memory_replica")),
            409,
            "the replica has not reached that position",
        ),
        "Conflict": (lambda: _noted(Conflict("exists", SECRET)), 409, "conflict (exists)"),
        "PreconditionFailed": (
            lambda: _noted(
                PreconditionFailed([Failure("fresh", "a use case with that code exists")])
            ),
            422,
            "a precondition failed",
        ),
        "Refused-no_access": (
            lambda: _noted(Refused("memory", "apply", "no_access")),
            403,
            "no access",
        ),
        "Refused-token_expired": (
            lambda: _noted(Refused("memory", "apply", "token_expired")),
            401,
            "sign in again",
        ),
        "RuntimeError": (lambda: RuntimeError(SECRET), 500, "internal error"),
    }


# (verb, the fake's method that is made to fail, path, body)
_VERBS = {
    "invoke": ("apply", INVOKE, {"inputs": ADD}),
    "validate": ("_validate", VALIDATE, {"inputs": ADD}),
    "batch": ("apply_batch", "/actions/catalog/AddUseCase/batch", {"items": [ADD]}),
    "changes": ("changes", "/audit/changes", {"module": "catalog"}),
    "loads": ("loads", "/audit/loads", {"module": "catalog"}),
}


@pytest.mark.parametrize("verb", sorted(_VERBS))
@pytest.mark.parametrize("kind", sorted(_errors()))
def test_every_error_type_maps_to_its_status_and_never_echoes_detail(
    verb: str, kind: str, monkeypatch, caplog
) -> None:
    import logging

    make, status, message = _errors()[kind]
    method, path, body = _VERBS[verb]

    def fail(self, *a, **k):
        raise make()

    c = Client()  # seeded before the backend is made to fail
    monkeypatch.setattr(MemoryStore, method, fail)
    with caplog.at_level(logging.DEBUG, logger="arras"):
        got, e, headers = c.post(path, body)
    assert got == status, (verb, kind, e)
    assert SECRET not in json.dumps(e) and SECRET not in json.dumps(headers)
    assert "_type" not in json.dumps(e)
    err = e["error"]
    assert err["message"] == message
    assert "detail" not in err and "notes" not in err
    if kind != "RuntimeError":
        assert err["type"] == kind.split("-")[0]
    if kind.startswith("Refused"):
        assert err["reason"] == kind.split("-")[1]
    for r in caplog.records:  # the operator's log at INFO never carries the backend's text
        if r.levelno == logging.INFO:
            assert SECRET not in r.getMessage() and not r.exc_info
        if kind != "RuntimeError" and r.levelno >= logging.INFO:
            assert SECRET not in r.getMessage() and not r.exc_info


@pytest.mark.parametrize("kind", ["Conflict", "PreconditionFailed", "Unavailable"])
def test_a_batch_items_refusal_is_scrubbed_like_any_error(kind: str, monkeypatch) -> None:
    from arras.results import BatchReceipt, ItemResult

    make, _, message = _errors()[kind]
    real = MemoryStore.apply_batch

    def one_refused(self, principal, plans, **k):
        ok = real(self, principal, plans[:1], **k)
        return BatchReceipt(
            ok.action, False, (ok.items[0], ItemResult(1, refusal=make())), 1, 1, ok.token
        )

    monkeypatch.setattr(MemoryStore, "apply_batch", one_refused)
    c = Client()
    items = [{**ADD, "code": "i0"}, {**ADD, "code": "i1"}]
    status, b, h = c.post("/actions/catalog/AddUseCase/batch", {"items": items})
    assert status == 200 and SECRET not in json.dumps(b) and SECRET not in json.dumps(h)
    refusal = b["items"][1]["refusal"]
    assert refusal["type"] == kind and refusal["message"] == message
    assert "detail" not in refusal and "notes" not in refusal and "_type" not in json.dumps(b)
    assert b["items"][0]["receipt"]["created"] == 1 and (b["succeeded"], b["failed"]) == (1, 1)


def test_a_conflict_inside_validate_is_scrubbed(monkeypatch) -> None:
    from arras import Conflict

    real = MemoryStore._effects

    def clash(self, *a, **k):
        raise Conflict("exists", SECRET)

    c = Client()
    monkeypatch.setattr(MemoryStore, "_effects", clash)
    status, v, _ = c.post(VALIDATE, {"inputs": ADD})
    assert status == 200 and v["ok"] is False and SECRET not in json.dumps(v)
    assert v["failures"] == [{"id": "conflict:exists", "reason": "conflict (exists)"}]
    _ = real


def test_a_group_that_no_provider_can_look_up_is_not_echoed(monkeypatch) -> None:
    from arras import Unsupported

    def no_journal(self, *a, **k):
        raise Unsupported("changes", [])

    monkeypatch.setattr(MemoryStore, "changes", no_journal)
    c = Client()
    status, e, _ = c.post("/audit/changes", {"group": f"g-{SECRET}"})
    assert status == 501 and SECRET not in json.dumps(e)  # every provider keeps no journal


# -- origin and headers (CONTRACT-009, Cross-origin and request rules) ----------------------------


def test_same_origin_by_sec_fetch_site_is_accepted_with_or_without_an_origin() -> None:
    bare = Client(public_origin=None, allowed_origins=())  # the host named no origin
    same = {"sec-fetch-site": "same-origin"}
    here = "http://ops.internal:8000"
    host = {"host": "ops.internal:8000"}
    # a browser's POST always carries Origin; same-origin is the browser's own word
    assert bare.post(VALIDATE, {"inputs": ADD}, origin=here, extra={**host, **same})[0] == 200
    assert bare.post(VALIDATE, {"inputs": ADD}, origin=None, extra=same)[0] == 200
    # the configured origins still pass without it, and an unlisted one does not
    c = Client()
    assert c.post(VALIDATE, {"inputs": ADD}, origin=PUBLIC, extra=same)[0] == 200
    assert c.post(VALIDATE, {"inputs": ADD}, origin=here, extra=same)[0] == 200
    assert c.post(VALIDATE, {"inputs": ADD}, origin=here)[0] == 403
    assert bare.post(VALIDATE, {"inputs": ADD}, origin=here, extra=host)[0] == 403
    for site in ("cross-site", "same-site", "none", "SAME-SITE"):
        for o in (None, here):
            got = bare.post(VALIDATE, {"inputs": ADD}, origin=o, extra={"sec-fetch-site": site})
            assert got[0] == 403, (site, o)
    # an origin that is not one well-formed origin is refused even with the browser's word
    for bad in ("null", "http://a.example, http://b.example", "ops.internal"):
        assert bare.post(VALIDATE, {"inputs": ADD}, origin=bad, extra=same)[0] == 403, bad


def test_a_repeated_origin_or_sec_fetch_site_is_refused_not_read_as_one_of_them() -> None:
    c = Client()
    for first, second in (
        (PUBLIC, PUBLIC),
        (PUBLIC, "https://evil.example"),
        ("https://evil.example", PUBLIC),
    ):
        status, _, h = c.call(
            "POST", VALIDATE, {"inputs": ADD}, origin=first, headers=[("origin", second)]
        )
        assert status == 403 and "access-control-allow-origin" not in h, (first, second)
        status, _, h = c.call("OPTIONS", INVOKE, origin=first, headers=[("origin", second)])
        assert status == 403 and "access-control-allow-origin" not in h
    for pair in (
        ("same-origin", "same-origin"),
        ("cross-site", "same-origin"),
        ("same-origin", "cross-site"),
    ):
        status, _, _ = c.call(
            "POST",
            VALIDATE,
            {"inputs": ADD},
            origin=None,
            headers=[("sec-fetch-site", pair[0]), ("sec-fetch-site", pair[1])],
        )
        assert status == 403, pair


def test_origins_are_compared_with_default_ports_case_and_ipv6_brackets() -> None:
    c = Client(public_origin="http://[::1]:8000", allowed_origins=("https://Ops.Example:443",))
    assert c.post(VALIDATE, {"inputs": ADD}, origin="http://[::1]:8000")[0] == 200
    assert c.post(VALIDATE, {"inputs": ADD}, origin="http://[::1]:8001")[0] == 403
    assert c.post(VALIDATE, {"inputs": ADD}, origin="http://[::2]:8000")[0] == 403
    assert c.post(VALIDATE, {"inputs": ADD}, origin="https://ops.example")[0] == 200
    assert c.post(VALIDATE, {"inputs": ADD}, origin="http://ops.example")[0] == 403
    v6 = Client(public_origin="http://[::1]")
    status, _, h = v6.post(VALIDATE, {"inputs": ADD}, origin="http://[::1]:80")
    assert status == 200 and h["access-control-allow-origin"] == "http://[::1]:80"


_ENDPOINTS = [
    ("GET", "/version", None),
    ("GET", "/openapi.json", None),
    ("POST", VALIDATE, {"inputs": ADD}),
    ("POST", INVOKE, {"inputs": {**ADD, "code": "uc-hdr"}, "idempotency_key": "hdr"}),
    (
        "POST",
        "/actions/catalog/AddUseCase/batch",
        {"items": [{**ADD, "code": "uc-b"}], "idempotency_key": "b"},
    ),
    ("POST", "/audit/changes", {"module": "catalog"}),
    ("POST", "/audit/loads", {"module": "catalog"}),
    ("POST", "/nowhere", {}),
    ("GET", INVOKE, None),
    ("PUT", "/audit/changes", {}),
]


@pytest.mark.parametrize("method,path,body", _ENDPOINTS, ids=lambda x: str(x)[:40])
@pytest.mark.parametrize("origin", [PUBLIC, OTHER, "https://evil.example", None])
def test_every_answer_is_no_store_and_carries_cors_only_for_an_allowed_origin(
    method: str, path: str, body: Any, origin: str | None
) -> None:
    c = Client()
    status, _, h = c.call(method, path, body, origin=origin)
    assert h["cache-control"] == "no-store", (method, path)
    if origin in (PUBLIC, OTHER):
        assert h["access-control-allow-origin"] == origin
        assert h["access-control-allow-credentials"] == "true"
        assert h["vary"] == "Origin"
    else:
        assert not {
            "access-control-allow-origin",
            "access-control-allow-credentials",
            "vary",
        } & set(h)
    if method == "POST" and path != "/nowhere" and origin in (PUBLIC, OTHER):
        assert status == 200


@pytest.mark.parametrize("path", [INVOKE, "/audit/changes", "/version", "/anything/at/all"])
def test_a_preflight_states_methods_headers_and_age(path: str) -> None:
    c = Client()
    status, body, h = c.call("OPTIONS", path, origin=OTHER, user=None)
    assert status == 204 and body is None
    assert h["access-control-allow-origin"] == OTHER
    assert h["access-control-allow-methods"] == "POST, GET"
    assert h["access-control-allow-headers"] == "content-type"
    assert h["access-control-allow-credentials"] == "true"
    assert h["access-control-max-age"] == "600"
    assert h["vary"] == "Origin" and h["cache-control"] == "no-store"
    for bad in ("https://evil.example", None):
        status, _, h = c.call("OPTIONS", path, origin=bad, user=None)
        assert status == 403 and h["cache-control"] == "no-store"
        assert "access-control-allow-origin" not in h and "access-control-allow-methods" not in h


# -- batches over HTTP (CONTRACT-003 through CONTRACT-009) ---------------------------------------

BATCH = "/actions/catalog/AddUseCase/batch"


def _groups(c: Client) -> list[str]:
    return [
        x["group"]
        for x in c.post("/audit/changes", {"module": "catalog", "limit": 100})[1]["items"]
    ]


def test_an_atomic_batch_with_one_failing_item_applies_and_records_nothing(c: Client) -> None:
    before = _groups(c)
    items = [{**ADD, "code": "a1"}, {**ADD, "code": "uc-pipeline"}, {**ADD, "code": "a2"}]
    status, e, _ = c.post(BATCH, {"items": items, "atomic": True})
    assert status == 422 and e["error"]["type"] == "PreconditionFailed"
    assert _groups(c) == before
    q = "SELECT u.code FROM catalog.UseCase u WHERE u.code = 'a1' ORDER BY u.code LIMIT 100"
    assert c.box.arras.session(c.box.people["alice"]).query("catalog", q).rows == ()


def test_an_atomic_batch_is_one_group_and_a_resend_with_its_key_replays(c: Client) -> None:
    before = _groups(c)
    items = [{**ADD, "code": f"g{i}"} for i in range(3)]
    status, b, _ = c.post(BATCH, {"items": items, "atomic": True, "idempotency_key": "ab-1"})
    assert status == 200 and b["atomic"] is True and (b["succeeded"], b["failed"]) == (3, 0)
    [group] = {i["receipt"]["group"] for i in b["items"]}
    assert all(i["receipt"]["replayed"] is False for i in b["items"])
    assert _groups(c) == [group, *before]  # one change for the whole batch
    status, again, _ = c.post(BATCH, {"items": items, "atomic": True, "idempotency_key": "ab-1"})
    assert status == 200 and all(i["receipt"]["replayed"] is True for i in again["items"])
    assert {i["receipt"]["group"] for i in again["items"]} == {group}
    assert _groups(c) == [group, *before]  # a replay records nothing
    other = [{**ADD, "code": "g0", "name": "changed"}]
    status, e, _ = c.post(BATCH, {"items": other, "atomic": True, "idempotency_key": "ab-1"})
    assert status == 409 and e["error"]["reason"] == "idempotency_key_reused"


def test_an_independent_batch_records_one_group_per_item_and_stop_on_error_stops(c: Client) -> None:
    before = _groups(c)
    items = [{**ADD, "code": "i0"}, {**ADD, "code": "uc-pipeline"}, {**ADD, "code": "i2"}]
    status, b, _ = c.post(BATCH, {"items": items, "idempotency_key": "ib"})
    assert status == 200 and b["atomic"] is False and (b["succeeded"], b["failed"]) == (2, 1)
    groups = [i["receipt"]["group"] for i in b["items"] if "receipt" in i]
    assert len(set(groups)) == 2 and _groups(c) == [*groups[::-1], *before]
    assert b["items"][1] == {
        "index": 1,
        "refusal": {
            "type": "PreconditionFailed",
            "message": "a precondition failed",
            "failures": [{"id": "fresh", "reason": "a use case with that code exists"}],
        },
    }
    status, again, _ = c.post(BATCH, {"items": items, "idempotency_key": "ib"})
    assert [i["receipt"]["replayed"] for i in again["items"] if "receipt" in i] == [True, True]
    status, s, _ = c.post(
        BATCH,
        {"items": [{**ADD, "code": "uc-alerts"}, {**ADD, "code": "s9"}], "stop_on_error": True},
    )
    assert status == 200 and len(s["items"]) == 1 and (s["succeeded"], s["failed"]) == (0, 1)
    q = "SELECT u.code FROM catalog.UseCase u WHERE u.code = 's9' ORDER BY u.code LIMIT 100"
    assert c.box.arras.session(c.box.people["alice"]).query("catalog", q).rows == ()
    status, n, _ = c.post(BATCH, {"items": [{**ADD, "code": "uc-alerts"}, {**ADD, "code": "s9"}]})
    assert len(n["items"]) == 2 and n["succeeded"] == 1  # without it, the rest still run


# -- plumbing -----------------------------------------------------------------------------------


def test_the_hosts_principal_hook_runs_off_the_event_loop() -> None:
    import threading

    seen: list[tuple[str, bool]] = []
    c = Client()
    real = c.who

    def who(request):
        try:
            asyncio.get_running_loop()
            on_loop = True
        except RuntimeError:
            on_loop = False
        seen.append((threading.current_thread().name, on_loop))
        return real(request)

    c.app.principal_for_request = who
    assert c.post(VALIDATE, {"inputs": ADD})[0] == 200
    [(thread, on_loop)] = seen
    assert thread != threading.main_thread().name and on_loop is False


def test_the_base_path_is_a_whole_segment_and_a_mounts_root_path_is_removed() -> None:
    c = Client(base_path="/api/operate")
    assert c.call("GET", "/api/operate/version")[0] == 200
    assert c.call("GET", "/api/operatefoo/version")[0] == 404
    assert c.call("GET", "/api/operateversion")[0] == 404  # the rest would route, were it read
    assert c.post("/api/operatefoo/actions/catalog/AddUseCase/validate", {"inputs": ADD})[0] == 404
    assert c.call("GET", "/version")[0] == 404
    assert c.post("/api/operate/actions/catalog/AddUseCase/validate", {"inputs": ADD})[0] == 200
    mounted = {"root_path": "/embedded"}
    assert c.call("GET", "/embedded/api/operate/version", scope=mounted)[0] == 200
    assert c.call("GET", "/embedded/api/operatex/version", scope=mounted)[0] == 404
    bare = Client()
    assert bare.call("GET", "/embedded/version", scope=mounted)[0] == 200


def test_a_body_is_read_whole_in_chunks_and_a_disconnect_or_bad_bytes_are_400(c: Client) -> None:
    data = json.dumps({"inputs": ADD}).encode()
    chunks = [
        {"type": "http.request", "body": data[:7], "more_body": True},
        {"type": "http.request", "body": data[7:20], "more_body": True},
        {"type": "http.request", "body": data[20:], "more_body": False},
    ]
    status, v, _ = c.call("POST", VALIDATE, messages=chunks)
    assert status == 200 and v["ok"] is True
    cut = [
        {"type": "http.request", "body": data[:7], "more_body": True},
        {"type": "http.disconnect"},
    ]
    status, e, _ = c.call("POST", VALIDATE, messages=cut)
    assert status == 400 and e["error"]["message"] == "client disconnected"
    for raw in (
        b'{"inputs": {"code": NaN}}',
        b'{"inputs": {"code": Infinity}}',
        b'{"inputs": {"code": -Infinity}}',
        b'{"inputs": {"code": "\xff\xfe"}}',
        b"{",
    ):
        status, e, _ = c.call("POST", VALIDATE, raw=raw)
        assert status == 400 and e["error"]["type"] == "BadRequest", raw
    status, e, _ = c.call("POST", "/audit/changes", raw=b"")
    assert status == 400  # an empty body is {}: no scope, so the library says Invalid


def _gated(monkeypatch):
    """`MemoryStore.apply` held at a gate: (entered count, release)."""
    import threading

    gate = threading.Event()
    lock = threading.Lock()
    entered = [0]
    real = MemoryStore.apply

    def slow(self, *a, **k):
        with lock:
            entered[0] += 1
        gate.wait(10)
        return real(self, *a, **k)

    monkeypatch.setattr(MemoryStore, "apply", slow)
    return entered, gate


async def _asgi(app, user: str, path: str = VALIDATE, body: Any = None) -> tuple[int, dict]:
    data = json.dumps(body or {"inputs": ADD}).encode()
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [
            (b"content-type", b"application/json"),
            (b"x-user", user.encode()),
            (b"origin", PUBLIC.encode()),
        ],
    }
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": data, "more_body": False}

    async def send(m: dict) -> None:
        sent.append(m)

    await app(scope, receive, send)
    return sent[0]["status"], {k.decode(): v.decode() for k, v in sent[0]["headers"]}


async def _until(cond, timeout: float = 5.0) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not cond():
        assert loop.time() < end, "timed out"
        await asyncio.sleep(0.005)


def test_a_fifth_request_from_one_person_is_429_while_four_run(monkeypatch) -> None:
    c = Client()
    entered, gate = _gated(monkeypatch)

    async def run() -> tuple[list[int], int, dict, dict]:
        held = [asyncio.ensure_future(_asgi(c.app, "alice")) for _ in range(4)]
        await _until(lambda: entered[0] == 4)
        fifth, h = await _asgi(c.app, "alice")
        inflight = dict(c.app.inflight)
        gate.set()
        done = await asyncio.gather(*held)
        return [s for s, _ in done], fifth, h, inflight

    try:
        statuses, fifth, h, inflight = asyncio.run(run())
    finally:
        gate.set()
    assert inflight == {"alice": 4}
    assert fifth == 429 and h["retry-after"] == "1" and h["cache-control"] == "no-store"
    assert statuses == [200] * 4
    assert c.app.inflight == {}


def test_the_global_cap_holds_across_people(monkeypatch) -> None:
    from arras.operate import MAX_IN_FLIGHT, MAX_WORKERS

    c = Client()
    for name in ("ana", "bea"):
        c.box.people[name] = c.box.access.grant(name, "catalog", "read", "write")
    entered, gate = _gated(monkeypatch)
    people = ["alice", "bob", "ana", "bea"]  # four each: sixteen, every one held at the gate

    async def run() -> tuple[list[int], int, dict]:
        held = [asyncio.ensure_future(_asgi(c.app, p)) for p in people for _ in range(4)]
        await _until(lambda: entered[0] == MAX_WORKERS)  # the pool is busy, the rest queued
        await _until(lambda: sum(c.app.inflight.values()) == MAX_IN_FLIGHT)
        seventeenth, _ = await _asgi(c.app, "carol")  # a fifth person, with nothing in flight
        inflight = dict(c.app.inflight)
        gate.set()
        done = await asyncio.gather(*held)
        return [s for s, _ in done], seventeenth, inflight

    try:
        statuses, seventeenth, inflight = asyncio.run(run())
    finally:
        gate.set()
    assert inflight == {p: 4 for p in people} and "carol" not in inflight
    assert seventeenth == 429
    assert statuses == [200] * 16 and entered[0] == 16
    assert c.app.inflight == {}


# -- the dev host: an expired token through every surface -----------------------------------------


def _dev(app, method: str, path: str, body: Any = None, **headers: str) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else b""
    hs = {"host": "127.0.0.1:8000", "content-type": "application/json", "x-arras-user": "alice"}
    hs.update({k.replace("_", "-"): v for k, v in headers.items()})
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [(k.encode(), v.encode()) for k, v in hs.items()],
    }
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": data, "more_body": False}

    async def send(m: dict) -> None:
        sent.append(m)

    asyncio.run(app(scope, receive, send))
    raw = sent[1]["body"]
    try:
        return sent[0]["status"], json.loads(raw)
    except ValueError:
        return sent[0]["status"], raw


def test_an_expired_token_is_a_401_on_every_surface_and_restore_mends_it(tmp_path) -> None:
    from arras.devhost import DevHost

    host = DevHost(Sandbox().seed(), port=8000, ui_dir=tmp_path)
    own = "http://127.0.0.1:8000"
    meta = ("/api/console/graphql", {"query": "{ modules { name } }"})
    module = ("/api/console/graphql/catalog", {"query": '{ useCase(key: "uc-pipeline") { key } }'})
    changes = ("/api/operate/audit/changes", {"module": "catalog"})
    invoke = ("/api/operate/actions/catalog/AddUseCase/validate", {"inputs": ADD})
    surfaces = (meta, module, changes, invoke)
    for path, body in surfaces:
        assert _dev(host, "POST", path, body, origin=own)[0] == 200, path
    assert (
        _dev(host, "POST", "/api/dev/control", {"op": "expire", "user": "alice"}, origin=own)[0]
        == 200
    )
    for path, body in (meta, module):
        status, out = _dev(host, "POST", path, body, origin=own)
        assert status == 401, path
        assert out == {
            "errors": [
                {
                    "message": "sign in again",
                    "extensions": {"code": "REFUSED", "reason": "token_expired"},
                }
            ]
        }
    for path, body in (changes, invoke):
        status, out = _dev(host, "POST", path, body, origin=own)
        assert status == 401 and out["error"]["reason"] == "token_expired", path
    # another person is not affected
    assert _dev(host, "POST", *module, origin=own, x_arras_user="bob")[0] == 200
    assert (
        _dev(host, "POST", "/api/dev/control", {"op": "restore", "user": "alice"}, origin=own)[0]
        == 200
    )
    for path, body in surfaces:
        assert _dev(host, "POST", path, body, origin=own)[0] == 200, path


def test_the_dev_host_answers_an_ipv6_loopback_and_its_control_takes_only_its_own_origin(
    tmp_path,
) -> None:
    from arras.devhost import DevHost

    host = DevHost(Sandbox().seed(), port=8000, ui_dir=tmp_path)
    assert _dev(host, "GET", "/api/people", host="[::1]:8000")[0] == 200
    assert _dev(host, "GET", "/api/people", host="[::2]:8000")[0] == 403
    assert (
        _dev(host, "POST", "/api/dev/control", {"op": "feed"}, origin="http://localhost:8000")[0]
        == 200
    )
    assert _dev(host, "POST", "/api/dev/control", {"op": "feed"})[0] == 200  # not a browser
    assert _dev(host, "GET", "/api/dev/control")[0] == 403
    assert (
        _dev(
            host,
            "POST",
            "/api/dev/control",
            {"op": "outage", "backend": "memory", "reason": "bogus"},
        )[0]
        == 400
    )
    status, page = _dev(host, "GET", "/")
    assert status == 200 and b"The UI is not built" in page  # no index.html in ui_dir


# -- the explorer's catalog (CONTRACT-009, GET explorer/schema-catalog.json) ---------------------

CATALOG = "/explorer/schema-catalog.json"
ENTRY_KEYS = {"id", "title", "category", "path", "text", "format", "description", "schemaFormat"}


def _odd_document() -> str:
    """The catalog module in other bytes: tabs, spaces before colons, an escape, no newline."""
    from arras.sandbox import catalog_document

    d = json.loads(catalog_document())
    root = {"modules": d.pop("modules"), **d}
    text = json.dumps(root, indent="\t", separators=(", ", " :  "))
    return text.replace('"Pipeline', '"\\u004cease', 1).rstrip("\n")


def test_the_catalog_lists_each_readable_module_with_its_document_verbatim(c: Client) -> None:
    from arras.sandbox import catalog_document

    status, body, h = c.call("GET", CATALOG, origin=None)
    assert status == 200 and h["cache-control"] == "no-store"
    assert h["content-type"] == "application/json"
    assert body["version"] == 1
    (entry,) = body["entries"]
    assert set(entry) == ENTRY_KEYS
    assert entry["id"] == "arras:catalog" and entry["title"] == "catalog"
    assert entry["category"] == "domain" and entry["path"] == "catalog.umf.json"
    assert entry["format"] == "json" and entry["schemaFormat"] == "umf"
    assert entry["text"] == catalog_document()  # the registered text, not a re-serialization
    rev = c.box.arras.session(c.box.people["alice"]).describe("catalog")[0].revision
    assert entry["description"] == (
        f"Registered at revision memory {rev['memory']}; record store memory; replicas memory_replica."
    )


def test_the_catalog_is_the_viewers_own(c: Client) -> None:
    assert c.call("GET", CATALOG, user="carol")[1]["entries"][0]["id"] == "arras:catalog"
    status, body, _ = c.call("GET", CATALOG, user="dave")  # dave reads no module here
    assert status == 200 and body == {"version": 1, "entries": []}


def test_the_catalog_needs_a_signed_in_viewer(c: Client) -> None:
    status, body, h = c.call("GET", CATALOG, user=None)
    assert status == 401 and body["error"]["type"] == "Refused"
    assert h["cache-control"] == "no-store"
    c.box.access.expire(c.box.people["alice"].token)
    status, body, _ = c.call("GET", CATALOG)
    assert status == 401 and body["error"]["reason"] == "token_expired"
    status, body, _ = c.call("GET", CATALOG, user="(no token)")
    assert status == 401 and body["error"]["reason"] == "token_expired"


def test_the_catalog_is_a_get_that_writes_nothing_and_needs_no_origin_proof(c: Client) -> None:
    before = c.box.store.state.seq
    assert c.call("GET", CATALOG, origin="https://evil.example")[0] == 200  # nothing to forge
    status, _, h = c.call("POST", CATALOG, {})
    assert status == 405 and h["allow"] == "GET"
    assert c.call("GET", "/explorer/other.json")[0] == 404
    assert c.box.store.state.seq == before


@pytest.mark.parametrize("origin", [PUBLIC, OTHER, "https://evil.example", None])
def test_the_catalog_carries_cors_only_for_an_allowed_origin(origin: str | None) -> None:
    _, _, h = Client().call("GET", CATALOG, origin=origin)
    cors = {"access-control-allow-origin", "access-control-allow-credentials", "vary"}
    if origin in (PUBLIC, OTHER):
        assert h["access-control-allow-origin"] == origin
    else:
        assert not cors & set(h)


def test_odd_whitespace_escapes_and_non_ascii_reach_the_explorer_byte_for_byte() -> None:
    text = _odd_document()
    c = Client(Sandbox().load(text))
    entry = c.call("GET", CATALOG)[1]["entries"][0]
    assert entry["text"] == text
    d = json.loads(text)
    d["modules"][0]["elements"][0]["description"] = "Cas d’usage — résumé "
    raw = json.dumps(d, ensure_ascii=False, indent=1)
    c = Client(Sandbox().load(raw))
    _, _, _ = c.call("GET", CATALOG)
    entry = c.call("GET", CATALOG)[1]["entries"][0]
    assert entry["text"].encode("utf-8") == raw.encode("utf-8")


def test_a_module_without_a_readable_document_is_omitted_not_an_error() -> None:
    from arras.sandbox import catalog_document

    box = Sandbox().seed()
    d = json.loads(catalog_document().replace('"catalog"', '"shelf"'))
    d["modules"][0]["actions"] = []
    box.arras = Arras.start(  # the host places `shelf` on the replica alone: read-only there
        box.backends,
        admin=box.people["root"],
        placement={"shelf": Placement(box.replica.name)},
        default_placement=Placement(box.store.name, (box.replica.name,)),
    )
    box.access.grant("root", "shelf", "read", "write", "schema", admin=True)
    box.arras.session(box.people["root"]).registry().attach(json.dumps(d))
    box.access.grant("alice", "shelf", "read")  # alice reads shelf, which has no document
    c = Client(box)
    status, body, _ = c.call("GET", CATALOG)
    assert status == 200 and [e["id"] for e in body["entries"]] == ["arras:catalog"]


def test_a_document_too_large_to_show_is_a_note_not_its_text() -> None:
    from arras.operate import explorer
    from arras.sandbox import catalog_document

    d = json.loads(catalog_document())
    d["modules"][0]["elements"][0]["description"] = "x" * (explorer.MAX_DOCUMENT + 1)
    c = Client(Sandbox().load(json.dumps(d)))
    (entry,) = c.call("GET", CATALOG)[1]["entries"]
    assert entry["id"] == "arras:catalog" and "x" * 100 not in entry["text"]
    assert "larger than" in entry["description"] and len(entry["text"]) < 1000
    assert json.loads(entry["text"])["title"] == "catalog (not shown)"


def test_an_outage_is_an_error_never_an_empty_catalog(c: Client) -> None:
    c.box.store.outage = "unreachable"
    status, body, h = c.call("GET", CATALOG)
    assert status == 503 and h["cache-control"] == "no-store"
    assert body["error"]["type"] == "Unavailable" and "detail" not in body["error"]
    c.box.replica.outage = "unreachable"
    assert c.call("GET", CATALOG)[0] == 503


def test_a_backends_text_never_reaches_the_catalogs_error(c: Client, monkeypatch) -> None:
    from arras import Unavailable

    def leak(self, principal, module):
        raise Unavailable("memory", "unreachable", "password=hunter2 at db.internal:5432")

    monkeypatch.setattr(MemoryStore, "document", leak)
    status, body, _ = c.call("GET", CATALOG)
    assert status == 503 and "hunter2" not in json.dumps(body) and "db.internal" not in str(body)


def test_the_catalog_holds_registered_documents_and_nothing_else(c: Client) -> None:
    c.post(INVOKE, {"inputs": {**ADD, "code": "uc-secret", "name": "Do not show"}})
    body = c.call("GET", CATALOG)[1]
    flat = json.dumps(body)
    assert "uc-secret" not in flat and "Do not show" not in flat and "uc-pipeline" not in flat
    assert "token-" not in flat and "alice" not in flat
