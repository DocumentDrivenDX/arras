---
ddx:
  id: CONTRACT-008
  type: contract
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-22
  authoring:
    home: repo
  links:
    - id: FEAT-006
      kind: informed_by
    - id: ADR-005
      kind: constrained_by
    - id: ADR-016
      kind: informed_by
    - id: ADR-018
      kind: informed_by
    - id: CONTRACT-001
      kind: informed_by
    - id: CONTRACT-005
      kind: informed_by
    - id: CONTRACT-007
      kind: informed_by
---

# Contract: Telemetry

**Contract ID**: CONTRACT-008
**Type**: signals emitted by the library
**Version**: v1
**Status**: draft
**Related**: FEAT-006, ADR-005, ADR-018, CONTRACT-001, CONTRACT-005, CONTRACT-007

## Purpose

Defines what Arras says about its own operation: which events it emits, which attributes they may carry, how they map to OpenTelemetry (OTel, the vendor-neutral standard for traces, metrics and logs), and what never leaves. A host or an operator uses them to see which backend served a read, how a change ended and when a backend went down, with the host's own tooling.

Terms. A span is one timed operation in a trace. W3C Trace Context is the standard `traceparent` header that carries a trace across processes. ADR-005 is the decision record that keeps structure derived from sensitive source records out of Arras. A backend is a named store with the roles reader and provider.

## Scope and Boundaries

- In scope: the event catalog, attributes, severity, the OTel mapping, trace continuation over MCP, redaction and loss.
- Out of scope: exporters, collectors, retention and dashboards (the host's); metrics; audit and usage records, which need their own durability and are not telemetry.
- Owning system or team: Arras. A host that embeds the library owns every sink.

## Normative Surface

**Emission.** Each event is one record to the standard library logger `arras.telemetry`, with `extra` carrying `arras_event` and `arras_attrs`. When `opentelemetry-api` is importable, an operation is also a span of the same name on the host's tracer provider (`trace.get_tracer("arras")`). Nothing is written to stdout, a file or a network.

| Event | When | Attributes besides `outcome` |
|-------|------|------------------------------|
| `arras.query` | A `query` ends | `consistency`, `module` once it is resolved; on success `backend`, `rows`, `truncated`; on `Unavailable` `backend`, `reason`; on `NotYetCurrent`, `Unsupported` or any other error raised by a backend, `backend` names the backend last asked (`Unsupported` carries no backend field of its own, so the attribute is the only place it is named); a `bulk` read that falls through to the record store is visible as `backend` |
| `arras.validate` | A `validate` ends | `action`, `module`; on success `valid`; `backend` and `recovered` when the backend names them (below); a validate is a dry-run apply on the provider, so `recovered` is always `false` for it |
| `arras.invoke` | An `invoke` ends | `action`, `module`; on success `replayed`; `backend` and `recovered` when the backend names them (below) |
| `arras.invoke_batch` | An `invoke_batch` ends | `action`, `module`, `atomic`, `items`; on success `succeeded`, `failed`; `backend` and `recovered` as for `arras.invoke` |
| `arras.import_records`, `arras.export_records` | An import or an export page ends | `module`; `backend` when the backend names it (below) |
| `arras.migrate` | A `Arras.migrate()` ends (CONTRACT-005) | none besides `outcome`; on `Unavailable` `backend`, `reason` |
| `arras.register`, `arras.attach` | A registration ends | on success `module` |
| `arras.schema_validate`, `arras.schema_register` | A person's validate-only registration or registration ends (CONTRACT-002, `session.schema()`) | on success `module`; never the document |
| `arras.changes`, `arras.loads` | An audit read ends | `module` once it is resolved |
| `arras.search` | A `search` ends | on success `rows` (the hits returned) and `truncated`; never the text, a word, a type or a key |
| `arras.document` | A `document` read ends | `module` and `backend` once the module is resolved (never the name a caller typed) |
| `arras.backend.migrate`, `arras.backend.configure_access` | An adapter's install-or-verify or module-access call ends (the Truss adapter; each is a child of `arras.migrate` when run through it) | `backend`; on `Unavailable` `reason`. Never a role name, a document name, a release or an installation id |
| `arras.backend.status` | A backend's availability changed since it was last reported, and its first report | `backend`, `available`, `reason` |

`outcome` is `ok` or `error`. On `error`, `error.type` is the exception's class name and never its message.

**Attributes.** The only attributes that may be emitted are `module`, `action`, `backend`, `consistency`, `outcome`, `reason`, `replayed`, `recovered`, `committed`, `atomic`, `valid`, `available`, `items`, `succeeded`, `failed`, `rows`, `truncated`, `duration_ms` (log records only; a span has its own duration) and `error.type`. A value is a boolean, an integer, or a string of at most 64 characters from letters, digits and `_ . : -`. Anything else is dropped. On spans the names are `arras.<name>`, except `error.type`, which is the OTel semantic convention of that name (pinned to semantic conventions v1.27 with `opentelemetry-api` 1.27 or later, below 2).

**Adapter calls.** An adapter's per-person call (a query, an apply, a batch, an import, an export, a `reached` wait) does not open an operation of its own: core already observes it, so the adapter names itself on the operation that is running (`backend`, whatever the outcome, so a `Conflict` or a `PreconditionFailed` from it carries the backend too). An adapter that recovers a commit whose outcome was unknown (the Truss adapter's retry of the same request, CONTRACT-004) sets `recovered`: `true` when recovery ran, `false` when it did not. A receipt for such a write has `replayed=false`, because this invocation wrote it; a keyed repeat that Truss answers from its record is `replayed=true`. The adapter's own repeat of a request to obtain the receipt token opens no event of its own. When both repeats fail after the write committed, the adapter sets `committed=true` on the running operation before it raises `Unavailable`, so the `arras.invoke` or `arras.invoke_batch` event (`outcome=error`, `reason=unreachable`) is told apart from a write that never landed: the write stands and a keyless caller cannot retry (CONTRACT-004). `committed` is absent otherwise. Lifecycle calls that no core operation observes are events of the backend (the `arras.backend.*` rows). None carries a request id, an idempotency key, a role, a token or an input.

**Severity.** A successful operation is DEBUG, including a `validate` that reports a failed precondition (`valid=false`): the validation itself succeeded. A refusal, or an invocation that fails a precondition (an outcome the caller can act on), is INFO. `Unavailable` and a backend becoming unavailable are WARNING. An exception that is not an Arras error is ERROR; an interrupt (`KeyboardInterrupt`, `SystemExit`) is INFO and does not mark the span as an error. A backend becoming available again is INFO.

**Spans.** A span's status is ERROR for `Unavailable` and for an unexpected exception, with no description, and unset for any other Arras error, which is the caller's outcome. Exceptions are not recorded on spans. Status probes do not create spans.

**Trace continuation.** The MCP binding reads `params._meta.traceparent` (and `tracestate`) of a `tools/call` and makes it the parent of the spans that call produces. A missing or invalid header leaves the call a root: a trace id is never invented. Without OTel installed this is a no-op.

**Redaction.** Attributes that name an action, module or consistency level are set only after the library has resolved them (a registered action's own name, a checked level), never from what a caller typed, so a request naming something unregistered carries none of its text. Entity keys, property values, query text, parameters, idempotency keys, tokens, user names and groups are never attributes, whatever a caller passes. The allowlist is the only gate, and it applies to the log record and the span alike.

**Other log lines.** A log line that is not a telemetry event carries the exception's class name and never its message or traceback; the MCP server's lines may also name the method or tool called. A request the MCP binding refuses as a protocol error (an unknown tool or method, malformed parameters) is answered with a JSON-RPC error and produces no event or span. An argument that does not convert is a failed `arras.invoke` event with `error.type=Invalid`.

**Reasons.** `reason` is one of `not_configured`, `unreachable`, `access_denied`, `migration_failed`, `unsupported_version`, or `other`: a backend's own wording is never emitted.

**Loss.** Telemetry never raises into the operation it observes. A signal that could not be emitted is counted, readable as `arras.telemetry.dropped()`. Arras does not sample.

### Optional host-scoped naming projection

CONTRACT-005 binds `TelemetryNames`, `TelemetryContext`, launcher factories and
ASGI composition. This is an additive v1 option; without it the names, logger
records, attributes, severities, counts and global-API fallback above are unchanged.
Canonical `EVENTS`, allowlisted attribute suffixes, `arras` tracer instrumentation
scope and log record origin keys remain stable. Only the selected host context's
output is projected, once, **after** event membership and `clean` default-deny
validation:

| Output | Selected projection | Stable identity |
| --- | --- | --- |
| Span name and telemetry log event/message prefix | Replace the initial `arras.` of a catalogued event with `<event_prefix>.` | The canonical event remains in `arras_event`; unknown events are still dropped |
| Span attribute name | `<attribute_namespace>.<allowlisted-suffix>` | `error.type` stays the OTel semantic-convention name; suffix allowlist and safe values are unchanged |
| Telemetry logger route | `<log_prefix>.telemetry` | `arras_attrs` keeps its current sanitized suffix-keyed mapping; no duplicate alias record |
| Other Arras diagnostic logger route | Replace only initial `arras` with `log_prefix` | Existing suffix/message/severity rules remain; no arbitrary logger names or global record rewrite |
| Resource `service.name` | Exact explicit value on the caller-owned provider Resource | Never a span attribute substitute or inferred person/service identity |

The diagnostic creation sites are `operate/wire.py`, `operate/schema_app.py`,
`operate/__init__.py`, `mcp/process.py`, `mcp/server.py`, `sandbox.py` and
`console/__init__.py` (seven besides `telemetry.py`). A small private context-aware
logger route may implement this; it must not add handlers, change unrelated host
loggers, duplicate records or change canonical default messages. Names are bounded
configuration values, not a new attribute-content escape hatch. Do not emit the
Brand, namespace configuration object, provider exceptions, credentials, inputs,
raw data or principal identity as additional attributes.

Each operation retains its entry context/provider through completion; immediate
events and diagnostics use the active context. Nested/concurrent hosts must route
to their own names and providers, and reset after failure. The host owns SDK/exporter
lifecycle. Explicit-service/provider mismatch is a pre-operation configuration
refusal; failures while acquiring a tracer, recording, finishing or exporting must
not change business results or route a signal to another host/global fallback.
Existing dropped-signal accounting remains readable. Existing diagnostic sites
that use `exc_info`, `log.exception` or raw exception/detail interpolation must be
changed to fixed safe labels plus exception class only; selecting a new route
does not qualify an existing leak as redacted. Actual sensitive principal/operator
callback and execution/provider-fault tests must capture DEBUG logs as well as
normal severity and assert no message, traceback or sentinel reaches any route.

Arras-owned executor submissions must explicitly carry a fresh copied context
for each submission. Actual worker-backed console/operator receiver tests must
prove the caller context reaches principal/operator callbacks and execution,
including completion after caller cancellation without cross-host routing.
No SDK or provider is a valid
log-only mode only when no explicit service name requires a matching Resource.

Actual SDK receiver tests MUST prove two concurrently interleaved contexts with
different Resource service names, event/attribute/log prefixes, and no global
provider mutation; nested restoration and finish-time snapshot behavior; default
compatibility; rejection of invalid names/provider mismatch before work; unchanged
traceparent/error/status semantics; and sensitive/unknown-value default denial in
both logs and exported spans. Inject failing provider/logger/exporter paths and
assert business results remain unchanged. A fresh installed public consumer must
construct both host-owned SDK providers and exercise public direct-library, MCP
and ASGI contexts without private imports or source checkout fallback. Source-only
name assertions or a span `service.name` attribute do not qualify this requirement.

## Precedence and Compatibility

- Versioning: v1. Adding an event or an attribute is compatible; removing or renaming one is breaking.
- A host that configures no handler and no provider sees nothing, at no cost beyond a lookup.

## Error Semantics

| Condition | Outcome | Recovery |
|-----------|---------|----------|
| An event name outside the catalog | Not emitted, counted as dropped | Add it to the catalog |
| OTel not installed or a provider not set | Log records only | Install `arras[otel]` and set a provider |
| A sink fails | The operation is unaffected | The host's sink |

## Examples

```python
logging.getLogger("arras.telemetry").addHandler(handler)   # the host's own
# a span on the host's provider:
# arras.invoke  arras.action=catalog.AddUseCase arras.outcome=ok arras.replayed=false
```

## Non-Normative Notes

Latency distributions and error rates are derived by the host from the spans. Per-signal sampling is the host's.
