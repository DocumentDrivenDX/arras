# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""`ui.create_app` mounted by real Starlette and FastAPI hosts.

A framework mount keeps the mount prefix in `scope["path"]` and names it in `scope["root_path"]`.
The app must serve the page, an asset, the console and operate surfaces the same way whether the
host passes `base_path="/ontology"` or `base_path=""` to a `Mount("/ontology", ...)`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("starlette")
pytest.importorskip("httpx")

from fastapi import FastAPI  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.routing import Mount  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from arras import operate, ui  # noqa: E402
from arras.sandbox import Sandbox  # noqa: E402
from test_ui import static  # noqa: E402,F401

MOUNT = "/ontology"


@pytest.fixture
def static_dir(static: Path) -> Path:  # noqa: F811
    return static


def child(static_dir: Path, base: str):
    box = Sandbox().seed()

    def who(request):
        return box.principal(request.headers["x-user"]) if "x-user" in request.headers else None

    return ui.create_app(
        box.arras,
        principal_for_request=who,
        authorize_operator=operate.operators_in_groups("admins", "builders"),
        base_path=base,
        public_origin="http://testserver",
        static_dir=static_dir,
    )


def starlette_host(static_dir: Path, base: str) -> TestClient:
    return TestClient(
        Starlette(routes=[Mount(MOUNT, app=cast(Any, child(static_dir, base)))]),
        follow_redirects=False,
    )


def fastapi_host(static_dir: Path, base: str) -> TestClient:
    app = FastAPI()
    app.mount(MOUNT, cast(Any, child(static_dir, base)))
    return TestClient(app, follow_redirects=False)


HOSTS = [starlette_host, fastapi_host]


@pytest.mark.parametrize("host", HOSTS)
@pytest.mark.parametrize("base", [MOUNT, ""])
def test_a_framework_mount_serves_every_surface(host, base: str, static_dir: Path) -> None:
    client = host(static_dir, base)
    page = client.get(f"{MOUNT}/")
    assert page.status_code == 200 and "<title>Arras</title>" in page.text
    asset = client.get(f"{MOUNT}/assets/app.js")
    assert asset.status_code == 200 and asset.text == "export {}"
    assert client.get(f"{MOUNT}/umf-explorer/index.html").status_code == 200
    assert client.get(f"{MOUNT}/nothing").status_code == 404

    version = client.get(f"{MOUNT}/api/operate/version")
    assert version.status_code == 200 and "operate" in version.json()["contracts"]
    assert client.get(f"{MOUNT}/api/operate/viewer").status_code == 401
    viewer = client.get(f"{MOUNT}/api/operate/viewer", headers={"x-user": "alice"})
    assert viewer.status_code == 200 and "admin" in viewer.json()["modes"]
    assert client.get(f"{MOUNT}/api/schema/version").status_code == 200

    graphql = client.post(
        f"{MOUNT}/api/console/graphql",
        json={"query": "{ modules { name } }"},
        headers={"x-user": "alice", "origin": "http://testserver"},
    )
    assert graphql.status_code == 200
    assert "catalog" in [m["name"] for m in json.loads(graphql.text)["data"]["modules"]]
    assert client.get(f"{MOUNT}/api/console/").status_code == 200


@pytest.mark.parametrize("host", HOSTS)
@pytest.mark.parametrize("base", [MOUNT, ""])
def test_a_framework_mount_redirects_the_bare_prefix_to_the_mounted_slash(
    host, base: str, static_dir: Path
) -> None:
    client = host(static_dir, base)
    response = client.get(f"{MOUNT}/api/console")
    assert response.status_code == 308
    assert response.headers["location"].endswith(f"{MOUNT}/api/console/")
    assert f"{MOUNT}{MOUNT}" not in response.headers["location"]
