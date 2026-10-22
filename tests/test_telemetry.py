# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Telemetry (CONTRACT-008): the events, the spans, what never leaves, and what never breaks."""

from __future__ import annotations

import logging
from typing import Any, NamedTuple

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from arras import Invalid, PreconditionFailed, Unavailable, telemetry
from arras.mcp import McpServer
from test_core import World

SECRET = "s3cret-token-VALUE"
LISTING = "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100"

_exporter = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_exporter))
trace.set_tracer_provider(_provider)  # once per process, as a host does


@pytest.fixture
def spans():
    _exporter.clear()
    return _exporter


@pytest.fixture
def records(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.DEBUG, logger="arras.telemetry")
    return caplog


class Event(NamedTuple):
    arras_event: str
    arras_attrs: dict[str, Any]
    levelno: int
    message: str

    def getMessage(self) -> str:
        return self.message


def events(caplog: pytest.LogCaptureFixture) -> list[Event]:
    return [
        Event(
            r.__dict__["arras_event"],
            r.__dict__["arras_attrs"],
            r.levelno,
            r.getMessage(),
        )
        for r in caplog.records
        if r.name == "arras.telemetry"
    ]


def test_an_invocation_is_a_span_with_safe_attributes(spans, records) -> None:
    w = World()
    w.o.invoke("catalog.AddUseCase", {"code": "uc-1", "name": SECRET}, idempotency_key=SECRET)
    (span,) = [s for s in spans.get_finished_spans() if s.name == "arras.invoke"]
    assert dict(span.attributes) == {
        "arras.action": "catalog.AddUseCase",
        "arras.module": "catalog",
        "arras.replayed": False,
        "arras.outcome": "ok",
    }
    assert span.status.status_code != trace.StatusCode.ERROR


def test_a_read_states_the_backend_and_consistency_it_was_served_at(spans, records) -> None:
    w = World()
    w.o.invoke("catalog.AddUseCase", {"code": "a", "name": "A"})
    w.read(LISTING)
    (span,) = [s for s in spans.get_finished_spans() if s.name == "arras.query"]
    a = span.attributes
    assert (a["arras.backend"], a["arras.consistency"], a["arras.rows"]) == (
        "primary",
        "latest",
        1,
    )
    assert a["arras.truncated"] is False
    assert a["arras.module"] == "catalog"  # the module the caller named, once it is known


def test_a_refusal_is_an_error_outcome_with_its_type_and_no_message(spans, records) -> None:
    w = World()
    w.o.invoke("catalog.AddUseCase", {"code": "a", "name": "A"})
    with pytest.raises(PreconditionFailed):
        w.o.invoke("catalog.AddUseCase", {"code": "a", "name": "A"})
    failed = [s for s in spans.get_finished_spans() if s.attributes["arras.outcome"] == "error"]
    assert [s.attributes["error.type"] for s in failed] == ["PreconditionFailed"]
    assert failed[0].status.status_code != trace.StatusCode.ERROR  # the caller's outcome, not ours


def test_an_outage_is_a_warning_and_an_error_span_with_its_reason(spans, records) -> None:
    w = World()
    w.auth.available = False
    with pytest.raises(Unavailable):
        w.read(LISTING)
    (span,) = [s for s in spans.get_finished_spans() if s.name == "arras.query"]
    assert span.status.status_code == trace.StatusCode.ERROR and span.status.description is None
    assert span.attributes["arras.reason"] == "unreachable"
    assert [r.levelno for r in events(records) if r.arras_event == "arras.query"] == [
        logging.WARNING
    ]


def test_a_backend_change_is_said_once_not_on_every_probe(records) -> None:
    w = World()
    w.h.status()
    w.h.status()
    w.auth.available = False
    w.h.status()
    w.h.status()
    w.auth.available = True
    w.h.status()
    seen = [
        (r.arras_attrs["backend"], r.arras_attrs["available"])
        for r in events(records)
        if r.arras_event == "arras.backend.status"
    ]
    assert seen == [("primary", True), ("mirror", True), ("primary", False), ("primary", True)]


def test_no_secret_reaches_a_span_or_a_log_record(spans, records) -> None:
    w = World()
    w.o.invoke("catalog.AddUseCase", {"code": "a", "name": SECRET}, idempotency_key=SECRET)
    w.read(
        f"SELECT u.code FROM catalog.UseCase u WHERE u.name = '{SECRET}' ORDER BY u.code LIMIT 100"
    )
    w.o.validate("catalog.AddUseCase", {"code": SECRET, "name": SECRET})
    w.o.invoke_batch("catalog.AddUseCase", [{"code": "b", "name": SECRET}])
    emitted = [str(s.attributes) + str(s.name) for s in spans.get_finished_spans()]
    emitted += [r.getMessage() + str(r.arras_attrs) for r in events(records)]
    assert emitted and not any(SECRET in e or w.alice.token in e or "alice" in e for e in emitted)


def test_a_schema_validate_and_register_name_the_module_and_never_the_document(
    spans, records
) -> None:
    import json

    from arras.testing import InMemory, example_module

    w = InMemory()
    w.register(example_module())
    d = json.loads(example_module())
    d["modules"][0]["elements"][0]["description"] = SECRET  # text the document carries
    text = json.dumps(d)
    ana = w.arras.session(w.person("ana", "catalog", "read", "schema"))
    ana.schema().validate(text)
    ana.schema().register(text)
    names = {s.name for s in spans.get_finished_spans()}
    assert {"arras.schema_validate", "arras.schema_register"} <= names
    emitted = [str(s.attributes) + s.name for s in spans.get_finished_spans()]
    emitted += [r.getMessage() + str(r.arras_attrs) for r in events(records)]
    assert any("schema_register" in e for e in emitted)
    assert not any(SECRET in e or "ana" in e or "token-ana" in e for e in emitted)


def test_only_allowlisted_safe_attributes_are_kept() -> None:
    kept = telemetry.clean(
        {
            "module": "catalog",
            "action": "catalog.A",
            "key": "uc-1",  # not on the list
            "reason": "has a space",  # not a safe value
            "backend": "x" * 65,  # too long
            "rows": 3,
            "available": False,
            "error.type": "Unavailable",
            "items": object(),  # not a scalar
        }
    )
    assert kept == {
        "module": "catalog",
        "action": "catalog.A",
        "rows": 3,
        "available": False,
        "error.type": "Unavailable",
    }


def test_nothing_is_written_to_stdout(capsys: pytest.CaptureFixture[str], records) -> None:
    w = World()
    w.o.invoke("catalog.AddUseCase", {"code": "a", "name": "A"})
    w.read(LISTING)
    w.h.status()
    assert capsys.readouterr().out == ""


def test_telemetry_that_fails_never_fails_the_operation() -> None:
    def explode(*_a: object, **_k: object) -> dict[str, object]:
        raise RuntimeError("attribute extraction broke")

    @telemetry.traced("arras.query", explode, explode)
    def op() -> int:
        return 7

    before = telemetry.dropped()
    assert op() == 7
    assert telemetry.dropped() > before  # and the loss is counted

    @telemetry.traced("not.in.the.catalog")
    def other() -> int:
        return 8

    assert other() == 8


def test_the_callers_trace_is_the_parent_of_a_tool_call(spans) -> None:
    w = World()
    server = McpServer(w.h, lambda: w.alice)
    trace_id = "0af7651916cd43dd8448eb211c80319c"
    parent = f"00-{trace_id}-b7ad6b7169203331-01"
    server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "query",
                "arguments": {"module": "catalog", "sql": LISTING},
                "_meta": {"traceparent": parent},
            },
        }
    )
    ours = [s for s in spans.get_finished_spans() if s.name == "arras.query"]
    assert ours and {format(s.context.trace_id, "032x") for s in ours} == {trace_id}


def test_without_a_valid_traceparent_no_trace_id_is_made_up(spans) -> None:
    w = World()
    server = McpServer(w.h, lambda: w.alice)
    server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "query",
                "arguments": {"module": "catalog", "sql": LISTING},
                "_meta": {"traceparent": "x"},
            },
        }
    )
    ours = [s for s in spans.get_finished_spans() if s.name == "arras.query"]
    assert ours and all(s.parent is None for s in ours)


def test_without_opentelemetry_installed_the_events_still_log(
    monkeypatch: pytest.MonkeyPatch, records, spans
) -> None:
    monkeypatch.setattr(telemetry, "_otel", lambda name: None)
    w = World()
    w.o.invoke("catalog.AddUseCase", {"code": "a", "name": "A"})
    assert spans.get_finished_spans() == ()
    assert [r.arras_event for r in events(records) if "invoke" in r.arras_event] == ["arras.invoke"]
    with telemetry.remote_parent({"traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01"}):
        pass


def test_what_a_caller_typed_is_never_an_attribute(spans, records) -> None:
    w = World()
    typed = "MAT-2024-0042_acme"  # short, and every character is a safe one
    with pytest.raises(Invalid):
        w.read(LISTING, consistency=typed)
    with pytest.raises(Invalid):
        w.o.invoke(f"catalog.{typed}", {})
    with pytest.raises(Invalid):
        w.o.validate(f"{typed}.Add", {})
    emitted = [str(s.attributes) for s in spans.get_finished_spans()]
    emitted += [str(r.arras_attrs) + r.message for r in events(records)]
    assert emitted and not any(typed in e for e in emitted)
    # a name the registry resolved is not what a caller typed, and is kept
    w.o.invoke("catalog.AddUseCase", {"code": "a", "name": "A"})
    assert any(r.arras_attrs.get("action") == "catalog.AddUseCase" for r in events(records))


def test_a_log_record_states_its_duration(records) -> None:
    w = World()
    w.o.invoke("catalog.AddUseCase", {"code": "a", "name": "A"})
    (done,) = [r for r in events(records) if r.arras_event == "arras.invoke"]
    assert "duration_ms=" in done.message and isinstance(done.arras_attrs["duration_ms"], int)


def test_an_unlisted_reason_is_reported_as_other(spans) -> None:
    w = World()
    w.auth.outage = "host:port refused"  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(Unavailable):
        w.read(LISTING)
    (span,) = [s for s in spans.get_finished_spans() if s.name == "arras.query"]
    assert span.attributes["arras.reason"] == "other"


def test_an_interrupt_still_ends_the_span_and_is_not_an_error(spans, records) -> None:
    with pytest.raises(KeyboardInterrupt):
        with telemetry.operation("arras.query"):
            raise KeyboardInterrupt
    (span,) = spans.get_finished_spans()
    assert span.status.status_code != trace.StatusCode.ERROR
    assert [r.levelno for r in events(records)] == [logging.INFO]
    assert (
        trace.get_current_span() is trace.INVALID_SPAN
        or not trace.get_current_span().is_recording()
    )


def test_a_backend_state_is_said_once_even_when_probed_together() -> None:
    import threading

    w = World()
    seen: list[str] = []
    real = telemetry.emit
    telemetry.emit = lambda event, **a: seen.append(event)  # type: ignore[assignment]
    try:
        gate = threading.Barrier(8)

        def probe() -> None:
            gate.wait()
            w.h.status()

        threads = [threading.Thread(target=probe) for _ in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
    finally:
        telemetry.emit = real
    assert len(seen) == 2  # the store and the replica, once each


def test_a_refusal_or_a_wait_names_the_backend_that_raised_it(spans) -> None:
    from arras import NotYetCurrent, Unsupported
    from arras.fakes_weft import ENTITY, WEFT
    from arras.results import WeftSupport

    w = World()
    w.auth.weft = WeftSupport(WEFT.version, (ENTITY,))
    with pytest.raises(Unsupported):
        w.read(
            "SELECT u.name, COUNT(*) FROM catalog.UseCase u GROUP BY u.name ORDER BY u.name LIMIT 5"
        )
    token = w.o.invoke("catalog.AddUseCase", {"code": "b", "name": "B"}).token
    with pytest.raises(NotYetCurrent):
        w.read(LISTING, consistency="bulk", at_least=token)
    failed = [s for s in spans.get_finished_spans() if s.name == "arras.query"]
    assert [(s.attributes["error.type"], s.attributes["arras.backend"]) for s in failed] == [
        ("Unsupported", "primary"),
        ("NotYetCurrent", "mirror"),
    ]
