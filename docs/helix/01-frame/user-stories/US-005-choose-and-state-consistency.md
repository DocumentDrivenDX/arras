---
ddx:
  id: US-005
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-001
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-005: Choose a consistency level and always see the answer's freshness

**Feature**: FEAT-001 — Ontology Reads
**Feature Requirements**: READ-05
**PRD Requirements**: FR-6
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to ask for `latest` or `bulk` and be told which backend answered and how current the answer is
**So that** I never mistake a replica's answer for the record store's

## Context

ADR-014 (the architecture decision record on consistency and freshness) sets two levels. `latest` is served by the record store, the system of record for the module. `bulk` may be served by a replica, a backend that holds a copy fed from the record store. Arras never swaps one level for the other silently.

## Walkthrough

1. Developer queries a Solution at `latest`.
2. The record store answers and the answer names it.
3. Developer queries use cases at `bulk`.
4. A replica answers and the answer states its age.
5. The record store becomes unavailable.
6. Developer queries at `latest` again.
7. The system raises `Unavailable`.

## Acceptance Criteria

- [ ] **US-005-AC1** — Given any read, when it returns, then it carries freshness naming the backend, the position and the consistency level.
- [ ] **US-005-AC2** — Given `latest`, when answered, then the record store answered.
- [ ] **US-005-AC3** — Given `bulk` and a replica, when answered, then the replica may answer and states its age.
- [ ] **US-005-AC4** — Given the record store is down, when `latest` is asked, then `Unavailable` is raised and no replica answers in its place.

## Edge Cases

- A type with no replica: `bulk` is served by the record store and the answer says so.
- No level given: the read is `latest`.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Stated | US-005-AC1 | Any read of `catalog.Solution` | Read | Freshness names backend, position and level |
| Latest | US-005-AC2 | `catalog.Solution` is placed on record store `memory` with replica `memory_replica` | Read at `latest` | `memory` answered |
| Bulk | US-005-AC3 | Same module | Read at `bulk` | `memory_replica` may answer; the answer states its age |
| No swap | US-005-AC4 | `memory` unreachable, `memory_replica` reachable | Read at `latest` | `Unavailable`; `memory_replica` not called |

## Dependencies

- **Stories**: US-001
- **Feature Spec**: FEAT-001
- **Feature Requirements**: READ-05
- **PRD Requirements**: FR-6
- **External**: CONTRACT-001, Consistency; ADR-014.

## Out of Scope

Requiring an answer at least as new as a receipt (US-006) and the report of each backend's availability (US-025).
