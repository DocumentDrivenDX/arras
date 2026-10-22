# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The published OpenAPI document against the surface's behavior (CONTRACT-009).

For every path and verb the document declares, real requests through the real app (success, every
refusal the fakes can be made to give) must answer only the status codes the document declares,
and a 200's body only the properties its schema names, as must an error body. The test fails when
the code and the document drift apart, in either direction it can see from here."""

from __future__ import annotations

import json
from typing import Any

import pytest

from arras.fakes import MemoryStore
from arras.operate import openapi_document
from test_operate import ADD, PUBLIC, Client

DOC = openapi_document()
SCHEMAS = DOC["components"]["schemas"]


def _schema(ref_or_schema: dict[str, Any]) -> dict[str, Any]:
    ref = ref_or_schema.get("$ref")
    return SCHEMAS[ref.rsplit("/", 1)[1]] if ref else ref_or_schema


def _props(s: dict[str, Any]) -> set[str]:
    return set(_schema(s).get("properties", {}))


def _concrete(path: str) -> str:
    return path.replace("{module}", "catalog").replace("{action}", "AddUseCase")


Request = dict[str, Any]


def _requests(path: str, verb: str) -> list[tuple[str, Request]]:
    """Requests that between them reach every answer the surface gives on this path."""
    if verb == "get" and path.startswith("/explorer/"):
        return [
            ("ok", {}),
            ("no viewer", {"user": None, "origin": None}),
            ("expired", {"expire": True}),
            ("crowded", {"crowd": True}),
            ("outage", {"outage": True}),
            ("no document kept", {"unsupported": "document"}),
            ("not an operator", {"user": "carol", "operator": False}),
        ]
    if verb == "get":
        return [("plain", {}), ("no viewer", {"user": None, "origin": None})]
    if path.startswith("/actions/"):
        good: Any = {"items": [ADD]} if path.endswith("/batch") else {"inputs": ADD}
        bad: Any = {"items": [{"code": 5}]} if path.endswith("/batch") else {"inputs": {"code": 5}}
        dup: Any = (
            {"items": [{**ADD, "code": "uc-pipeline"}], "atomic": True}
            if path.endswith("/batch")
            else {"inputs": {**ADD, "code": "uc-pipeline"}}
        )
        out = [
            ("ok", {"body": good}),
            ("invalid inputs", {"body": bad}),
            ("precondition", {"body": dup}),
            ("stale revision", {"body": {**good, "expected_revision": {"memory": 99}}}),
            ("unknown action", {"path": path.replace("AddUseCase", "NoSuch"), "body": good}),
            ("unreadable module", {"body": good, "user": "dave"}),
            ("cannot write", {"body": good, "user": "carol"}),
            ("not signed in", {"body": good, "user": None}),
            ("foreign origin", {"body": good, "origin": "https://evil.example"}),
            ("not json", {"body": good, "ctype": "text/plain"}),
            ("too large", {"raw": b'{"inputs": "' + b"x" * (300 * 1024) + b'"}'}),
            ("not an object", {"body": [1]}),
            ("outage", {"body": good, "outage": True}),
            ("crowded", {"body": good, "crowd": True}),
            ("expired", {"body": good, "expire": True}),
            ("no journal kept", {"body": good, "unsupported": "apply"}),
            ("not an operator", {"body": good, "user": "carol", "operator": False}),
        ]
        if not path.endswith("/batch"):
            out.append(("key reused", {"body": {**good, "idempotency_key": "k"}, "reuse": True}))
        return out
    if path == "/query":
        sql = "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
        q = {"module": "catalog", "sql": sql}
        return [
            ("ok", {"body": q}),
            ("bulk", {"body": {**q, "consistency": "bulk"}}),
            (
                "does not parse",
                {"body": {"module": "catalog", "sql": "DELETE FROM catalog.UseCase"}},
            ),
            ("bad limit", {"body": {**q, "limit": 101}}),
            ("a cursor, which a statement does not take", {"body": {**q, "after": "-1"}}),
            ("no module", {"body": {"sql": sql}}),
            ("unreadable module", {"body": q, "user": "dave"}),
            ("not signed in", {"body": q, "user": None}),
            ("foreign origin", {"body": q, "origin": "https://evil.example"}),
            ("not yet current", {"body": {**q, "consistency": "bulk", "at_least": "fake:999999"}}),
            ("outage", {"body": q, "outage": True}),
            ("expired", {"body": q, "expire": True}),
            ("too large", {"raw": b'{"sql": "' + b"x" * (300 * 1024) + b'"}'}),
            ("crowded", {"body": q, "crowd": True}),
            ("not json", {"body": q, "ctype": "text/plain"}),
            ("unsupported", {"body": q, "unsupported": "query"}),
        ]
    if path == "/export":
        e = {"module": "catalog"}
        return [
            ("ok", {"body": e}),
            ("a page", {"body": {**e, "limit": 5, "after": "5"}}),
            ("bad limit", {"body": {**e, "limit": 501}}),
            ("bad cursor", {"body": {**e, "after": "-1"}}),
            ("no module", {"body": {}}),
            ("unreadable module", {"body": e, "user": "dave"}),
            ("not signed in", {"body": e, "user": None}),
            ("foreign origin", {"body": e, "origin": "https://evil.example"}),
            ("outage", {"body": e, "outage": True}),
            ("unsupported", {"body": e, "unsupported": "export_records"}),
            ("expired", {"body": e, "expire": True}),
            ("too large", {"raw": b'{"module": "' + b"x" * (300 * 1024) + b'"}'}),
            ("crowded", {"body": e, "crowd": True}),
            ("not json", {"body": e, "ctype": "text/plain"}),
            ("not an operator", {"body": e, "user": "carol", "operator": False}),
        ]
    body = {"module": "catalog"}
    return [
        ("ok", {"body": body}),
        ("bad limit", {"body": {**body, "limit": 101}}),
        ("bad cursor", {"body": {**body, "after": "-1"}}),
        ("no journal grant", {"body": body, "user": "carol"}),
        ("unreadable module", {"body": body, "user": "dave"}),
        ("not signed in", {"body": body, "user": None}),
        ("foreign origin", {"body": body, "origin": "https://evil.example"}),
        ("outage", {"body": body, "outage": True}),
        ("no journal kept", {"body": body, "unsupported": path.rsplit("/", 1)[1]}),
        ("expired", {"body": body, "expire": True}),
        ("too large", {"raw": b'{"module": "' + b"x" * (300 * 1024) + b'"}'}),
        ("crowded", {"body": body, "crowd": True}),
        ("not json", {"body": body, "ctype": "text/plain"}),
        ("not an operator", {"body": body, "user": "carol", "operator": False}),
    ]


def _client(req: Request) -> Client:
    """The app; a request that says `operator: False` runs where carol is not an operator."""
    if req.get("operator") is False:
        return Client(authorize_operator=lambda p: p.user != "carol")
    return Client()


CASES = [
    (path, verb, name, req)
    for path, ops in DOC["paths"].items()
    for verb in ops
    if verb in ("get", "post")
    for name, req in _requests(path, verb)
]


@pytest.mark.parametrize("path,verb,name,req", CASES, ids=[f"{v} {p} {n}" for p, v, n, _ in CASES])
def test_every_answer_is_one_the_document_declares(
    path: str, verb: str, name: str, req: Request, monkeypatch
) -> None:
    from arras import Unsupported

    c = _client(req)
    op = DOC["paths"][path][verb]
    declared = set(op["responses"])
    target = req.get("path", _concrete(path))
    if req.get("outage"):
        c.box.store.outage = "unreachable"
    if req.get("crowd"):
        c.app.inflight["alice"] = 4
    if req.get("expire"):
        c.box.access.expire(c.box.people["alice"].token)
    if req.get("reuse"):
        c.post(target, req["body"])
        req = {**req, "body": {**req["body"], "inputs": {**ADD, "name": "other"}}}
    if method := req.get("unsupported"):

        def no(self, *a, **k):
            raise Unsupported(method, [])

        monkeypatch.setattr(MemoryStore, method, no)
    status, body, _ = c.call(
        verb.upper(),
        target,
        req.get("body"),
        user=req.get("user", "alice"),
        origin=req.get("origin", PUBLIC),
        ctype=req.get("ctype", "application/json"),
        raw=req.get("raw"),
    )
    assert str(status) in declared, (name, status, body)
    content = op["responses"][str(status)].get("content", {}).get("application/json")
    assert content is not None, (name, status)
    schema = _schema(content["schema"])
    if "oneOf" in schema:  # a 403 is an error or a refusal of a non-operator
        error = next(x for x in schema["oneOf"] if x["$ref"].endswith("/Error"))
        schema = _schema(error) if body.get("error") != "REFUSED" else schema
    if status == 200:
        assert set(body) <= _props(schema), (name, set(body) - _props(schema))
        for key in _props(schema) - {"replay"}:
            if key in ("freshness",) and path.startswith("/actions/") and body.get(key) is None:
                continue
            assert key in body, (name, key)
    elif body.get("error") == "REFUSED":  # a non-operator: its own declared shape
        assert body == {"error": "REFUSED", "reason": "not_operator"}
        assert {"$ref": "#/components/schemas/NotOperator"} in schema["oneOf"]
    else:
        assert set(body) == {"error"}
        error_props = set(schema["properties"]["error"]["properties"])
        assert set(body["error"]) <= error_props, (name, set(body["error"]) - error_props)


def test_every_declared_status_is_reached_by_some_request() -> None:
    """The other direction: a code the document declares that no request above reaches is a
    claim nothing checks. (Run after the parametrized test has proven each answer.)"""
    reached: dict[tuple[str, str], set[str]] = {}
    for path, verb, _, req in CASES:
        c = _client(req)
        target = req.get("path", _concrete(path))
        if req.get("outage"):
            c.box.store.outage = "unreachable"
        if req.get("crowd"):
            c.app.inflight["alice"] = 4
        if req.get("expire"):
            c.box.access.expire(c.box.people["alice"].token)
        if req.get("reuse"):
            c.post(target, req["body"])
            req = {**req, "body": {**req["body"], "inputs": {**ADD, "name": "other"}}}
        if req.get("unsupported"):
            continue  # needs a patched backend; proven in the test above
        status, _, _ = c.call(
            verb.upper(),
            target,
            req.get("body"),
            user=req.get("user", "alice"),
            origin=req.get("origin", PUBLIC),
            ctype=req.get("ctype", "application/json"),
            raw=req.get("raw"),
        )
        reached.setdefault((path, verb), set()).add(str(status))
    for (path, verb), got in reached.items():
        declared = set(DOC["paths"][path][verb]["responses"])
        missing = declared - got - {"501", "405"}  # 501 needs a patched backend; 405 a wrong verb
        assert not missing, (path, verb, sorted(missing))


def test_the_document_is_json_and_names_every_schema_it_references() -> None:
    text = json.dumps(DOC)
    for ref in {r.split('"')[0] for r in text.split('"$ref": "')[1:]}:
        assert ref.rsplit("/", 1)[1] in SCHEMAS, ref
