---
ddx:
  id: US-057
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-09
  authoring:
    home: repo
  links:
    - id: FEAT-006
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-057: Observe operations without leaking content

**Feature**: FEAT-006 — Embedding and Lifecycle
**Feature Requirements**: EMB-07
**PRD Requirements**: FR-49
**Priority**: P1
**Status**: Draft

## Story

**As a** Platform owner
**I want** each read, change, refusal and backend change to be visible in the host's own tooling, with nothing that identifies a person's data
**So that** I can tell what was asked of which backend, how it ended and when a backend went down

## Context

Arras emits named events to the host's logger and, when OpenTelemetry is installed, spans on the host's tracer provider (CONTRACT-008). It owns no exporter, collector or log file. Attributes are allowlisted: no inputs, keys, query text, tokens or user names. In the MCP process a caller's `traceparent` continues across the stdio boundary and nothing is written to stdout.

## Walkthrough

1. A person invokes an action and reads.
2. The host sees an event and a span for each, with the action, module, backend and outcome.
3. A backend goes down; the host sees one warning, and one event when it returns.

## Acceptance Criteria

- [ ] **US-057-AC1** — Given an invocation, a read and an outage, when each ends, then one event and one span state its operation, backend and outcome.
- [ ] **US-057-AC2** — Given a sensitive value in an input, a key or a query, when any operation runs, then the value is in no log record and no span.
- [ ] **US-057-AC3** — Given a tool call with a valid `traceparent`, when it runs, then its spans share the caller's trace; with none, no trace id is invented.
- [ ] **US-057-AC4** — Given a backend's availability, when it is probed repeatedly, then a change is reported once.
- [ ] **US-057-AC5** — Given telemetry that fails, when an operation runs, then the operation is unaffected and the loss is counted.
- [ ] **US-057-AC6** — Given any operation, when it runs, then nothing is written to stdout.

## Edge Cases

- **OpenTelemetry not installed**: the same events are log records
- **An event name outside the catalog**: not emitted, counted as dropped

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Span per operation | US-057-AC1 | invoke, read, outage | Run with a real OTel receiver | One span each with safe attributes |
| Secret injection | US-057-AC2 | a secret in input, key and query | Run every operation | Absent from every sink |
| Trace continues | US-057-AC3 | `_meta.traceparent` on a tool call | Call a tool | Spans share the trace id |
| Status once | US-057-AC4 | three probes, one outage | Probe | One event per change |
| Failure isolated | US-057-AC5 | extraction raises | Run an operation | Result unchanged, loss counted |
| Stdout clean | US-057-AC6 | reads, changes, probes | Capture stdout | Empty |
