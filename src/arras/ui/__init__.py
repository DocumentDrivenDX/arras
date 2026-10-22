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

import html
import json
import mimetypes
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from arras import console, operate
from arras.core import Arras
from arras.http import Receive, Request, Scope, Send
from arras.operate import schema_app
from arras.types import Principal

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
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:\S")
_IMAGE_URL = re.compile(r"^https://[^\s;,'\"]+$")
_TITLE = re.compile(r"<title>.*?</title>", re.IGNORECASE | re.DOTALL)


# The most characters each field may hold: the UI reads the same caps from the page's meta tag
# (`ui/src/lib/brand.tsx`), and `tests/vectors/brand.json` holds both sides to them.
BRAND_CAPS = {"name": 80, "title": 120, "wordmark": 2048, "tagline": 200}


def _length(text: str) -> int:
    """UTF-16 code units of the trimmed text, which is how the browser counts."""
    return len(text.strip().encode("utf-16-le")) // 2


@dataclass(frozen=True)
class Brand:
    """What the console is called. `title` is the page title (default `name`); `wordmark` is text or an
    `https://` URL; `tagline` is a line under the name;
    `logo` is `"theme"` to show the theme's mark before the name."""

    name: str = "Arras"
    title: str | None = None
    wordmark: str | None = None
    tagline: str | None = None
    logo: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("a brand needs a name")
        for field_name, cap in BRAND_CAPS.items():
            value = getattr(self, field_name)
            if value is not None and _length(value) > cap:
                raise ValueError(f"a brand's {field_name} is at most {cap} characters")
        w = self.wordmark
        if w is not None and _SCHEME.match(w) and not w.startswith("https://"):
            raise ValueError("a wordmark is text or an https:// URL")
        if (
            w is not None
            and w.startswith("https://")
            and not (_IMAGE_URL.match(w) and self.image_origin)
        ):
            raise ValueError("a wordmark is text or an https:// URL")
        if self.logo is not None and self.logo != "theme":
            raise ValueError('a logo is "theme"')

    @property
    def image_origin(self) -> str | None:
        """The origin of an `https://` image wordmark, else None (text, or no wordmark)."""
        w = self.wordmark
        if w is None or not w.startswith("https://"):
            return None
        try:
            parts = urlsplit(w)
            host = parts.hostname
            port = parts.port
        except ValueError:
            return None
        if not host or host == "*" or parts.username is not None or parts.password is not None:
            return None
        if parts.netloc.endswith(":"):  # an empty port
            return None
        shown = f"[{host}]" if ":" in host else host
        return f"https://{shown}" if port is None else f"https://{shown}:{port}"

    def csp(self) -> str:
        """`PAGE_CSP`, with the origin of an image wordmark admitted to `img-src`."""
        origin = self.image_origin
        return (
            PAGE_CSP
            if origin is None
            else PAGE_CSP.replace("img-src 'self'", f"img-src 'self' {origin}")
        )

    def meta(self) -> str:
        """The brand as JSON, the fields that are set."""
        fields = {
            "name": self.name,
            "title": self.title,
            "wordmark": self.wordmark,
            "tagline": self.tagline,
            "logo": self.logo,
        }
        return json.dumps({k: v for k, v in fields.items() if v is not None})


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


def branded(page: bytes, brand: Brand) -> bytes:
    """The built page with its title and the brand's meta tag."""
    text = page.decode()
    title = html.escape(brand.title or brand.name, quote=True)
    meta = f'<meta name="arras-brand" content="{html.escape(brand.meta(), quote=True)}">'
    text = _TITLE.sub(lambda _: f"<title>{title}</title>", text, count=1)
    if "</head>" in text:
        text = text.replace("</head>", meta + "</head>", 1)
    else:
        text = text.replace("</title>", "</title>" + meta, 1)
    return text.encode()


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
    def __init__(
        self,
        arras: Arras,
        *,
        principal_for_request: Callable[[Request], Principal | None],
        authorize_operator: Callable[[Principal], bool] | None,
        authorize_action: Callable[[Principal, str, str], bool] | None,
        base_path: str,
        public_origin: str | None,
        allowed_origins: tuple[str, ...],
        static_dir: Path,
        brand: Brand | None = None,
    ) -> None:
        self.brand = brand or Brand()
        title = self.brand.name
        self.base = base_path.rstrip("/")
        self.static_dir = static_dir
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
                **shared,
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
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
        status, ctype, body = self.static(rel or "/")
        await self._send(send, status, ctype, body, page_headers(self.brand.csp()))

    def static(self, rel: str) -> tuple[int, str, bytes]:
        """A file of the built UI: the page at `/`, `assets/` and the schema browser's files. Never
        a path outside the build, and no fallback page: the page's routes live in its fragment."""
        root = self.static_dir.resolve()
        if not (root / PAGE).is_file():
            return 503, "text/html; charset=utf-8", not_built_page(self.brand, _NOT_BUILT_HINT)
        name = PAGE if rel == "/" else rel.lstrip("/")
        target = (root / name).resolve()
        served = (root / "assets", root / EXPLORER.lstrip("/"))
        if target != root / PAGE and not any(d in target.parents for d in served):
            return 404, "text/plain", b"not found"  # also what `assets/../x` resolves to
        if not target.is_file():
            return 404, "text/plain", b"not found"
        ctype = _TYPES.get(target.suffix) or mimetypes.guess_type(target.name)[0]
        body = self._branded_page(target) if target == root / PAGE else target.read_bytes()
        return 200, ctype or "application/octet-stream", body

    def _branded_page(self, page: Path) -> bytes:
        """The page re-branded, kept until the file or the brand changes: the key is where the
        page is (so the static directory), what the file is now (its size and modification) and
        the brand."""
        st = page.stat()
        key = (page, st.st_mtime_ns, st.st_size, st.st_ino, self.brand)
        if self._page is None or self._page[0] != key:
            self._page = (key, branded(page.read_bytes(), self.brand))
        return self._page[1]

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
    authorize_action: Callable[[Principal, str, str], bool] | None = None,
    base_path: str = "",
    public_origin: str | None = None,
    allowed_origins: tuple[str, ...] = (),
    static_dir: Path = STATIC,
    brand: Brand | None = None,
) -> UI:
    """The ASGI application; mount it at `base_path`. `authorize_operator` is the host's decision
    that a principal is an operator (`operate.operators_in_groups("admins", "builders")`); without it
    every principal is one on the operator surface and schema import is not mounted."""
    return UI(
        arras,
        principal_for_request=principal_for_request,
        authorize_operator=authorize_operator,
        authorize_action=authorize_action,
        base_path=base_path,
        public_origin=public_origin,
        allowed_origins=allowed_origins,
        static_dir=static_dir,
        brand=brand,
    )
