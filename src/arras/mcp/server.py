# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The MCP server over the library (CONTRACT-007): JSON-RPC 2.0 messages in, messages out.

The transport (stdio frames) is separate: `McpServer.handle` takes one decoded message and returns
the response, or `None` for a notification. One server serves one person: the principal comes from
the process's token and no tool takes a principal argument, so a caller cannot name another user.

Tools are dispatched through the mapping the last `tools/list` gave out, so a name never comes to
mean another action between a host's listing and its call. A failure of the server's own is never
reported as a protocol error once a tool is running: it is a tool result the agent can act on.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any, TextIO

from arras import telemetry
from arras.core import Arras, Ontology
from arras.errors import (
    ArrasError,
    Conflict,
    Invalid,
    NotYetCurrent,
    PreconditionFailed,
    Refused,
    Unavailable,
    Unsupported,
    Violation,
)
from arras.mcp.tools import (
    FIXED,
    MAX_BATCH,
    STATEMENT,
    ActionTool,
    action_tool_schema,
    action_tools,
    convert_inputs,
)
from arras.model import COLUMN_SCALARS, ModuleInfo
from arras.names import quoted, quoted_type
from arras.results import BatchReceipt, Receipt, Validation
from arras.serialize import jsonable
from arras.types import Principal, Rows

log = logging.getLogger("arras.mcp")

# 2025-03-26 required batches; this server answers one message per line and offers only the
# revision that dropped them.
PROTOCOLS = ("2025-06-18",)
MAX_ANSWER_BYTES = 50 * 1024
CHANGE_CHECK_SECONDS = 5.0
_WIDE = 2**53
NO_TOKEN = "no usable token: the host refreshes the token file or restarts the session"
_CONFLICT_HINTS = {
    "idempotency_key_reused": "use a new idempotency_key for different inputs",
    "exists": "read the entity, then decide whether to update it instead",
    "deleted": "that key was retired and cannot be created again; use another key",
    "version": "read the entity's current version, then try again",
    "duplicate_relationship": "the relationship already exists; nothing to do",
}

_PARSE, _INVALID_REQUEST, _INVALID_PARAMS, _INTERNAL = -32700, -32600, -32602, -32603


class _Protocol(Exception):
    def __init__(self, code: int, message: str) -> None:
        self.code, self.message = code, message


def _text(payload: Any, *, error: bool = False) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    out: dict[str, Any] = {
        "content": [{"type": "text", "text": body}],
        "structuredContent": payload,
    }
    if error:
        out["isError"] = True
    return out


def _fail(code: str, message: str, hint: str, **more: Any) -> dict[str, Any]:
    return _text({"code": code, "message": message, "hint": hint, **more}, error=True)


def _v(path: str, code: str, message: str) -> Violation:
    return Violation(path, code, message)


def _wide(v: Any) -> Any:
    """Integers beyond 53 bits go out as decimal text, as they come in."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return str(v) if abs(v) >= _WIDE else v
    if isinstance(v, dict):
        return {k: _wide(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_wide(x) for x in v]
    return v


class McpServer:
    def __init__(
        self,
        arras: Arras,
        principal: Callable[[], Principal | None],
        *,
        name: str = "arras",
        version: str = "0.1.0",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.h = arras
        self.principal = principal
        self.info = {"name": name, "version": version}
        self.clock = clock
        self._listed: tuple[Any, ...] | None = None  # the signature the host last listed
        self._tools: dict[str, str] = {}  # tool name -> qualified action, as last listed
        self._checked = float("-inf")
        self._queue: list[dict[str, Any]] = []

    # -- JSON-RPC
    def handle(self, msg: Any) -> dict[str, Any] | None:
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return self._error(None, _INVALID_REQUEST, "a message is a JSON-RPC 2.0 object")
        if "method" not in msg:
            return (
                None
                if "result" in msg or "error" in msg
                else self._error(None, _INVALID_REQUEST, "no method")
            )
        method = msg["method"]
        is_request = "id" in msg
        mid = msg.get("id")
        if is_request and (isinstance(mid, bool) or not isinstance(mid, str | int)):
            return self._error(None, _INVALID_REQUEST, "an id is a string or an integer")
        if not isinstance(method, str):
            return (
                self._error(mid, _INVALID_REQUEST, "a method is a string") if is_request else None
            )
        params = msg.get("params", {})
        if not isinstance(params, dict):
            return self._error(mid, _INVALID_PARAMS, "params is an object") if is_request else None
        try:
            result = self._dispatch(method, params)
        except _Protocol as e:
            return self._error(mid, e.code, e.message) if is_request else None
        except Exception as e:  # never the cause of a dead process, never message text in a log
            log.error("mcp request failed: %s in %s", type(e).__name__, method)
            return self._error(mid, _INTERNAL, "internal error") if is_request else None
        return {"jsonrpc": "2.0", "id": mid, "result": result} if is_request else None

    @staticmethod
    def _error(mid: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}

    def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "initialize":
            wanted = params.get("protocolVersion")
            return {
                "protocolVersion": wanted if wanted in PROTOCOLS else PROTOCOLS[0],
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": self.info,
                "instructions": "Read the ontology with query and describe; change it only through action tools.",
            }
        if method.startswith("notifications/"):
            return None
        if method == "ping":
            self._note_changes()
            return {}
        if method == "tools/list":
            return {"tools": self._list()}
        if method == "tools/call":
            name, args = params.get("name"), params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(args, dict):
                raise _Protocol(_INVALID_PARAMS, "tools/call takes a name and an arguments object")
            try:
                with telemetry.remote_parent(params.get("_meta")):  # the caller's trace, if any
                    return self._call(name, args)
            except _Protocol:
                raise
            except Exception as e:
                log.error("tool failed: %s in %s", type(e).__name__, name)  # no data, no text
                return _fail(
                    "unavailable",
                    "the tool failed",
                    "try again; if it persists the server needs attention",
                    reason="internal",
                )
            finally:
                self._note_changes()
        raise _Protocol(-32601, f"method {method!r} is not supported")

    def drain(self) -> list[dict[str, Any]]:
        """Notifications to send now (`tools/list_changed`)."""
        out, self._queue = self._queue, []
        return out

    # -- the registry as tools
    def _session(self) -> Ontology | None:
        p = self.principal()
        return self.h.session(p) if p is not None else None

    def _signature(self, o: Ontology) -> tuple[Any, ...]:
        """What the host's tool list depends on: the tools, their revisions, who is available."""
        mods = o.modules()
        status = self.h.status()
        return (
            tuple(
                (t.tool, t.action.name, str(m.revision)) for m in mods for t in action_tools([m])
            ),
            tuple(sorted((n, s.available) for n, s in status.items())),
        )

    def _note_changes(self) -> None:
        """Queue `tools/list_changed` when what was listed no longer holds; at most once per
        interval, and never able to change the result of the call it follows."""
        now = self.clock()
        if self._listed is None or now - self._checked < CHANGE_CHECK_SECONDS:
            return
        self._checked = now
        try:
            o = self._session()
            if o is None:
                return
            if self._signature(o) != self._listed:
                self._listed = None  # the next list is the new baseline
                self._queue.append({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
        except Exception as e:  # a transient failure is not a change
            log.warning("tool list check failed: %s", type(e).__name__)

    def _list(self) -> list[dict[str, Any]]:
        o = self._session()
        mods: list[ModuleInfo] = []
        if o is not None:
            try:
                mods = o.modules()
            except ArrasError:
                mods = []  # listed again once the backends answer; the fixed tools remain
        tools = action_tools(mods)
        self._tools = {t.tool: t.action.name for t in tools}
        try:
            self._listed = self._signature(o) if o is not None else None
        except ArrasError:
            self._listed = None
        self._checked = self.clock()
        return self._tool_defs(mods, tools)

    def _tool_defs(self, mods: list[ModuleInfo], tools: list[ActionTool]) -> list[dict[str, Any]]:
        defs: list[dict[str, Any]] = [
            {
                "name": "describe",
                "description": "The modules you may read: types with columns and relationships, per-backend capabilities and status, actions and their tool names, and the ontology revision.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"module": {"type": "string"}},
                    "additionalProperties": False,
                },
                "annotations": {"readOnlyHint": True, "openWorldHint": False},
            },
            {
                "name": "query",
                "description": f"Read the ontology. {STATEMENT} {self._example(mods)}",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "module": {"type": "string"},
                        "sql": {"type": "string"},
                        "params": {"type": "object"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                        "consistency": {"enum": ["latest", "bulk"]},
                        "at_least": {"type": "string"},
                    },
                    "required": ["module", "sql"],
                    "additionalProperties": False,
                },
                "annotations": {"readOnlyHint": True, "openWorldHint": False},
            },
            {
                "name": "validate_action",
                "description": "Check an action's inputs and preconditions and see the effects it would have, writing nothing.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"action": {"type": "string"}, "inputs": {"type": "object"}},
                    "required": ["action", "inputs"],
                    "additionalProperties": False,
                },
                "annotations": {"readOnlyHint": True, "openWorldHint": False},
            },
        ]
        for t in tools:
            ann: dict[str, Any] = {
                "idempotentHint": True,
                "openWorldHint": False,
                "readOnlyHint": False,
            }
            if t.destructive:
                ann["destructiveHint"] = True  # only ever set to tighten: the default is the host's
            defs.append(
                {
                    "name": t.tool,
                    "description": f"{t.action.description} (action {t.action.name}). Pass exactly one of inputs, or items (1 to {MAX_BATCH}) for a batch; repeat safely with an idempotency_key.",
                    "inputSchema": action_tool_schema(t),
                    "annotations": ann,
                }
            )
        return defs

    @staticmethod
    def _example(mods: list[ModuleInfo]) -> str:
        for m in mods:
            for t in m.entity_types:
                cols = [
                    p.name
                    for p in t.properties
                    if p.required and p.scalar and p.type in COLUMN_SCALARS
                ][:2] or [t.key]
                select = ", ".join(f"x.{quoted(c)}" for c in cols)
                key = f"x.{quoted(t.key)}"
                return f'Example: module "{m.name}", SELECT {select} FROM {quoted_type(t.name)} x WHERE {key} = :k ORDER BY {key} LIMIT 1 with params {{"k": "..."}}.'
        return ""

    # -- calls
    def _call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        o = self._session()
        if o is None:
            if name == "describe":
                return _text(
                    {
                        "modules": [],
                        "backends": jsonable(self.h.status(), tag=False),
                        "note": NO_TOKEN,
                    }
                )
            return _fail("refused", "no usable token", NO_TOKEN)  # even for a name it cannot place
        try:
            if name in FIXED:
                if name == "describe":
                    return self._describe(o, args)
                mods = o.modules() if name == "validate_action" else []
                return self._query(o, args) if name == "query" else self._validate(o, mods, args)
            if not self._tools:
                self._list()  # a host that never listed gets the names it would have been given
            action = self._tools.get(name)
            mods = o.modules()  # an outage or a refusal here is the answer, not "no such tool"
            found = (
                next(
                    ((t, m) for m in mods for t in action_tools([m]) if t.action.name == action),
                    None,
                )
                if action
                else None
            )
            if found is None:
                raise _Protocol(_INVALID_PARAMS, f"no tool {name!r}: list the tools again")
            return self._act(o, found[0], args)
        except ArrasError as e:
            return self._translate(e, o)

    def _describe(self, o: Ontology, args: dict[str, Any]) -> dict[str, Any]:
        self._only(args, {"module"})
        want = args.get("module")
        if want is not None and not isinstance(want, str):
            raise Invalid([_v("module", "type", "a module name")])
        found = o.describe(want) if want else o.describe()
        by_tool = {a: t for t, a in self._tools.items()}
        if not by_tool:
            by_tool = {t.action.name: t.tool for t in action_tools(o.modules())}
        return _text(
            {
                "modules": [_render(m, by_tool) for m in found],
                "backends": jsonable(self.h.status(), tag=False),
            }
        )

    def _query(self, o: Ontology, args: dict[str, Any]) -> dict[str, Any]:
        self._only(args, {"module", "sql", "params", "limit", "consistency", "at_least"})
        module, sql, params = args.get("module"), args.get("sql"), args.get("params")
        if not isinstance(module, str):
            raise Invalid([_v("module", "type", "the module the statement reads")])
        if not isinstance(sql, str):
            raise Invalid([_v("sql", "type", "a statement")])
        if params is not None and not isinstance(params, dict):
            raise Invalid([_v("params", "type", "an object")])
        if args.get("at_least") is not None and not isinstance(args["at_least"], str):
            raise Invalid([_v("at_least", "type", "a string")])
        limit = args.get("limit", 50)
        cut = False
        for _ in range(5):
            rows = o.query(
                module,
                sql,
                params,
                limit=limit,
                consistency=args.get("consistency", "latest"),
                at_least=args.get("at_least"),
            )
            payload = _rows(rows)
            size = len(json.dumps(payload, separators=(",", ":")).encode())
            n = len(rows.rows)
            if size <= MAX_ANSWER_BYTES or n <= 1:
                break  # a single row beyond the budget is returned whole
            # one proportional step toward a page that fits; the caller continues with a keyset
            limit, cut = max(1, min(n - 1, int(n * MAX_ANSWER_BYTES / size * 0.9))), True
        if cut:
            payload["truncated"] = True  # cut at a row boundary to fit the answer budget
        return _text(payload)

    def _validate(
        self, o: Ontology, mods: list[ModuleInfo], args: dict[str, Any]
    ) -> dict[str, Any]:
        self._only(args, {"action", "inputs"})
        action, inputs = args.get("action"), args.get("inputs")
        if not isinstance(action, str) or not isinstance(inputs, dict):
            raise Invalid([_v("arguments", "type", "an action name and an inputs object")])
        found = next(((a, m) for m in mods for a in m.actions if a.name == action), None)
        values, faults = convert_inputs(found[0], found[1], inputs) if found else (inputs, [])
        return _text(_validation(o.validate(action, values), faults))

    def _act(self, o: Ontology, t: ActionTool, args: dict[str, Any]) -> dict[str, Any]:
        self._only(args, {"inputs", "items", "atomic", "stop_on_error", "idempotency_key"})
        if ("inputs" in args) == ("items" in args):
            raise Invalid([_v("arguments", "required", "exactly one of inputs or items")])
        for flag in ("atomic", "stop_on_error"):
            if flag in args and not isinstance(args[flag], bool):
                raise Invalid([_v(flag, "type", "true or false")])
        key = args.get("idempotency_key")
        if key is not None and not isinstance(key, str):
            raise Invalid([_v("idempotency_key", "type", "a string")])
        if "inputs" in args:
            inputs = args["inputs"]
            if not isinstance(inputs, dict):
                raise Invalid([_v("inputs", "type", "an object")])
            values, faults = convert_inputs(t.action, t.module, inputs)
            if faults:
                raise Invalid(faults)
            return _text(_receipt(o.invoke(t.action.name, values, idempotency_key=key)))
        items = args["items"]
        if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
            raise Invalid([_v("items", "type", "a list of objects")])
        converted: list[dict[str, Any]] = []
        faults: list[Violation] = []
        for i, item in enumerate(items):
            vals, f = convert_inputs(t.action, t.module, item, f"items[{i}].inputs")
            converted.append(vals)
            faults += f
        if faults:
            raise Invalid(faults)
        batch = o.invoke_batch(
            t.action.name,
            converted,
            atomic=args.get("atomic", False),
            stop_on_error=args.get("stop_on_error", False),
            idempotency_key=key,
        )
        return _text(_batch(batch))

    @staticmethod
    def _only(args: dict[str, Any], allowed: set[str]) -> None:
        extra = set(args) - allowed
        if extra:
            raise Invalid(
                [_v(k, "unknown_input", "not an argument of this tool") for k in sorted(extra)]
            )

    # -- errors an agent can act on
    def _translate(self, e: ArrasError, o: Ontology) -> dict[str, Any]:
        if isinstance(e, Refused):
            return _fail(
                "refused",
                f"{e.backend} refused {e.operation}",
                "re-authenticate, or ask for access to the module",
            )
        if isinstance(e, Unavailable):
            return _fail(
                "unavailable",
                f"{e.backend} is unavailable ({e.reason})",
                "try again shortly; reads can ask for consistency 'bulk' if another backend serves them",
                backend=e.backend,
                reason=e.reason,
            )
        if isinstance(e, Unsupported):
            nearest = e.supported[0] if e.supported else "describe the type to see what it supports"
            return _fail(
                "unsupported",
                f"not supported: {e.construct}",
                f"rewrite the statement; supported: {nearest}",
                supported=e.supported,
            )
        if isinstance(e, NotYetCurrent):
            return _fail(
                "not_yet_current",
                f"{e.backend} has not reached {e.token}",
                "retry, or read with consistency 'latest'",
                backend=e.backend,
                token=e.token,
            )
        if isinstance(e, PreconditionFailed):
            return _fail(
                "precondition_failed",
                "a precondition failed",
                "call validate_action first to see what to change",
                failures=jsonable(e.failures, tag=False),
            )
        if isinstance(e, Conflict):
            return _fail(
                "conflict",
                f"conflict: {e.reason}",
                _CONFLICT_HINTS.get(e.reason, "read the current state, then decide"),
                reason=e.reason,
            )
        if isinstance(e, Invalid):
            return _fail(
                "invalid",
                "the request is not valid",
                self._hint(e, o),
                violations=jsonable(e.violations, tag=False),
            )
        return _fail("invalid", "the request could not be served", "check the arguments")

    @staticmethod
    def _hint(e: Invalid, o: Ontology) -> str:
        try:
            names = sorted(
                {p.name for m in o.modules() for t in m.entity_types for p in t.properties}
            )
        except ArrasError:
            names = []
        for v in e.violations:
            m = re.search(r"no property '([^']+)'", v.message)
            if v.code == "unknown_field" and m:
                close = difflib.get_close_matches(m.group(1), names, n=1)
                if close:
                    return f"unknown field {m.group(1)!r}; did you mean {close[0]!r}?"
        return "correct the listed fields and call again"


# -- compact answers ------------------------------------------------------------------------


def _rows(r: Rows) -> dict[str, Any]:
    return _wide(
        {
            "rows": jsonable(list(r.rows), tag=False),
            "truncated": r.truncated,
            "freshness": {
                "backend": r.freshness.backend,
                "as_of": {"value": r.freshness.as_of.value, "at": r.freshness.as_of.at.isoformat()},
                "consistency": r.freshness.consistency,
            },
        }
    )


def _receipt(r: Receipt) -> dict[str, Any]:
    return _wide(jsonable(r, tag=False))


def _batch(b: BatchReceipt) -> dict[str, Any]:
    return _wide(jsonable(b, tag=False))


def _validation(v: Validation, faults: list[Violation]) -> dict[str, Any]:
    out = _wide(jsonable(v, tag=False))
    if faults:
        seen = {(x["path"], x["code"]) for x in out["violations"]}
        extra = [x for x in jsonable(faults, tag=False) if (x["path"], x["code"]) not in seen]
        out["ok"] = False
        out["violations"] = [*out["violations"], *extra]
    return out


def _render(m: ModuleInfo, tool_of: Mapping[str, str]) -> dict[str, Any]:
    return {
        "name": m.name,
        "record": m.placement.record,
        "replicas": list(m.placement.replicas),
        "providers": dict(m.placement.providers),
        "revision": jsonable(m.revision, tag=False),
        "types": [
            {
                "name": t.name,
                "key": t.key,
                "properties": [
                    {"name": p.name, "type": p.type, "required": p.required} for p in t.properties
                ],
                "capabilities": jsonable(dict(t.capabilities), tag=False),
            }
            for t in m.entity_types
        ],
        "relationships": [
            {
                "name": r.name,
                "inverse": r.inverse,
                "source": list(r.source),
                "target": list(r.target),
            }
            for r in m.relationships
        ],
        "actions": [
            {"name": a.name, "tool": tool_of.get(a.name), "description": a.description}
            for a in m.actions
        ],
        "status": jsonable(dict(m.status), tag=False),
    }


# -- stdio frames ---------------------------------------------------------------------------


def _reject(c: str) -> Any:
    raise ValueError(c)


def serve(inp: Iterable[str], out: TextIO, server: McpServer) -> None:
    """One JSON message per line in, one per line out; stdout carries nothing else. A bad frame
    is answered or skipped, and never ends the loop."""

    def send(msg: dict[str, Any]) -> None:
        try:
            line = json.dumps(msg, separators=(",", ":"), allow_nan=False)
        except (ValueError, TypeError):
            line = json.dumps(McpServer._error(msg.get("id"), _INTERNAL, "not serializable"))
        out.write(line + "\n")
        out.flush()

    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line, parse_constant=_reject)
        except (ValueError, RecursionError):
            send(McpServer._error(None, _PARSE, "not JSON"))
            continue
        try:
            resp = server.handle(msg)
            if resp is not None:
                send(resp)
            for n in server.drain():
                send(n)
        except Exception as e:  # the loop outlives any one message
            log.error("frame failed: %s", type(e).__name__)
