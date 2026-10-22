# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The operator surface: an ASGI app that binds the library's actions and audit reads (CONTRACT-009).

`create_app(arras, principal_for_request=...)` returns an ASGI application the host mounts. It
accepts no write other than invoking an action the module declares, holds no credential and decides
no access: every call runs through `arras.session(principal)`, so the backends decide, and a host
may narrow what is offered with `authorize_action` and who is an operator with
`authorize_operator` (CONTRACT-010, section E): `GET /viewer` tells a viewer which modes the shell
offers, and every other endpoint but `GET /version` refuses a non-operator before any work. Errors are answered by type and reason; a
backend's own text is never sent.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from arras.actions import Create, Delete, Effect, Link, Unlink, Update
from arras.core import Arras
from arras.errors import (
    ArrasError,
    Invalid,
    Refused,
    Violation,
)
from arras.http import Receive, Request, Response, Scope
from arras.inputs import convert_inputs, parse_timestamp
from arras.operate.explorer import schema_catalog
from arras.operate.openapi import openapi_document
from arras.operate.schema_app import create_schema_app as create_schema_app
from arras.operate.wire import (
    MAX_WORKERS,
    WireApp,
    _Bad,
    answer_error,
    error_json,
)
from arras.operate.wire import (
    NOT_OPERATOR as NOT_OPERATOR,
)
from arras.results import (
    BatchReceipt,
    Change,
    ChangesPage,
    Load,
    LoadsPage,
    Receipt,
    Validation,
)
from arras.serialize import jsonable
from arras.types import Freshness, Principal, Revision
from arras.versions import CONTRACT_VERSIONS

log = logging.getLogger("arras.operate")

MAX_BODY = 256 * 1024
MAX_SQL = 16 * 1024  # a query's text, in bytes
MAX_PER_PRINCIPAL = 4
MAX_IN_FLIGHT = 2 * MAX_WORKERS  # across people, so one crowd cannot queue the pool without bound
ACTION_VERBS = ("validate", "invoke", "batch")


# -- the wire ------------------------------------------------------------------------------------


def _iso(t: datetime) -> str:
    return t.isoformat()


def _fresh(f: Freshness | None) -> dict[str, Any] | None:
    if f is None:
        return None
    return {
        "backend": f.backend,
        "asOf": f.as_of.value,
        "at": _iso(f.as_of.at),
        "consistency": f.consistency,
    }


def _ref(r: Any) -> dict[str, Any]:
    return {"type": r.type, "key": r.key, "generated": bool(r.generated)}


def effect_json(e: Effect) -> dict[str, Any]:
    if isinstance(e, Create):
        return {
            "kind": "create",
            "ref": _ref(e.ref),
            "properties": jsonable(dict(e.properties), tag=False),
        }
    if isinstance(e, Update):
        return {
            "kind": "update",
            "ref": _ref(e.ref),
            "set": jsonable(dict(e.set), tag=False),
            "unset": list(e.unset),
        }
    if isinstance(e, Delete):
        return {"kind": "delete", "ref": _ref(e.ref)}
    kind = "link" if isinstance(e, Link) else "unlink"
    assert isinstance(e, Link | Unlink)
    return {
        "kind": kind,
        "relationship": e.relationship,
        "source": _ref(e.source),
        "target": _ref(e.target),
    }


def receipt_json(r: Receipt) -> dict[str, Any]:
    return {
        "action": r.action,
        "refs": [{"type": x.type, "key": x.key, "version": x.version} for x in r.refs],
        "created": r.created,
        "updated": r.updated,
        "deleted": r.deleted,
        "linked": r.linked,
        "unlinked": r.unlinked,
        "token": r.token,
        "group": r.group,
        "replayed": r.replayed,
    }


def _failure_reason(f: Any) -> str:
    """A declared precondition's reason is the module's own text. A conflict's is the backend's,
    and may echo an input or a key, so it is worded by its kind alone."""
    if f.id.startswith("conflict:"):
        return f"conflict ({f.id.partition(':')[2]})"
    return f.reason


def validation_json(v: Validation, faults: list[Violation] | None = None) -> dict[str, Any]:
    violations = [*v.violations]
    seen = {(x.path, x.code) for x in violations}
    violations += [x for x in faults or [] if (x.path, x.code) not in seen]
    return {
        "ok": v.ok and not faults,
        "violations": [{"path": x.path, "code": x.code, "message": x.message} for x in violations],
        "failures": [{"id": x.id, "reason": _failure_reason(x)} for x in v.failures],
        "effects": [effect_json(e) for e in v.effects],
        "replay": receipt_json(v.replay) if v.replay else None,
        "freshness": _fresh(v.freshness),
    }


def batch_json(b: BatchReceipt) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for i in b.items:
        if i.receipt is not None:
            items.append({"index": i.index, "receipt": receipt_json(i.receipt)})
        else:
            assert i.refusal is not None
            items.append({"index": i.index, "refusal": error_json(i.refusal)["error"]})
    return {
        "action": b.action,
        "atomic": b.atomic,
        "items": items,
        "succeeded": b.succeeded,
        "failed": b.failed,
        "token": b.token,
    }


def change_json(c: Change) -> dict[str, Any]:
    return {
        "group": c.group,
        "at": _iso(c.at),
        "by": c.by,
        "action": c.action,
        "module": c.module,
        "ops": jsonable(list(c.ops), tag=False),
        "backend": c.backend,
    }


def load_json(ld: Load) -> dict[str, Any]:
    return {
        "load_id": ld.load_id,
        "initiated_by": ld.initiated_by,
        "at": _iso(ld.at),
        "module": ld.module,
        "created": ld.created,
        "skipped": ld.skipped,
        "rejected": ld.rejected,
        "partial": ld.partial,
    }


def page_json(p: ChangesPage | LoadsPage) -> dict[str, Any]:
    items = [change_json(c) if isinstance(c, Change) else load_json(c) for c in p.items]
    return {
        "items": items,
        "nextCursor": p.next_cursor,
        "truncated": p.truncated,
        "freshness": _fresh(p.freshness),
    }


# -- request checks ------------------------------------------------------------------------------


def _text(body: Mapping[str, Any], key: str) -> str | None:
    v = body.get(key)
    if v is None:
        return None
    if not isinstance(v, str):
        raise _Bad(400, f"{key} is a string")
    return v


def _object(body: Mapping[str, Any], key: str) -> dict[str, Any] | None:
    v = body.get(key)
    if v is None:
        return None
    if not isinstance(v, dict):
        raise _Bad(400, f"{key} is a JSON object")
    return v  # type: ignore[return-value]


def _flag(body: Mapping[str, Any], key: str) -> bool:
    v = body.get(key, False)
    if not isinstance(v, bool):
        raise _Bad(400, f"{key} is true or false")
    return v


def _revision_body(body: Mapping[str, Any]) -> dict[str, Any] | None:
    r = _object(body, "expected_revision")
    if r is None:
        return None
    try:
        Revision.from_wire(r)
    except ValueError as e:
        raise _Bad(400, f"expected_revision is an object keyed by backend name: {e}") from None
    return r


def _when(body: Mapping[str, Any], key: str) -> datetime | None:
    v = _text(body, key)
    if v is None:
        return None
    t = parse_timestamp(v)  # the converter's own rule, so a time is read alike everywhere
    if t is None:
        raise _Bad(400, f"{key} is an RFC 3339 time with an offset")
    return t


def _limit(body: Mapping[str, Any]) -> int:
    v = body.get("limit", 50)
    if isinstance(v, bool) or not isinstance(v, int):
        raise _Bad(400, "limit is an integer")
    return v


# -- the application -----------------------------------------------------------------------------


class Operate(WireApp):
    def __init__(
        self,
        arras: Arras,
        principal_for_request: Callable[[Request], Principal | None],
        authorize_action: Callable[[Principal, str, str], bool] | None,
        public_origin: str | None,
        allowed_origins: tuple[str, ...],
        base_path: str,
        authorize_operator: Callable[[Principal], bool] | None = None,
        title: str = "Arras",
    ) -> None:
        self.title = title
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
        self.authorize_action = authorize_action

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
            keys = ("interface", "actions", "console", "operate")
            return self.json(200, {"contracts": {k: CONTRACT_VERSIONS[k] for k in keys}})
        if method == "GET" and parts == ["openapi.json"]:
            return self.json(200, openapi_document(self.title))
        if parts == ["viewer"]:
            if method != "GET":
                return self.json(
                    405,
                    {"error": {"type": "MethodNotAllowed", "message": method}},
                    [("allow", "GET")],
                )
            return await self._viewer(Request(method, path, headers, {}, scope))
        if parts == ["explorer", "schema-catalog.json"]:
            if method != "GET":
                return self.json(
                    405,
                    {"error": {"type": "MethodNotAllowed", "message": method}},
                    [("allow", "GET")],
                )
            # a read: no Origin proof (nothing to forge), the viewer's own catalog, never cached
            return await self._as_viewer(Request(method, path, headers, {}, scope), ("explorer",))
        target = self._target(parts)
        if target is None:
            return self.json(404, {"error": {"type": "NotFound", "message": "not found"}})
        if method != "POST":
            return self.json(
                405, {"error": {"type": "MethodNotAllowed", "message": method}}, [("allow", "POST")]
            )
        if not self._post_allowed(headers, repeated):
            return self.json(403, {"error": {"type": "Forbidden", "message": "origin not allowed"}})
        return await self._as_viewer(Request(method, path, headers, {}, scope), target, receive)

    async def _viewer(self, request: Request) -> Response:
        """The viewer's modes (CONTRACT-010): `admin` exactly when they are an operator. A read
        that changes nothing, so it needs no origin proof; it answers a non-operator."""
        loop = asyncio.get_running_loop()
        principal = await loop.run_in_executor(None, self.principal_for_request, request)
        if principal is None:
            return self.json(401, {"error": {"type": "Refused", "message": "sign in"}})
        operator = await self._operator(principal)
        if operator is None:
            return self.busy()
        return self.json(
            200, {"user": principal.user, "modes": ["user", "admin"] if operator else ["user"]}
        )

    @staticmethod
    def _target(parts: list[str]) -> tuple[str, ...] | None:
        if len(parts) == 4 and parts[0] == "actions" and parts[3] in ACTION_VERBS:
            return ("action", parts[1], parts[2], parts[3])
        if len(parts) == 2 and parts[0] == "audit" and parts[1] in ("changes", "loads"):
            return ("audit", parts[1])
        if parts == ["query"]:
            return ("query",)
        if parts == ["export"]:
            return ("export",)
        return None

    # -- execution, in a worker thread (the library is synchronous)
    def execute(
        self, principal: Principal, target: tuple[str, ...], body: dict[str, Any]
    ) -> Response:
        try:
            o = self.h.session(principal)
            if target[0] == "action":
                return self._action(o, principal, target, body)
            if target[0] == "explorer":
                return self.json(200, schema_catalog(o))
            if target[0] == "query":
                return self._query(o, body)
            if target[0] == "export":
                return self._export(o, body)
            return self._audit(o, target[1], body)
        except _Bad as e:
            return self.json(e.status, {"error": {"type": "BadRequest", "message": e.message}})
        except ArrasError as e:
            return answer_error(e)
        except Exception:
            log.exception("operate execution failed")
            return self.json(500, {"error": {"type": "InternalError", "message": "internal error"}})

    def _action(
        self, o: Any, principal: Principal, target: tuple[str, ...], body: dict[str, Any]
    ) -> Response:
        _, module, short, verb = target
        name = f"{module}.{short}"
        if self.authorize_action is not None and not self.authorize_action(principal, module, name):
            return self.json(403, {"error": {"type": "Refused", "message": "not offered"}})
        try:
            mods = o.describe(module)
        except (Invalid, Refused) as e:
            if isinstance(e, Refused) and e.reason == "token_expired":
                raise  # sign in again is not "no such module"
            return self.json(
                404, {"error": {"type": "NotFound", "message": "no such module or action"}}
            )
        info = next((a for a in mods[0].actions if a.name == name), None)
        if info is None:
            return self.json(
                404, {"error": {"type": "NotFound", "message": "no such module or action"}}
            )
        key = _text(body, "idempotency_key")
        revision = _revision_body(body)
        atomic, stop = _flag(body, "atomic"), _flag(body, "stop_on_error")
        if verb == "batch":
            items = body.get("items")
            if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):  # type: ignore[reportUnknownVariableType]
                raise _Bad(400, "items is a list of JSON objects")
            values: list[Any] = []
            faults: list[Violation] = []
            for i, item in enumerate(items):  # type: ignore[reportUnknownVariableType]
                v, f = convert_inputs(info, mods[0], item, f"items[{i}].inputs")  # type: ignore[reportUnknownArgumentType]
                values.append(v)
                faults += f
            if faults:
                return self.json(400, error_json(Invalid(faults)))
            b = o.invoke_batch(
                name,
                values,
                atomic=atomic,
                stop_on_error=stop,
                idempotency_key=key,
                expected_revision=revision,
            )
            return self.json(200, batch_json(b))
        inputs = _object(body, "inputs") or {}
        values_, faults = convert_inputs(info, mods[0], inputs)
        if verb == "validate":
            v = o.validate(name, values_, idempotency_key=key, expected_revision=revision)
            return self.json(200, validation_json(v, faults))
        if faults:
            return self.json(400, error_json(Invalid(faults)))
        r = o.invoke(name, values_, idempotency_key=key, expected_revision=revision)
        return self.json(200, receipt_json(r))

    def _query(self, o: Any, body: dict[str, Any]) -> Response:
        """`query` as the viewer (CONTRACT-001): a Weft statement over the named module. The text is
        in this body only; no error, log or attribute here carries it."""
        if "after" in body:
            raise _Bad(400, "a page is the statement's own (ORDER BY, LIMIT, a keyset): no after")
        module = body.get("module")
        if not isinstance(module, str) or not module:
            raise _Bad(400, "module is the module the statement reads")
        sql = body.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            raise _Bad(400, "sql is a string")
        if (
            len(sql.encode("utf-8", "surrogatepass")) > MAX_SQL
        ):  # a lone surrogate is a count, not a fault
            raise _Bad(400, "sql is at most 16 KiB")
        consistency = body.get("consistency", "latest")
        if not isinstance(consistency, str):
            raise _Bad(400, "consistency is latest or bulk")
        rows = o.query(
            module,
            sql,
            _object(body, "params"),
            limit=_limit(body),
            consistency=consistency,
            at_least=_text(body, "at_least"),
        )
        return self.json(
            200,
            {
                "columns": [
                    {"name": c.name, "scalar": c.scalar, "type": c.type} for c in rows.columns
                ],
                "rows": [jsonable(r) for r in rows.rows],
                "truncated": rows.truncated,
                "freshness": _fresh(rows.freshness),
                "revision": dict(rows.revision.by_backend),
            },
        )

    def _export(self, o: Any, body: dict[str, Any]) -> Response:
        """`export_records` as the viewer (CONTRACT-003): a page of the module's graph as records.
        A `POST`, so the module and the cursor are never in a URL."""
        module = _text(body, "module")
        if module is None:
            raise _Bad(400, "module is required")
        limit = body.get("limit", 500)
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise _Bad(400, "limit is an integer")
        page = o.export_records(module, limit=limit, after=_text(body, "after"))
        return self.json(
            200,
            {
                "items": [jsonable(r) for r in page.items],
                "nextCursor": page.next_cursor,
                "omitted": list(page.omitted),
                "freshness": _fresh(page.freshness),
            },
        )

    def _audit(self, o: Any, which: str, body: dict[str, Any]) -> Response:
        limit, after = _limit(body), _text(body, "after")
        provider = _text(body, "provider")
        if which == "loads":
            module = _text(body, "module")
            if module is None:
                raise _Bad(400, "module is required")
            return self.json(
                200, page_json(o.loads(module, limit=limit, after=after, provider=provider))
            )
        page = o.changes(
            _text(body, "module"),
            type=_text(body, "type"),
            key=_text(body, "key"),
            by=_text(body, "by"),
            action=_text(body, "action"),
            group=_text(body, "group"),
            since=_when(body, "since"),
            until=_when(body, "until"),
            limit=limit,
            after=after,
            provider=provider,
        )
        return self.json(200, page_json(page))


def operators_in_groups(*groups: str) -> Callable[[Principal], bool]:
    """An `authorize_operator` that admits the principals who belong to any of `groups`. The group
    names are the host's configuration (by default `admins` and `builders`); Arras infers no role."""
    names = frozenset(groups)
    return lambda principal: bool(names.intersection(principal.groups))


def create_app(
    arras: Arras,
    *,
    principal_for_request: Callable[[Request], Principal | None],
    authorize_action: Callable[[Principal, str, str], bool] | None = None,
    public_origin: str | None = None,
    allowed_origins: tuple[str, ...] = (),
    base_path: str = "",
    authorize_operator: Callable[[Principal], bool] | None = None,
    title: str = "Arras",
) -> Operate:
    """The ASGI application; mount it at `base_path`. `authorize_operator` is the host's decision
    that a principal is an operator; without it every principal is (and the start says so). `title` names the product in the published OpenAPI document."""
    return Operate(
        arras,
        principal_for_request,
        authorize_action,
        public_origin,
        allowed_origins,
        base_path,
        authorize_operator,
        title,
    )
