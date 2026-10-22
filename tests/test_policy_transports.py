# SPDX-License-Identifier: MIT OR Apache-2.0
"""Real interface bindings preserve safe policy denial metadata."""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast

from arras import Arras, Placement
from arras.backend import Backend
from arras.errors import PolicyRefused
from arras.mcp import McpServer
from arras.operate import create_app
from arras.policy import PolicyBackend, PolicyDecision, PolicyRequest
from arras.sandbox import Sandbox


def _denied(request: PolicyRequest) -> PolicyDecision:
    assert request.operation == "apply"
    return PolicyDecision(False, code="host_denied")


def _wrapped_sandbox() -> Sandbox:
    box = Sandbox().seed()
    backends = {
        name: PolicyBackend(cast(Backend, backend), _denied)
        for name, backend in box.backends.items()
    }
    box.arras = Arras.start(
        backends,
        admin=box.people["root"],
        default_placement=Placement("memory", ("memory_replica",)),
    )
    return box


def test_mcp_actual_action_refusal_carries_only_safe_policy_code() -> None:
    box = _wrapped_sandbox()
    before = box.store.status().position
    server = McpServer(box.arras, lambda: box.principal("alice"))
    response = cast(
        dict[str, Any],
        server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "catalog_add_use_case",
                    "arguments": {"inputs": {"code": "denied", "name": "Denied"}},
                },
            }
        ),
    )
    payload = cast(dict[str, Any], response["result"]["structuredContent"])
    assert payload["code"] == "refused"
    assert payload["policy_code"] == "host_denied"
    assert "secret-token" not in json.dumps(payload)
    assert box.store.status().position == before


async def _asgi_post(app: Any, path: str, body: dict[str, object]) -> tuple[int, dict[str, Any]]:
    raw = json.dumps(body).encode()
    events = [
        {"type": "http.request", "body": raw, "more_body": False},
        {"type": "http.disconnect"},
    ]
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return events.pop(0)

    async def send(event: dict[str, Any]) -> None:
        sent.append(event)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/json"),
                (b"origin", b"https://ops.example"),
                (b"x-user", b"alice"),
            ],
            "client": ("127.0.0.1", 1000),
            "server": ("ops.example", 443),
        },
        receive,
        send,
    )
    start = next(event for event in sent if event["type"] == "http.response.start")
    chunk = next(event for event in sent if event["type"] == "http.response.body")
    return start["status"], json.loads(chunk["body"])


def test_http_actual_action_refusal_keeps_refused_wire_type() -> None:
    box = _wrapped_sandbox()
    before = box.store.status().position
    app = create_app(
        box.arras,
        principal_for_request=lambda request: box.principal(request.headers.get("x-user")),
        public_origin="https://ops.example",
    )
    status, payload = asyncio.run(
        _asgi_post(
            app,
            "/actions/catalog/AddUseCase/invoke",
            {"inputs": {"code": "denied", "name": "Denied"}},
        )
    )
    assert status == 403
    assert payload["error"]["type"] == "Refused"
    assert payload["error"]["reason"] == "no_access"
    assert payload["error"]["policy_code"] == "host_denied"
    assert "secret-token" not in json.dumps(payload)
    assert box.store.status().position == before


def test_direct_wrapped_action_preserves_policy_refusal_type() -> None:
    box = _wrapped_sandbox()
    before = box.store.status().position
    try:
        box.arras.session(box.principal("alice")).invoke(
            "catalog.AddUseCase", {"code": "denied", "name": "Denied"}
        )
    except PolicyRefused as error:
        assert error.policy_code == "host_denied"
        assert error.reason == "no_access"
    else:
        raise AssertionError("policy denial did not stop direct action invocation")
    assert box.store.status().position == before
