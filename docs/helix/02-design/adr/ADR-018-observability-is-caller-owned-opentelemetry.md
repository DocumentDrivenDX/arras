---
ddx:
  id: ADR-018
  type: adr
  activity: design
  status: accepted
  owner: Erik LaBianca
  updated: 2026-10-22
  authoring:
    home: repo
  links:
    - id: ADR-005
      kind: constrained_by
    - id: ADR-016
      kind: informed_by
    - id: ADR-017
      kind: informed_by
    - id: CONTRACT-008
      kind: informs
    - id: CONTRACT-007
      kind: informs
---

# ADR-018: Observability is caller-owned OpenTelemetry

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-09 | Accepted | Erik LaBianca (architecture lead) | [ADR-005](ADR-005-durable-knowledge-state.md), [ADR-016](ADR-016-mcp-stdio-binding-over-the-library.md), [ADR-017](ADR-017-backends-are-reached-with-the-users-own-token.md) | Medium |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | Arras exists to state what a read is (its consistency and freshness) and to attribute every change. An operator cannot see any of it while it runs: which backend served a read, how stale it was, why a backend went unavailable, which change was refused and why. Arras is a library inside the embedding application and a stdio process beside it, so it cannot own an exporter, a collector or a log file. |
| Requirements | A host or an operator can answer, after a failure, what was asked, of which backend, with what outcome and how long it took, without Arras holding a sink. Nothing that identifies a person's data leaves: ADR-005 keeps sensitive source records out, and ADR-017 makes the user's token the person's own. |
| Decision Drivers | OpenTelemetry (OTel) is the telemetry model the concern `o11y-otel` names; a library accepts caller-owned instrumentation; the MCP process's stdout carries protocol frames only. |

## Decision

Arras emits **named events with a few allowlisted attributes**, to the standard library logger `arras.telemetry` and, when `opentelemetry-api` is importable, as spans on the host's tracer provider. The host owns the logging handlers, the provider, the exporter and the collector. The catalog of events, the attributes and the rules are CONTRACT-008.

**Key Points**:
1. **No sink of its own.** No exporter, collector, log file or metric registry. The OTel API is an optional extra (`arras[otel]`); without it the same events are log records.
2. **Default-deny attributes.** Only the allowlist in CONTRACT-008 is emitted, and only short values of safe characters. Inputs, entity keys, query text, tokens and user names cannot reach a sink, even when passed by mistake.
3. **Telemetry never fails an operation.** It catches its own errors and counts a signal it could not emit, so a quiet sink is not read as a healthy system.
4. **Never stdout.** The MCP binding's diagnostics go to stderr.
5. **The caller's trace continues across the stdio boundary.** An MCP request's `_meta.traceparent` becomes the parent of the spans a tool call produces. With no valid header there is no trace id; one is never made up.
6. **Transitions are said once.** A backend's availability is reported when it changes, not on every probe.

### Scoped downstream names preserve caller ownership

CONTRACT-005/008 add immutable distribution telemetry names and an explicit
`TelemetryContext`. Output aliases for attribute namespaces and event/log prefixes
are applied after the existing allowlists; canonical definitions and default output
remain unchanged. This fulfills generic downstream naming without a fork or a
second instrumentation stack. No global provider/logger mutation is permitted.

`service.name` belongs to the OpenTelemetry **Resource**, not to span attributes.
An explicit name therefore requires a caller-owned provider with that exact Resource
attribute; missing/mismatched Resource information refuses before observed work.
A launcher accepts a host factory only after validated effective ADR-019 naming is
available. The factory constructs/configures the provider and exporters; Arras only
uses it in a context-local scope and never shuts it down. Without an explicit name
or provider, prior optional global-API behavior remains available.

ASGI dispatch and MCP serve/frame scopes carry that selection through awaited work;
operations retain their entry selection through finish. Detached tasks/threads need
explicit host activation. Default-deny values and failure isolation apply equally to
projected output. Qualification requires actual independent SDK receiver Resources,
concurrent/nested context restoration and an installed public consumer, rather than
an assertion that a configured string or span attribute changed a service Resource.

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| Arras configures an OTel SDK and exporter | Works out of the box | A library that owns a collector route fights the host's; a hard SDK dependency in a shared app | Rejected |
| Plain logging only, no OTel | No dependency | No traces across the embedding host, the MCP process and Arras | Rejected as the only route; kept as the fallback |
| **Events to the logger, spans through the optional API** | Host decides; one emission; no dependency required | Two projections to keep consistent | **Selected** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | Reads, changes, refusals and outages are visible with the host's own tooling; the ADR-005 line holds by construction. |
| Negative | The allowlist is a deliberate limit: an operator cannot see which entity a failure concerned. |
| Neutral | Metrics are not emitted; a host derives rates from the spans. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| A new attribute leaks content | L | H | The allowlist is the only gate and a test injects sensitive values into every operation and asserts their absence in every sink |
| Instrumentation slows a read | L | M | A no-op tracer costs a lookup; spans are not created for status probes |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| Every operation in CONTRACT-008's catalog yields one event, and one span when OTel is present | An operation is added without an event |
| No test value reaches a log record or a span | One does |

## References

- [CONTRACT-008](../contracts/CONTRACT-008-telemetry.md), [CONTRACT-007](../contracts/CONTRACT-007-mcp-binding.md)
