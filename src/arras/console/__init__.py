# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The read-only console: an ASGI app serving GraphiQL and GraphQL over the interface (CONTRACT-006).

`create_app(arras, principal_for_request=...)` returns an ASGI application the host mounts. The
host authenticates the viewer and maps its identity to a `Principal`; Arras never does. Every
resolver reads through `arras.session(principal)`, so the backends decide what the viewer sees.

The page loads GraphiQL, React and their styles from `asset_base` at pinned versions. The host's
content-security policy must allow that origin for `script-src` and `style-src` (and the app's own
origin for `console.js`). Pass `integrity={"react": "sha384-…", …}` (keys `react`, `react-dom`,
`graphiql`, `css`) to add Subresource Integrity; with an `asset_base` of your own, allow that
origin instead.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html import escape
from typing import Any
from urllib.parse import parse_qsl

from graphql import (
    DocumentNode,
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    GraphQLError,
    GraphQLSchema,
    InlineFragmentNode,
    OperationDefinitionNode,
    SelectionSetNode,
    execute_sync,
    parse,
    validate,
)
from graphql.error import GraphQLSyntaxError

from arras.core import Arras
from arras.errors import ArrasError, Invalid, Refused, Unavailable
from arras.gqlschema import (
    RequestContext,
    build_meta_schema,
    build_module_schema,
    coded,
    gql_error,
)
from arras.http import Receive, Request, Response, Scope, Send, parse_origin, post_origin_ok
from arras.serialize import jsonable
from arras.types import Principal

log = logging.getLogger("arras.console")

MAX_DEPTH = 6
MAX_FIELDS = 50
# Introspection is exempt from the limits above (GraphiQL needs it) but has its own bound; the
# standard introspection query is depth 15 with about 220 selections.
MAX_INTROSPECTION_DEPTH = 20
MAX_INTROSPECTION_FIELDS = 500
MAX_BODY = 256 * 1024
MAX_TOKENS = 5000
MAX_CONCURRENT = 8
ASSET_BASE = "https://unpkg.com"
ASSET_VERSIONS = {"react": "18.3.1", "react-dom": "18.3.1", "graphiql": "3.7.1"}


@dataclass(frozen=True)
class Measure:
    depth: int
    fields: int
    intro_depth: int
    intro_fields: int


def measure_all(doc: DocumentNode, operation_name: str | None) -> Measure:
    """Depth and field selections of the operation, fragments expanded once each (linear in the
    document), with `__schema` and `__type` measured apart from everything else."""
    frags = {d.name.value: d for d in doc.definitions if isinstance(d, FragmentDefinitionNode)}
    ops = [d for d in doc.definitions if isinstance(d, OperationDefinitionNode)]
    op = next(
        (o for o in ops if operation_name is None or (o.name and o.name.value == operation_name)),
        None,
    )
    if op is None:
        return Measure(0, 0, 0, 0)
    memo: dict[tuple[str, bool], tuple[int, int, int, int]] = {}
    active: set[str] = set()

    def spread(name: str, intro: bool) -> tuple[int, int, int, int]:
        key = (name, intro)
        if key in memo:
            return memo[key]
        if name in active or name not in frags:
            return (0, 0, 0, 0)  # a cycle or a missing fragment is validation's to report
        active.add(name)
        try:
            memo[key] = walk(frags[name].selection_set, intro)
        finally:
            active.discard(name)
        return memo[key]

    def walk(sel: SelectionSetNode, intro: bool) -> tuple[int, int, int, int]:
        """(depth, fields, introspection depth, introspection fields), relative to `sel`."""
        d = c = idepth = icount = 0
        for s in sel.selections:
            if isinstance(s, FieldNode):
                name = s.name.value
                sub = walk(s.selection_set, intro) if s.selection_set else (0, 0, 0, 0)
                if name == "__typename":
                    continue  # one scalar, no amplification
                if name in ("__schema", "__type") and not intro:
                    sub = walk(s.selection_set, True) if s.selection_set else (0, 0, 0, 0)
                    idepth = max(idepth, 1 + sub[0], sub[2])
                    icount += 1 + sub[1] + sub[3]
                    continue
                d = max(d, 1 + sub[0])
                c += 1 + sub[1]
                idepth, icount = max(idepth, sub[2]), icount + sub[3]
            elif isinstance(s, InlineFragmentNode):
                sd, sc, si, sn = walk(s.selection_set, intro)
                d, c, idepth, icount = max(d, sd), c + sc, max(idepth, si), icount + sn
            elif isinstance(s, FragmentSpreadNode):
                sd, sc, si, sn = spread(s.name.value, intro)
                d, c, idepth, icount = max(d, sd), c + sc, max(idepth, si), icount + sn
        return d, c, idepth, icount

    return Measure(*walk(op.selection_set, False))


def measure(doc: DocumentNode, operation_name: str | None) -> tuple[int, int]:
    """(depth, field selections) of the operation, introspection aside."""
    m = measure_all(doc, operation_name)
    return m.depth, m.fields


class Console:
    def __init__(
        self,
        arras: Arras,
        principal_for_request: Callable[[Request], Principal | None],
        base_path: str = "",
        asset_base: str = ASSET_BASE,
        integrity: Mapping[str, str] | None = None,
        public_origin: str | None = None,
        allowed_origins: tuple[str, ...] = (),
        title: str = "Arras",
    ) -> None:
        self.title = title
        self.origins = {
            p
            for o in ((public_origin,) if public_origin else ()) + allowed_origins
            if (p := parse_origin(o))
        }
        self.h = arras
        self.principal_for_request = principal_for_request
        self.base = base_path.rstrip("/")
        self.asset_base = asset_base.rstrip("/")
        self.integrity = dict(integrity or {})
        self.meta = build_meta_schema()
        # A bounded pool of its own, so a console cannot starve the host's default executor.
        self.pool = ThreadPoolExecutor(MAX_CONCURRENT, thread_name_prefix="arras-console")
        self.busy = 0

    # -- ASGI
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        try:
            status, headers, body = await self.handle(scope, receive)
        except Exception as e:  # never a traceback to the viewer, never silent to the operator
            log.error("console request failed: %s", type(e).__name__)  # no text, no traceback
            status, headers, body = self.err(500, "INTERNAL_ERROR", "internal error")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(k.encode(), v.encode()) for k, v in headers],
            }
        )
        await send({"type": "http.response.body", "body": body})

    def json(
        self, status: int, payload: Any, extra: list[tuple[str, str]] | None = None
    ) -> Response:
        body = json.dumps(payload, allow_nan=False).encode()
        headers = [("content-type", "application/json"), ("cache-control", "no-store")]
        return status, headers + (extra or []), body

    def err(
        self, status: int, code: str, message: str, extra: list[tuple[str, str]] | None = None
    ) -> Response:
        return self.json(
            status, {"errors": [{"message": message, "extensions": {"code": code}}]}, extra
        )

    def text(self, status: int, ctype: str, body: str) -> Response:
        headers = [
            ("content-type", ctype),
            ("cache-control", "no-store"),
            ("x-content-type-options", "nosniff"),
        ]
        return status, headers, body.encode()

    async def handle(self, scope: Scope, receive: Receive) -> Response:
        method, raw_path = scope["method"], scope["path"]
        root = scope.get("root_path") or ""
        if root and raw_path.startswith(root):
            raw_path = raw_path[len(root) :] or "/"  # a host's mount keeps the prefix in the path
        if self.base and not (raw_path == self.base or raw_path.startswith(self.base + "/")):
            return self.err(404, "NOT_FOUND", "not found")
        if self.base and raw_path == self.base:
            qs = scope.get("query_string", b"").decode()
            return 308, [("location", f"{root}{self.base}/" + (f"?{qs}" if qs else ""))], b""
        path = raw_path[len(self.base) :] or "/"
        headers: dict[str, str] = {}
        repeated: set[str] = set()
        for k, v in scope.get("headers", []):
            name = k.decode("latin-1").lower()
            val = v.decode("latin-1")
            if name in headers:
                repeated.add(name)
            headers[name] = f"{headers[name]}, {val}" if name in headers else val
        query = dict(parse_qsl(scope.get("query_string", b"").decode(errors="replace")))
        request = Request(method, path, headers, query, scope)
        if method == "POST" and not post_origin_ok(
            headers, repeated, self.origins, browser_or_host=True
        ):
            return self.err(403, "REFUSED", "cross-origin requests are not accepted")
        if path == "/console.js" and method == "GET":
            return self.text(200, "text/javascript; charset=utf-8", _JS)
        if path == "/" and method == "GET":
            return self.page()
        if path == "/graphql" or path.startswith("/graphql/"):
            if method != "POST":
                return self.err(405, "BAD_QUERY", "POST only", [("allow", "POST")])
            principal = self.principal_for_request(request)
            if principal is None:
                return self.err(401, "REFUSED", "sign in")
            module = path.removeprefix("/graphql/") if path != "/graphql" else None
            if module is not None and (not module or "/" in module):
                return self.err(404, "NOT_FOUND", "no such module")
            return await self.graphql(request, receive, principal, module)
        return self.err(404, "NOT_FOUND", "not found")

    def page(self) -> Response:
        v, base = ASSET_VERSIONS, self.asset_base

        def attrs(name: str) -> str:
            sri = self.integrity.get(name)
            return f' integrity="{sri}" crossorigin="anonymous"' if sri else ""

        html = _PAGE.format(
            react=f"{base}/react@{v['react']}/umd/react.production.min.js",
            react_dom=f"{base}/react-dom@{v['react-dom']}/umd/react-dom.production.min.js",
            graphiql=f"{base}/graphiql@{v['graphiql']}/graphiql.min.js",
            css=f"{base}/graphiql@{v['graphiql']}/graphiql.min.css",
            a_react=attrs("react"),
            a_react_dom=attrs("react-dom"),
            a_graphiql=attrs("graphiql"),
            a_css=attrs("css"),
            origin=base,
            title=escape(self.title),
        )
        return self.text(200, "text/html; charset=utf-8", html)

    async def body(self, receive: Receive) -> bytes:
        chunks: list[bytes] = []
        size = 0
        while True:
            msg = await receive()
            if msg.get("type") == "http.disconnect":
                raise _Bad(400, "client disconnected")
            chunk = msg.get("body", b"")
            size += len(chunk)
            if size > MAX_BODY:
                raise _Bad(413, "body too large")
            chunks.append(chunk)
            if not msg.get("more_body"):
                return b"".join(chunks)

    async def graphql(
        self, request: Request, receive: Receive, principal: Principal, module: str | None
    ) -> Response:
        try:
            if not request.headers.get("content-type", "").startswith("application/json"):
                raise _Bad(400, "send application/json")  # so another site needs a preflight
            payload = json.loads(await self.body(receive) or b"{}", parse_constant=_refuse)
            if not isinstance(payload, dict) or not isinstance(payload.get("query"), str):
                raise _Bad(400, "a request is a JSON object with a query")
            variables, op_name = payload.get("variables"), payload.get("operationName")
            if variables is not None and not isinstance(variables, dict):
                raise _Bad(400, "variables is an object")
            if op_name is not None and not isinstance(op_name, str):
                raise _Bad(400, "operationName is a string")
        except _Bad as e:
            return self.err(e.status, "BAD_QUERY", e.message)
        except (ValueError, RecursionError):
            return self.err(400, "BAD_QUERY", "body is not JSON")
        if self.busy >= MAX_CONCURRENT:
            return self.err(503, "UNAVAILABLE", "the console is busy")
        self.busy += 1
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                self.pool, self.execute, principal, module, payload["query"], variables, op_name
            )
        finally:
            self.busy -= 1

    # -- execution, in a worker thread (resolvers are synchronous)
    def execute(
        self,
        principal: Principal,
        module: str | None,
        query: str,
        variables: Any,
        op_name: str | None,
    ) -> Response:
        try:
            return self._execute(principal, module, query, variables, op_name)
        except Exception as e:
            log.error("console execution failed: %s", type(e).__name__)
            return self.err(200, "INTERNAL_ERROR", "internal error")

    def _execute(
        self,
        principal: Principal,
        module: str | None,
        query: str,
        variables: Any,
        op_name: str | None,
    ) -> Response:
        ontology = self.h.session(principal)
        ctx = RequestContext(ontology)
        try:
            if module is None:
                if self.all_down():
                    return self.err(503, "UNAVAILABLE", "no backend is available")
                schema: GraphQLSchema = self.meta
            else:
                mods = ontology.describe(module)  # unknown or unreadable is a 404 before any query
                ctx.module = mods[0]
                ctx.revision = jsonable(mods[0].revision, tag=False)
                schema = build_module_schema(mods[0])
        except Refused as e:
            if e.reason == "token_expired":
                return self.expired()  # sign in again is not "no such module"
            return self.err(404, "NOT_FOUND", "no such module")  # unreadable is unknown
        except Invalid:
            return self.err(404, "NOT_FOUND", "no such module")
        except Unavailable:
            return self.err(503, "UNAVAILABLE", "no backend is available")
        except ArrasError as e:
            return self.json(200, {"errors": [self.fmt(gql_error(e))]})
        try:
            doc = parse(query, max_tokens=MAX_TOKENS)
            m = measure_all(doc, op_name)
        except GraphQLSyntaxError as e:
            return self.err(400, "BAD_QUERY", e.message)
        except RecursionError:
            return self.err(400, "BAD_QUERY", "the query is nested too deeply")
        if m.depth > MAX_DEPTH:
            return self.reply(
                None, [coded("DEPTH_EXCEEDED", f"queries are at most {MAX_DEPTH} deep")], ctx
            )
        if m.fields > MAX_FIELDS:
            return self.reply(
                None, [coded("COST_EXCEEDED", f"queries select at most {MAX_FIELDS} fields")], ctx
            )
        if m.intro_depth > MAX_INTROSPECTION_DEPTH or m.intro_fields > MAX_INTROSPECTION_FIELDS:
            return self.reply(
                None, [coded("COST_EXCEEDED", "that introspection query is too large")], ctx
            )
        problems = validate(schema, doc)
        if problems:
            return self.reply(None, [coded("BAD_QUERY", p.message) for p in problems], ctx)
        ctx_obj = _Context(ctx, self.h)
        result = execute_sync(
            schema, doc, context_value=ctx_obj, variable_values=variables, operation_name=op_name
        )
        return self.reply(result.data, result.errors or [], ctx)

    def all_down(self) -> bool:
        s = self.h.status()
        return bool(s) and not any(x.available for x in s.values())

    @staticmethod
    def fmt(e: GraphQLError) -> dict[str, Any]:
        out: dict[str, Any] = {"message": e.message, "extensions": dict(e.extensions or {})}
        out["extensions"].setdefault("code", "BAD_QUERY")
        if e.path:
            out["path"] = list(e.path)
        if e.locations:
            out["locations"] = [{"line": loc.line, "column": loc.column} for loc in e.locations]
        return out

    def expired(self) -> Response:
        """An expired token is a 401 on either path, whichever resolver met it (CONTRACT-006)."""
        body = {
            "message": "sign in again",
            "extensions": {"code": "REFUSED", "reason": "token_expired"},
        }
        return self.json(401, {"errors": [body]})

    def reply(self, data: Any, errors: list[GraphQLError], ctx: RequestContext) -> Response:
        if any(_expired(e.original_error) for e in errors):
            return self.expired()
        errs = []
        for e in errors:
            inner = e.original_error
            if inner is not None and not isinstance(inner, GraphQLError):
                if isinstance(inner, ArrasError):
                    e = gql_error(inner)
                else:
                    log.error("resolver failed: %s", type(inner).__name__)
                    e = coded("INTERNAL_ERROR", "internal error")
            errs.append(self.fmt(e))
        body: dict[str, Any] = {"data": data}
        if errs:
            body["errors"] = errs
        body["extensions"] = {"revision": ctx.revision} if ctx.module is not None else {}
        return self.json(200, jsonable(body, tag=False))


@dataclass
class _Context:
    """The resolvers' context: the request's state, and the host's `Arras` for `status`."""

    request: RequestContext
    arras: Arras

    @property
    def ontology(self):
        return self.request.ontology

    def reserve(self, n: int) -> None:
        self.request.reserve(n)

    def settle(self, reserved: int, actual: int) -> None:
        self.request.settle(reserved, actual)

    @property
    def module(self):
        return self.request.module


def _expired(e: BaseException | None) -> bool:
    """A resolver's error, or the interface error under it, says the token has expired."""
    while e is not None:
        if isinstance(e, Refused):
            return e.reason == "token_expired"
        e = e.__cause__ if isinstance(e, GraphQLError) else None
    return False


class _Bad(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status, self.message = status, message


def _refuse(c: str) -> Any:
    raise ValueError(c)


def create_app(
    arras: Arras,
    *,
    principal_for_request: Callable[[Request], Principal | None],
    base_path: str = "",
    asset_base: str = ASSET_BASE,
    integrity: Mapping[str, str] | None = None,
    public_origin: str | None = None,
    allowed_origins: tuple[str, ...] = (),
    title: str = "Arras",
) -> Console:
    """The ASGI application; mount it at `base_path`. A POST from a browser must come from the
    host's own origin: `public_origin` and `allowed_origins` when given (behind a proxy that
    rewrites `Host`), otherwise the `Host` it asked. `title` names the product in the page's title."""
    return Console(
        arras,
        principal_for_request,
        base_path,
        asset_base,
        integrity,
        public_origin,
        allowed_origins,
        title,
    )


_PAGE = """<!doctype html>
<!-- Loads scripts and styles from {origin} (script-src, style-src); console.js is this app's own. -->
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} console</title>
<link rel="stylesheet" href="{css}"{a_css}>
<style>html,body,#root{{height:100%;margin:0}}</style></head>
<body><div id="root">Loading…</div>
<script src="{react}"{a_react}></script><script src="{react_dom}"{a_react_dom}></script><script src="{graphiql}"{a_graphiql}></script>
<script src="console.js"></script></body></html>
"""

_JS = """// Addresses the GraphQL endpoints relative to this page, so any path prefix or proxy works.
(function () {
  const module = new URLSearchParams(location.search).get("module");
  const url = new URL(module ? "graphql/" + encodeURIComponent(module) : "graphql", location.href.split("?")[0]).href;
  const fetcher = (params) => fetch(url, {
    method: "POST", headers: {"content-type": "application/json"}, credentials: "same-origin",
    body: JSON.stringify(params),
  }).then((r) => r.json());
  ReactDOM.createRoot(document.getElementById("root")).render(React.createElement(GraphiQL, {fetcher}));
})();
"""
