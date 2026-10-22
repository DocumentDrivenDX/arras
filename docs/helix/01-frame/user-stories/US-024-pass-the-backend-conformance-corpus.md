---
ddx:
  id: US-024
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-004
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-024: Pass the shared backend conformance corpus

**Feature**: FEAT-004 — Backends
**Feature Requirements**: BE-04
**PRD Requirements**: FR-25
**Priority**: P0
**Status**: Draft

## Story

**As a** Backend implementer
**I want** to run a corpus that every adapter must pass for the operations they declare
**So that** backends are interchangeable by evidence

## Context

The corpus is data: setup, calls and expected results, errors and freshness, tagged by backend role (reader or provider). Every adapter (Truss, Ashlar and memory) runs it (CONTRACT-004, the backend contract).

## Walkthrough

1. Implementer loads the corpus.
2. Implementer runs each case against the adapter.
3. The system compares results, errors and freshness.
4. The system reports each failing case.

## Acceptance Criteria

- [ ] **US-024-AC1** — Given the corpus, when an adapter with the provider role runs it, then every case for the operations it declares passes: key lookups, lists, `HAS_RELATED`, `RELATED_KEYS`, `alias.*` with appended fact columns, counts and keyset paging; actions, idempotency, bulk changes and import.
- [ ] **US-024-AC2** — Given a replica adapter, when it runs the corpus, then reads, consistency, positions and unsupported capabilities pass.
- [ ] **US-024-AC3** — Given a case that asks for `latest`, when a replica would answer, then the adapter fails the case unless it refuses.
- [ ] **US-024-AC4** — Given empty, not permitted and unavailable, when each is provoked, then the three outcomes are distinct.
- [ ] **US-024-AC5** — Given a call with no token or an expired one, when it runs, then it is refused and never answered from a shared identity.
- [ ] **US-024-AC6** — Given the memory adapter's backends, when they run the corpus, then every case for the operations they declare passes.

## Edge Cases

- A host-specific case: tagged and outside the pass rule.
- A newer corpus than the adapter: reported, never silently passed.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Provider | US-024-AC1 | Truss adapter and `memory` | Run the provider cases | All cases for declared operations pass |
| Reader | US-024-AC2 | Ashlar adapter and `memory_replica` | Run the reader cases | Read, consistency, position and unsupported-capability cases pass |
| No swap | US-024-AC3 | Replica adapter, a `latest` case | Run | Case fails unless the adapter refuses |
| Outcomes | US-024-AC4 | A type with no rows; a module the caller cannot read; a stopped backend | Query each | Empty, not permitted and unavailable are three distinct results |
| No token | US-024-AC5 | A call with no token; a call with an expired token | Run | Refused both times; no shared identity answers |
| Memory | US-024-AC6 | `memory` and `memory_replica` | Run the corpus | All cases for declared operations pass |

## Dependencies

- **Stories**: US-021
- **Feature Spec**: FEAT-004
- **Feature Requirements**: BE-04
- **PRD Requirements**: FR-25
- **External**: CONTRACT-004, Conformance corpus.

## Out of Scope

Performance benchmarks (the latency targets are US-044), and tests of one adapter's internals.
