# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""What the operator surface and the schema surface share: the ASGI shell, the origin and CORS
rules, the body reader, the per-person and global concurrency gate and the error body
(CONTRACT-009, CONTRACT-011). A surface subclasses `WireApp` and supplies `_route` and `execute`."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from arras.core import Arras
from arras.errors import (
    ArrasError,
    Conflict,
    Invalid,
    NotYetCurrent,
    PreconditionFailed,
    Refused,
    Unavailable,
    Unsupported,
)
from arras.http import (
    Receive,
    Request,
    Response,
    Scope,
    Send,
    origin_in,
    parse_origin,
    post_origin_ok,
)
from arras.serialize import error_body
from arras.types import Principal

log = logging.getLogger("arras.operate")

MAX_WORKERS = 8
NOT_OPERATOR = {"error": "REFUSED", "reason": "not_operator"}  # CONTRACT-010 (the Graph Browser's)
_NOT_FOUND = {"unknown_action", "unknown_type"}  # how the library says a name is not there


class _Bad(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status, self.message = status, message


def status_of(e: ArrasError) -> int:
    if isinstance(e, Invalid):
        return 404 if any(v.code in _NOT_FOUND for v in e.violations) else 400
    if isinstance(e, Refused):
        return 401 if e.reason == "token_expired" else 403
    if isinstance(e, PreconditionFailed):
        return 422
    if isinstance(e, Conflict | NotYetCurrent):
        return 409
    if isinstance(e, Unsupported):
        return 501
    if isinstance(e, Unavailable):
        return 503
    return 500


def _untag(v: Any) -> Any:
    """`error_body` tags nested records with their type; the wire shape of a violation is the same
    in an error as in a `Validation`, so the tag is dropped."""
    if isinstance(v, dict):
        return {k: _untag(x) for k, x in v.items() if k != "_type"}  # type: ignore[reportUnknownVariableType]
    if isinstance(v, list):
        return [_untag(x) for x in v]  # type: ignore[reportUnknownVariableType]
    return v


def error_json(e: ArrasError) -> dict[str, Any]:
    """The error body without a backend's `detail` or notes, which may echo an input; the message
    is rebuilt from the type and reason alone."""
    body = _untag(error_body(e))
    for k in ("detail", "notes"):
        body.pop(k, None)
    if isinstance(e, Conflict):
        body["message"] = f"conflict ({e.reason})"
    elif isinstance(e, Unavailable):
        body["message"] = f"{e.backend} is unavailable ({e.reason})"
    elif isinstance(e, Refused):
        body["message"] = "sign in again" if e.reason == "token_expired" else "no access"
    else:
        body["message"] = {
            "Invalid": "invalid request",
            "PreconditionFailed": "a precondition failed",
            "NotYetCurrent": "the replica has not reached that position",
            "Unsupported": "not supported",
        }.get(type(e).__name__, "request failed")
    return {"error": body}


def answer_error(e: ArrasError) -> Response:
    """A library error as the surface answers it: logged by type, never by its detail."""
    if not isinstance(
        e,
        Invalid
        | Refused
        | PreconditionFailed
        | Conflict
        | Unsupported
        | Unavailable
        | NotYetCurrent,
    ):
        log.error("operate: library fault", exc_info=e)
    log.info("operate refused: %s", type(e).__name__)
    log.debug("operate refused detail: %s", getattr(e, "detail", ""))
    return WireApp.json(status_of(e), error_json(e))


class WireApp:
    """The ASGI application's shell. The limits are parameters because the two surfaces differ."""

    def __init__(
        self,
        arras: Arras,
        principal_for_request: Callable[[Request], Principal | None],
        public_origin: str | None,
        allowed_origins: tuple[str, ...],
        base_path: str,
        *,
        max_body: int,
        max_per_principal: int,
        max_in_flight: int,
        authorize_operator: Callable[[Principal], bool] | None = None,
    ) -> None:
        self.h = arras
        self.principal_for_request = principal_for_request
        self.authorize_operator = authorize_operator
        if authorize_operator is None:
            log.warning(
                "%s: no authorize_operator, so every principal is an operator "
                "(CONTRACT-010); a host that serves people who are not operators must pass it",
                type(self).__name__,
            )
        # scheme, host and port, with the default port and case normalized (as the console does)
        self.origins = {
            p
            for o in ((public_origin,) if public_origin else ()) + tuple(allowed_origins)
            if (p := parse_origin(o.rstrip("/")))
        }
        self.base = base_path.rstrip("/")
        self.max_body = max_body
        self.max_per_principal = max_per_principal
        self.max_in_flight = max_in_flight
        self.pool = ThreadPoolExecutor(MAX_WORKERS, thread_name_prefix="arras-operate")
        self.inflight: dict[str, int] = {}

    # -- ASGI
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        try:
            status, headers, body = await self.handle(scope, receive)
        except Exception:  # never a traceback to the viewer, never silent to the operator
            log.exception("operate request failed")
            status, headers, body = self.json(
                500, {"error": {"type": "InternalError", "message": "internal error"}}
            )
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(k.encode(), v.encode()) for k, v in headers],
            }
        )
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    def json(status: int, payload: Any, extra: list[tuple[str, str]] | None = None) -> Response:
        body = json.dumps(payload, allow_nan=False).encode()
        headers = [("content-type", "application/json"), ("cache-control", "no-store")]
        return status, headers + (extra or []), body

    def _origin_ok(self, origin: str | None) -> bool:
        return origin_in(origin, self.origins)

    def _post_allowed(self, headers: Mapping[str, str], repeated: set[str]) -> bool:
        """CONTRACT-009: an `Origin` that is `public_origin` or in `allowed_origins`, or the
        browser's own word that the request is same-origin (`Sec-Fetch-Site: same-origin`). With
        that word an `Origin`, if sent, need not be listed (a host may leave `public_origin`
        unset), but it must be one well-formed origin. A repeated `Origin` or `Sec-Fetch-Site`
        is refused, never read as its first or last value."""
        return post_origin_ok(headers, repeated, self.origins)

    def _cors(self, origin: str | None) -> list[tuple[str, str]]:
        if not self._origin_ok(origin):
            return []
        assert origin is not None
        return [
            ("access-control-allow-origin", origin),
            ("access-control-allow-credentials", "true"),
            ("vary", "Origin"),
        ]

    async def handle(self, scope: Scope, receive: Receive) -> Response:
        method, path = scope["method"], scope["path"]
        root = scope.get("root_path") or ""
        if root and path.startswith(root):
            path = path[len(root) :] or "/"
        if self.base:
            if not (path == self.base or path.startswith(self.base + "/")):
                return self.json(404, {"error": {"type": "NotFound", "message": "not found"}})
            path = path[len(self.base) :] or "/"
        headers: dict[str, str] = {}
        repeated: set[str] = set()
        for k, v in scope.get("headers", []):
            name = k.decode("latin-1").lower()
            val = v.decode("latin-1")
            if name in headers:
                repeated.add(name)
            headers[name] = f"{headers[name]}, {val}" if name in headers else val
        origin = None if "origin" in repeated else headers.get("origin")
        cors = self._cors(origin)
        if method == "OPTIONS":
            if not cors:
                return self.json(
                    403, {"error": {"type": "Forbidden", "message": "origin not allowed"}}
                )
            return (
                204,
                [
                    *cors,
                    ("access-control-allow-methods", "POST, GET"),
                    ("access-control-allow-headers", "content-type"),
                    ("access-control-max-age", "600"),
                    ("cache-control", "no-store"),
                ],
                b"",
            )
        status, hdrs, body = await self._route(method, path, headers, scope, receive, repeated)
        return status, [*hdrs, *cors], body

    async def _route(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        scope: Scope,
        receive: Receive,
        repeated: set[str],
    ) -> Response:
        raise NotImplementedError

    def execute(
        self, principal: Principal, target: tuple[str, ...], body: dict[str, Any]
    ) -> Response:
        raise NotImplementedError

    async def _as_viewer(
        self, request: Request, target: tuple[str, ...], receive: Receive | None = None
    ) -> Response:
        """Resolve the viewer, refuse a non-operator, read the body (a POST's), and run the work
        in the pool under the per-person and global caps."""
        loop = asyncio.get_running_loop()
        principal = await loop.run_in_executor(None, self.principal_for_request, request)
        if principal is None:
            return self.json(401, {"error": {"type": "Refused", "message": "sign in"}})
        operator = await self._operator(principal)
        if operator is None:
            return self.busy()
        if not operator:
            return self.json(403, NOT_OPERATOR)  # before any other work
        body: dict[str, Any] = {}
        if receive is not None:
            try:
                body = await self._body(request.headers, receive)
            except _Bad as e:
                return self.json(e.status, {"error": {"type": "BadRequest", "message": e.message}})
        if not self._admit(principal.user):
            return self.busy()
        work = loop.run_in_executor(self.pool, self.execute, principal, target, body)
        # when the work ends, not when the caller stops waiting
        work.add_done_callback(lambda _: self._release(principal.user))
        return await asyncio.shield(work)

    def is_operator(self, principal: Principal) -> bool:
        """The host's word that `principal` may use admin mode; with no hook, everyone is. A hook
        that fails refuses: an operator is never assumed."""
        if self.authorize_operator is None:
            return True
        try:
            return bool(self.authorize_operator(principal))
        except Exception:
            log.exception("operate: authorize_operator failed")
            return False

    def busy(self) -> Response:
        return self.json(
            429,
            {"error": {"type": "TooManyRequests", "message": "too many requests"}},
            [("retry-after", "1")],
        )

    def _admit(self, user: str) -> bool:
        """Take one place under the per-person and global caps; `False` when there is none."""
        n = self.inflight.get(user, 0)
        if n >= self.max_per_principal or sum(self.inflight.values()) >= self.max_in_flight:
            return False
        self.inflight[user] = n + 1
        return True

    def _release(self, user: str) -> None:
        left = self.inflight.get(user, 1) - 1
        if left > 0:
            self.inflight[user] = left
        else:
            self.inflight.pop(user, None)

    async def _operator(self, principal: Principal) -> bool | None:
        """Whether `principal` is an operator, asked of the host's hook on the capped pool and
        within the same caps as the work, so a viewer who is not an operator cannot make the
        hook run without limit; `None` when the caps leave no place."""
        if not self._admit(principal.user):
            return None
        try:
            return await asyncio.get_running_loop().run_in_executor(
                self.pool, self.is_operator, principal
            )
        finally:
            self._release(principal.user)

    async def _body(self, headers: Mapping[str, str], receive: Receive) -> dict[str, Any]:
        if not headers.get("content-type", "").startswith("application/json"):
            raise _Bad(400, "send application/json")
        chunks: list[bytes] = []
        size = 0
        while True:
            msg = await receive()
            if msg.get("type") == "http.disconnect":
                raise _Bad(400, "client disconnected")
            chunk = msg.get("body", b"")
            size += len(chunk)
            if size > self.max_body:
                raise _Bad(413, "body too large")
            chunks.append(chunk)
            if not msg.get("more_body"):
                break

        def refuse(c: str) -> Any:
            raise ValueError(c)

        try:
            data = json.loads(b"".join(chunks) or b"{}", parse_constant=refuse)
        except (ValueError, RecursionError):
            raise _Bad(400, "body is not JSON") from None
        if not isinstance(data, dict):
            raise _Bad(400, "body is a JSON object")
        return data  # type: ignore[return-value]
