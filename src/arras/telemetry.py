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
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar

from arras.distribution import DistributionConfig, TelemetryNames
from arras.errors import UNAVAILABLE_REASONS, ArrasError, NotYetCurrent, Unavailable

_DEFAULT_NAMES = TelemetryNames()
log = logging.getLogger("arras.telemetry")

# The event catalog. A signal with another name is refused at the emitting call.
EVENTS = frozenset(
    {
        "arras.query",
        "arras.execute",
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
_active: ContextVar[TelemetryContext | None] = ContextVar("arras_telemetry_context", default=None)

P = ParamSpec("P")
R = TypeVar("R")


def dropped() -> int:
    """How many signals could not be emitted, so a quiet sink is not read as a healthy one."""
    return _dropped


@dataclass(frozen=True, init=False)
class TelemetryContext:
    """Host-scoped output names and optional caller-owned tracer provider."""

    names: TelemetryNames
    _tracer_provider: Any

    def __init__(self, names: TelemetryNames = _DEFAULT_NAMES, *, tracer_provider: Any = None):
        if not _is_names(names):
            raise ValueError("names: expected TelemetryNames")
        if names.service_name is not None:
            if tracer_provider is None:
                raise ValueError("tracer_provider: required for explicit service_name")
            try:
                resource = tracer_provider.resource
                attributes = resource.attributes
                service_name = attributes.get("service.name")
                if service_name != names.service_name:
                    raise ValueError
            except Exception:
                raise ValueError(
                    "tracer_provider: unreadable or mismatched service.name Resource"
                ) from None
        if tracer_provider is not None:
            try:
                get_tracer = getattr(tracer_provider, "get_tracer", None)
            except Exception:
                raise ValueError("tracer_provider: unreadable get_tracer") from None
            if not callable(get_tracer):
                raise ValueError("tracer_provider: expected get_tracer")
        object.__setattr__(self, "names", names)
        object.__setattr__(self, "_tracer_provider", tracer_provider)

    @contextmanager
    def activate(self) -> Generator[None]:
        token = _active.set(self)
        try:
            yield
        finally:
            _active.reset(token)

    def wrap_asgi(self, app: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapped(scope: Any, receive: Any, send: Any) -> Any:
            with self.activate():
                return await app(scope, receive, send)

        return wrapped


def _context_for(  # pyright: ignore[reportUnusedFunction]
    telemetry_context: TelemetryContext | None,
    distribution: DistributionConfig | None,
) -> TelemetryContext:
    """Resolve a host scope and ensure explicitly selected names agree."""
    if telemetry_context is not None and not _is_context(telemetry_context):
        raise ValueError("telemetry_context: expected TelemetryContext")
    if distribution is not None:
        names = distribution.telemetry
        if telemetry_context is not None and telemetry_context.names != names:
            raise ValueError("telemetry_context: names do not match distribution")
        return telemetry_context or TelemetryContext(names)
    return telemetry_context or TelemetryContext()


def _make_context(  # pyright: ignore[reportUnusedFunction]
    names: TelemetryNames,
    factory: Callable[[TelemetryNames], TelemetryContext] | None = None,
) -> TelemetryContext:
    """Validate the host factory result without exposing its exception or accepting drift."""
    try:
        context = factory(names) if factory is not None else TelemetryContext(names)
    except Exception:
        raise ValueError("telemetry factory refused") from None
    if not _is_context(context) or context.names != names:
        raise ValueError("telemetry factory returned incompatible context")
    return context


class _RoutedLogger:
    """Small context-aware facade; it does not install handlers or mutate logger state."""

    def __init__(self, canonical_name: str) -> None:
        self._canonical_name = canonical_name

    def _logger(self) -> logging.Logger:
        context = _active.get()
        if context is None:
            name = self._canonical_name
        elif self._canonical_name == "arras.telemetry":
            name = f"{context.names.log_prefix}.telemetry"
        else:
            name = context.names.log_prefix + self._canonical_name[len("arras") :]
        return logging.getLogger(name)

    def __getattr__(self, name: str) -> Any:
        method = getattr(self._logger(), name)
        if name not in {"debug", "info", "warning", "error", "exception", "critical", "log"}:
            return method

        def safely_log(*args: Any, **kwargs: Any) -> Any:
            try:
                return method(*args, **kwargs)
            except Exception:
                _count_dropped()
                return None

        return safely_log


def _logger(name: str) -> _RoutedLogger:  # pyright: ignore[reportUnusedFunction]
    return _RoutedLogger(name)


def _is_names(value: object) -> bool:
    return isinstance(value, TelemetryNames)


def _is_context(value: object) -> bool:
    return isinstance(value, TelemetryContext)


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


def _exported(name: str, context: TelemetryContext | None) -> str:
    if name == "error.type":
        return name
    namespace = context.names.attribute_namespace if context is not None else "arras"
    return f"{namespace}.{name}"


def _event_name(event: str, context: TelemetryContext | None) -> str:
    prefix = context.names.event_prefix if context is not None else "arras"
    return f"{prefix}.{event[len('arras.') :]}" if event.startswith("arras.") else event


class Operation:
    """The attributes of one operation, added as it learns them (a result's backend, say)."""

    def __init__(self, event: str, attrs: Mapping[str, object]) -> None:
        self.event = event
        self.attrs: dict[str, object] = dict(attrs)
        self.refusal: str | None = None

    def set(self, **attrs: object) -> None:
        self.attrs.update(attrs)

    def refused(self, code: str) -> None:
        self.refusal = code


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


def _record(
    event: str,
    attrs: Mapping[str, object],
    level: int,
    context: TelemetryContext | None = None,
) -> None:
    logger_name = (
        f"{context.names.log_prefix}.telemetry" if context is not None else "arras.telemetry"
    )
    target = logging.getLogger(logger_name)
    if not target.isEnabledFor(level):
        return
    safe = clean(attrs)
    fields = " ".join(f"{k}={safe[k]}" for k in sorted(safe))
    projected = _event_name(event, context)
    target.log(level, "%s %s", projected, fields, extra={"arras_event": event, "arras_attrs": safe})


def emit(event: str, **attrs: object) -> None:
    """One event with no duration (a backend changing state). Never raises."""
    global _dropped
    try:
        if event not in EVENTS:
            raise ValueError(event)
        available = attrs.get("available")
        _record(
            event, attrs, logging.WARNING if available is False else logging.INFO, _active.get()
        )
    except Exception:
        _count_dropped()


def annotate(**attrs: object) -> None:
    """Add attributes to the operation now running. Call it with values the library resolved
    (a registered action's name, a checked consistency level), never with what a caller typed:
    a value a caller chose is a value a caller can fill with content."""
    op = _current.get()
    if op is not None:
        op.set(**attrs)


def record_refusal(code: str) -> None:
    """Mark a translated, known no-effect refusal on the current operation."""
    try:
        if type(code) is not str:
            return
        if code not in {
            "DENIED",
            "CONFLICT",
            "PRECONDITION_FAILED",
            "UNSUPPORTED",
            "BUSY",
            "SCHEMA_MISMATCH",
            "LIMIT_EXCEEDED",
            "INVALID",
        }:
            return
        op = _current.get()
        if op is not None and op.event == "arras.execute":
            op.refused(code.lower())
            op.set(reason=code.lower())
    except Exception:
        _count_dropped()


@contextmanager
def operation(event: str, **attrs: object) -> Generator[Operation]:
    """Observe one operation: a span (when OpenTelemetry is installed) and one log record at its
    end, with its outcome and duration. An error passes through untouched."""
    op = Operation(event, attrs)
    selected = _active.get()
    started = time.perf_counter()
    failure: BaseException | None = None
    span: Any = None
    stack = ExitStack()
    try:
        trace = _otel("opentelemetry.trace")
        provider = getattr(selected, "_tracer_provider", None) if selected is not None else None
        if provider is not None:
            tracer = provider.get_tracer("arras")
            if tracer is None:
                _count_dropped()
        else:
            tracer = trace.get_tracer("arras") if trace is not None else None
        if tracer is not None and event in EVENTS:
            span = stack.enter_context(
                tracer.start_as_current_span(
                    _event_name(event, selected),
                    record_exception=False,
                    set_status_on_exception=False,
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
            _finish(op, span, failure, time.perf_counter() - started, selected)
        finally:  # the span ends and the context detaches even if finishing is interrupted
            try:
                stack.close()
            except Exception:
                _count_dropped()


def _count_dropped() -> None:
    global _dropped
    with _lock:
        _dropped += 1


def _finish(
    op: Operation,
    span: Any,
    failure: BaseException | None,
    seconds: float,
    context: TelemetryContext | None,
) -> None:
    try:
        if op.event not in EVENTS:
            raise ValueError(op.event)
        attrs = dict(op.attrs)
        refused = failure is None and op.refusal is not None
        attrs["outcome"] = "refused" if refused else "ok" if failure is None else "error"
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
                span.set_attribute(_exported(name, context), value)
            unexpected = isinstance(failure, Exception) and not isinstance(failure, ArrasError)
            if unexpected or isinstance(failure, Unavailable):
                status = _otel("opentelemetry.trace")
                if status is not None:
                    span.set_status(status.Status(status.StatusCode.ERROR))  # no description
        _record(
            op.event,
            {**safe, "duration_ms": round(seconds * 1000)},
            logging.INFO if refused else _level(failure),
            context,
        )
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
