# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The dev host's made-up people: a name and a role (US-076), over the real apps in process.

The sandbox has no sign-in, so a developer picks a role and any name; the role is a set of grants
on the fake backends, and the backends decide everything the person may do."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from arras.devhost import DevHost
from arras.sandbox import ROLES, Sandbox, catalog_document
from test_schema_library import with_property

DOC = catalog_document()
PORT = 8765
ADD = {"code": "uc-r", "name": "R", "workArea": "finance"}


@pytest.fixture
def app(tmp_path: Path) -> DevHost:
    return DevHost(Sandbox().seed(), port=PORT, ui_dir=tmp_path)


def call(
    app: DevHost,
    method: str,
    path: str,
    body: Any = None,
    *,
    user: str = "alice",
    role: str | None = None,
    host: str = f"127.0.0.1:{PORT}",
) -> tuple[int, Any]:
    headers = [
        (b"host", host.encode()),
        (b"content-type", b"application/json"),
        (b"origin", f"http://127.0.0.1:{PORT}".encode()),
        (b"x-arras-user", user.encode()),
    ]
    if role is not None:
        headers.append((b"x-arras-role", role.encode()))
    data = json.dumps(body).encode() if body is not None else b""
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": data, "more_body": False}

    async def send(msg: dict) -> None:
        sent.append(msg)

    asyncio.run(
        app({"type": "http", "method": method, "path": path, "headers": headers}, receive, send)
    )
    raw = sent[1]["body"]
    ctype = dict(sent[0]["headers"]).get(b"content-type", b"")
    return sent[0]["status"], json.loads(raw) if raw and ctype.startswith(
        b"application/json"
    ) else raw


def validate(app: DevHost, **who: Any) -> int:
    return call(
        app, "POST", "/api/operate/actions/catalog/AddUseCase/validate", {"inputs": ADD}, **who
    )[0]


def invoke(app: DevHost, **who: Any) -> int:
    return call(
        app, "POST", "/api/operate/actions/catalog/AddUseCase/invoke", {"inputs": ADD}, **who
    )[0]


def plan(app: DevHost, doc: str, **who: Any) -> int:
    return call(app, "POST", "/api/schema/validate", {"document": doc}, **who)[0]


def test_the_people_list_names_the_roles(app: DevHost) -> None:
    status, people = call(app, "GET", "/api/people")
    assert status == 200 and people["roles"] == list(ROLES) and "alice" in people["people"]
    assert "zed" not in people["people"]  # made up per request, not listed


def modules(app: DevHost, **who: Any) -> list[str]:
    status, g = call(app, "POST", "/api/console/graphql", {"query": "{ modules { name } }"}, **who)
    assert status == 200 and "errors" not in g
    return [m["name"] for m in g["data"]["modules"]]


def test_a_viewer_reads_and_nothing_else(app: DevHost) -> None:
    who = {"user": "zed", "role": "viewer"}
    assert modules(app, **who) == ["catalog"]
    assert validate(app, **who) == 403 and invoke(app, **who) == 403
    assert plan(app, DOC, **who) == 403


def test_an_editor_changes_data_but_not_the_schema(app: DevHost) -> None:
    who = {"user": "zed", "role": "editor"}
    assert validate(app, **who) == 200 and invoke(app, **who) == 200
    assert plan(app, DOC, **who) == 403


def test_a_schema_author_changes_the_schema_but_not_the_data(app: DevHost) -> None:
    who = {"user": "ana", "role": "schema author"}
    assert invoke(app, **who) == 403
    optional = with_property(DOC, "notes", required=False)
    status, p = call(app, "POST", "/api/schema/validate", {"document": optional}, **who)
    assert status == 200 and p["ok"] and p["changed"]
    status, r = call(
        app,
        "POST",
        "/api/schema/register",
        {"document": optional, "expected_revision": p["revision"]},
        **who,
    )
    assert status == 200 and r["changed"]
    # every reader sees it: the record store holds it, and the replica learns through its feed
    app.box.replica.feed()
    seen = app.box.replica.modules["catalog"]
    assert "notes" in {p.name for t in seen.entity_types for p in t.properties}


def test_an_auditor_reads_the_journal_and_a_role_of_none_sees_nothing(app: DevHost) -> None:
    aud = {"user": "ada", "role": "auditor"}
    status, changes = call(app, "POST", "/api/operate/audit/changes", {"module": "catalog"}, **aud)
    assert status == 200 and changes["items"]
    viewer = {"user": "vic", "role": "viewer"}  # reads, but holds no journal grant
    assert (
        call(app, "POST", "/api/operate/audit/changes", {"module": "catalog"}, **viewer)[0] == 403
    )
    nobody = {"user": "nil", "role": "none"}
    assert modules(app, **nobody) == []
    assert validate(app, **nobody) == 404  # no module to act on, as for an unknown one


def test_a_maintainer_does_all_of_it(app: DevHost) -> None:
    who = {"user": "max", "role": "maintainer"}
    assert invoke(app, **who) == 200 and plan(app, DOC, **who) == 200
    assert call(app, "POST", "/api/operate/audit/changes", {"module": "catalog"}, **who)[0] == 200


@pytest.mark.parametrize(
    ("name", "role"),
    [
        ("Zed", "viewer"),  # upper case
        ("", "viewer"),
        ("z z", "viewer"),
        ("1zed", "viewer"),
        ("z" * 33, "viewer"),
        ("zed\r\nx-evil: 1", "viewer"),
        ("root", "maintainer"),  # the administrator
        ("alice", "viewer"),  # a fixed person
        ("zed", "wizard"),  # not a role
    ],
)
def test_a_name_or_role_that_is_not_allowed_makes_no_principal(
    app: DevHost, name: str, role: str
) -> None:
    before = dict(app.box.access.grants)
    status, _ = call(
        app,
        "POST",
        "/api/console/graphql/catalog",
        {"query": "{ __typename }"},
        user=name,
        role=role,
    )
    assert status == 401
    assert app.box.access.grants == before and not app.box.minted


def test_the_administrator_is_refused_by_every_surface(app: DevHost) -> None:
    _, g = call(app, "POST", "/api/console/graphql", {"query": "{ modules { name } }"}, user="root")
    assert g["errors"][0]["extensions"]["code"] == "REFUSED"  # `describe` is a user operation
    assert validate(app, user="root") == 404  # no module to act on
    assert plan(app, DOC, user="root") == 403
    assert call(app, "POST", "/api/schema/register", {"document": DOC}, user="root")[0] == 403
    for status in (  # claiming a role does not make the administrator a made-up person
        validate(app, user="root", role="maintainer"),
        plan(app, DOC, user="root", role="maintainer"),
    ):
        assert status == 401


def test_a_name_used_again_holds_the_new_role_and_only_that(app: DevHost) -> None:
    assert invoke(app, user="zed", role="editor") == 200
    assert invoke(app, user="zed", role="viewer") == 403
    assert plan(app, DOC, user="zed", role="schema author") == 200
    assert validate(app, user="zed", role="schema author") == 403  # no write any more
    assert validate(app, user="zed", role="editor") == 200
    assert plan(app, DOC, user="zed", role="editor") == 403  # no schema any more


def test_a_made_up_person_is_attributed_by_name(app: DevHost) -> None:
    who = {"user": "kai", "role": "editor"}
    key = {"inputs": {"code": "uc-k", "name": "K"}}
    status, r = call(app, "POST", "/api/operate/actions/catalog/AddUseCase/invoke", key, **who)
    assert status == 200
    status, g = call(
        app,
        "POST",
        "/api/console/graphql/catalog",
        {"query": '{ useCase(key: "uc-k") { createdBy } }'},
        user="kai",
        role="editor",
    )
    assert g["data"]["useCase"]["createdBy"] == "kai"


def test_the_control_can_expire_a_made_up_persons_token(app: DevHost) -> None:
    who = {"user": "zed", "role": "viewer"}
    assert validate(app, **who) == 403  # known
    status, _ = call(app, "POST", "/api/dev/control", {"op": "expire", "user": "zed"})
    assert status == 200
    assert (
        call(
            app, "POST", "/api/operate/actions/catalog/AddUseCase/validate", {"inputs": ADD}, **who
        )[0]
        == 401
    )
    assert call(app, "POST", "/api/dev/control", {"op": "restore", "user": "zed"})[0] == 200
    assert validate(app, **who) == 403
    assert call(app, "POST", "/api/dev/control", {"op": "expire", "user": "nobody-here"})[0] == 400


def test_the_dev_host_answers_only_on_loopback(app: DevHost) -> None:
    status, _ = call(app, "GET", "/api/people", host="evil.example")
    assert status == 403


def test_minting_and_knowing_modules_race_without_error(app: DevHost) -> None:
    box = app.box

    def mint(i: int) -> None:
        box.person(f"p{i}", list(ROLES)[i % len(ROLES)])
        if i % 5 == 0:
            box.know(f"m{i}")

    with ThreadPoolExecutor(8) as pool:
        for f in [pool.submit(mint, i) for i in range(200)]:
            f.result()
    assert len(box.minted) == 200


def test_the_sandbox_readers_are_not_operators_and_made_up_people_are(app: DevHost) -> None:
    refused = {"error": "REFUSED", "reason": "not_operator"}
    for user in ("carol", "dave"):  # no praxis group: the Graph Browser's user mode only
        assert call(app, "GET", "/api/operate/viewer", user=user)[1]["modes"] == ["user"]
        assert (
            call(
                app,
                "POST",
                "/api/operate/query",
                {"sql": "SELECT u.code FROM catalog.UseCase u"},
                user=user,
            )[1]
            == refused
        )
        assert call(app, "POST", "/api/schema/validate", {"document": DOC}, user=user)[1] == refused
    for who in ({"user": "vic", "role": "viewer"}, {"user": "nil", "role": "none"}):
        assert call(app, "GET", "/api/operate/viewer", **who)[1]["modes"] == ["user", "admin"]
