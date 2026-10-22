# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""`arras.ui.create_app`: one mount for the page and the three surfaces (ADR-027), driven in
process through the ASGI interface, over the sandbox's fakes."""

from __future__ import annotations

import asyncio
import html
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from arras import operate, ui
from arras.sandbox import Sandbox

BASE = "/ontology"


@pytest.fixture
def static(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "umf-explorer").mkdir()
    (tmp_path / ui.PAGE).write_text("<!doctype html><title>Arras</title>")
    (tmp_path / "assets" / "app.js").write_text("export {}")
    (tmp_path / "assets" / "app.css").write_text("a{}")
    (tmp_path / "umf-explorer" / "index.html").write_text("<p>explorer")
    (tmp_path / "secret.txt").write_text("no")
    return tmp_path


def make(static_dir: Path, *, operators: bool = True, base: str = BASE):
    box = Sandbox().seed()

    def who(request):
        return box.principal(request.headers["x-user"]) if "x-user" in request.headers else None

    return ui.create_app(
        box.arras,
        principal_for_request=who,
        authorize_operator=operate.operators_in_groups("admins", "builders") if operators else None,
        base_path=base,
        static_dir=static_dir,
    )


def call(
    app,
    method: str,
    path: str,
    *,
    user: str | None = "alice",
    body: Any = None,
    root_path: str = "",
) -> tuple[int, dict[str, str], bytes]:
    raw = json.dumps(body).encode() if body is not None else b""
    headers = [(b"host", b"app.example"), (b"content-type", b"application/json")]
    if user:
        headers.append((b"x-user", user.encode()))
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "root_path": root_path,
        "query_string": b"",
        "headers": headers,
    }
    sent: list[dict[str, Any]] = []

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    out = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    hdrs = {k.decode().lower(): v.decode() for k, v in start["headers"]}
    return start["status"], hdrs, out


def test_the_page_is_served_under_the_strict_policy(static: Path) -> None:
    status, headers, body = call(make(static), "GET", f"{BASE}/", user=None)
    assert status == 200 and b"<title>Arras</title>" in body
    assert headers["content-security-policy"] == ui.PAGE_CSP
    assert headers["x-frame-options"] == "SAMEORIGIN"
    assert headers["x-content-type-options"] == "nosniff"
    assert "unsafe-inline" not in ui.PAGE_CSP and "unsafe-eval" not in ui.PAGE_CSP


def test_assets_have_the_right_types_and_the_policy(static: Path) -> None:
    app = make(static)
    status, headers, _ = call(app, "GET", f"{BASE}/assets/app.js", user=None)
    assert status == 200 and headers["content-type"] == "text/javascript; charset=utf-8"
    assert headers["content-security-policy"] == ui.PAGE_CSP
    assert call(app, "GET", f"{BASE}/assets/app.css", user=None)[1]["content-type"].startswith(
        "text/css"
    )
    status, headers, body = call(app, "GET", f"{BASE}/umf-explorer/index.html", user=None)
    assert (
        status == 200
        and body == b"<p>explorer"
        and headers["content-security-policy"] == ui.PAGE_CSP
    )


def test_only_the_page_and_its_two_directories_are_served(static: Path) -> None:
    app = make(static)
    for path in (f"{BASE}/secret.txt", f"{BASE}/assets/missing.js", f"{BASE}/assets/../secret.txt"):
        assert call(app, "GET", path, user=None)[0] == 404
    assert call(app, "GET", f"{BASE}/assets/%2e%2e/secret.txt", user=None)[0] == 404


def test_the_bare_mount_redirects_to_the_page_so_relative_urls_resolve(static: Path) -> None:
    status, headers, _ = call(make(static), "GET", BASE, user=None)
    assert status == 308 and headers["location"] == f"{BASE}/"


def test_a_path_outside_the_mount_is_not_found(static: Path) -> None:
    assert call(make(static), "GET", "/elsewhere/", user=None)[0] == 404


def test_the_page_is_read_only_and_the_surfaces_answer_for_themselves(static: Path) -> None:
    app = make(static)
    assert call(app, "POST", f"{BASE}/", user=None, body={})[0] == 405
    assert (
        call(app, "GET", f"{BASE}/api/operate/viewer", user=None)[0] == 401
    )  # the surface's own refusal
    status, _, body = call(
        app, "GET", f"{BASE}/api/operate/version", user=None
    )  # public: the page checks it
    assert status == 200 and "operate" in json.loads(body)["contracts"]


def test_the_console_graphql_surface_is_mounted(static: Path) -> None:
    app = make(static)
    status, _, body = call(
        app, "POST", f"{BASE}/api/console/graphql", body={"query": "{ modules { name } }"}
    )
    assert status == 200 and "catalog" in [m["name"] for m in json.loads(body)["data"]["modules"]]
    assert (
        call(
            app,
            "POST",
            f"{BASE}/api/console/graphql",
            user=None,
            body={"query": "{ status { backend } }"},
        )[0]
        == 401
    )


def test_schema_import_is_mounted_only_with_an_operator_rule(static: Path) -> None:
    assert call(make(static), "GET", f"{BASE}/api/schema/version")[0] == 200
    assert call(make(static, operators=False), "GET", f"{BASE}/api/schema/version")[0] == 404


def test_operators_are_decided_by_the_hosts_rule(static: Path) -> None:
    app = make(static)

    def modes(user: str) -> list[str]:
        return json.loads(call(app, "GET", f"{BASE}/api/operate/viewer", user=user)[2])["modes"]

    assert "admin" in modes("alice")  # a builder
    assert "admin" not in modes("carol")  # a reader


def test_it_honours_a_hosts_root_path(static: Path) -> None:
    """A framework mount keeps the prefix in `path` and names it in `root_path`."""
    app = make(static, base="")
    status, _, body = call(app, "GET", "/ontology/", user=None, root_path="/ontology")
    assert status == 200 and b"<title>Arras</title>" in body


def test_a_source_checkout_without_the_build_says_so(tmp_path: Path) -> None:
    status, headers, body = call(make(tmp_path), "GET", f"{BASE}/", user=None)
    assert status == 503 and b"not built" in body
    assert (
        call(make(tmp_path), "GET", f"{BASE}/api/operate/version")[0] == 200
    )  # the API does not need it


def test_the_page_carries_the_default_brand(static: Path) -> None:
    _, _, body = call(make(static), "GET", f"{BASE}/", user=None)
    assert b"<title>Arras</title>" in body
    assert b'<meta name="arras-brand" content="{&quot;name&quot;: &quot;Arras&quot;}">' in body


def test_a_custom_brand_renders_its_title_and_escaped_json(static: Path) -> None:
    (static / ui.PAGE).write_text("<!doctype html><head><title>Arras</title></head>")
    brand = ui.Brand(name='A<t>"las', tagline="x & y", wordmark="https://e.example/w.svg")
    app = ui.create_app(
        Sandbox().seed().arras,
        principal_for_request=lambda r: None,
        base_path=BASE,
        static_dir=static,
        brand=brand,
    )
    _, headers, body = call(app, "GET", f"{BASE}/", user=None)
    text = body.decode()
    assert "<title>A&lt;t&gt;&quot;las</title>" in text
    m = re.search(r'<meta name="arras-brand" content="([^"]*)">', text)
    assert m and "<" not in m.group(1)
    assert json.loads(html.unescape(m.group(1))) == {
        "name": 'A<t>"las',
        "wordmark": "https://e.example/w.svg",
        "tagline": "x & y",
    }
    assert text.index("arras-brand") < text.index("</head>")
    assert headers["content-security-policy"] == brand.csp()
    assert "img-src 'self' https://e.example;" in brand.csp()


def test_a_brand_title_overrides_the_name(static: Path) -> None:
    app = make(static)
    app.brand = ui.Brand(name="Atlas", title="Atlas Console")
    _, _, body = call(app, "GET", f"{BASE}/", user=None)
    assert b"<title>Atlas Console</title>" in body


def test_the_branded_page_is_kept_until_the_file_or_the_brand_changes(
    static: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = make(static)
    calls: list[str] = []
    real = ui.branded

    def counting(page: bytes, brand: ui.Brand) -> bytes:
        calls.append(brand.name)
        return real(page, brand)

    monkeypatch.setattr(ui, "branded", counting)
    first = app.static("/")[2]
    assert app.static("/")[2] == first and calls == ["Arras"]  # branded once, then kept
    app.brand = ui.Brand(name="Atlas")  # another brand is not served the first's page
    assert b"<title>Atlas</title>" in app.static("/")[2]
    assert b"<title>Arras</title>" not in app.static("/")[2]
    page = static / ui.PAGE
    page.write_text("<!doctype html><title>Other</title><!-- rebuilt -->")  # a rebuilt page
    assert b"rebuilt" in app.static("/")[2]
    same_size = page.read_text().replace("rebuilt", "REBUILT")  # a change that keeps the size
    stat = page.stat()
    page.write_text(same_size)
    os.utime(page, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert b"REBUILT" in app.static("/")[2]
    other = static.parent / "other-build"  # another directory is another page
    (other / "assets").mkdir(parents=True)
    (other / ui.PAGE).write_text("<!doctype html><title>Elsewhere</title>")
    app.static_dir = other
    assert b"<meta" in app.static("/")[2] and b"Elsewhere" not in app.static("/")[2]


BRAND_VECTORS = json.loads(
    (Path(__file__).parent / "vectors" / "brand.json").read_text(encoding="utf-8")
)


def test_the_brand_caps_are_the_ones_the_interface_reads() -> None:
    """`tests/vectors/brand.json` is read by the UI too (ui/src/test/brand-caps.test.ts)."""
    assert ui.BRAND_CAPS == BRAND_VECTORS["caps"]


@pytest.mark.parametrize("field", list(BRAND_VECTORS["caps"]))
def test_a_brand_field_may_be_as_long_as_its_cap_and_no_longer(field: str) -> None:
    cap = BRAND_VECTORS["caps"][field]
    ok = ui.Brand(**{"name": "A", field: "x" * cap})
    assert len(json.loads(ok.meta())[field]) == cap
    with pytest.raises(ValueError, match=f"{field} is at most {cap}"):
        ui.Brand(**{"name": "A", field: "x" * (cap + 1)})
    assert ui.Brand(**{"name": "A", field: f"  {'x' * cap} "})  # the page trims before it counts


def test_a_wordmark_url_at_the_cap_is_kept_and_one_over_is_refused() -> None:
    cap = BRAND_VECTORS["caps"]["wordmark"]
    url = "https://e.example/" + "p" * (cap - len("https://e.example/"))
    assert ui.Brand(wordmark=url).wordmark == url
    with pytest.raises(ValueError, match="at most"):
        ui.Brand(wordmark=url + "p")


@pytest.mark.parametrize(
    "w", ["javascript:alert(1)", "data:image/svg+xml,x", "http://x/y.png", "https:x/y.png"]
)
def test_a_wordmark_is_text_or_an_https_url(w: str) -> None:
    with pytest.raises(ValueError, match="wordmark"):
        ui.Brand(wordmark=w)
    assert ui.Brand(wordmark="Atlas: Law").wordmark == "Atlas: Law"


def test_a_brand_logo_is_the_theme_mark_or_refused() -> None:
    meta = json.loads(ui.Brand(name="Atlas", logo="theme").meta())
    assert meta == {"name": "Atlas", "logo": "theme"}
    assert "logo" not in json.loads(ui.Brand().meta())
    for bad in ("", "https://e.example/l.svg", "Theme"):
        with pytest.raises(ValueError, match="logo"):
            ui.Brand(logo=bad)


def test_the_not_built_page_names_the_brand(tmp_path: Path) -> None:
    app = ui.create_app(
        Sandbox().seed().arras,
        principal_for_request=lambda r: None,
        base_path=BASE,
        static_dir=tmp_path,
        brand=ui.Brand(name="Atlas"),
    )
    status, headers, body = call(app, "GET", f"{BASE}/", user=None)
    assert status == 503 and b"<title>Atlas</title>" in body and b"(Atlas)" in body
    assert headers["content-security-policy"] == ui.PAGE_CSP


def test_the_wheel_carries_the_npm_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui, "NPM", tmp_path)
    with pytest.raises(FileNotFoundError, match="build:wheel"):
        ui.npm_package()
    tarball = tmp_path / "documentdrivendx-arras-ui-0.2.0.tgz"
    tarball.write_bytes(b"x")
    assert ui.npm_package() == tarball


def test_the_policy_admits_own_images_and_a_wordmark_origin_only() -> None:
    assert "img-src 'self';" in ui.PAGE_CSP
    assert ui.Brand(logo="theme").csp() == ui.PAGE_CSP
    assert ui.Brand(wordmark="Atlas").csp() == ui.PAGE_CSP
    csp = ui.Brand(wordmark="https://cdn.example:8443/a/w.svg?x=1").csp()
    assert "img-src 'self' https://cdn.example:8443;" in csp
    assert csp.count("https://") == 1 and "unsafe" not in csp


@pytest.mark.parametrize(
    "w",
    [
        "https://",
        "https://x.example/a;script-src *",
        "https://x.example/a b.png",
        "https://u:p@x.example/w.png",
        "https://*/w.png",
        "https://x.example:/w.png",
    ],
)
def test_an_image_wordmark_cannot_inject_into_the_policy(w: str) -> None:
    with pytest.raises(ValueError, match="wordmark"):
        ui.Brand(wordmark=w)


def test_the_brand_names_the_graphiql_page_and_the_openapi_document(static: Path) -> None:
    app = ui.create_app(
        Sandbox().seed().arras,
        principal_for_request=lambda r: None,
        base_path=BASE,
        static_dir=static,
        brand=ui.Brand(name="Atlas<"),
    )
    _, _, page = call(app, "GET", f"{BASE}/api/console/", user=None)
    assert b"<title>Atlas&lt; console</title>" in page
    _, _, doc = call(app, "GET", f"{BASE}/api/operate/openapi.json", user=None)
    assert json.loads(doc)["info"]["title"] == "Atlas< operator surface"
    _, _, page = call(make(static), "GET", f"{BASE}/api/console/", user=None)
    assert b"<title>Arras console</title>" in page
