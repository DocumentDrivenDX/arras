# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""CONTRACT-005/008 scoped naming and caller-owned receiver behavior."""

from __future__ import annotations

import logging
import threading
from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from arras import telemetry
from arras.distribution import TelemetryNames


def _context(service: str, prefix: str):
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    context = telemetry.TelemetryContext(
        TelemetryNames(
            service_name=service,
            attribute_namespace=f"{prefix}.attrs",
            log_prefix=f"{prefix}.logs",
            event_prefix=f"{prefix}.events",
        ),
        tracer_provider=provider,
    )
    return context, exporter


def test_distinct_concurrent_contexts_use_their_own_provider_and_names(caplog) -> None:
    a, exporter_a = _context("service-a", "alpha")
    b, exporter_b = _context("service-b", "beta")
    global_provider = trace.get_tracer_provider()
    gate = threading.Barrier(2)

    def work(context: telemetry.TelemetryContext, module: str) -> None:
        with context.activate():
            gate.wait(timeout=5)
            with telemetry.operation("arras.query", module=module, record_key="secret"):
                telemetry.annotate(rows=2, secret="not-allowlisted")
            telemetry._logger("arras.mcp").warning("safe diagnostic")

    caplog.set_level(logging.DEBUG)
    threads = [
        threading.Thread(target=work, args=(a, "catalog")),
        threading.Thread(target=work, args=(b, "orders")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert trace.get_tracer_provider() is global_provider
    for prefix, service, exporter in (
        ("alpha", "service-a", exporter_a),
        ("beta", "service-b", exporter_b),
    ):
        (span,) = exporter.get_finished_spans()
        assert span.name == f"{prefix}.events.query"
        assert span.resource.attributes["service.name"] == service
        attributes = span.attributes or {}
        assert attributes[f"{prefix}.attrs.rows"] == 2
        assert f"{prefix}.attrs.secret" not in attributes
    assert {r.name for r in caplog.records if r.message == "safe diagnostic"} == {
        "alpha.logs.mcp",
        "beta.logs.mcp",
    }
    events = [r for r in caplog.records if hasattr(r, "arras_event")]
    assert {r.name for r in events} == {"alpha.logs.telemetry", "beta.logs.telemetry"}
    assert all(getattr(r, "arras_event", None) == "arras.query" for r in events)
    assert all(
        "secret" not in r.getMessage() and "secret" not in str(getattr(r, "arras_attrs", {}))
        for r in events
    )


def test_nested_context_restores_and_finish_uses_operation_entry_snapshot(caplog) -> None:
    outer, outer_exporter = _context("outer", "outer")
    inner, inner_exporter = _context("inner", "inner")
    caplog.set_level(logging.DEBUG)
    with outer.activate():
        operation = telemetry.operation("arras.invoke", action="catalog.Add")
        operation.__enter__()
        with inner.activate():
            operation.__exit__(None, None, None)
            telemetry._logger("arras.console").warning("nested diagnostic")
    (span,) = outer_exporter.get_finished_spans()
    assert span.name == "outer.events.invoke"
    assert (span.attributes or {})["outer.attrs.action"] == "catalog.Add"
    assert inner_exporter.get_finished_spans() == ()
    events = [
        record
        for record in caplog.records
        if getattr(record, "arras_event", None) == "arras.invoke"
    ]
    assert len(events) == 1 and events[0].name == "outer.logs.telemetry"
    assert events[0].arras_attrs["action"] == "catalog.Add"
    assert (
        next(r for r in caplog.records if r.message == "nested diagnostic").name
        == "inner.logs.console"
    )


def test_projected_signal_uses_custom_logger_level_independently() -> None:
    """A host may enable its projected logger while canonical Arras logging is disabled."""
    context = telemetry.TelemetryContext(TelemetryNames(log_prefix="tenant"))
    canonical = logging.getLogger("arras.telemetry")
    projected = logging.getLogger("tenant.telemetry")
    old_canonical_level = canonical.level
    old_projected_level = projected.level
    old_projected_propagate = projected.propagate
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    capture = Capture()
    canonical.setLevel(logging.CRITICAL)
    projected.setLevel(logging.INFO)
    projected.propagate = False
    projected.addHandler(capture)
    try:
        with context.activate():
            telemetry.emit("arras.query", outcome="ok")
        assert len(records) == 1
        assert records[0].name == "tenant.telemetry"
        assert getattr(records[0], "arras_event", None) == "arras.query"
    finally:
        projected.removeHandler(capture)
        projected.setLevel(old_projected_level)
        projected.propagate = old_projected_propagate
        canonical.setLevel(old_canonical_level)


def test_routed_diagnostic_handler_failure_is_counted_and_does_not_escape() -> None:
    from arras.errors import Unavailable
    from arras.operate.wire import answer_error

    context = telemetry.TelemetryContext(TelemetryNames(log_prefix="tenant"))
    logger = logging.getLogger("tenant.operate")
    old_level = logger.level
    logger.setLevel(logging.INFO)

    class BrokenHandler(logging.Handler):
        def emit(self, _record: logging.LogRecord) -> None:
            raise RuntimeError("private handler failure")

    handler = BrokenHandler()
    logger.addHandler(handler)
    before = telemetry.dropped()
    try:
        with context.activate():
            answer_error(Unavailable("primary", "unreachable", "private detail"))
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    assert telemetry.dropped() == before + 1


def test_explicit_resource_validation_and_provider_fault_never_fall_back(monkeypatch) -> None:
    with pytest.raises(ValueError, match="required for explicit service_name"):
        telemetry.TelemetryContext(TelemetryNames(service_name="required"))
    other = TracerProvider(resource=Resource.create({"service.name": "other"}))
    with pytest.raises(ValueError, match="mismatched service.name"):
        telemetry.TelemetryContext(TelemetryNames(service_name="required"), tracer_provider=other)

    class NoTracerProvider:
        resource = Resource.create({"service.name": "required"})

    with pytest.raises(ValueError, match="expected get_tracer"):
        telemetry.TelemetryContext(
            TelemetryNames(service_name="required"), tracer_provider=NoTracerProvider()
        )

    class UnreadableTracerProvider:
        resource = Resource.create({"service.name": "required"})

        @property
        def get_tracer(self):
            raise RuntimeError("private provider sentinel")

    with pytest.raises(ValueError, match="unreadable get_tracer") as error:
        telemetry.TelemetryContext(
            TelemetryNames(service_name="required"), tracer_provider=UnreadableTracerProvider()
        )
    assert "sentinel" not in str(error.value)

    class BrokenProvider:
        resource = Resource.create({"service.name": "broken"})

        def get_tracer(self, _name: str):
            raise RuntimeError("private provider diagnostic")

    context = telemetry.TelemetryContext(
        TelemetryNames(service_name="broken"), tracer_provider=BrokenProvider()
    )
    global_provider = trace.get_tracer_provider()
    global_calls: list[str] = []

    def global_get_tracer(name: str, *args, **kwargs):
        global_calls.append(name)
        return global_provider.get_tracer(name, *args, **kwargs)

    monkeypatch.setattr(trace, "get_tracer", global_get_tracer)
    with context.activate():
        with telemetry.operation("arras.query", module="catalog"):
            assert 1 + 1 == 2
    assert trace.get_tracer_provider() is global_provider
    assert global_calls == []

    class EmptyTracerProvider:
        resource = Resource.create({"service.name": "empty"})

        def get_tracer(self, _name: str):
            return None

    empty_context = telemetry.TelemetryContext(
        TelemetryNames(service_name="empty"), tracer_provider=EmptyTracerProvider()
    )
    with empty_context.activate(), telemetry.operation("arras.query", module="catalog"):
        pass
    assert global_calls == []


def test_provider_comparison_failure_is_redacted() -> None:
    class BadComparison:
        def __eq__(self, _other: object) -> bool:
            raise RuntimeError("comparison-secret")

    class Provider:
        resource = type("ResourceLike", (), {"attributes": {"service.name": BadComparison()}})()

        def get_tracer(self, _name: str):
            return None

    with pytest.raises(ValueError, match="unreadable or mismatched") as error:
        telemetry.TelemetryContext(
            TelemetryNames(service_name="expected"), tracer_provider=Provider()
        )
    assert "comparison-secret" not in str(error.value)


def test_mcp_frame_uses_the_context_provider_and_event_projection() -> None:
    from arras.distribution import DistributionConfig
    from arras.mcp import McpServer
    from test_core import World

    context, exporter = _context("mcp-service", "mcp_host")
    selected = DistributionConfig(telemetry=context.names)
    world = World()
    server = McpServer(
        world.h,
        lambda: world.alice,
        distribution=selected,
        telemetry_context=context,
    )
    server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "query",
                "arguments": {
                    "module": "catalog",
                    "sql": "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
                },
                "_meta": {"traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"},
            },
        }
    )
    (span,) = [
        value for value in exporter.get_finished_spans() if value.name == "mcp_host.events.query"
    ]
    assert span.context is not None
    assert format(span.context.trace_id, "032x") == "0af7651916cd43dd8448eb211c80319c"


def test_mcp_failed_action_projects_error_attribute_and_status(monkeypatch) -> None:
    from arras.distribution import DistributionConfig
    from arras.fakes import MemoryStore
    from arras.mcp import McpServer
    from test_core import World

    context, exporter = _context("mcp-error-service", "mcp_error")
    world = World()
    server = McpServer(
        world.h,
        lambda: world.alice,
        distribution=DistributionConfig(telemetry=context.names),
        telemetry_context=context,
    )

    def fail_apply(self, *_args, **_kwargs):
        raise RuntimeError("backend-secret-sentinel")

    monkeypatch.setattr(MemoryStore, "apply", fail_apply)
    trace_id = "0af7651916cd43dd8448eb211c80319c"
    result = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "catalog_add_use_case",
                "arguments": {"inputs": {"code": "uc-error", "name": "Error"}},
                "_meta": {"traceparent": f"00-{trace_id}-b7ad6b7169203331-01"},
            },
        }
    )
    assert result is not None and result["result"]
    [span] = [
        value for value in exporter.get_finished_spans() if value.name == "mcp_error.events.invoke"
    ]
    assert span.context is not None
    assert format(span.context.trace_id, "032x") == trace_id
    assert (span.attributes or {})["error.type"] == "RuntimeError"
    assert span.status.status_code.name == "ERROR"
    assert "backend-secret-sentinel" not in str(span.attributes)


def test_wrapped_asgi_context_reaches_arras_worker_threads() -> None:
    import asyncio
    import json

    from arras.operate import create_app
    from test_core import World

    context, exporter = _context("http-service", "http_host")
    world = World()
    app = context.wrap_asgi(
        create_app(
            world.h,
            principal_for_request=lambda _request: world.alice,
            public_origin="https://ops.example",
        )
    )
    sent: list[dict[str, Any]] = []
    body = json.dumps(
        {
            "module": "catalog",
            "sql": "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
            "params": {},
        }
    ).encode()

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "method": "POST",
                "path": "/query",
                "headers": [
                    (b"origin", b"https://ops.example"),
                    (b"content-type", b"application/json"),
                ],
            },
            receive,
            send,
        )
    )
    assert sent[0]["status"] == 200
    assert any(span.name == "http_host.events.query" for span in exporter.get_finished_spans())


def test_interleaved_operate_apps_keep_provider_and_callback_context_separate() -> None:
    import asyncio
    import json

    from arras.operate import create_app
    from test_core import World

    alpha, exporter_alpha = _context("alpha-service", "alpha")
    beta, exporter_beta = _context("beta-service", "beta")
    worlds = (World(), World())
    seen: dict[str, list[tuple[str, telemetry.TelemetryContext | None]]] = {
        "alpha": [],
        "beta": [],
    }
    principal_barrier = threading.Barrier(2)
    operator_barrier = threading.Barrier(2)

    def make_app(label, world, context):
        def principal(request):
            seen[label].append(("principal", telemetry._active.get()))
            principal_barrier.wait(timeout=5)
            return world.alice if request.headers.get("x-user") == "alice" else None

        def is_operator(_principal):
            seen[label].append(("operator", telemetry._active.get()))
            operator_barrier.wait(timeout=5)
            return True

        return context.wrap_asgi(
            create_app(
                world.h,
                principal_for_request=principal,
                authorize_operator=is_operator,
                public_origin="https://ops.example",
            )
        )

    apps = (make_app("alpha", worlds[0], alpha), make_app("beta", worlds[1], beta))
    body = json.dumps(
        {
            "module": "catalog",
            "sql": "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
            "params": {},
        }
    ).encode()

    async def call(app) -> int:
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, object]:
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        await app(
            {
                "type": "http",
                "method": "POST",
                "path": "/query",
                "headers": [
                    (b"x-user", b"alice"),
                    (b"origin", b"https://ops.example"),
                    (b"content-type", b"application/json"),
                ],
            },
            receive,
            send,
        )
        return int(sent[0]["status"])

    async def interleave() -> list[int]:
        return list(await asyncio.gather(call(apps[0]), call(apps[1])))

    assert asyncio.run(interleave()) == [200, 200]
    assert seen == {
        "alpha": [("principal", alpha), ("operator", alpha)],
        "beta": [("principal", beta), ("operator", beta)],
    }
    assert any(span.name == "alpha.events.query" for span in exporter_alpha.get_finished_spans())
    assert any(span.name == "beta.events.query" for span in exporter_beta.get_finished_spans())


def test_operate_callback_fault_is_scoped_redacted_and_does_not_change_response() -> None:
    import asyncio

    from arras.operate import create_app
    from test_core import World

    context = telemetry.TelemetryContext(TelemetryNames(log_prefix="tenant"))
    app_base = create_app(
        (world := World()).h,
        principal_for_request=lambda request: (
            world.alice if request.headers.get("x-user") else None
        ),
        authorize_operator=lambda _principal: (_ for _ in ()).throw(
            RuntimeError("callback-secret-sentinel")
        ),
    )
    app = context.wrap_asgi(app_base)
    logger = logging.getLogger("tenant.operate")
    old_level = logger.level
    logger.setLevel(logging.ERROR)
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Capture()
    logger.addHandler(handler)

    class BrokenHandler(logging.Handler):
        def emit(self, _record: logging.LogRecord) -> None:
            raise RuntimeError("handler-secret-sentinel")

    broken_handler = BrokenHandler()
    logger.addHandler(broken_handler)

    async def request() -> list[dict[str, Any]]:
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, object]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        await app(
            {
                "type": "http",
                "method": "GET",
                "path": "/viewer",
                "headers": [(b"x-user", b"alice")],
            },
            receive,
            send,
        )
        return sent

    try:
        sent = asyncio.run(request())
    finally:
        logger.removeHandler(handler)
        logger.removeHandler(broken_handler)
        logger.setLevel(old_level)
    assert sent[0]["status"] == 200
    assert any(b'"modes": ["user"]' in bytes(sent[-1]["body"]) for _ in (0,))
    assert len(records) == 1 and records[0].name == "tenant.operate"
    assert records[0].getMessage() == "operate: authorize_operator failed: RuntimeError"
    assert "callback-secret-sentinel" not in records[0].getMessage()
    assert records[0].exc_info is None
    assert telemetry._active.get() is None


def test_console_worker_uses_custom_scope_for_execution_fault_log() -> None:
    import asyncio
    import json

    from arras.console import create_app
    from test_core import World

    context = telemetry.TelemetryContext(TelemetryNames(log_prefix="tenant"))
    world = World()
    app_base = create_app(
        world.h,
        principal_for_request=lambda request: (
            world.alice if request.headers.get("x-user") == "alice" else None
        ),
    )
    active: list[telemetry.TelemetryContext | None] = []

    def fail_execution(*_args, **_kwargs):
        active.append(telemetry._active.get())
        raise RuntimeError("console-worker-secret")

    app_base._execute = fail_execution
    app = context.wrap_asgi(app_base)
    logger = logging.getLogger("tenant.console")
    old_level = logger.level
    logger.setLevel(logging.ERROR)
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Capture()
    logger.addHandler(handler)

    async def request() -> list[dict[str, Any]]:
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, object]:
            return {
                "type": "http.request",
                "body": json.dumps({"query": "{ modules { name } }"}).encode(),
                "more_body": False,
            }

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        await app(
            {
                "type": "http",
                "method": "POST",
                "path": "/graphql",
                "headers": [(b"x-user", b"alice"), (b"content-type", b"application/json")],
            },
            receive,
            send,
        )
        return sent

    try:
        sent = asyncio.run(request())
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    body = bytes(sent[-1]["body"])
    assert sent[0]["status"] == 200 and b"INTERNAL_ERROR" in body
    assert active == [context]
    assert len(records) == 1 and records[0].name == "tenant.console"
    assert records[0].getMessage() == "console execution failed: RuntimeError"
    assert "console-worker-secret" not in records[0].getMessage() and records[0].exc_info is None


def test_asgi_wrapper_keeps_scope_through_awaited_stream_and_resets() -> None:
    import asyncio

    context, exporter = _context("stream-service", "stream")

    async def streaming_app(_scope, _receive, send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await asyncio.sleep(0)
        assert telemetry._active.get() is context
        with telemetry.operation("arras.query", module="catalog"):
            telemetry.annotate(rows=1)
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    sent: list[dict[str, Any]] = []

    async def run() -> None:
        async def receive() -> dict[str, object]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        await context.wrap_asgi(streaming_app)({"type": "http"}, receive, send)

    asyncio.run(run())
    assert len(sent) == 2
    (span,) = exporter.get_finished_spans()
    assert span.name == "stream.events.query"
    assert telemetry._active.get() is None


def test_cancelled_operate_request_finishes_in_selected_context_then_worker_resets() -> None:
    import asyncio
    import json
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from arras.fakes import MemoryStore
    from arras.operate import create_app
    from test_core import World

    context, exporter = _context("cancel-service", "cancelled")
    world = World()
    app_base = create_app(
        world.h,
        principal_for_request=lambda request: (
            world.alice if request.headers.get("x-user") else None
        ),
        public_origin="https://ops.example",
    )
    pool = ThreadPoolExecutor(max_workers=1)
    app_base.pool.shutdown(wait=True)
    app_base.pool = pool
    app = context.wrap_asgi(app_base)
    entered, release = threading.Event(), threading.Event()
    original_query = MemoryStore.query

    def blocked_query(self, *args, **kwargs):
        entered.set()
        if not release.wait(5):
            raise TimeoutError("worker release timed out")
        return original_query(self, *args, **kwargs)

    MemoryStore.query = blocked_query
    body = json.dumps(
        {
            "module": "catalog",
            "sql": "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
            "params": {},
        }
    ).encode()

    async def cancelled_request() -> None:
        async def receive() -> dict[str, object]:
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(_message: dict[str, object]) -> None:
            return None

        task = asyncio.create_task(
            app(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/query",
                    "headers": [
                        (b"x-user", b"alice"),
                        (b"origin", b"https://ops.example"),
                        (b"content-type", b"application/json"),
                    ],
                },
                receive,
                send,
            )
        )
        while not entered.is_set():
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    try:
        asyncio.run(cancelled_request())
        assert exporter.get_finished_spans() == ()
        release.set()
        assert pool.submit(lambda: telemetry._active.get()).result(timeout=5) is None
        spans = exporter.get_finished_spans()
        assert any(span.name == "cancelled.events.query" for span in spans)
    finally:
        release.set()
        MemoryStore.query = original_query
        pool.shutdown(wait=True, cancel_futures=True)


def test_operate_diagnostic_projects_route_without_raw_exception_details(caplog) -> None:
    from arras.errors import Unavailable
    from arras.operate.wire import answer_error

    secret = "private-backend-detail-sentinel"
    context = telemetry.TelemetryContext(TelemetryNames(log_prefix="tenant.ops"))
    caplog.set_level(logging.DEBUG)
    with context.activate():
        answer_error(Unavailable("primary", "unreachable", secret))
    selected = [r for r in caplog.records if r.name == "tenant.ops.operate"]
    assert selected and all(secret not in r.getMessage() for r in selected)
    assert all(not r.exc_info for r in selected)


def test_telemetry_names_are_bounded_and_context_names_are_immutable() -> None:
    for values in (
        {"attribute_namespace": "Upper"},
        {"log_prefix": "space "},
        {"event_prefix": "x" * 65},
        {"service_name": " name"},
    ):
        with pytest.raises(ValueError):
            TelemetryNames(**values)
    context = telemetry.TelemetryContext()
    with pytest.raises((AttributeError, TypeError)):
        context.names = TelemetryNames(log_prefix="changed")  # type: ignore[misc]
