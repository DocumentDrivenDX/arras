# SPDX-License-Identifier: MIT OR Apache-2.0
"""Telemetry (CONTRACT-008): named events with a few safe attributes, and spans when OpenTelemetry
is installed.

Arras owns no exporter, collector or log file. It emits to the standard library logger
`arras.telemetry` and, when `opentelemetry-api` is importable, to the host's tracer provider, so
the host decides where signals go. Nothing here writes to stdout: the MCP binding's stdout carries
protocol frames only.

Attributes are default-deny. Only the names in `ATTRIBUTES` are kept, and only a short value of
safe characters: no inputs, entity keys, query text, tokens or user names can reach a sink, even
when a caller passes one. Telemetry never raises into the operation it observes; a signal that
could not be emitted is counted in `dropped()`.
"""

from __future__ import annotations

import functools
import importlib
import logging
import re
import threading
import time
from collections.abc import Callable, Generator, Mapping
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from typing import Any, ParamSpec, TypeVar

from arras.errors import UNAVAILABLE_REASONS, ArrasError, NotYetCurrent, Unavailable

log = logging.getLogger("arras.telemetry")

# The event catalog. A signal with another name is refused at the emitting call.
EVENTS = frozenset(
    {
        "arras.query",
        "arras.validate",
        "arras.invoke",
        "arras.invoke_batch",
        "arras.import_records",
        "arras.export_records",
        "arras.migrate",
        "arras.changes",
        "arras.loads",
        "arras.search",
        "arras.document",
        "arras.register",
        "arras.attach",
        "arras.schema_validate",
        "arras.schema_register",
        "arras.backend.status",
        "arras.backend.migrate",
        "arras.backend.configure_access",
    }
)

# The attributes a signal may carry. Names are exported as `arras.<name>`, except `error.type`,
# which is the OpenTelemetry semantic convention of that name.
ATTRIBUTES = frozenset(
    {
        "module",
        "action",
        "backend",
        "consistency",
        "outcome",
        "reason",
        "replayed",
        "recovered",
        "committed",
        "atomic",
        "valid",
        "available",
        "items",
        "succeeded",
        "failed",
        "rows",
        "truncated",
        "duration_ms",
        "error.type",
    }
)

MAX_VALUE_LENGTH = 64
_SAFE = re.compile(r"[A-Za-z0-9_.:\-]*")
_dropped = 0
_lock = threading.Lock()
_current: ContextVar[Operation | None] = ContextVar("arras_operation", default=None)

P = ParamSpec("P")
R = TypeVar("R")


def dropped() -> int:
    """How many signals could not be emitted, so a quiet sink is not read as a healthy one."""
    return _dropped


def clean(attrs: Mapping[str, object]) -> dict[str, bool | int | str]:
    """The attributes that may be emitted: allowlisted names, safe short values, nothing else."""
    out: dict[str, bool | int | str] = {}
    for name, value in attrs.items():
        if name not in ATTRIBUTES:
            continue
        if isinstance(value, bool | int):
            out[name] = value
        elif isinstance(value, str) and len(value) <= MAX_VALUE_LENGTH and _SAFE.fullmatch(value):
            out[name] = value
    return out


def _exported(name: str) -> str:
    return name if name == "error.type" else f"arras.{name}"


class Operation:
    """The attributes of one operation, added as it learns them (a result's backend, say)."""

    def __init__(self, event: str, attrs: Mapping[str, object]) -> None:
        self.event = event
        self.attrs: dict[str, object] = dict(attrs)

    def set(self, **attrs: object) -> None:
        self.attrs.update(attrs)


def _otel(name: str) -> Any:
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def _level(error: BaseException | None) -> int:
    if error is None:
        return logging.DEBUG
    if isinstance(error, Unavailable):
        return logging.WARNING
    if isinstance(error, ArrasError) or not isinstance(error, Exception):
        return logging.INFO  # a caller's outcome, or an interrupt: not a fault of ours
    return logging.ERROR


def _record(event: str, attrs: Mapping[str, object], level: int) -> None:
    if not log.isEnabledFor(level):
        return
    safe = clean(attrs)
    fields = " ".join(f"{k}={safe[k]}" for k in sorted(safe))
    log.log(level, "%s %s", event, fields, extra={"arras_event": event, "arras_attrs": safe})


def emit(event: str, **attrs: object) -> None:
    """One event with no duration (a backend changing state). Never raises."""
    global _dropped
    try:
        if event not in EVENTS:
            raise ValueError(event)
        available = attrs.get("available")
        _record(event, attrs, logging.WARNING if available is False else logging.INFO)
    except Exception:
        _count_dropped()


def annotate(**attrs: object) -> None:
    """Add attributes to the operation now running. Call it with values the library resolved
    (a registered action's name, a checked consistency level), never with what a caller typed:
    a value a caller chose is a value a caller can fill with content."""
    op = _current.get()
    if op is not None:
        op.set(**attrs)


@contextmanager
def operation(event: str, **attrs: object) -> Generator[Operation]:
    """Observe one operation: a span (when OpenTelemetry is installed) and one log record at its
    end, with its outcome and duration. An error passes through untouched."""
    op = Operation(event, attrs)
    started = time.perf_counter()
    failure: BaseException | None = None
    span: Any = None
    stack = ExitStack()
    try:
        trace = _otel("opentelemetry.trace")
        if trace is not None and event in EVENTS:
            span = stack.enter_context(
                trace.get_tracer("arras").start_as_current_span(
                    event, record_exception=False, set_status_on_exception=False
                )
            )
    except Exception:
        _count_dropped()
    token = _current.set(op)
    try:
        yield op
    except BaseException as e:
        failure = e
        raise
    finally:
        _current.reset(token)
        try:
            _finish(op, span, failure, time.perf_counter() - started)
        finally:  # the span ends and the context detaches even if finishing is interrupted
            try:
                stack.close()
            except Exception:
                _count_dropped()


def _count_dropped() -> None:
    global _dropped
    with _lock:
        _dropped += 1


def _finish(op: Operation, span: Any, failure: BaseException | None, seconds: float) -> None:
    try:
        if op.event not in EVENTS:
            raise ValueError(op.event)
        attrs = dict(op.attrs)
        attrs["outcome"] = "ok" if failure is None else "error"
        if failure is not None:
            attrs["error.type"] = type(failure).__name__
            if isinstance(failure, Unavailable):
                attrs["reason"] = (
                    failure.reason if failure.reason in UNAVAILABLE_REASONS else "other"
                )
                attrs["backend"] = failure.backend
            elif isinstance(failure, NotYetCurrent):
                attrs["backend"] = failure.backend
        safe = clean(attrs)
        if span is not None:
            for name, value in safe.items():
                span.set_attribute(_exported(name), value)
            unexpected = isinstance(failure, Exception) and not isinstance(failure, ArrasError)
            if unexpected or isinstance(failure, Unavailable):
                status = _otel("opentelemetry.trace")
                if status is not None:
                    span.set_status(status.Status(status.StatusCode.ERROR))  # no description
        _record(op.event, {**safe, "duration_ms": round(seconds * 1000)}, _level(failure))
    except Exception:
        _count_dropped()


def traced(
    event: str,
    attrs: Callable[..., Mapping[str, object]] | None = None,
    result: Callable[[Any], Mapping[str, object]] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Wrap a method in `operation`. `attrs(*args, **kwargs)` names what is known before the call
    and `result(value)` what the answer adds. Neither may raise into the operation."""

    def decorate(fn: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                before: Mapping[str, object] = attrs(*args, **kwargs) if attrs is not None else {}
            except Exception:
                _count_dropped()
                before = {}
            with operation(event, **before) as op:
                value = fn(*args, **kwargs)
                try:
                    if result is not None:
                        op.set(**result(value))
                except Exception:
                    _count_dropped()
                return value

        return wrapper

    return decorate


@contextmanager
def remote_parent(meta: object) -> Generator[None]:
    """Make the caller's trace the parent of what runs inside, from a W3C `traceparent` (and
    `tracestate`) in a request's `_meta`. Without OpenTelemetry, or with no valid header, it does
    nothing: a trace id is never made up."""
    token: Any = None
    try:
        context = _otel("opentelemetry.context")
        propagate = _otel("opentelemetry.propagate")
        if context is not None and propagate is not None and isinstance(meta, dict):
            carrier = {
                k: v
                for k, v in meta.items()  # pyright: ignore[reportUnknownVariableType]
                if k in ("traceparent", "tracestate") and isinstance(v, str)
            }
            if carrier:
                token = context.attach(propagate.extract(carrier))
    except Exception:
        _count_dropped()
    try:
        yield
    finally:
        if token is not None:
            try:
                _otel("opentelemetry.context").detach(token)
            except Exception:
                _count_dropped()
