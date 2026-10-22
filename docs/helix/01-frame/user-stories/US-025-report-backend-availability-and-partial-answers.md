---
ddx:
  id: US-025
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

# US-025: Report each backend's availability and never fall back silently

**Feature**: FEAT-004 — Backends
**Feature Requirements**: BE-05
**PRD Requirements**: FR-26
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to see which backend is down and why, keep working with the rest, and never get a silently different answer
**So that** an outage of one store does not break or mislead my screen

## Context

This is interaction 12 of the client interactions draft (`docs/helix/01-frame/client-interactions-draft.md`): the record store (in production Truss, the hot, mutable store on Lakebase) goes down, then the replica (in production Ashlar, the replica store on Unity Catalog). `status()` reports each backend's availability and the reason for any outage (CONTRACT-004, the backend contract; CONTRACT-005, the embedding and lifecycle contract).

## Walkthrough

1. The record store becomes unreachable.
2. Client invokes an action, reads a record-store type and reads a replica type.
3. The system refuses the action and the record store read with `Unavailable` and a reason, and answers the replica read with its age.
4. The replica becomes unreachable instead.
5. The system serves record store reads and actions and refuses the replica-only read with a reason.

## Acceptance Criteria

- [ ] **US-025-AC1** — Given the record store (also the provider) down, when an action is invoked, then `Unavailable` is returned with the reason and nothing is applied.
- [ ] **US-025-AC2** — Given the record store down, when a replica-served query at `bulk` is made, then it answers and states its age.
- [ ] **US-025-AC3** — Given the replica down, when a record store query or an action is made, then it works.
- [ ] **US-025-AC5** — Given the replica down, when a `bulk` query of a replica-only type is made, then it fails with the reason.
- [ ] **US-025-AC4** — Given any backend, when `status()` is read, then each is reported with availability and reason.

## Edge Cases

- A partial answer: says which backend produced it.
- A fallback that would change the consistency level: never taken.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Record store down | US-025-AC1 | `memory` stopped | Invoke `CreateCandidateSolution` | `Unavailable` with reason; nothing applied |
| Replica up | US-025-AC2 | `memory` stopped, `memory_replica` up | Read `catalog.UseCase` at `bulk` | Answer from `memory_replica` with its age |
| Replica down, record store read | US-025-AC3 | `memory_replica` stopped | Read a record-store type | The read works |
| Replica down, replica-only | US-025-AC5 | `memory_replica` stopped | Read a replica-only type at `bulk` | Read fails with reason |
| Status | US-025-AC4 | `memory` stopped | `status()` | `memory` reported unavailable with reason; `memory_replica` reported available |

## Dependencies

- **Stories**: US-005
- **Feature Spec**: FEAT-004
- **Feature Requirements**: BE-05
- **PRD Requirements**: FR-26
- **External**: CONTRACT-004, Status; CONTRACT-005.

## Out of Scope

Startup behavior of the host when a backend is unusable (US-032), and retry or failover policy.
