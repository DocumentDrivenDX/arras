# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The schema administration surface: validate and register a UMF document as the viewer (CONTRACT-011).

A separate app from the operator surface, which writes nothing but declared actions (CONTRACT-009).
It holds no credential and decides no access: every call runs through `arras.session(principal)`
and the record store's `schema` grant decides, with `authorize_schema` a host's way to narrow it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from arras.core import Arras
from arras.errors import ArrasError, Violation
from arras.http import Receive, Request, Response, Scope
from arras.operate.wire import WireApp, _Bad, answer_error
from arras.results import RegistryResult, SchemaChange, SchemaPlan
from arras.telemetry import _logger
from arras.types import Principal, Revision
from arras.umf import parse_module
from arras.versions import CONTRACT_VERSIONS

log = _logger("arras.operate")

MAX_DOCUMENT = 1024 * 1024  # after decoding
MAX_BODY = 4 * 1024 * 1024  # carries a document with every character escaped
MAX_PER_PRINCIPAL = 2
MAX_IN_FLIGHT = 4
VERBS = ("validate", "register")


def _revision(r: Revision | None) -> dict[str, Any] | None:
    return None if r is None else dict(r.by_backend)


def _violation(v: Violation) -> dict[str, str]:
    return {"path": v.path, "code": v.code, "message": v.message}


def _change(c: SchemaChange) -> dict[str, str]:
    return {"kind": c.kind, "element": c.element, "name": c.name, "detail": c.detail}


def plan_json(p: SchemaPlan) -> dict[str, Any]:
    return {
        "module": p.module,
        "ok": p.ok,
        "violations": [_violation(v) for v in p.violations],
        "changed": p.changed,
        "revision": _revision(p.revision),
        "changes": [_change(c) for c in p.changes],
        "report": list(p.report),
    }


def result_json(r: RegistryResult) -> dict[str, Any]:
    return {
        "module": r.module,
        "revision": _revision(r.revision),
        "changed": r.changed,
        "report": list(r.report),
    }


class SchemaApp(WireApp):
    def __init__(
        self,
        arras: Arras,
        principal_for_request: Callable[[Request], Principal | None],
        authorize_schema: Callable[[Principal, str], bool] | None,
        public_origin: str | None,
        allowed_origins: tuple[str, ...],
        base_path: str,
        authorize_operator: Callable[[Principal], bool] | None = None,
    ) -> None:
        super().__init__(
            arras,
            principal_for_request,
            public_origin,
            allowed_origins,
            base_path,
            max_body=MAX_BODY,
            max_per_principal=MAX_PER_PRINCIPAL,
            max_in_flight=MAX_IN_FLIGHT,
            authorize_operator=authorize_operator,
        )
        self.authorize_schema = authorize_schema

    async def _route(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        scope: Scope,
        receive: Receive,
        repeated: set[str],
    ) -> Response:
        parts = [p for p in path.split("/") if p]
        if method == "GET" and parts == ["version"]:
            return self.json(200, {"contracts": {"schema": CONTRACT_VERSIONS["schema"]}})
        if len(parts) != 1 or parts[0] not in VERBS:
            return self.json(404, {"error": {"type": "NotFound", "message": "not found"}})
        if method != "POST":
            return self.json(
                405, {"error": {"type": "MethodNotAllowed", "message": method}}, [("allow", "POST")]
            )
        if not self._post_allowed(headers, repeated):
            return self.json(403, {"error": {"type": "Forbidden", "message": "origin not allowed"}})
        return await self._as_viewer(
            Request(method, path, headers, {}, scope), (parts[0],), receive
        )

    def execute(
        self, principal: Principal, target: tuple[str, ...], body: dict[str, Any]
    ) -> Response:
        try:
            document = body.get("document")
            if not isinstance(document, str):
                raise _Bad(400, "document is a string")
            if len(document.encode()) > MAX_DOCUMENT:
                raise _Bad(413, "document too large")
            policy = body.get("unknown_endpoint", "reject")
            if policy not in ("reject", "provisional"):
                raise _Bad(400, "unknown_endpoint is reject or provisional")
            name = parse_module(document).name  # a document that does not parse is 400, here
            if self.authorize_schema is not None and not self.authorize_schema(principal, name):
                return self.json(403, {"error": {"type": "Refused", "message": "no access"}})
            schema = self.h.session(principal).schema()
            if target[0] == "validate":
                return self.json(200, plan_json(schema.validate(document, unknown_endpoint=policy)))
            want = body.get("expected_revision")
            if want is not None:
                if not isinstance(want, dict):
                    raise _Bad(400, "expected_revision is a JSON object")
                try:
                    Revision.from_wire(want)
                except ValueError as e:
                    raise _Bad(400, f"expected_revision is keyed by backend name: {e}") from None
            result = schema.register(document, unknown_endpoint=policy, expected_revision=want)
            return self.json(200, result_json(result))
        except _Bad as e:
            return self.json(e.status, {"error": {"type": "BadRequest", "message": e.message}})
        except ArrasError as e:
            return answer_error(e)
        except Exception as error:
            log.error("schema execution failed: %s", type(error).__name__)
            return self.json(500, {"error": {"type": "InternalError", "message": "internal error"}})


def create_schema_app(
    arras: Arras,
    *,
    principal_for_request: Callable[[Request], Principal | None],
    authorize_schema: Callable[[Principal, str], bool] | None = None,
    public_origin: str | None = None,
    allowed_origins: tuple[str, ...] = (),
    base_path: str = "",
    authorize_operator: Callable[[Principal], bool] | None = None,
) -> SchemaApp:
    """The ASGI application; mount it at `base_path`, only where the host wants schema import."""
    return SchemaApp(
        arras,
        principal_for_request,
        authorize_schema,
        public_origin,
        allowed_origins,
        base_path,
        authorize_operator,
    )
