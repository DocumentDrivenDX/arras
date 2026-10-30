# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""`arras.ui.create_app`: one mount for the page and the three surfaces (ADR-027), driven in
process through the ASGI interface, over the sandbox's fakes."""

from __future__ import annotations

import asyncio
import hashlib
import html
import importlib.metadata
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from arras import operate, ui
from arras.sandbox import Sandbox
from arras.ui.assets import load_manifest

BASE = "/ontology"
UI_VERSION = importlib.metadata.version("arras")


def refresh_page_manifest(root: Path) -> None:
    data = json.loads((root / "asset-manifest.json").read_text())
    for name in data["files"]:
        body = (root / name).read_bytes()
        data["files"][name]["size"] = len(body)
        data["files"][name]["sha256"] = hashlib.sha256(body).hexdigest()
    (root / "asset-manifest.json").write_text(json.dumps(data))


@pytest.fixture
def static(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "umf-explorer").mkdir()
    (tmp_path / ui.PAGE).write_text("<!doctype html><title>Arras</title>")
    (tmp_path / "assets" / "app.js").write_text("export {}")
    (tmp_path / "assets" / "app.css").write_text("a{}")
    (tmp_path / "umf-explorer" / "index.html").write_text("<p>explorer")
    (tmp_path / "secret.txt").write_text("no")
    files = {}
    for candidate in (
        tmp_path / "embed.html",
        tmp_path / "assets" / "app.js",
        tmp_path / "assets" / "app.css",
        tmp_path / "umf-explorer" / "index.html",
    ):
        body = candidate.read_bytes()
        mime = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}[
            candidate.suffix
        ]
        files[candidate.relative_to(tmp_path).as_posix()] = {
            "sha256": hashlib.sha256(body).hexdigest(),
            "size": len(body),
            "mime": mime,
        }
    (tmp_path / "asset-manifest.json").write_text(
        json.dumps(
            {
                "format": "arras.ui.assets",
                "version": 1,
                "kind": "page",
                "package": {"name": "@documentdrivendx/arras-ui", "version": UI_VERSION},
                "contracts": {"console": 2, "operate": 2, "schema": 1, "browser": 1},
                "schema_browser": {
                    "name": "@documentdrivendx/umf-schema-browser",
                    "version": "2.0.0",
                    "integrity": "sha512-test",
                },
                "entry": {"html": "embed.html"},
                "files": files,
            }
        )
    )
    return tmp_path


def make(
    static_dir: Path,
    *,
    operators: bool = True,
    base: str = BASE,
    authorize_schema=None,
    distribution=None,
    brand=None,
):
    box = Sandbox().seed()

    def who(request):
        return box.principal(request.headers["x-user"]) if "x-user" in request.headers else None

    return ui.create_app(
        box.arras,
        principal_for_request=who,
        authorize_operator=operate.operators_in_groups("admins", "builders") if operators else None,
        authorize_schema=authorize_schema,
        base_path=base,
        public_origin="https://app.example",
        static_dir=static_dir,
        distribution=distribution,
        brand=brand,
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
    headers = [
        (b"host", b"app.example"),
        (b"content-type", b"application/json"),
        (b"origin", b"https://app.example"),
    ]
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


def test_external_theme_is_digest_served_same_origin_and_version_pinned(
    static: Path, tmp_path: Path
) -> None:
    css = b".arras-root{--arras-color-text:#111}"
    font = b"font-bytes"
    icon = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
    for name, body in (("theme.css", css), ("font.woff2", font), ("favicon.svg", icon)):
        (tmp_path / name).write_bytes(body)
    files = {
        name: {"sha256": hashlib.sha256(body).hexdigest(), "size": len(body), "mime": mime}
        for name, body, mime in (
            ("theme.css", css, "text/css"),
            ("font.woff2", font, "font/woff2"),
            ("favicon.svg", icon, "image/svg+xml"),
        )
    }
    manifest = tmp_path / "theme.json"
    manifest.write_text(
        json.dumps(
            {
                "format": "arras.ui.assets",
                "version": 1,
                "kind": "theme",
                "package": {"name": "neutral-theme", "version": "1"},
                "contracts": {"console": 2, "operate": 2, "schema": 1, "browser": 1},
                "ui_versions": [UI_VERSION],
                "entry": {
                    "stylesheet": "theme.css",
                    "fonts": ["font.woff2"],
                    "favicon": "favicon.svg",
                },
                "files": files,
            }
        )
    )
    app = ui.create_app(
        Sandbox().seed().arras,
        principal_for_request=lambda _request: None,
        base_path=BASE,
        static_dir=static,
        theme_manifest=manifest,
    )
    status, headers, body = call(app, "GET", f"/mount{BASE}/", user=None, root_path="/mount")
    assert (
        status == 200
        and b"/mount/ontology/theme-assets/" in body
        and b"theme.css" in body
        and b"favicon.svg" in body
    )
    assert "font-src 'self'" in headers["content-security-policy"]
    assert app.theme_manifest is not None
    digest = app.theme_manifest.manifest_sha256
    status, headers, body = call(
        app, "GET", f"/mount{BASE}/theme-assets/{digest}/font.woff2", user=None, root_path="/mount"
    )
    assert status == 200 and body == font and headers["cache-control"].endswith("immutable")
    assert call(app, "GET", f"{BASE}/theme-assets/{digest}/../theme.json", user=None)[0] == 404
    assert call(app, "GET", f"{BASE}/theme-assets/{digest}/secret.txt", user=None)[0] == 404
    changed = json.loads(manifest.read_text())
    changed["ui_versions"] = ["9.9.9"]
    manifest.write_text(json.dumps(changed))
    assert call(app, "GET", f"{BASE}/theme-assets/{digest}/font.woff2", user=None)[0] == 503


def _theme_manifest(directory: Path, **entry: Any) -> Path:
    css = b".arras-root{--arras-color-text:#111}"
    (directory / "theme.css").write_bytes(css)
    path = directory / "theme.json"
    path.write_text(
        json.dumps(
            {
                "format": "arras.ui.assets",
                "version": 1,
                "kind": "theme",
                "package": {"name": "theme", "version": "1"},
                "contracts": {"console": 2, "operate": 2, "schema": 1, "browser": 1},
                "ui_versions": [UI_VERSION],
                "entry": {"stylesheet": "theme.css", **entry},
                "files": {
                    "theme.css": {
                        "sha256": hashlib.sha256(css).hexdigest(),
                        "size": len(css),
                        "mime": "text/css",
                    }
                },
            }
        )
    )
    return path


def _themed_app(static: Path, manifest: Path):
    (static / ui.PAGE).write_text(
        '<!doctype html><html lang="en"><head><title>Arras</title></head><body></body></html>'
    )
    refresh_page_manifest(static)
    return ui.create_app(
        Sandbox().seed().arras,
        principal_for_request=lambda _request: None,
        base_path=BASE,
        static_dir=static,
        theme_manifest=manifest,
    )


@pytest.mark.parametrize("appearance", ["light", "dark"])
def test_a_theme_that_declares_its_appearance_puts_it_on_the_served_page(
    static: Path, tmp_path: Path, appearance: str
) -> None:
    """A runtime theme that supplies one set of role tokens needs the page to say which appearance it is:
    a `color-scheme` in its stylesheet is not read, and the derived tokens would follow the OS."""
    app = _themed_app(static, _theme_manifest(tmp_path, appearance=appearance))
    status, _, body = call(app, "GET", f"{BASE}/", user=None)
    assert status == 200
    assert f'<html lang="en" data-appearance="{appearance}">'.encode() in body
    assert body.count(b"data-appearance") == 1


def test_a_theme_without_an_appearance_leaves_it_to_the_os(static: Path, tmp_path: Path) -> None:
    app = _themed_app(static, _theme_manifest(tmp_path))
    status, _, body = call(app, "GET", f"{BASE}/", user=None)
    assert status == 200 and b"theme-assets/" in body
    assert b"data-appearance" not in body and b'<html lang="en">' in body


def test_a_declared_appearance_replaces_the_one_the_page_has(static: Path, tmp_path: Path) -> None:
    manifest = _theme_manifest(tmp_path, appearance="light")
    app = _themed_app(static, manifest)
    (static / ui.PAGE).write_text(
        "<!doctype html><HTML data-appearance='dark' lang=en><head><title>Arras</title></head></HTML>"
    )
    refresh_page_manifest(static)
    status, _, body = call(app, "GET", f"{BASE}/", user=None)
    assert status == 200
    assert b'<html lang=en data-appearance="light">' in body and b"dark" not in body


@pytest.mark.parametrize("bad", ["auto", "Light", "", None, 1, ["light"]])
def test_a_theme_appearance_is_light_or_dark_only(static: Path, tmp_path: Path, bad: Any) -> None:
    manifest = _theme_manifest(tmp_path, appearance=bad)
    with pytest.raises(ValueError, match="entry.appearance"):
        load_manifest(manifest, kind="theme")


def test_invalid_and_wrong_cohort_theme_manifests_refuse(static: Path, tmp_path: Path) -> None:
    path = tmp_path / "theme.json"
    body = b"a{}"
    (tmp_path / "theme.css").write_bytes(body)
    path.write_text(
        json.dumps(
            {
                "format": "arras.ui.assets",
                "version": 1,
                "kind": "theme",
                "package": {"name": "theme", "version": "1"},
                "contracts": {"console": 2, "operate": 2, "schema": 1, "browser": 1},
                "ui_versions": ["9.9.9"],
                "entry": {"stylesheet": "theme.css"},
                "files": {
                    "theme.css": {
                        "sha256": hashlib.sha256(body).hexdigest(),
                        "size": len(body),
                        "mime": "text/css",
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="ui_versions"):
        ui.create_app(
            Sandbox().seed().arras,
            principal_for_request=lambda _request: None,
            static_dir=static,
            theme_manifest=path,
        )


def test_asset_manifest_rejects_bool_version_and_exposes_immutable_entry(static: Path) -> None:
    manifest_path = static / "asset-manifest.json"
    data = json.loads(manifest_path.read_text())
    data["version"] = True
    manifest_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="format, version or kind"):
        load_manifest(manifest_path, kind="page")
    refresh_page_manifest(static)
    theme_data = {
        "format": "arras.ui.assets",
        "version": 1,
        "kind": "theme",
        "package": {"name": "theme", "version": "1"},
        "contracts": {"console": 2, "operate": 2, "schema": 1, "browser": 1},
        "ui_versions": [UI_VERSION],
        "entry": {"stylesheet": "theme.css", "fonts": ["font.woff2"]},
        "files": {},
    }
    (static / "theme.css").write_text("a{}")
    (static / "font.woff2").write_bytes(b"font")
    for name in ("theme.css", "font.woff2"):
        body = (static / name).read_bytes()
        theme_data["files"][name] = {
            "sha256": hashlib.sha256(body).hexdigest(),
            "size": len(body),
            "mime": "text/css" if name.endswith(".css") else "font/woff2",
        }
    theme_path = static / "theme-manifest.json"
    theme_path.write_text(json.dumps(theme_data))
    checked = load_manifest(theme_path, kind="theme")
    assert checked.entry["fonts"] == ("font.woff2",)
    assert isinstance(checked.entry["fonts"], tuple)
    with pytest.raises(TypeError):
        checked.entry["fonts"][0] = "other.woff2"  # pyright: ignore[reportIndexIssue]


def test_page_entry_is_manifest_selected_and_refreshed_cohort_is_rechecked(static: Path) -> None:
    page = static / "embed.html"
    page.rename(static / "host.html")
    data = json.loads((static / "asset-manifest.json").read_text())
    data["entry"]["html"] = "host.html"
    data["files"]["host.html"] = data["files"].pop("embed.html")
    (static / "asset-manifest.json").write_text(json.dumps(data))
    app = make(static)
    assert call(app, "GET", f"{BASE}/", user=None)[0] == 200
    data["package"]["version"] = "9.9.9"
    (static / "asset-manifest.json").write_text(json.dumps(data))
    status, _, body = call(app, "GET", f"{BASE}/", user=None)
    assert status == 503 and b"asset manifest invalid" in body


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
    app = make(
        static,
        operators=False,
        authorize_schema=lambda principal, module: True,
    )
    assert call(app, "GET", f"{BASE}/api/schema/version")[0] == 404


def test_composed_schema_hook_receives_the_viewer_and_module_for_both_verbs(
    static: Path,
) -> None:
    box = Sandbox().seed()
    asked: list[tuple[str, str]] = []

    def authorize(principal, module: str) -> bool:
        asked.append((principal.user, module))
        return True

    app = ui.create_app(
        box.arras,
        principal_for_request=lambda request: (
            box.principal(request.headers["x-user"]) if "x-user" in request.headers else None
        ),
        authorize_operator=operate.operators_in_groups("admins", "builders"),
        authorize_schema=authorize,
        base_path=BASE,
        public_origin="https://app.example",
        static_dir=static,
    )
    document = box.arras.session(box.people["alice"]).document("catalog").text
    before = box.arras.session(box.people["alice"]).document("catalog")
    candidate = json.loads(document)
    candidate["modules"][0]["actions"][0]["description"] = "Add a catalog use case"
    changed_document = json.dumps(candidate)
    status, _, body = call(
        app, "POST", f"{BASE}/api/schema/validate", body={"document": changed_document}
    )
    plan = json.loads(body)
    assert status == 200 and plan["ok"] and plan["changed"]
    status, _, body = call(
        app,
        "POST",
        f"{BASE}/api/schema/register",
        body={"document": changed_document, "expected_revision": plan["revision"]},
    )
    result = json.loads(body)
    assert status == 200 and result["changed"]
    assert asked == [("alice", "catalog"), ("alice", "catalog")]
    after = box.arras.session(box.people["alice"]).document("catalog")
    assert after.text != before.text and after.revision != before.revision


def test_composed_schema_callback_denial_and_error_are_scrubbed_and_do_not_mutate(
    static: Path,
) -> None:
    box = Sandbox().seed()
    before = box.arras.session(box.people["alice"]).document("catalog")
    candidate = json.loads(before.text)
    candidate["modules"][0]["actions"][0]["description"] = "Add a catalog use case"
    changed_document = json.dumps(candidate)
    app = ui.create_app(
        box.arras,
        principal_for_request=lambda request: (
            box.principal(request.headers["x-user"]) if "x-user" in request.headers else None
        ),
        authorize_operator=operate.operators_in_groups("admins", "builders"),
        authorize_schema=lambda _principal, _module: False,
        base_path=BASE,
        public_origin="https://app.example",
        static_dir=static,
    )
    for verb in ("validate", "register"):
        status, _, body = call(
            app, "POST", f"{BASE}/api/schema/{verb}", body={"document": changed_document}
        )
        assert status == 403
        assert b"secret" not in body
    after = box.arras.session(box.people["alice"]).document("catalog")
    assert (after.text, after.revision) == (before.text, before.revision)

    def broken(_principal, _module: str) -> bool:
        raise RuntimeError("private-group-service-detail")

    error_app = ui.create_app(
        box.arras,
        principal_for_request=lambda request: (
            box.principal(request.headers["x-user"]) if "x-user" in request.headers else None
        ),
        authorize_operator=operate.operators_in_groups("admins", "builders"),
        authorize_schema=broken,
        base_path=BASE,
        public_origin="https://app.example",
        static_dir=static,
    )
    for verb in ("validate", "register"):
        status, _, body = call(
            error_app, "POST", f"{BASE}/api/schema/{verb}", body={"document": changed_document}
        )
        assert status == 500 and b"internal error" in body
        assert b"private-group-service-detail" not in body
    after = box.arras.session(box.people["alice"]).document("catalog")
    assert (after.text, after.revision) == (before.text, before.revision)


def test_composed_schema_precedence_and_backend_grant_still_apply(static: Path) -> None:
    box = Sandbox().seed()
    asked: list[tuple[str, str]] = []

    def authorize(principal, module: str) -> bool:
        asked.append((principal.user, module))
        return True

    app = ui.create_app(
        box.arras,
        principal_for_request=lambda request: (
            box.principal(request.headers["x-user"]) if "x-user" in request.headers else None
        ),
        authorize_operator=operate.operators_in_groups("admins", "builders"),
        authorize_schema=authorize,
        base_path=BASE,
        public_origin="https://app.example",
        static_dir=static,
    )
    document = box.arras.session(box.people["alice"]).document("catalog").text
    assert (
        call(app, "POST", f"{BASE}/api/schema/validate", user=None, body={"document": document})[0]
        == 401
    )
    assert (
        call(app, "POST", f"{BASE}/api/schema/validate", user="carol", body={"document": document})[
            0
        ]
        == 403
    )
    assert call(app, "POST", f"{BASE}/api/schema/validate", body={"document": "{"})[0] == 400
    assert asked == []

    status, _, body = call(
        app,
        "POST",
        f"{BASE}/api/schema/validate",
        user="bob",
        body={"document": document},
    )
    assert status == 403 and b"no access" in body
    assert asked == [("bob", "catalog")]


def test_composed_schema_callback_survives_nonempty_root_path(static: Path) -> None:
    box = Sandbox().seed()
    seen: list[tuple[str, str]] = []
    app = ui.create_app(
        box.arras,
        principal_for_request=lambda request: (
            box.principal(request.headers["x-user"]) if "x-user" in request.headers else None
        ),
        authorize_operator=operate.operators_in_groups("admins", "builders"),
        authorize_schema=lambda principal, module: seen.append((principal.user, module)) or True,
        base_path=BASE,
        public_origin="https://app.example",
        static_dir=static,
    )
    document = box.arras.session(box.people["alice"]).document("catalog").text
    status, _, _ = call(
        app,
        "POST",
        f"/mount{BASE}/api/schema/validate",
        body={"document": document},
        root_path="/mount",
    )
    assert status == 200 and seen == [("alice", "catalog")]


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


class _BrandMetaParser(HTMLParser):
    """Count browser-visible metadata while treating raw-text element contents as text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.raw_text_tag: str | None = None
        self.brands: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.raw_text_tag is not None:
            return
        if tag.lower() == "meta":
            values = dict(attrs)
            if (values.get("name") or "").casefold() == "arras-brand":
                self.brands.append(values.get("content"))
        if tag.lower() in {
            "script",
            "style",
            "textarea",
            "title",
            "xmp",
            "iframe",
            "noembed",
            "noframes",
            "plaintext",
        }:
            self.raw_text_tag = tag.lower()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if self.raw_text_tag == tag.lower():
            self.raw_text_tag = None


def _brand_meta_values(page: bytes) -> list[str | None]:
    parser = _BrandMetaParser()
    parser.feed(page.decode())
    parser.close()
    return parser.brands


@pytest.mark.parametrize(
    "existing",
    [
        b"",
        b'<meta name="arras-brand" content="old">',
        b'<META content=old NAME=ARRAS-BRAND/><meta name="arras-brand" content="second">',
    ],
)
def test_branded_replaces_all_real_brand_metadata(existing: bytes) -> None:
    brand = ui.Brand(name='Café <Atlas> "Console"', tagline="x & y")
    page = (
        b"<!doctype html><head><title lang='en'>Old</title>"
        + existing
        + b"</head><body>kept</body>"
    )

    result = ui.branded(page, brand)

    values = _brand_meta_values(result)
    assert len(values) == 1 and values[0] is not None
    assert json.loads(values[0]) == {"name": 'Café <Atlas> "Console"', "tagline": "x & y"}
    assert b"<title lang='en'>Caf\xc3\xa9 &lt;Atlas&gt; &quot;Console&quot;</title>" in result
    assert result.index(b'<meta name="arras-brand"') < result.index(b"</head>")
    assert ui.branded(result, brand) == result


def test_branded_ignores_fake_tags_in_comments_and_raw_text() -> None:
    brand = ui.Brand(name="Atlas")
    fake_comment = b'<!-- <meta name="arras-brand" content="comment"></head> -->'
    fake_script = (
        b'<script>const fake = \'<meta name="arras-brand">\'; const close = "</head>";</script>'
    )
    fake_textarea = b"<textarea><meta name=arras-brand></textarea>"
    fake_title = b"<title data-x='kept'><meta name=arras-brand></title>"
    page = b"<head>" + fake_comment + fake_script + fake_textarea + fake_title + b"</head>"

    result = ui.branded(page, brand)

    assert fake_comment in result
    assert fake_script in result
    assert fake_textarea in result
    assert b"<title data-x='kept'>Atlas</title>" in result
    assert len(_brand_meta_values(result)) == 1
    assert result.index(b'<meta name="arras-brand"') < result.rindex(b"</head>")


def test_branded_fragment_fallback_is_token_aware_and_preserves_source() -> None:
    brand = ui.Brand(name="A&B")
    title_fragment = b'<title>Old</title><!-- </head> --><script>"</head>"</script>'
    result = ui.branded(title_fragment, brand)
    meta = b'<meta name="arras-brand" content="{&quot;name&quot;: &quot;A&amp;B&quot;}">'
    assert result.startswith(b"<title>A&amp;B</title>" + meta)
    assert b"<!-- </head> -->" in result and b'<script>"</head>"</script>' in result

    plain_fragment = b"text\r\n<!-- no head or title -->"
    appended = ui.branded(plain_fragment, brand)
    assert appended == plain_fragment

    branded_fragment = b'text\r\n<meta name="arras-brand" content="old">'
    assert ui.branded(branded_fragment, brand) == branded_fragment


def test_a_custom_brand_renders_its_title_and_escaped_json(static: Path) -> None:
    (static / ui.PAGE).write_text("<!doctype html><head><title>Arras</title></head>")
    refresh_page_manifest(static)
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
    refresh_page_manifest(static)
    assert b"rebuilt" in app.static("/")[2]
    same_size = page.read_text().replace("rebuilt", "REBUILT")  # a change that keeps the size
    stat = page.stat()
    page.write_text(same_size)
    os.utime(page, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    refresh_page_manifest(static)
    assert b"REBUILT" in app.static("/")[2]
    other = static.parent / "other-build"  # another directory is another page
    (other / "assets").mkdir(parents=True)
    (other / ui.PAGE).write_text("<!doctype html><title>Elsewhere</title>")
    app.static_dir = other
    assert app.static("/")[0] == 503  # validated manifest pins its own root


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


def test_distribution_brand_is_used_by_the_ui_and_explicit_brand_wins(static: Path) -> None:
    from arras.distribution import DistributionConfig

    configured = ui.Brand(name="Catalog Brand", tagline="from distribution")
    app = make(static, distribution=DistributionConfig(brand=configured))
    assert app.brand is configured
    assert b"Catalog Brand" in app.static("/")[2]
    override = ui.Brand(name="Explicit Brand")
    app = make(static, distribution=DistributionConfig(brand=configured), brand=override)
    assert app.brand is override
    assert b"Explicit Brand" in app.static("/")[2]
    assert ui.Brand is __import__("arras.branding", fromlist=["Brand"]).Brand


def _theme_sources(root: Path) -> dict[str, Path]:
    root.mkdir(exist_ok=True)
    sources = {
        "theme.css": b".arras-root{--arras-color-text:#111}",
        "mark.svg": b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
        "body.woff2": b"font-bytes",
    }
    for name, body in sources.items():
        (root / name).write_bytes(body)
    return {name: root / name for name in sources}


def test_the_public_theme_manifest_builder_is_served_by_create_app(
    static: Path, tmp_path: Path
) -> None:
    from arras.ui.assets import build_theme_manifest

    src = _theme_sources(tmp_path / "src")
    out = tmp_path / "bundle"
    manifest = build_theme_manifest(
        out,
        stylesheet=src["theme.css"],
        favicon=src["mark.svg"],
        fonts=[src["body.woff2"]],
        package_name="host-theme",
        package_version="3",
    )
    assert manifest == out / "theme-manifest.json"
    data = json.loads(manifest.read_text())
    assert data["package"] == {"name": "host-theme", "version": "3"}
    assert data["ui_versions"] == [UI_VERSION]
    assert data["entry"] == {
        "stylesheet": "theme.css",
        "fonts": ["body.woff2"],
        "favicon": "mark.svg",
    }
    assert {n: f["sha256"] for n, f in data["files"].items()} == {
        n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in src.items()
    }
    assert load_manifest(manifest, kind="theme").entry["stylesheet"] == "theme.css"
    app = ui.create_app(
        Sandbox().seed().arras,
        principal_for_request=lambda _request: None,
        base_path=BASE,
        static_dir=static,
        theme_manifest=manifest,
    )
    status, _, page = call(app, "GET", f"{BASE}/", user=None)
    assert status == 200 and b"theme-assets/" in page and b"theme.css" in page
    assert app.theme_manifest is not None
    digest = app.theme_manifest.manifest_sha256
    status, _, body = call(app, "GET", f"{BASE}/theme-assets/{digest}/body.woff2", user=None)
    assert status == 200 and body == b"font-bytes"


def test_the_theme_manifest_builder_refuses_what_create_app_would_and_leaves_no_manifest(
    tmp_path: Path,
) -> None:
    from arras.ui.assets import build_theme_manifest

    src = _theme_sources(tmp_path / "src")
    (tmp_path / "src" / "notes.txt").write_text("x")
    out = tmp_path / "bundle"
    with pytest.raises(ValueError, match="unsupported type"):
        build_theme_manifest(out, stylesheet=src["theme.css"], favicon=tmp_path / "src/notes.txt")
    with pytest.raises(ValueError, match="missing"):
        build_theme_manifest(out, stylesheet=tmp_path / "absent.css")
    with pytest.raises(ValueError, match="repeated"):
        build_theme_manifest(out, stylesheet=src["theme.css"], fonts=[src["theme.css"]])
    with pytest.raises(ValueError, match="stylesheet"):  # the entry must be CSS
        build_theme_manifest(out, stylesheet=src["body.woff2"])
    assert not (out / "theme-manifest.json").exists()


def test_theme_manifest_command_writes_a_bundle_the_loader_accepts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from arras.ui.__main__ import main

    src = _theme_sources(tmp_path / "src")
    out = tmp_path / "bundle"
    code = main(
        [
            "theme-manifest",
            "--css",
            str(src["theme.css"]),
            "--favicon",
            str(src["mark.svg"]),
            "--out",
            str(out),
            "--ui-version",
            "9.9.9",
        ]
    )
    assert code == 0 and capsys.readouterr().out.strip() == str(out / "theme-manifest.json")
    loaded = load_manifest(out / "theme-manifest.json", kind="theme")
    assert loaded.ui_versions == ("9.9.9",) and set(loaded.files) == {"theme.css", "mark.svg"}
    with pytest.raises(SystemExit) as refused:
        main(["theme-manifest", "--css", str(tmp_path / "none.css"), "--out", str(out)])
    assert refused.value.code == 2
