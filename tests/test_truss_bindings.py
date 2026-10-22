# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic, reportOptionalSubscript=false, reportOptionalMemberAccess=false, reportReturnType=false, reportOperatorIssue=false
"""The bindings on Truss (TR-14): the MCP process, the console, the operator surface and the dev host
over a real Truss on a local PostgreSQL, serving the registered `catalog` module.

All Truss-marked (`uv run --extra truss --group truss-test pytest -m truss`): one `TrussBox` per
module, the dev host's own world, so these tests also prove what `python -m arras.devhost --truss`
serves. Without PostgreSQL 18.6 they skip with the reason, and fail under ARRAS_REQUIRE_TRUSS=1.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from arras.core import Arras
from arras.devhost import DevHost
from arras.devtruss import TrussBox
from arras.mcp import McpServer, principal_from_token
from arras.mcp.backends import build_backends
from arras.mcp.config import Config
from arras.testing import example_module
from test_console import Client as ConsoleClient
from test_devhost_roles import call as dev_call
from test_operate import Client as OperateClient
from test_truss_harness import _require

pytestmark = pytest.mark.truss

QUERY = "SELECT u.code, u.name FROM catalog.UseCase u WHERE u.code = :k ORDER BY u.code LIMIT 10"


def _jwt(user: str) -> str:
    """A token of the shape the MCP process reads: its claims name the person, and it is also the
    person's password in the database."""
    body = base64.urlsafe_b64encode(json.dumps({"preferred_username": user}).encode()).rstrip(b"=")
    return f"h.{body.decode()}.s"


def notes_document() -> str:
    """A second module, whose one type has no relationships."""
    doc = json.loads(example_module())
    doc["id"] = "notes-doc"
    mod = doc["modules"][0]
    mod["id"] = mod["namespace"] = "notes"
    mod["elements"] = [e for e in mod["elements"] if not e["id"].startswith("Solution")]
    mod["relationships"] = []
    mod["actions"] = [a for a in mod["actions"] if a["id"] == "AddUseCase"]
    return json.dumps(doc).replace('"module": "catalog"', '"module": "notes"')


@pytest.fixture(scope="module")
def box() -> Iterator[TrussBox]:
    _require()
    b = TrussBox().seed()
    b.load(notes_document(), [("notes.AddUseCase", {"code": "n-1", "name": "First note"})])
    for user in ("alice", "carol", "dave"):  # the token is the password
        b.use_token(user, _jwt(user))
    try:
        yield b
    finally:
        b.close()


def handle(box: TrussBox, host: str | None = None) -> str:
    return f"postgresql:///{box.truss.endpoint.dbname}?host={quote(host or box.truss.endpoint.host, safe='/')}"


@pytest.fixture(scope="module")
def config_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Where a module lives is the dev's committed file, never the handle (CONTRACT-002)."""
    d = tmp_path_factory.mktemp("config")
    (d / "default.toml").write_text('[placement]\nrecord = "primary"\n')
    return d


def mcp_over(
    box: TrussBox, config_dir: Path, user: str, host: str | None = None
) -> tuple[McpServer, Arras]:
    config = Config.from_env(
        {
            "ARRAS_BACKEND_PRIMARY_ENDPOINT": handle(box, host),
            "ARRAS_CONFIG_DIR": str(config_dir),
        }
    )
    backends, unbuilt = build_backends(config)
    assert unbuilt == {}
    h = Arras.start(
        backends,
        expected=tuple(config.endpoints),
        placement=config.placements,
        default_placement=config.default_placement,
    )
    return McpServer(h, lambda: principal_from_token(_jwt(user))), h


class Rpc:
    def __init__(self, server: McpServer) -> None:
        self.server, self.n = server, 0

    def call(self, name: str, **args: Any) -> dict[str, Any]:
        self.n += 1
        msg = {
            "jsonrpc": "2.0",
            "id": self.n,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        }
        reply = self.server.handle(msg)
        return reply["result"] if "result" in reply else reply


# -- the MCP binding


def test_the_mcp_server_reads_and_writes_through_truss_as_the_person(
    box: TrussBox, config_dir: Path
) -> None:
    server, _ = mcp_over(box, config_dir, "alice")
    rpc = Rpc(server)
    listed = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    # tools come from the registered module, read from Truss as the person
    described = rpc.call("describe")["structuredContent"]
    assert {m["name"] for m in described["modules"]} == {"catalog", "notes"}
    names = {t["name"] for t in listed["result"]["tools"]}
    assert {"query", "describe", "catalog_add_use_case"} <= names
    # no installing connection here: the status is what the calls above showed of the database
    # (the catalog read that listed the tools reached it), never a probe (CONTRACT-007)
    primary = described["backends"]["primary"]
    assert primary["available"] is True and primary["reason"] is None

    rows = rpc.call("query", module="catalog", sql=QUERY, params={"k": "uc-pipeline"})
    assert rows["structuredContent"]["rows"] == [
        {"code": "uc-pipeline", "name": "Pipeline mapping"}
    ]
    assert rows["structuredContent"]["freshness"]["backend"] == "primary"

    code = f"uc-{uuid.uuid4().hex[:8]}"
    first = rpc.call(
        "catalog_add_use_case", inputs={"code": code, "name": "N"}, idempotency_key=code
    )
    again = rpc.call(
        "catalog_add_use_case", inputs={"code": code, "name": "N"}, idempotency_key=code
    )
    assert first["structuredContent"]["created"] == 1
    assert again["structuredContent"]["replayed"] is True
    after = rpc.call("query", module="catalog", sql=QUERY, params={"k": code})
    assert after["structuredContent"]["rows"] == [{"code": code, "name": "N"}]


def test_the_database_refuses_what_the_persons_roles_do_not_allow(
    box: TrussBox, config_dir: Path
) -> None:
    reader, _ = mcp_over(box, config_dir, "carol")
    res = Rpc(reader).call("catalog_add_use_case", inputs={"code": "uc-no", "name": "No"})
    assert res["isError"] and res["structuredContent"]["code"] in ("refused", "unauthorized")
    nobody, _ = mcp_over(box, config_dir, "dave")
    res = Rpc(nobody).call("query", module="catalog", sql=QUERY, params={"k": "uc-pipeline"})
    assert res["isError"]


def test_an_unreachable_database_is_unavailable_not_a_crash(
    box: TrussBox, config_dir: Path
) -> None:
    server, h = mcp_over(box, config_dir, "alice", host=str(box.truss.root / "nowhere"))
    rpc = Rpc(server)
    res = rpc.call("query", module="catalog", sql=QUERY, params={"k": "uc-pipeline"})
    assert res["isError"]
    # with no installing connection the status is what the call showed: the database was not reached
    primary = h.status()["primary"]
    assert primary.available is False and primary.reason == "unreachable"


def test_the_process_ignores_ambient_libpq_variables(
    box: TrussBox, config_dir: Path, tmp_path: Path
) -> None:
    """PGSERVICE has no connection keyword that switches it off: the process clears every PG*
    variable, so a deploy environment that sets them cannot redirect the person's connection."""
    frames = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "query",
                "arguments": {"module": "catalog", "sql": QUERY, "params": {"k": "uc-pipeline"}},
            },
        },
    ]
    service = tmp_path / "pg_service.conf"
    service.write_text("[bogus]\nhost=intruder.invalid\n")
    done = subprocess.run(
        [sys.executable, "-m", "arras.mcp"],
        env={
            "ARRAS_BACKEND_PRIMARY_ENDPOINT": handle(box),
            "ARRAS_TOKEN": _jwt("carol"),
            "ARRAS_CONFIG_DIR": str(config_dir),
            "PGSERVICE": "bogus",
            "PGSERVICEFILE": str(service),
            "PGOPTIONS": "-c role=intruder",
            "PGHOST": "intruder.invalid",
            "PGPASSWORD": "not-the-token",
            "PGTARGETSESSIONATTRS": "read-only",
            "PATH": os.environ.get("PATH", ""),
        },
        input="".join(json.dumps(f) + "\n" for f in frames),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    reply = json.loads(done.stdout.splitlines()[2])
    assert reply["result"]["structuredContent"]["rows"] == [
        {"code": "uc-pipeline", "name": "Pipeline mapping"}
    ]
    assert _jwt("carol") not in done.stderr and "intruder" not in done.stderr


# -- the console and the operator surface


def test_the_console_serves_registered_modules_from_truss(box: TrussBox) -> None:
    c = ConsoleClient(box=box)
    status, r, _ = c.gql(
        "{ modules { name record replicas entityTypes { name } } status { backend available } }",
        "/graphql",
    )
    assert status == 200 and "errors" not in r, r
    assert {m["name"] for m in r["data"]["modules"]} == {"catalog", "notes"}
    assert {(m["record"], tuple(m["replicas"])) for m in r["data"]["modules"]} == {("primary", ())}
    assert r["data"]["status"] == [{"backend": "primary", "available": True}]
    status, e, _ = c.gql(
        "{ useCaseList(limit: 50) { items { key name } freshness { backend } } }",
        "/graphql/notes",
    )
    assert status == 200 and "errors" not in e, e
    page = e["data"]["useCaseList"]
    assert page["items"] == [{"key": "n-1", "name": "First note"}]
    assert page["freshness"]["backend"] == "primary"
    # a whole entity of a type with relationships: Truss appends the relationship columns to `x.*`,
    # so the statement names its own keys column differently (R17.2)
    status, whole, _ = c.gql("{ useCaseList(limit: 5) { items { key addressedBy { key } } } }")
    assert status == 200 and "errors" not in whole, whole
    assert "uc-pipeline" in [i["key"] for i in whole["data"]["useCaseList"]["items"]]
    _, nobody, _ = c.gql("{ modules { name } }", "/graphql", user="dave")
    assert nobody["data"]["modules"] == []


def test_the_operator_surface_applies_actions_on_truss_and_serves_its_audit(box: TrussBox) -> None:
    c = OperateClient(box=box)
    code = f"uc-{uuid.uuid4().hex[:8]}"
    inputs = {"code": code, "name": "Op", "workArea": "finance"}
    status, v, _ = c.post("/actions/catalog/AddUseCase/validate", {"inputs": inputs})
    assert status == 200 and v["ok"], v
    status, r, _ = c.post("/actions/catalog/AddUseCase/invoke", {"inputs": inputs})
    assert status == 200 and r["created"] == 1, r
    # Truss's audit pages answer for the person who holds the audit role (the `journal` grant): the
    # change just made is listed with its group, and the module's loads answer too (TR-11)
    status, page, _ = c.post("/audit/changes", {"module": "catalog", "limit": 5})
    assert status == 200, page
    assert page["items"][0]["action"] == "catalog.AddUseCase"
    assert page["items"][0]["group"] == r["group"]
    status, loads, _ = c.post("/audit/loads", {"module": "catalog", "limit": 5})
    assert status == 200 and loads["items"] == [], loads  # nothing was imported into this box


# -- the dev host


def test_the_dev_host_browses_a_registered_module_from_truss(box: TrussBox, tmp_path: Path) -> None:
    app = DevHost(box, port=8765, ui_dir=tmp_path)
    status, people = dev_call(app, "GET", "/api/people")
    assert status == 200 and "root" in people["people"]
    status, r = dev_call(
        app,
        "POST",
        "/api/console/graphql/notes",
        {"query": "{ useCaseList(limit: 50) { items { key name } } }"},
        user="carol",
    )
    assert status == 200 and "errors" not in r, r
    assert {u["key"] for u in r["data"]["useCaseList"]["items"]} == {"n-1"}
    # an unbuilt UI says so and the rest still serves
    status, page = dev_call(app, "GET", "/")
    assert status == 200 and b"not built" in page


def test_the_dev_hosts_controls_are_real_database_changes_or_a_plain_400(
    box: TrussBox, tmp_path: Path
) -> None:
    app = DevHost(box, port=8765, ui_dir=tmp_path)
    read = {"query": "{ useCaseList(limit: 50) { items { key } } }"}
    path = "/api/console/graphql/notes"
    ok = lambda body, **kw: dev_call(app, "POST", "/api/dev/control", body, **kw)[0]  # noqa: E731
    assert dev_call(app, "POST", path, read, user="carol")[0] == 200
    assert ok({"op": "expire", "user": "carol"}) == 200  # ALTER ROLE ... VALID UNTIL
    assert dev_call(app, "POST", path, read, user="carol")[0] == 401
    assert ok({"op": "restore", "user": "carol"}) == 200
    assert dev_call(app, "POST", path, read, user="carol")[0] == 200
    assert ok({"op": "revoke", "user": "carol", "module": "notes", "modes": ["read"]}) == 200
    assert dev_call(app, "POST", path, read, user="carol")[0] == 404  # the role is gone: no module
    assert ok({"op": "grant", "user": "carol", "module": "notes"}) == 200
    assert dev_call(app, "POST", path, read, user="carol")[0] == 200
    assert ok({"op": "outage", "backend": "primary", "reason": "unreachable"}) == 200
    assert dev_call(app, "POST", path, read, user="carol")[0] == 503
    assert ok({"op": "outage", "backend": "primary", "reason": None}) == 200
    assert dev_call(app, "POST", path, read, user="carol")[0] == 200
    # what Truss has no meaning for is refused, never a no-op and never a 500
    assert ok({"op": "feed"}) == 400
    assert (
        ok({"op": "search", "backend": "primary", "type": "catalog.UseCase", "mode": "none"}) == 400
    )
    assert ok({"op": "outage", "backend": "primary", "reason": "migration_failed"}) == 400
    # a made-up person is a login role holding what the role holds
    status, r = dev_call(app, "POST", path, read, user="pat", role="viewer")
    assert status == 200 and "errors" not in r
