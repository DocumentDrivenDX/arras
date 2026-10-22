# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The interface as one mountable ASGI app: the built React UI and the surfaces it reads (ADR-027).

    app.mount("/ontology", arras.ui.create_app(arras, base_path="/ontology",
        principal_for_request=..., authorize_operator=operate.operators_in_groups("admins", "builders")))

A host mounts this one app instead of the console, operator and schema apps and the UI's files. It
serves, under `base_path`: the page (`/`), its assets (`/assets/`), UMF's schema browser
(`/umf-explorer/`) and the three surfaces the page calls (`/api/console`, `/api/operate`, and
`/api/schema` when `authorize_operator` is given: schema import is for operators). The UI ships in the
wheel, built from `ui/`, so its version is the library's.

The host authenticates and maps its identity to a `Principal` (`principal_for_request`, CONTRACT-006
and CONTRACT-009); the page sends the browser's own credentials to its own origin and stores none. The
page and assets are public files and carry no data: every read and write goes through a surface that
answers 401 to a viewer with no principal. They are served under a Content-Security-Policy
(`PAGE_CSP`, with `img-src` extended by `Brand.csp()` for an image wordmark); the host must not weaken it, and may not frame the page from another origin.

`brand=Brand(name="Atlas", title=..., wordmark=..., tagline=..., logo=...)` renames the console: the page's
`<title>` becomes `brand.title or brand.name` and a `<meta name="arras-brand">` tag carries the brand
as HTML-escaped JSON for the UI to read (the policy forbids inline scripts, so nothing else is
injected). A wordmark is text or an `https://` URL (its origin joins `img-src`, nothing else does); anything else is a `ValueError`. `logo="theme"` shows
the active theme's mark before the name (a wordmark takes precedence); any other value is a `ValueError`.
A field longer than its cap (`BRAND_CAPS`: name 80, title 120, wordmark 2048, tagline 200, counted as the
browser counts) is a `ValueError`, so the page never shows a field cut short. The default brand is
`Brand()`, "Arras".
"""

from __future__ import annotations

import hashlib
import html
import importlib.metadata
from collections.abc import Callable
from pathlib import Path

from arras import console, operate, telemetry
from arras.branding import BRAND_CAPS as BRAND_CAPS
from arras.branding import Brand
from arras.core import Arras
from arras.distribution import DistributionConfig
from arras.http import Receive, Request, Scope, Send
from arras.operate import schema_app
from arras.types import Principal
from arras.ui._brand_page import branded as branded
from arras.ui.assets import AssetManifest, load_manifest, read_verified

STATIC = Path(__file__).resolve().parent / "static"
NPM = Path(__file__).resolve().parent / "npm"
PAGE = "embed.html"
EXPLORER = "/umf-explorer"
# UMF's strict profile for its schema browser (its README, "Hosting and boundaries") plus
# `frame-ancestors 'self'`: nothing inline, no font or worker source, and images from the page's own
# origin only (the theme's mark is served from there). The browser runs in a `srcdoc` iframe, which
# inherits the page's policy, so this is the policy it runs under. A brand whose wordmark is an
# `https://` image adds that one origin to `img-src` (`page_csp`).
PAGE_CSP = (
    "default-src 'none'; base-uri 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "frame-src 'self' about:; connect-src 'self'; frame-ancestors 'self'"
)


def page_headers(csp: str = PAGE_CSP) -> tuple[tuple[bytes, bytes], ...]:
    return (
        (b"content-security-policy", csp.encode()),
        (b"x-frame-options", b"SAMEORIGIN"),
        (b"x-content-type-options", b"nosniff"),
        (b"referrer-policy", b"no-referrer"),
    )


PAGE_HEADERS = page_headers()
_TYPES = {  # not left to the platform's table, which differs (a .js as text/plain breaks nosniff)
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json",
}


def not_built_page(brand: Brand, hint: bytes) -> bytes:
    name = html.escape(brand.name).encode()
    return (
        b"<!doctype html><title>"
        + name
        + b"</title><p>The UI is not built ("
        + name
        + b"). "
        + hint
    )


_NOT_BUILT_HINT = (
    b"In a source checkout run <code>npm ci &amp;&amp; npm run build:embed</code> in "
    b"<code>ui/</code>; an installed wheel carries it.</p>"
)


def npm_package() -> Path:
    """The `@documentdrivendx/arras-ui` npm tarball this wheel carries, for a host that bundles the components into
    its own app: `npm install <path>` (or `python -m arras.ui npm-package`). Its version is this
    library's, so a host that pins the wheel pins the UI."""
    found = sorted(NPM.glob("documentdrivendx-arras-ui-*.tgz"))
    if not found:
        raise FileNotFoundError(
            "this build carries no npm tarball; in a source checkout run "
            "`npm run build:wheel` in ui/"
        )
    return found[-1]


class UI:
    def __init__(  # noqa: PLR0915
        self,
        arras: Arras,
        *,
        principal_for_request: Callable[[Request], Principal | None],
        authorize_operator: Callable[[Principal], bool] | None,
        authorize_schema: Callable[[Principal, str], bool] | None = None,
        authorize_action: Callable[[Principal, str, str], bool] | None,
        base_path: str,
        public_origin: str | None,
        allowed_origins: tuple[str, ...],
        static_dir: Path,
        asset_manifest: Path | None = None,
        theme_manifest: Path | None = None,
        brand: Brand | None = None,
        distribution: DistributionConfig | None = None,
        telemetry_context: telemetry.TelemetryContext | None = None,
    ) -> None:
        self.telemetry_context = telemetry._context_for(telemetry_context, distribution)
        self.brand = brand if brand is not None else (distribution or DistributionConfig()).brand
        title = self.brand.name
        self.base = base_path.rstrip("/")
        self.static_dir = static_dir
        self.asset_manifest_path = asset_manifest or (static_dir / "asset-manifest.json")
        self.asset_manifest: AssetManifest | None = None
        self.runtime_version: str | None = None
        manifest_exists = self.asset_manifest_path.is_file()
        page_exists = (static_dir / PAGE).is_file()
        if asset_manifest is not None and not manifest_exists:
            raise ValueError(f"invalid asset manifest {self.asset_manifest_path}: file is missing")
        if manifest_exists:
            if (
                asset_manifest is not None
                and static_dir != STATIC
                and static_dir != self.asset_manifest_path.parent
            ):
                raise ValueError("asset_manifest parent conflicts with nondefault static_dir")
            self.asset_manifest = load_manifest(self.asset_manifest_path, kind="page")
            expected_contracts = {"console": 2, "operate": 2, "schema": 1, "browser": 1}
            if dict(self.asset_manifest.contracts) != expected_contracts:
                raise ValueError(
                    f"invalid asset manifest {self.asset_manifest_path}: unsupported contracts"
                )
            try:
                runtime_version = importlib.metadata.version("arras")
            except importlib.metadata.PackageNotFoundError:
                runtime_version = self.asset_manifest.package["version"]
            self.runtime_version = runtime_version
            if self.asset_manifest.package["version"] != runtime_version:
                raise ValueError(
                    f"invalid asset manifest {self.asset_manifest_path}: package version does not match runtime"
                )
            schema = self.asset_manifest.schema_browser or {}
            if schema.get("name") != "@documentdrivendx/umf-schema-browser" or not str(
                schema.get("integrity", "")
            ).startswith("sha512-"):
                raise ValueError(
                    f"invalid asset manifest {self.asset_manifest_path}: schema_browser identity or integrity is invalid"
                )
            if self.asset_manifest.root != self.asset_manifest_path.parent.resolve():
                raise ValueError("asset manifest root is invalid")
            self.static_dir = self.asset_manifest.root
        elif page_exists:
            raise ValueError(
                f"invalid asset manifest {self.asset_manifest_path}: required for built page"
            )
        self.theme_manifest = (
            load_manifest(theme_manifest, kind="theme") if theme_manifest else None
        )
        self.theme_manifest_path = theme_manifest
        if self.theme_manifest and dict(self.theme_manifest.contracts) != {
            "console": 2,
            "operate": 2,
            "schema": 1,
            "browser": 1,
        }:
            raise ValueError(f"invalid asset manifest {theme_manifest}: unsupported contracts")
        if self.theme_manifest and self.asset_manifest:
            if (
                self.theme_manifest.ui_versions
                and self.asset_manifest.version
                and self.asset_manifest.package["version"] not in self.theme_manifest.ui_versions
            ):
                raise ValueError(
                    f"invalid asset manifest {theme_manifest}: ui_versions does not include {self.asset_manifest.package['version']}"
                )
        self._page: tuple[tuple[object, ...], bytes] | None = None  # the branded page and its key
        shared = {
            "principal_for_request": principal_for_request,
            "public_origin": public_origin,
            "allowed_origins": allowed_origins,
        }
        self.apis: dict[str, console.Console | operate.Operate | schema_app.SchemaApp] = {
            "/api/console": console.create_app(
                arras, base_path=f"{self.base}/api/console", title=title, **shared
            ),
            "/api/operate": operate.create_app(
                arras,
                base_path=f"{self.base}/api/operate",
                title=title,
                authorize_operator=authorize_operator,
                authorize_action=authorize_action,
                **shared,
            ),
        }
        if authorize_operator is not None:
            self.apis["/api/schema"] = operate.create_schema_app(
                arras,
                base_path=f"{self.base}/api/schema",
                authorize_operator=authorize_operator,
                authorize_schema=authorize_schema,
                **shared,
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        with self.telemetry_context.activate():
            await self._dispatch(scope, receive, send)

    async def _dispatch(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        root = scope.get("root_path") or ""
        path = scope["path"]
        if root and path.startswith(root):
            path = path[len(root) :] or "/"  # a host's mount keeps the prefix in the path
        if self.base and not (path == self.base or path.startswith(self.base + "/")):
            return await self._send(send, 404, "text/plain", b"not found")
        rel = path[len(self.base) :]
        if rel == "" and self.base:
            qs = scope.get("query_string", b"").decode()
            location = f"{root}{self.base}/" + (f"?{qs}" if qs else "")
            return await self._send(
                send, 308, "text/plain", b"", extra=((b"location", location.encode()),)
            )
        for prefix, app in self.apis.items():
            if rel == prefix or rel.startswith(prefix + "/"):
                return await app(scope, receive, send)
        if scope["method"] not in ("GET", "HEAD"):
            return await self._send(
                send, 405, "text/plain", b"GET only", extra=((b"allow", b"GET, HEAD"),)
            )
        if rel.startswith("/theme-assets/"):
            status, ctype, body, cache = self.theme_asset(rel)
            csp = self.brand.csp()
            if self.theme_manifest and self.theme_manifest.entry.get("fonts"):
                csp += "; font-src 'self'"
            return await self._send(
                send, status, ctype, body, page_headers(csp), ((b"cache-control", cache.encode()),)
            )
        status, ctype, body = self.static(rel or "/", root_path=root)
        csp = self.brand.csp()
        if self.theme_manifest and self.theme_manifest.entry.get("fonts"):
            csp += "; font-src 'self'"
        extra = ((b"cache-control", b"no-store"),) if rel in ("", "/") else ()
        await self._send(send, status, ctype, body, page_headers(csp), extra)

    def theme_asset(self, rel: str) -> tuple[int, str, bytes, str]:
        theme = self.theme_manifest
        if theme is None or self.theme_manifest_path is None:
            return 404, "text/plain", b"not found", "no-store"
        try:
            theme = load_manifest(self.theme_manifest_path, kind="theme")
            self._check_theme_cohort(theme)
            self.theme_manifest = theme
        except ValueError:
            return 503, "text/plain", b"theme manifest invalid", "no-store"
        prefix = f"/theme-assets/{theme.manifest_sha256}/"
        if not rel.startswith(prefix):
            return 404, "text/plain", b"not found", "no-store"
        name = rel[len(prefix) :]
        metadata = theme.files.get(name)
        if metadata is None:
            return 404, "text/plain", b"not found", "no-store"
        body = read_verified(theme, name)
        if body is None:
            return 503, "text/plain", b"theme asset changed after validation", "no-store"
        return 200, str(metadata["mime"]), body, "public, max-age=31536000, immutable"

    def static(self, rel: str, *, root_path: str = "") -> tuple[int, str, bytes]:
        """A file of the built UI: the page at `/`, `assets/` and the schema browser's files. Never
        a path outside the build, and no fallback page: the page's routes live in its fragment."""
        root = self.static_dir.resolve()
        if self.asset_manifest is None:
            return 503, "text/html; charset=utf-8", not_built_page(self.brand, _NOT_BUILT_HINT)
        # Revalidate the declared cohort and bytes at each response, so changed files are never
        # returned under stale digest metadata.
        try:
            current = load_manifest(self.asset_manifest_path, kind="page")
            self._check_page_cohort(current)
            self.asset_manifest = current
        except ValueError:
            return 503, "text/plain", b"asset manifest invalid"
        if root != self.asset_manifest.root:
            return 503, "text/plain", b"asset manifest root changed after validation"
        page_name = str(self.asset_manifest.entry["html"])
        if not (root / page_name).is_file():
            return 503, "text/html; charset=utf-8", not_built_page(self.brand, _NOT_BUILT_HINT)
        name = page_name if rel == "/" else rel.lstrip("/")
        target = (root / name).resolve()
        if name not in self.asset_manifest.files or target != (root / name).resolve():
            return 404, "text/plain", b"not found"
        if not target.is_file():
            return 404, "text/plain", b"not found"
        metadata = self.asset_manifest.files[name]
        body = read_verified(self.asset_manifest, name)
        if body is None:
            return 503, "text/plain", b"asset changed after validation"
        if name == self.asset_manifest.entry["html"]:
            body = self._branded_page(target, body)
            if self.theme_manifest:
                prefix = (
                    f"{root_path}{self.base}/theme-assets/{self.theme_manifest.manifest_sha256}/"
                )
                css = prefix + str(self.theme_manifest.entry["stylesheet"])
                link = f'<link rel="stylesheet" href="{html.escape(css, quote=True)}">'
                favicon = self.theme_manifest.entry.get("favicon")
                if favicon:
                    link += (
                        f'<link rel="icon" href="{html.escape(prefix + str(favicon), quote=True)}">'
                    )
                if b"</head>" in body:
                    body = body.replace(b"</head>", link.encode() + b"</head>", 1)
                else:
                    body = body.replace(b"</title>", b"</title>" + link.encode(), 1)
            return 200, "text/html; charset=utf-8", body
        ctype = str(metadata["mime"])
        if ctype.startswith("text/") or ctype == "application/json":
            ctype += "; charset=utf-8"
        return 200, ctype, body

    def _branded_page(self, page: Path, content: bytes) -> bytes:
        """Brand already-verified bytes, caching by their digest and selected Brand."""
        key = (page, hashlib.sha256(content).hexdigest(), self.brand)
        if self._page is None or self._page[0] != key:
            self._page = (key, branded(content, self.brand))
        return self._page[1]

    def _check_page_cohort(self, manifest: AssetManifest) -> None:
        if dict(manifest.contracts) != {"console": 2, "operate": 2, "schema": 1, "browser": 1}:
            raise ValueError("unsupported page contracts")
        if self.runtime_version and manifest.package["version"] != self.runtime_version:
            raise ValueError("page package version does not match runtime")
        schema = manifest.schema_browser or {}
        if schema.get("name") != "@documentdrivendx/umf-schema-browser" or not str(
            schema.get("integrity", "")
        ).startswith("sha512-"):
            raise ValueError("schema-browser metadata is incompatible")

    def _check_theme_cohort(self, manifest: AssetManifest) -> None:
        if dict(manifest.contracts) != {"console": 2, "operate": 2, "schema": 1, "browser": 1}:
            raise ValueError("unsupported theme contracts")
        if (
            self.asset_manifest
            and self.asset_manifest.package["version"] not in manifest.ui_versions
        ):
            raise ValueError("theme does not declare the active UI version")

    async def _send(
        self,
        send: Send,
        status: int,
        ctype: str,
        body: bytes,
        headers: tuple[tuple[bytes, bytes], ...] = (),
        extra: tuple[tuple[bytes, bytes], ...] = (),
    ) -> None:
        hs = [(b"content-type", ctype.encode()), (b"content-length", str(len(body)).encode())]
        await send(
            {"type": "http.response.start", "status": status, "headers": [*hs, *headers, *extra]}
        )
        await send({"type": "http.response.body", "body": body})


def create_app(
    arras: Arras,
    *,
    principal_for_request: Callable[[Request], Principal | None],
    authorize_operator: Callable[[Principal], bool] | None = None,
    authorize_schema: Callable[[Principal, str], bool] | None = None,
    authorize_action: Callable[[Principal, str, str], bool] | None = None,
    base_path: str = "",
    public_origin: str | None = None,
    allowed_origins: tuple[str, ...] = (),
    static_dir: Path = STATIC,
    asset_manifest: Path | None = None,
    theme_manifest: Path | None = None,
    brand: Brand | None = None,
    distribution: DistributionConfig | None = None,
    telemetry_context: telemetry.TelemetryContext | None = None,
) -> UI:
    """The ASGI application; mount it at `base_path`. `authorize_operator` is the host's decision
    that a principal is an operator (`operate.operators_in_groups("admins", "builders")`); without it
    every principal is one on the operator surface and schema import is not mounted."""
    return UI(
        arras,
        principal_for_request=principal_for_request,
        authorize_operator=authorize_operator,
        authorize_schema=authorize_schema,
        authorize_action=authorize_action,
        base_path=base_path,
        public_origin=public_origin,
        allowed_origins=allowed_origins,
        static_dir=static_dir,
        asset_manifest=asset_manifest,
        theme_manifest=theme_manifest,
        brand=brand,
        distribution=distribution,
        telemetry_context=telemetry_context,
    )
