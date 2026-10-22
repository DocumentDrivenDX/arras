# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""CONTRACT-010, section E: who is an operator. `authorize_operator`, `GET /viewer`, and the
refusal of a non-operator on every other operate endpoint, before any work."""

from __future__ import annotations

import logging
from typing import Any

import pytest

import arras
from arras.operate import create_app
from test_operate import ADD, INVOKE, VALIDATE, Client

REFUSED = {"error": "REFUSED", "reason": "not_operator"}


def not_carol(p: Any) -> bool:
    return p.user != "carol"


def endpoints() -> list[tuple[str, str, Any]]:
    return [
        ("GET", "/explorer/schema-catalog.json", None),
        ("POST", VALIDATE, {"inputs": ADD}),
        ("POST", INVOKE, {"inputs": ADD}),
        ("POST", "/actions/catalog/AddUseCase/batch", {"items": [ADD]}),
        ("POST", "/audit/changes", {"module": "catalog"}),
        ("POST", "/audit/loads", {"module": "catalog"}),
    ]


def test_the_browser_contract_has_a_version() -> None:
    assert arras.CONTRACT_VERSIONS["browser"] == 1


def test_viewer_names_the_modes_of_an_operator_and_of_a_reader() -> None:
    """@covers US-072-AC5: the modes endpoint answers `["user"]` for a viewer who is not an operator."""
    c = Client(authorize_operator=not_carol)
    assert c.call("GET", "/viewer", user="alice") == (
        200,
        {"user": "alice", "modes": ["user", "admin"]},
        c.call("GET", "/viewer", user="alice")[2],
    )
    status, body, headers = c.call("GET", "/viewer", user="carol", origin=None)
    assert (status, body) == (200, {"user": "carol", "modes": ["user"]})
    assert headers["cache-control"] == "no-store"


def test_viewer_needs_a_principal_and_is_a_get() -> None:
    c = Client(authorize_operator=not_carol)
    assert c.call("GET", "/viewer", user=None, origin=None)[0] == 401
    status, _, headers = c.call("POST", "/viewer", {}, user="alice")
    assert status == 405 and headers["allow"] == "GET"


@pytest.mark.parametrize("method,path,body", endpoints())
def test_a_non_operator_is_refused_on_every_other_endpoint(
    method: str, path: str, body: Any
) -> None:
    """@covers US-072-AC5: each endpoint answers 403 REFUSED not_operator."""
    c = Client(authorize_operator=not_carol)
    status, answer, _ = c.call(method, path, body, user="carol")
    assert (status, answer) == (403, REFUSED)
    assert c.call(method, path, body, user="alice")[0] == 200


def test_the_refusal_comes_before_any_work() -> None:
    """@covers US-072-AC5: a person who may write, and is not an operator, changes nothing, and
    the host's per-action approval is not even asked."""
    asked: list[str] = []
    c = Client(
        authorize_operator=lambda p: p.user != "bob",
        authorize_action=lambda p, m, a: asked.append(a) or True,
    )
    status, answer, _ = c.post(INVOKE, {"inputs": ADD}, user="bob")
    assert (status, answer) == (403, REFUSED) and asked == []
    assert (
        c.box.arras.session(c.box.people["alice"])
        .query(
            "catalog",
            "SELECT u.* FROM catalog.UseCase u WHERE u.code = 'uc-x' ORDER BY u.code LIMIT 1",
        )
        .rows
        == ()
    )


def test_the_version_and_the_openapi_document_answer_a_non_operator_too() -> None:
    c = Client(authorize_operator=lambda p: False)
    assert c.call("GET", "/version", user="carol", origin=None)[0] == 200
    assert c.call("GET", "/openapi.json", user=None, origin=None)[0] == 200


def test_no_principal_is_a_401_not_a_refusal_of_an_operator() -> None:
    c = Client(authorize_operator=lambda p: False)
    for method, path, body in endpoints():
        assert c.call(method, path, body, user=None)[0] == 401


def test_the_default_is_that_every_accepted_principal_is_an_operator() -> None:
    """@covers US-072-AC7: behaviour before this feature."""
    c = Client()
    for user in ("alice", "carol"):
        _, body, _ = c.call("GET", "/viewer", user=user)
        assert body["modes"] == ["user", "admin"]
    assert c.call("GET", "/explorer/schema-catalog.json", user="carol")[0] == 200


def test_an_operator_hook_that_fails_refuses() -> None:
    def broken(p: Any) -> bool:
        raise RuntimeError("directory down")

    c = Client(authorize_operator=broken)
    assert c.call("GET", "/viewer", user="alice")[1]["modes"] == ["user"]
    assert c.post(VALIDATE, {"inputs": ADD}, user="alice")[:2] == (403, REFUSED)


def test_the_host_log_says_once_at_start_that_everyone_is_an_operator(caplog) -> None:
    """@covers US-072-AC7"""
    with caplog.at_level(logging.INFO, logger="arras.operate"):
        c = Client()
        for _ in range(3):
            c.call("GET", "/viewer")
        Client(authorize_operator=not_carol)
    said = [r for r in caplog.records if "authorize_operator" in r.getMessage()]
    assert len(said) == 1 and "every principal is an operator" in said[0].getMessage()


def test_create_app_takes_the_hook_as_a_keyword() -> None:
    c = Client()
    app = create_app(c.box.arras, principal_for_request=c.who, authorize_operator=not_carol)
    assert app.authorize_operator is not_carol


def test_the_operator_hook_runs_within_the_in_flight_caps() -> None:
    """@covers US-072-AC5: a viewer who is not an operator cannot make the hook run without limit."""
    import asyncio
    import threading

    from test_operate import _asgi, _until

    gate, lock, calls = threading.Event(), threading.Lock(), [0]

    def slow_no(_: Any) -> bool:
        with lock:
            calls[0] += 1
        gate.wait(10)
        return False

    c = Client(authorize_operator=slow_no)

    async def run() -> tuple[list[int], int, dict[str, int]]:
        held = [asyncio.ensure_future(_asgi(c.app, "carol")) for _ in range(4)]
        await _until(lambda: calls[0] == 4)
        fifth, _ = await _asgi(c.app, "carol")
        inflight = dict(c.app.inflight)
        gate.set()
        return [s for s, _ in await asyncio.gather(*held)], fifth, inflight

    try:
        statuses, fifth, inflight = asyncio.run(run())
    finally:
        gate.set()
    assert fifth == 429 and statuses == [403] * 4 and inflight == {"carol": 4}
    assert calls[0] == 4  # the fifth never reached the hook
    assert c.app.inflight == {}


def test_operators_in_groups_admits_members_of_any_named_group() -> None:
    """The host's groups decide who is an operator (CONTRACT-010 section E); no group, no admin."""
    from arras.operate import operators_in_groups
    from arras.types import Principal

    decide = operators_in_groups("admins", "builders")
    assert decide(Principal("a", "t", groups=("admins",)))
    assert decide(Principal("b", "t", groups=("staff", "builders")))
    assert not decide(Principal("c", "t", groups=("staff",)))
    assert not decide(Principal("d", "t", groups=()))
    assert not decide(Principal("e", "t", admin=True))  # admin is the host's principal, not a role
