# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The dev host as a real server: `uvicorn` on a free loopback port, the real `DevHost` over the
sandbox, and real HTTP requests over a socket. This is the Python side's "against a real server"
tier; the UI's integration tests and Playwright run against the same host (docs/helix/03-test).
Skipped where `uvicorn` (the dev dependency group) is not installed."""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from arras.devhost import DEFAULT_USER, DevHost, seed_demo
from arras.sandbox import Sandbox

uvicorn = pytest.importorskip("uvicorn")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory) -> Iterator[int]:
    port = _free_port()
    ui = tmp_path_factory.mktemp("ui")  # no index.html: the not-built page
    app = DevHost(seed_demo(Sandbox().seed()), port=port, ui_dir=ui)
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not srv.started:
        assert time.monotonic() < deadline, "the dev host did not start"
        time.sleep(0.02)
    yield port
    srv.should_exit = True
    t.join(10)


def request(
    port: int,
    method: str,
    path: str,
    body: Any = None,
    *,
    user: str = DEFAULT_USER,
    origin: str | None = "own",
    host: str | None = None,
) -> tuple[int, dict[str, str], Any]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"content-type": "application/json", "x-arras-user": user}
    if origin:
        headers["origin"] = f"http://127.0.0.1:{port}" if origin == "own" else origin
    if host:
        headers["host"] = host
    conn.request(method, path, json.dumps(body) if body is not None else None, headers)
    r = conn.getresponse()
    raw = r.read()
    conn.close()
    hdrs = {k.lower(): v for k, v in r.getheaders()}
    is_json = hdrs.get("content-type", "").startswith("application/json")
    return r.status, hdrs, json.loads(raw) if is_json and raw else raw


ADD = {"code": "uc-socket", "name": "Over a socket", "workArea": "finance"}


def test_version_and_the_page_are_served(server: int) -> None:
    status, h, v = request(server, "GET", "/api/operate/version")
    assert status == 200 and v["contracts"]["operate"] == 2 and h["cache-control"] == "no-store"
    status, _, page = request(server, "GET", "/")
    assert status == 200 and b"The UI is not built" in page
    status, _, people = request(server, "GET", "/api/people")
    assert status == 200 and people["default"] == DEFAULT_USER


def test_validate_then_invoke_then_read_it_back_and_see_it_in_the_audit(server: int) -> None:
    base = "/api/operate/actions/catalog/AddUseCase"
    status, _, v = request(server, "POST", f"{base}/validate", {"inputs": ADD})
    assert status == 200 and v["ok"] is True and v["effects"][0]["kind"] == "create"
    status, _, r = request(
        server, "POST", f"{base}/invoke", {"inputs": ADD, "idempotency_key": "sock-1"}
    )
    assert status == 200 and r["created"] == 1 and r["replayed"] is False
    status, _, again = request(
        server, "POST", f"{base}/invoke", {"inputs": ADD, "idempotency_key": "sock-1"}
    )
    assert again["replayed"] is True and again["group"] == r["group"]
    q = {"query": '{ useCase(key: "uc-socket") { name createdBy freshness { backend } } }'}
    status, _, g = request(server, "POST", "/api/console/graphql/catalog", q)
    assert status == 200 and g["data"]["useCase"] == {
        "name": "Over a socket",
        "createdBy": "alice",
        "freshness": {"backend": "memory"},
    }
    status, _, page = request(server, "POST", "/api/operate/audit/changes", {"group": r["group"]})
    assert status == 200 and [c["action"] for c in page["items"]] == ["catalog.AddUseCase"]
    assert page["items"][0]["by"] == "alice"


def test_an_expired_token_is_a_401_until_restored(server: int) -> None:
    control = "/api/dev/control"
    assert request(server, "POST", control, {"op": "expire", "user": "bob"})[0] == 200
    try:
        status, _, e = request(
            server, "POST", "/api/operate/audit/changes", {"module": "catalog"}, user="bob"
        )
        assert status == 401 and e["error"]["reason"] == "token_expired"
        status, _, g = request(
            server, "POST", "/api/console/graphql", {"query": "{ modules { name } }"}, user="bob"
        )
        assert status == 401 and g["errors"][0]["extensions"]["reason"] == "token_expired"
    finally:
        assert request(server, "POST", control, {"op": "restore", "user": "bob"})[0] == 200
    status, _, _ = request(
        server, "POST", "/api/operate/audit/changes", {"module": "catalog"}, user="bob"
    )
    assert status == 200


def test_a_foreign_origin_and_a_rebound_host_are_refused(server: int) -> None:
    path = "/api/operate/actions/catalog/AddUseCase/validate"
    status, h, e = request(server, "POST", path, {"inputs": ADD}, origin="https://evil.example")
    assert status == 403 and "access-control-allow-origin" not in h
    status, h, _ = request(server, "POST", path, {"inputs": ADD})
    assert status == 200 and h["access-control-allow-origin"] == f"http://127.0.0.1:{server}"
    status, _, _ = request(server, "GET", "/", host=f"evil.example:{server}")
    assert status == 403
    status, _, _ = request(
        server,
        "POST",
        "/api/console/graphql",
        {"query": "{ modules { name } }"},
        origin="https://evil.example",
    )
    assert status == 403


# -- UMF's schema browser: the package's assets at /umf-explorer, the console's page policy -------

ROOT = Path(__file__).resolve().parent.parent
# UMF's strict profile (no 'unsafe-eval') plus frame-ancestors; ui/e2e/umf-explorer.spec.ts runs the
# real package under it in Chromium.
CSP = (
    "default-src 'none'; base-uri 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "frame-src 'self' about:; connect-src 'self'; frame-ancestors 'self'"
)
# Stand-ins for the package's assets: what is served is whatever the build copied to
# ui/dist/umf-explorer (the npm package's `assets/`; the UI tests compare those bytes with the
# installed package). Here only the serving is under test, so the bytes are this test's own.
ASSET_FILES = {
    "index.html": b"<!doctype html><title>Schema browser</title>",
    "explorer.js": b"export {};\n",
    "explorer.css": b"body{}\n",
    "style.css": b":root{}\n",
    "schema-catalog.json": b'{"version":1,"entries":[]}\n',
}


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Iterator[int]:
    """A dev host over a built UI: an index page and the package's assets copied as the build
    copies them (ui/dist/umf-explorer)."""
    ui = tmp_path_factory.mktemp("built")
    (ui / "index.html").write_text("<!doctype html><title>console</title>")
    (ui / "umf-explorer").mkdir()
    for name, raw in ASSET_FILES.items():
        (ui / "umf-explorer" / name).write_bytes(raw)
    port = _free_port()
    srv = uvicorn.Server(
        uvicorn.Config(
            DevHost(Sandbox().seed(), port=port, ui_dir=ui), port=port, log_level="warning"
        )
    )
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not srv.started:
        assert time.monotonic() < deadline, "the dev host did not start"
        time.sleep(0.02)
    yield port
    srv.should_exit = True
    t.join(10)


def get(port: int, path: str, **headers: str) -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path, headers={k.replace("_", "-"): v for k, v in headers.items()})
    r = conn.getresponse()
    raw = r.read()
    conn.close()
    return r.status, {k.lower(): v for k, v in r.getheaders()}, raw


def test_the_catalog_is_the_operator_surfaces_and_names_the_person_by_header_only(
    built: int,
) -> None:
    path = "/api/operate/explorer/schema-catalog.json"
    status, h, raw = get(built, path, x_arras_user="alice")
    body = json.loads(raw)
    assert status == 200 and h["cache-control"] == "no-store"
    assert [e["id"] for e in body["entries"]] == ["arras:catalog"]
    from arras.sandbox import catalog_document

    assert body["entries"][0]["text"] == catalog_document()
    status, _, raw = get(built, path, x_arras_user="dave")  # dave is not an operator
    assert status == 403 and json.loads(raw) == {"error": "REFUSED", "reason": "not_operator"}
    control = "/api/dev/control"
    try:  # an operator who may read no module has an empty catalog
        assert (
            request(built, "POST", control, {"op": "revoke", "user": "bob", "module": "catalog"})[0]
            == 200
        )
        status, _, raw = get(built, path, x_arras_user="bob")
        assert status == 200 and json.loads(raw) == {"version": 1, "entries": []}
    finally:
        request(
            built,
            "POST",
            control,
            {
                "op": "grant",
                "user": "bob",
                "module": "catalog",
                "modes": ["read", "write", "journal"],
            },
        )
    # No cookie names a person any more: dave's cookie reads as the dev host's default person.
    status, _, raw = get(built, path, cookie="arras_user=dave")
    assert status == 200 and len(json.loads(raw)["entries"]) == 1
    status, _, raw = get(built, path, x_arras_user="nobody")
    assert status == 401 and json.loads(raw)["error"]["type"] == "Refused"


def test_the_package_catalog_path_is_a_static_file_not_the_viewers_catalog(built: int) -> None:
    # The old relative-fetch route is gone: the package's own empty catalog file is what is there.
    status, _, raw = get(built, "/umf-explorer/schema-catalog.json", x_arras_user="alice")
    assert status == 200 and raw == ASSET_FILES["schema-catalog.json"]
    assert json.loads(raw) == {"version": 1, "entries": []}


def test_an_expired_token_reaches_the_catalog_as_a_401(built: int) -> None:
    control = "/api/dev/control"
    assert request(built, "POST", control, {"op": "expire", "user": "bob"})[0] == 200
    try:
        status, _, raw = get(built, "/api/operate/explorer/schema-catalog.json", x_arras_user="bob")
        assert status == 401 and json.loads(raw)["error"]["reason"] == "token_expired"
    finally:
        assert request(built, "POST", control, {"op": "restore", "user": "bob"})[0] == 200


def test_the_package_assets_and_the_console_page_are_served_under_one_policy(built: int) -> None:
    for name in ("index.html", "explorer.js", "explorer.css", "style.css"):
        status, h, raw = get(built, f"/umf-explorer/{name}")
        assert status == 200, name
        assert raw == ASSET_FILES[name], name
        assert h["content-security-policy"] == CSP, name
        assert h["x-content-type-options"] == "nosniff"
        assert h["x-frame-options"] == "SAMEORIGIN"
    assert get(built, "/umf-explorer/explorer.js")[1]["content-type"].startswith("text/javascript")
    assert get(built, "/umf-explorer/style.css")[1]["content-type"].startswith("text/css")
    status, h, raw = get(built, "/umf-explorer/")
    assert status == 200 and raw == ASSET_FILES["index.html"]
    assert get(built, "/umf-explorer/missing.js")[0] == 404
    assert get(built, "/umf-explorer/../index.html")[0] in (200, 404)  # never outside the build
    # The browser's srcdoc frame inherits the console page's policy: the same one.
    status, h, _ = get(built, "/")
    assert status == 200 and h["content-security-policy"] == CSP
    assert get(built, "/#/catalog/schema")[1]["content-security-policy"] == CSP


def test_npm_run_dev_sets_the_same_policy() -> None:
    from arras.devhost import PAGE_CSP

    assert PAGE_CSP == CSP
    assert "unsafe-eval" not in PAGE_CSP and "unsafe-inline" not in PAGE_CSP
    assert f'"{CSP}"' in (ROOT / "ui" / "vite.config.ts").read_text()


def test_control_registers_another_module_the_people_hold_like_catalog(tmp_path) -> None:
    """The UI's tests register a second module to switch modules in UMF's schema browser."""
    from arras.sandbox import catalog_document

    port = _free_port()
    srv = uvicorn.Server(
        uvicorn.Config(
            DevHost(Sandbox().seed(), port=port, ui_dir=tmp_path), port=port, log_level="warning"
        )
    )
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not srv.started:
        assert time.monotonic() < deadline, "the dev host did not start"
        time.sleep(0.02)
    try:
        doc = catalog_document().replace('"catalog"', '"intake"')
        assert (
            request(port, "POST", "/api/dev/control", {"op": "register", "document": doc})[0] == 200
        )
        status, _, body = request(port, "GET", "/api/operate/explorer/schema-catalog.json")
        assert status == 200
        assert [e["id"] for e in body["entries"]] == ["arras:catalog", "arras:intake"]
        assert next(e for e in body["entries"] if e["id"] == "arras:intake")["text"] == doc
        bad = {"op": "register", "document": "{}"}
        status, _, body = request(port, "POST", "/api/dev/control", bad)
        assert status == 400 and body["error"] == "not registered"
        assert (
            request(port, "POST", "/api/dev/control", {"op": "register", "document": 1})[0] == 400
        )
    finally:
        srv.should_exit = True
        t.join(10)


def test_the_dev_host_marks_alice_bob_and_root_as_operators_and_carol_and_dave_as_not(
    server: int,
) -> None:
    """@covers US-072-AC5: over a real socket, as the sandbox's people."""
    for user, modes in (
        ("alice", ["user", "admin"]),
        ("bob", ["user", "admin"]),
        ("root", ["user", "admin"]),
        ("carol", ["user"]),
        ("dave", ["user"]),
    ):
        status, _, body = request(server, "GET", "/api/operate/viewer", user=user, origin=None)
        assert (status, body) == (200, {"user": user, "modes": modes})
    status, _, body = request(
        server, "POST", "/api/operate/audit/changes", {"module": "catalog"}, user="carol"
    )
    assert (status, body) == (403, {"error": "REFUSED", "reason": "not_operator"})
    status, _, _ = request(server, "GET", "/api/operate/explorer/schema-catalog.json", user="carol")
    assert status == 403
    status, _, body = request(
        server, "POST", "/api/console/graphql", {"query": "{ modules { name } }"}, user="carol"
    )
    assert status == 200 and body["data"]["modules"] == [{"name": "catalog"}]  # user mode reads


def test_control_grants_and_revokes_a_persons_access_to_a_module(server: int) -> None:
    control = "/api/dev/control"
    query = {"query": "{ modules { name } }"}
    graphql = "/api/console/graphql"

    def modules(user: str) -> list[str]:
        return [
            m["name"]
            for m in request(server, "POST", graphql, query, user=user)[2]["data"]["modules"]
        ]

    assert modules("carol") == ["catalog"] and modules("dave") == []
    try:
        assert (
            request(
                server, "POST", control, {"op": "revoke", "user": "carol", "module": "catalog"}
            )[0]
            == 200
        )
        assert modules("carol") == []
        assert (
            request(server, "POST", control, {"op": "grant", "user": "dave", "module": "catalog"})[
                0
            ]
            == 200
        )
        assert modules("dave") == ["catalog"]
    finally:
        request(server, "POST", control, {"op": "grant", "user": "carol", "module": "catalog"})
        request(server, "POST", control, {"op": "revoke", "user": "dave", "module": "catalog"})
    assert modules("carol") == ["catalog"] and modules("dave") == []
    for bad in (
        {"op": "grant", "user": "nobody", "module": "catalog"},
        {"op": "grant", "user": "carol", "module": ""},
        {"op": "grant", "user": "carol", "module": "catalog", "modes": ["admin"]},
        {"op": "revoke", "user": "carol"},
    ):
        assert request(server, "POST", control, bad)[0] == 400


def test_control_declares_what_search_a_backend_offers_for_a_type(server: int) -> None:
    """@covers US-065-AC6: the e2e suite stages a type that is not searched."""
    control = "/api/dev/control"
    graphql = "/api/console/graphql/catalog"
    query = {
        "query": '{ _search(text: "pipeline") { hits { type } notSearched { type reason backend } } }'
    }

    def searched() -> dict:
        return request(server, "POST", graphql, query, user="carol")[2]["data"]["_search"]

    assert searched()["notSearched"] == []
    declare = {"op": "search", "backend": "memory", "type": "catalog.Solution", "mode": "none"}
    try:
        assert request(server, "POST", control, declare)[0] == 200
        page = searched()
        assert page["notSearched"] == [
            {"type": "Solution", "reason": "no_capability", "backend": "memory"}
        ]
        assert {h["type"] for h in page["hits"]} == {"UseCase"}
    finally:
        restore = {**declare, "mode": None}
        assert request(server, "POST", control, restore)[0] == 200
    assert searched()["notSearched"] == []
    for bad in (
        {**declare, "mode": "fuzzy"},
        {**declare, "type": "catalog.Nope"},
        {**declare, "backend": "nope"},
    ):
        assert request(server, "POST", control, bad)[0] == 400
