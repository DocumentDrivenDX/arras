# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic, reportOptionalSubscript=false, reportOptionalMemberAccess=false
import base64
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from arras.errors import Violation
from arras.mcp import McpServer, TokenSource, principal_from_token, serve
from arras.mcp.tools import action_tools, convert_inputs, snake, to_python
from arras.sandbox import Sandbox


class Rig:
    def __init__(self, user: str | None = "alice") -> None:
        self.box = Sandbox().seed()
        self.user = user
        self.now = 1000.0
        self.server = McpServer(
            self.box.arras,
            lambda: self.box.principal(self.user) if self.user else None,
            clock=lambda: self.now,
        )
        self.n = 0

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def rpc(self, method: str, params: Any = None) -> Any:
        self.n += 1
        msg = {"jsonrpc": "2.0", "id": self.n, "method": method}
        if params is not None:
            msg["params"] = params
        return self.server.handle(msg)

    def call(self, name: str, **args: Any) -> dict:
        r = self.rpc("tools/call", {"name": name, "arguments": args})
        return r["result"] if "result" in r else r

    def body(self, name: str, **args: Any) -> Any:
        return self.call(name, **args)["structuredContent"]


@pytest.fixture
def r() -> Rig:
    return Rig()


def test_initialize_negotiates_and_declares_tools(r: Rig) -> None:
    res = r.rpc("initialize", {"protocolVersion": "2025-03-26"})["result"]
    assert res["protocolVersion"] == "2025-06-18" and res["capabilities"]["tools"]["listChanged"]
    assert (
        r.rpc("initialize", {"protocolVersion": "1999-01-01"})["result"]["protocolVersion"]
        == "2025-06-18"
    )
    assert r.rpc("ping")["result"] == {}


def test_tools_are_generated_from_the_registry(r: Rig) -> None:
    tools = {t["name"]: t for t in r.rpc("tools/list")["result"]["tools"]}
    assert set(tools) == {
        "describe",
        "query",
        "validate_action",
        "catalog_add_use_case",
        "catalog_add_solution",
        "catalog_draft_solution",
        "catalog_correct_solution",
        "catalog_unlink_solution",
        "catalog_retire_use_case",
    }
    for fixed in ("describe", "query", "validate_action"):
        assert tools[fixed]["annotations"]["readOnlyHint"] is True
    assert tools["catalog_retire_use_case"]["annotations"]["destructiveHint"] is True
    assert tools["catalog_add_use_case"]["annotations"] == {
        "idempotentHint": True,
        "openWorldHint": False,
        "readOnlyHint": False,
    }
    assert (
        "Weft SQL" in tools["query"]["description"]
        and "arras-sql" not in tools["query"]["description"]
        and tools["query"]["description"].count('Example: module "catalog", SELECT x.') == 1
    )
    assert tools["query"]["inputSchema"]["required"] == ["module", "sql"]
    assert "after" not in tools["query"]["inputSchema"]["properties"]
    schema = tools["catalog_add_solution"]["inputSchema"]
    assert (
        "oneOf" not in schema and "anyOf" not in schema and "allOf" not in schema
    )  # no top-level combinators
    assert schema["additionalProperties"] is False
    assert "exactly one of inputs" in tools["catalog_add_solution"]["description"]
    assert schema["properties"]["inputs"]["required"] == ["code", "name", "useCase"]
    assert schema["properties"]["items"]["maxItems"] == 100
    assert (
        "workArea"
        not in tools["catalog_add_use_case"]["inputSchema"]["properties"]["inputs"]["required"]
    )
    assert "invoke" not in tools  # no generic write tool: the host classifies each by name


def test_snake_case_and_collisions() -> None:
    assert snake("SetCoverage") == "set_coverage" and snake("AddUCRecord") == "add_uc_record"
    from dataclasses import replace

    rig = Rig()
    [m] = rig.box.arras.session(rig.box.people["alice"]).describe()
    twin = replace(m, name="catalog_add", actions=())
    names = [t.tool for t in action_tools([m, twin, m])]
    assert len(names) == len(set(names))  # the second module of a name gets a suffix


def test_describe_lists_modules_tools_and_status(r: Rig) -> None:
    d = r.body("describe")
    [m] = d["modules"]
    assert m["name"] == "catalog" and {t["name"] for t in m["types"]} == {
        "catalog.UseCase",
        "catalog.Solution",
    }
    assert {a["name"]: a["tool"] for a in m["actions"]}[
        "catalog.AddSolution"
    ] == "catalog_add_solution"
    assert d["backends"]["memory"]["available"] and m["revision"]["memory"] == 1
    assert "_type" not in json.dumps(d)
    assert r.body("describe", module="catalog")["modules"][0]["name"] == "catalog"
    assert r.call("describe", module="nope")["isError"]


def test_query_is_compact_and_states_freshness(r: Rig) -> None:
    a = r.body(
        "query",
        module="catalog",
        sql="SELECT u.code, u.name FROM catalog.UseCase u WHERE u.code = :k ORDER BY u.code LIMIT 100",
        params={"k": "uc-pipeline"},
    )
    assert a["rows"] == [{"code": "uc-pipeline", "name": "Pipeline mapping"}]
    assert a["freshness"]["backend"] == "memory" and a["freshness"]["consistency"] == "latest"
    assert set(a) == {"rows", "truncated", "freshness"}  # no echo of the request, no cursor
    whole = r.body(
        "query",
        module="catalog",
        sql="SELECT u.*, RELATED_KEYS(u.addressedBy, 100) AS addressedBy FROM catalog.UseCase u"
        " WHERE u.code = 'uc-pipeline' ORDER BY u.code LIMIT 1",
    )["rows"][0]
    assert whole["addressedBy"] == ["sol-1"] and whole["_version"] == 1
    res = r.call(
        "query",
        module="catalog",
        sql="SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
    )
    assert json.loads(res["content"][0]["text"]) == res["structuredContent"]


def test_large_answers_are_cut_at_a_page_the_backend_can_continue(r: Rig) -> None:
    big = "x" * 1500
    recs = [{"type": "UseCase", "key": f"b{i:03}", "properties": {"name": big}} for i in range(100)]
    r.box.store.import_records(
        r.box.people["root"], "catalog", recs, load_id="L", initiated_by="root"
    )
    seen: list[str] = []
    last = ""
    for _ in range(40):  # the caller continues with a keyset predicate in its own statement
        a = r.body(
            "query",
            module="catalog",
            sql="SELECT u.code, u.name FROM catalog.UseCase u WHERE u.code > :last ORDER BY u.code"
            " LIMIT 1000",
            params={"last": last},
            limit=100,
        )
        assert len(json.dumps(a).encode()) <= 52 * 1024
        seen += [row["code"] for row in a["rows"]]
        if not a["truncated"]:
            break
        last = a["rows"][-1]["code"]
    assert seen == sorted(seen) and len(seen) == len(set(seen)) == 102  # every row, once, in order


def test_actions_are_tools_with_receipts_idempotency_and_batches(r: Rig) -> None:
    rec = r.body(
        "catalog_add_use_case", inputs={"code": "uc-9", "name": "Nine"}, idempotency_key="k"
    )
    assert rec["created"] == 1 and rec["replayed"] is False and rec["refs"][0]["key"] == "uc-9"
    again = r.body(
        "catalog_add_use_case", inputs={"code": "uc-9", "name": "Nine"}, idempotency_key="k"
    )
    assert again["replayed"] is True and again["token"] == rec["token"]
    b = r.body(
        "catalog_add_use_case", items=[{"code": "b1", "name": "B"}, {"code": "uc-9", "name": "dup"}]
    )
    assert (b["succeeded"], b["failed"]) == (1, 1) and b["items"][1]["refusal"]["failures"][0][
        "id"
    ] == "fresh"
    atomic = r.body(
        "catalog_add_use_case",
        items=[{"code": "c1", "name": "C"}, {"code": "c2", "name": "C"}],
        atomic=True,
    )
    assert atomic["atomic"] and atomic["succeeded"] == 2
    got = r.body(
        "query",
        module="catalog",
        sql="SELECT u.code FROM catalog.UseCase u WHERE u.code = 'uc-9' ORDER BY u.code LIMIT 100",
        at_least=rec["token"],
    )
    assert got["rows"] == [{"code": "uc-9"}]


def test_validate_action_writes_nothing(r: Rig) -> None:
    v = r.body(
        "validate_action",
        action="catalog.AddSolution",
        inputs={"code": "s2", "name": "S", "useCase": "nope"},
    )
    assert v["ok"] is False and v["failures"][0]["id"] == "use_case_exists"
    ok = r.body(
        "validate_action",
        action="catalog.AddSolution",
        inputs={"code": "s2", "name": "S", "useCase": "uc-alerts"},
    )
    assert ok["ok"] and [e["_type"] if "_type" in e else None for e in ok["effects"]] != []
    assert (
        r.body(
            "query",
            module="catalog",
            sql="SELECT s.code FROM catalog.Solution s WHERE s.code = 's2' ORDER BY s.code LIMIT 100",
        )["rows"]
        == []
    )


def test_errors_are_tool_results_with_codes_and_hints(r: Rig) -> None:
    res = r.call(
        "query",
        module="catalog",
        sql="SELECT u.nmae FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
    )
    assert res["isError"] is True
    body = res["structuredContent"]
    assert (
        body["code"] == "invalid" and "did you mean 'name'" in body["hint"] and body["violations"]
    )
    un = r.body(
        "query", module="catalog", sql="SELECT u.code FROM catalog.UseCase u ORDER BY u.name"
    )
    assert un["code"] == "unsupported" and un["supported"] and "supported:" in un["hint"]
    pre = r.body("catalog_add_solution", inputs={"code": "s2", "name": "S", "useCase": "nope"})
    assert (
        pre["code"] == "precondition_failed"
        and "validate_action" in pre["hint"]
        and pre["failures"][0]["id"] == "use_case_exists"
    )
    bad = r.body("catalog_add_solution", inputs={"code": "s2"})
    assert bad["code"] == "invalid" and {v["path"] for v in bad["violations"]} == {
        "inputs.name",
        "inputs.useCase",
    }
    r.box.store.available = False
    un = r.body(
        "query",
        module="catalog",
        sql="SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
    )
    assert (
        un["code"] == "unavailable" and un["backend"] == "memory" and un["reason"] == "unreachable"
    )
    r.box.store.available = True
    c = r.body("catalog_add_use_case", inputs={"code": "uc-pipeline", "name": "x"})
    assert c["code"] == "precondition_failed"  # absent(code) fails before any conflict
    token = r.body("catalog_add_use_case", inputs={"code": "uc-new", "name": "x"})["token"]
    nyc = r.body(
        "query",
        module="catalog",
        sql="SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
        consistency="bulk",
        at_least=token,
    )
    assert nyc["code"] == "not_yet_current" and nyc["backend"] == "memory_replica"
    bogus = r.body(
        "query",
        module="catalog",
        sql="SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
        consistency="bulk",
        at_least="not-a-position",
    )
    assert bogus["code"] == "invalid"  # a token nothing issued is not "not yet current"


def test_a_caller_cannot_name_another_person() -> None:
    r = Rig("carol")
    for tool, args in (
        (
            "query",
            {
                "module": "catalog",
                "sql": "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
                "user": "alice",
            },
        ),
        ("describe", {"as": "alice"}),
        ("catalog_add_use_case", {"inputs": {"code": "x", "name": "x"}, "principal": "alice"}),
    ):
        body = r.body(tool, **args)
        assert body["code"] == "invalid" and body["violations"][0]["code"] == "unknown_input"
    res = r.body("catalog_add_use_case", inputs={"code": "x", "name": "x"})
    assert res["code"] == "refused"  # carol can only read; her own token decides


def test_no_usable_token_refuses_everything_but_describe() -> None:
    r = Rig(None)
    d = r.body("describe")
    assert d["modules"] == [] and "no usable token" in d["note"] and "memory" in d["backends"]
    for tool, args in (
        (
            "query",
            {
                "module": "catalog",
                "sql": "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
            },
        ),
        ("validate_action", {"action": "catalog.AddUseCase", "inputs": {}}),
    ):
        res = r.call(tool, **args)
        assert res["isError"] and res["structuredContent"]["code"] == "refused"
    assert [t["name"] for t in r.rpc("tools/list")["result"]["tools"]] == [
        "describe",
        "query",
        "validate_action",
    ]
    for name in (
        "catalog_add_use_case",
        "no_such_tool",
    ):  # whatever its name: refused, not "no tool"
        res = r.call(name)
        assert res["isError"] and res["structuredContent"]["code"] == "refused"


def test_protocol_errors_are_protocol_errors(r: Rig) -> None:
    assert r.rpc("nope")["error"]["code"] == -32601
    assert r.rpc("tools/call", {"name": "gone", "arguments": {}})["error"]["code"] == -32602
    assert r.rpc("tools/call", {"name": 5})["error"]["code"] == -32602
    assert r.server.handle([{"jsonrpc": "2.0"}])["error"]["code"] == -32600
    assert r.server.handle({"id": 1})["error"]["code"] == -32600
    assert r.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert (
        r.server.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": [1]})[
            "error"
        ]["code"]
        == -32602
    )
    assert (
        r.server.handle({"jsonrpc": "2.0", "id": 3, "result": {}}) is None
    )  # a response is ignored


def test_the_server_says_when_the_tool_list_changes(r: Rig) -> None:
    r.rpc("tools/list")
    assert r.server.drain() == []
    doc = json.loads(__import__("arras.sandbox", fromlist=["x"]).catalog_document())
    doc["modules"][0]["actions"].append(
        {
            "id": "Ping",
            "description": "p",
            "inputs": [],
            "effects": [
                {
                    "op": "create",
                    "type": "UseCase",
                    "key": {"generate": "uuid"},
                    "properties": {"name": {"literal": "p"}},
                }
            ],
        }
    )
    r.box.arras.session(r.box.people["root"]).registry().register(json.dumps(doc))
    r.advance(10)
    r.body(
        "query",
        module="catalog",
        sql="SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
    )
    notes = r.server.drain()
    assert notes == [{"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}]
    names = [t["name"] for t in r.rpc("tools/list")["result"]["tools"]]
    assert "catalog_ping" in names and r.server.drain() == []


def test_wire_values_become_the_values_the_interface_takes() -> None:
    from arras.sandbox import catalog_document
    from arras.umf import parse_module

    mod = parse_module(catalog_document())
    out: list[Violation] = []
    assert to_python("integer", "scalar", "12", "p", out, mod) == 12
    assert to_python("decimal", "scalar", "1.50", "p", out, mod) == Decimal("1.50")
    assert to_python(
        "timestamp", "scalar", "2026-01-02T03:04:05Z", "p", out, mod
    ) == datetime.fromisoformat("2026-01-02T03:04:05+00:00")
    assert to_python("binary", "scalar", base64.b64encode(b"hi").decode(), "p", out, mod) == b"hi"
    assert not out
    for typ, val in (
        ("integer", "x"),
        ("integer", 2**60),
        ("decimal", "NaN"),
        ("decimal", "abc"),
        ("timestamp", "2026-01-02T03:04:05"),
        ("timestamp", "yesterday"),
        ("binary", "!!"),
    ):
        bad: list[Violation] = []
        to_python(typ, "scalar", val, "p", bad, mod)
        assert bad, (typ, val)
    action = mod.actions[0]
    values, faults = convert_inputs(action, mod, {"code": "a", "name": "n", "extra": 1})
    assert values["extra"] == 1 and not faults


# -- identity
def jwt(claims: dict) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")  # noqa: E731
    return f"{enc({'alg': 'none'})}.{enc(claims)}.sig"


def test_the_principal_is_read_from_the_token_claims() -> None:
    p = principal_from_token(jwt({"preferred_username": "jsmith", "groups": ["catalog-editors"]}))
    assert (p.user, p.groups) == ("jsmith", ("catalog-editors",)) and p.token.count(".") == 2
    assert principal_from_token(jwt({"email": "a@b.c"})).user == "a@b.c"
    assert principal_from_token(jwt({"sub": "42"})).user == "42"
    assert principal_from_token(jwt({"other": 1})) is None
    assert principal_from_token("not-a-jwt") is None and principal_from_token("a.b.c") is None
    assert principal_from_token(jwt({"mail": "m"}), ("mail",)).user == "m"


def test_the_token_file_is_reread_when_it_changes_or_nears_expiry(tmp_path) -> None:
    f = tmp_path / "token"
    now = [1_000_000.0]
    src = TokenSource(token_file=str(f), clock=lambda: now[0])
    assert src.current() is None  # no file yet: refused, not a crash
    f.write_text(jwt({"sub": "a", "exp": now[0] + 600}))
    assert src.current() and src.current().user == "a"
    f.write_text(jwt({"sub": "bb", "exp": now[0] + 600}))
    assert src.current().user == "bb"  # refreshed by the host, without a restart
    now[0] += 560  # within a minute of expiry: re-read, still the same file, now expired claims
    f.write_text(jwt({"sub": "bb", "exp": now[0] - 1}))
    assert src.current() is None  # an expired token is never presented to a backend
    f.write_text(jwt({"sub": "cc", "exp": now[0] + 3600}))
    assert src.current().user == "cc"
    f.unlink()
    assert src.current() is None


def test_identity_from_the_environment() -> None:
    t = jwt({"sub": "x", "preferred_username": "px"})
    assert TokenSource.from_env({"ARRAS_TOKEN": t}).current().user == "px"
    assert TokenSource.from_env({"ARRAS_TOKEN": t, "ARRAS_USER_CLAIM": "sub"}).current().user == "x"
    assert TokenSource.from_env({}).current() is None
    assert TokenSource.from_env({"ARRAS_TOKEN": "junk"}).current() is None


# -- stdio
def test_serve_frames_one_message_per_line(r: Rig) -> None:
    inp = io.StringIO(
        "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                "{not json",
                "",
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            ]
        )
        + "\n"
    )
    out = io.StringIO()
    serve(inp, out, r.server)
    lines = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [m.get("id") for m in lines] == [1, None, 2]
    assert lines[1]["error"]["code"] == -32700 and "tools" in lines[2]["result"]


def run_main(env: dict, lines: list[dict]) -> tuple[list[dict], str]:
    proc = subprocess.run(
        [sys.executable, "-m", "arras.mcp"],
        input="\n".join(json.dumps(m) for m in lines) + "\n",
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        timeout=60,
    )
    return [json.loads(line) for line in proc.stdout.splitlines()], proc.stderr


def test_the_process_writes_only_frames_to_stdout_and_no_secrets_to_stderr() -> None:
    token = jwt({"sub": "tok-user"})
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "describe", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "query",
                "arguments": {
                    "module": "catalog",
                    "sql": "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
                },
            },
        },
    ]
    out, err = run_main({"ARRAS_TOKEN": token}, msgs)
    assert [m["id"] for m in out] == [1, 2, 3] and all(m["jsonrpc"] == "2.0" for m in out)
    # degraded start: no backends are configured yet, and the token is a person but no backend knows them
    assert token not in err and "tok-user" not in err
    assert out[2]["result"]["isError"] is True
    assert out[2]["result"]["structuredContent"]["code"] == "unavailable"


def test_the_sandbox_mode_serves_a_real_session_end_to_end() -> None:
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "query",
                "arguments": {
                    "module": "catalog",
                    "sql": "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
                },
            },
        },
    ]
    out, err = run_main({"ARRAS_DEV_SANDBOX": "1", "ARRAS_DEV_USER": "carol"}, msgs)
    assert [r["code"] for r in out[1]["result"]["structuredContent"]["rows"]] == [
        "uc-alerts",
        "uc-pipeline",
    ]
    assert "traceback" not in err.lower()
    _ = time


# -- the review's cases
def test_a_committed_write_is_never_reported_as_a_failure_by_the_change_check(r: Rig) -> None:
    r.rpc("tools/list")
    r.advance(10)

    def boom() -> dict:
        raise RuntimeError("probe broke")

    r.box.arras.status = boom  # the change check will fail after the write has committed
    rec = r.body("catalog_add_use_case", inputs={"code": "w1", "name": "W"})
    assert rec["created"] == 1  # the receipt, not a protocol error
    assert r.rpc("ping")["result"] == {}


def test_an_unexpected_backend_failure_is_a_tool_result_without_its_text(
    r: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    real = r.box.store.query

    def leaky(*a: Any, **k: Any) -> Any:
        raise RuntimeError("Key (code)=(secret-record) already exists")

    r.box.store.query = leaky
    with caplog.at_level("DEBUG"):
        res = r.call(
            "query",
            module="catalog",
            sql="SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
        )
    assert res["isError"] and res["structuredContent"]["code"] == "unavailable"
    assert "secret-record" not in caplog.text and "secret-record" not in json.dumps(res)
    assert "RuntimeError" in caplog.text
    r.box.store.query = real


def test_a_refused_or_down_backend_is_refused_or_unavailable_not_no_such_tool(r: Rig) -> None:
    r.rpc("tools/list")
    r.box.access.expire(r.box.people["alice"].token)
    for tool, args in (
        ("catalog_add_use_case", {"inputs": {"code": "x", "name": "x"}}),
        ("describe", {}),
    ):
        res = r.call(tool, **args)
        assert res["isError"] and res["structuredContent"]["code"] == "refused", tool
    r.box.access.tokens[r.box.people["alice"].token] = "alice"
    r.box.store.available = False
    r.box.replica.available = False
    res = r.call("catalog_add_use_case", inputs={"code": "x", "name": "x"})
    assert res["structuredContent"]["code"] == "unavailable"
    assert r.call("describe")["structuredContent"]["code"] == "unavailable"
    r.box.replica.available = True
    res = r.call(
        "query",
        module="catalog",
        sql="SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
    )  # latest: never from the replica
    assert (
        res["structuredContent"]["code"] == "unavailable"
        and res["structuredContent"]["backend"] == "memory"
    )


def test_a_name_means_the_action_it_was_listed_for(r: Rig) -> None:
    listed = {t["name"] for t in r.rpc("tools/list")["result"]["tools"]}
    doc = json.loads(__import__("arras.sandbox", fromlist=["x"]).catalog_document())
    doc["modules"][0]["actions"].insert(
        0,
        {
            "id": "Newer",
            "description": "n",
            "inputs": [],
            "effects": [
                {
                    "op": "create",
                    "type": "UseCase",
                    "key": {"generate": "uuid"},
                    "properties": {"name": {"literal": "n"}},
                }
            ],
        },
    )
    r.box.arras.session(r.box.people["root"]).registry().register(json.dumps(doc))
    assert (
        r.rpc("tools/call", {"name": "catalog_newer", "arguments": {"inputs": {}}})["error"]["code"]
        == -32602
    )
    assert (
        r.body("catalog_add_use_case", inputs={"code": "k1", "name": "K"})["created"] == 1
    )  # still itself
    assert "catalog_newer" in {t["name"] for t in r.rpc("tools/list")["result"]["tools"]} - listed


def test_destructive_covers_foreach_deletes_and_handlers() -> None:
    from arras.sandbox import catalog_document
    from arras.umf import parse_module

    d = json.loads(catalog_document())
    d["modules"][0]["actions"] += [
        {
            "id": "Sweep",
            "inputs": [
                {"name": "xs", "type": {"kind": "ref", "type": "UseCase"}, "cardinality": "many"}
            ],
            "effects": [
                {
                    "op": "foreach",
                    "over": "xs",
                    "body": [{"op": "delete", "refType": "UseCase", "key": {"item": True}}],
                }
            ],
        },
        {"id": "Custom", "inputs": [], "handler": "custom"},
    ]
    mod = parse_module(json.dumps(d))
    by = {t.action.name: t.destructive for t in action_tools([mod])}
    assert by["catalog.Sweep"] and by["catalog.Custom"] and by["catalog.RetireUseCase"]
    assert not by["catalog.AddUseCase"] and not by["catalog.CorrectSolution"]


def test_cross_module_collisions_get_suffixes_and_describe_maps_them(r: Rig) -> None:
    from dataclasses import replace

    [m] = r.box.arras.session(r.box.people["alice"]).describe()
    # module `catalog_add` with an action `UseCase` would also be `catalog_add_use_case`
    twin_action = replace(m.actions[0], name="catalog_add.UseCase")
    twin = replace(m, name="catalog_add", actions=(twin_action,))
    tools = action_tools([m, twin])
    names = [t.tool for t in tools]
    assert len(set(names)) == len(names) and "catalog_add_use_case" in names
    assert any(n.startswith("catalog_add_use_case_") for n in names)  # the later one is suffixed
    listed = {t["name"] for t in r.rpc("tools/list")["result"]["tools"]}
    mapping = {a["name"]: a["tool"] for a in r.body("describe")["modules"][0]["actions"]}
    assert (
        set(mapping.values()) <= listed and mapping["catalog.AddUseCase"] == "catalog_add_use_case"
    )


def test_argument_types_are_checked(r: Rig) -> None:
    sql = "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
    for args in (
        {"limit": True},
        {"limit": "5"},
        {"at_least": 5},
        {"params": [1]},
        {"consistency": []},
    ):
        res = r.call("query", module="catalog", sql=sql, **args)
        assert res["isError"] and res["structuredContent"]["code"] == "invalid", args
    res = r.call("query", module=5, sql=sql)
    assert res["isError"] and res["structuredContent"]["code"] == "invalid"
    res = r.call("query", sql=sql)  # the module is named
    assert res["isError"] and res["structuredContent"]["code"] == "invalid"
    ok = {"code": "t1", "name": "T"}
    for bad in ({"atomic": "false"}, {"stop_on_error": 1}, {"idempotency_key": 5}):
        res = r.call("catalog_add_use_case", items=[ok], **bad)
        assert res["structuredContent"]["code"] == "invalid", bad
    assert (
        r.call("catalog_add_use_case", inputs=ok, items=[ok])["structuredContent"]["code"]
        == "invalid"
    )
    assert r.call("catalog_add_use_case")["structuredContent"]["code"] == "invalid"
    many = r.call(
        "catalog_add_use_case", items=[{"code": f"m{i}", "name": "M"} for i in range(101)]
    )
    assert many["structuredContent"]["code"] == "invalid"
    stopped = r.body(
        "catalog_add_use_case",
        items=[{"code": "uc-pipeline", "name": "x"}, {"code": "s1", "name": "S"}],
        stop_on_error=True,
    )
    assert len(stopped["items"]) == 1


def test_violation_paths_agree_for_batches_and_are_not_duplicated(r: Rig) -> None:
    res = r.body("catalog_add_use_case", items=[{"code": "b1"}])
    assert [v["path"] for v in res["violations"]] == ["items[0].inputs.name"]
    v = r.body(
        "validate_action",
        action="catalog.AddSolution",
        inputs={"code": 5, "name": "n", "useCase": "x"},
    )
    keys = [(x["path"], x["code"]) for x in v["violations"]]
    assert len(keys) == len(set(keys))


def test_one_row_over_the_budget_is_returned_whole(r: Rig) -> None:
    huge = "y" * (60 * 1024)
    r.box.store.import_records(
        r.box.people["root"],
        "catalog",
        [{"type": "UseCase", "key": "zzz", "properties": {"name": huge}}],
        load_id="L",
        initiated_by="root",
    )
    calls: list[int] = []
    real = r.box.store.query

    def spy(*a: Any, **k: Any) -> Any:
        calls.append(k["limit"])
        return real(*a, **k)

    r.box.store.query = spy
    a = r.body(
        "query",
        module="catalog",
        sql="SELECT u.code, u.name FROM catalog.UseCase u WHERE u.code = 'zzz' ORDER BY u.code LIMIT 100",
    )
    assert a["rows"][0]["name"] == huge and a["truncated"] is False
    assert len(calls) == 1  # nothing to cut: no re-query
    page = r.body(
        "query",
        module="catalog",
        sql="SELECT u.code, u.name FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
        limit=100,
    )
    assert page["truncated"] is (len(page["rows"]) < 3)  # three use cases: cut to fit says so
    assert len(calls) <= 6  # a bounded number of re-queries


def test_wide_integers_and_binary_go_out_as_they_come_in() -> None:
    from arras.mcp.server import _wide
    from arras.serialize import jsonable

    assert _wide({"a": 2**53, "b": 2**53 - 1, "c": [2**60], "d": True}) == {
        "a": str(2**53),
        "b": 2**53 - 1,
        "c": [str(2**60)],
        "d": True,
    }
    assert jsonable(b"hi") == base64.b64encode(b"hi").decode()


def test_record_fields_holding_lists_are_converted() -> None:
    from arras.sandbox import catalog_document
    from arras.umf import parse_module

    mod = parse_module(catalog_document())
    from dataclasses import replace

    from arras.model import PropertyInfo, ValueTypeInfo

    vt = ValueTypeInfo(
        "catalog.Span",
        (
            PropertyInfo("at", "timestamp", True, "many"),
            PropertyInfo("amt", "decimal", True, "many"),
        ),
    )
    mod = replace(mod, value_types=(vt,))
    bad: list[Violation] = []
    out = to_python(
        "Span", "record", {"at": ["2026-01-02T03:04:05Z"], "amt": ["1.5", "2"]}, "p", bad, mod
    )
    assert (
        not bad and out["amt"] == [Decimal("1.5"), Decimal(2)] and out["at"][0].tzinfo is not None
    )
    to_python("Span", "record", {"at": ["yesterday"], "amt": []}, "p", bad, mod)
    assert bad and bad[0].path == "p.at[0]"


def test_hints_for_conflicts_are_specific(r: Rig) -> None:
    r.body("catalog_add_use_case", inputs={"code": "h1", "name": "H"}, idempotency_key="K")
    res = r.body("catalog_add_use_case", inputs={"code": "h2", "name": "H"}, idempotency_key="K")
    assert res["code"] == "conflict" and res["reason"] == "idempotency_key_reused"
    assert "new idempotency_key" in res["hint"]
    assert "H" not in res.get("detail", "")


def test_jsonrpc_edges(r: Rig) -> None:
    h = r.server.handle
    for bad_id in (True, 1.5, [1], {"a": 1}, None):
        resp = h({"jsonrpc": "2.0", "id": bad_id, "method": "ping"})
        assert resp["error"]["code"] == -32600, bad_id
    assert h({"jsonrpc": "2.0", "id": 0, "method": "ping"})["result"] == {}
    assert h({"jsonrpc": "2.0", "id": "a", "method": 5})["error"]["code"] == -32600
    assert h({"jsonrpc": "2.0", "method": "ping"}) is None  # a notification
    out = io.StringIO()
    inp = io.StringIO(
        '{"jsonrpc":"2.0","id":NaN,"method":"ping"}\n'
        + "[" * 100000
        + "\n"
        + '{"jsonrpc":"2.0","id":1e999,"method":"ping"}\n'
        + '[{"jsonrpc":"2.0","id":1,"method":"ping"}]\n'
        + '{"jsonrpc":"2.0","id":7,"method":"ping"}\n'
    )
    serve(inp, out, r.server)
    msgs = [json.loads(line) for line in out.getvalue().splitlines()]
    # NaN and a nesting too deep are not JSON; 1e999 reads as an infinite id, and a batch is not accepted
    assert [m["error"]["code"] for m in msgs[:4]] == [-32700, -32700, -32600, -32600]
    assert msgs[4]["result"] == {}  # the loop lived on


def test_a_static_token_expires_after_it_was_loaded() -> None:
    now = [100.0]
    src = TokenSource(token=jwt({"sub": "a", "exp": 160}), clock=lambda: now[0])
    assert src.current() is not None
    now[0] = 161.0
    assert src.current() is None
    assert TokenSource(token=jwt({"sub": "a", "exp": float("nan")})).current() is None
    assert TokenSource(token=jwt({"sub": "a", "exp": "soon"})).current() is None


def test_list_changed_on_status_change_once_and_not_before_a_relist(r: Rig) -> None:
    r.rpc("tools/list")
    r.advance(10)
    r.box.store.available = False
    r.rpc("ping")
    assert len(r.server.drain()) == 1
    r.advance(10)
    r.rpc("ping")
    assert r.server.drain() == []  # not again before the host lists
    r.box.store.available = True
    r.rpc("tools/list")
    r.advance(10)
    r.rpc("ping")
    assert r.server.drain() == []
    r.rpc("ping")  # within the interval: no check at all
    assert r.server.drain() == []


def test_distribution_prefixes_tools_but_keeps_action_identity_canonical() -> None:
    from arras.distribution import DistributionConfig

    box = Sandbox().seed()
    config = DistributionConfig(mcp_server_name="Acme", mcp_tool_prefix="acme")
    server = McpServer(box.arras, lambda: box.principal("alice"), distribution=config)
    initialized = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert initialized["result"]["serverInfo"]["name"] == "Acme"
    tools = {
        t["name"]: t
        for t in server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"][
            "tools"
        ]
    }
    assert "acme_describe" in tools and "acme_catalog_add_use_case" in tools
    assert "describe" not in tools and "catalog_add_use_case" not in tools
    described = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "acme_describe", "arguments": {}},
        }
    )["result"]["structuredContent"]
    action = next(
        a for m in described["modules"] for a in m["actions"] if a["name"] == "catalog.AddUseCase"
    )
    assert action["tool"] == "acme_catalog_add_use_case"
    bare = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "describe", "arguments": {}},
        }
    )
    assert bare["error"]["code"] == -32602


def test_distribution_name_validation_and_tool_prefix_bounds() -> None:
    from arras.distribution import DistributionConfig

    for kw in (
        {"mcp_server_name": " padded "},
        {"mcp_server_name": "x\n"},
        {"mcp_tool_prefix": "Acme"},
        {"mcp_tool_prefix": "a" * 17},
        {"mcp_tool_prefix": None},
        {"mcp_tool_prefix": 0},
        {"env_prefix": "bad"},
        {"env_prefix": "A" * 33},
    ):
        with pytest.raises(ValueError):
            DistributionConfig(**cast(Any, kw))


def test_initial_inventory_rejects_prefixed_collisions_before_initialize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    import arras.mcp.server as server_module
    from arras.distribution import DistributionConfig

    box = Sandbox().seed()
    original = server_module.action_tools
    monkeypatch.setattr(
        server_module,
        "action_tools",
        lambda mods: [replace(original(mods)[0], tool="describe")],
    )
    server = McpServer(
        box.arras,
        lambda: box.principal("alice"),
        distribution=DistributionConfig(mcp_tool_prefix="tenant"),
    )
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert response["error"]["code"] == -32603


def test_initial_inventory_rejects_prefixed_overlong_action_before_initialize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    import arras.mcp.server as server_module
    from arras.distribution import DistributionConfig

    box = Sandbox().seed()
    original = server_module.action_tools
    monkeypatch.setattr(
        server_module,
        "action_tools",
        lambda mods: [replace(original(mods)[0], tool="x" * 128)],
    )
    server = McpServer(
        box.arras,
        lambda: box.principal("alice"),
        distribution=DistributionConfig(mcp_tool_prefix="tenant"),
    )
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert response["error"]["code"] == -32603


def test_ping_detected_registry_change_requires_explicit_relist_for_cached_alias(r: Rig) -> None:
    from arras.sandbox import catalog_document

    r.rpc("tools/list")
    doc = json.loads(catalog_document())
    doc["modules"][0]["actions"].append(
        {
            "id": "Ping",
            "description": "p",
            "inputs": [],
            "effects": [
                {
                    "op": "create",
                    "type": "UseCase",
                    "key": {"generate": "uuid"},
                    "properties": {"name": {"literal": "p"}},
                }
            ],
        }
    )
    r.box.arras.session(r.box.people["root"]).registry().register(json.dumps(doc))
    r.advance(10)
    r.rpc("ping")
    r.server.drain()
    for _ in range(2):
        result = r.call("catalog_ping", inputs={})
        assert result["error"]["code"] == -32602
    described = r.body("describe")
    ping = next(
        a
        for module in described["modules"]
        for a in module["actions"]
        if a["name"] == "catalog.Ping"
    )
    assert ping["tool"] == "catalog_ping"
    assert "catalog_ping" in [t["name"] for t in r.rpc("tools/list")["result"]["tools"]]


def test_retargeted_collision_alias_stays_refused_until_explicit_relist(r: Rig) -> None:
    from copy import deepcopy

    from arras.sandbox import catalog_document

    r.rpc("tools/list")
    doc = json.loads(catalog_document())
    original = next(
        action for action in doc["modules"][0]["actions"] if action["id"] == "AddUseCase"
    )
    alias = deepcopy(original)
    alias["id"] = "add_use_case"
    doc["modules"][0]["actions"].insert(0, alias)
    r.box.arras.session(r.box.people["root"]).registry().register(json.dumps(doc))
    for code in ("collision-1", "collision-2"):
        result = r.call("catalog_add_use_case", inputs={"code": code, "name": code})
        assert result["error"]["code"] == -32602
    before_relist = {
        action["name"]: action["tool"]
        for module in r.body("describe")["modules"]
        for action in module["actions"]
    }
    assert before_relist["catalog.AddUseCase"] == "catalog_add_use_case_2"
    tools = {tool["name"] for tool in r.rpc("tools/list")["result"]["tools"]}
    assert "catalog_add_use_case" in tools and "catalog_add_use_case_2" in tools
    mapping = {
        action["name"]: action["tool"]
        for module in r.body("describe")["modules"]
        for action in module["actions"]
    }
    assert mapping["catalog.AddUseCase"] == "catalog_add_use_case_2"
