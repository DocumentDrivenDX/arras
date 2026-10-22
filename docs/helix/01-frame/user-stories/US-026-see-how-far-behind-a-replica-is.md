---
ddx:
  id: US-026
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

# US-026: See how far behind a replica is

**Feature**: FEAT-004 — Backends
**Feature Requirements**: BE-06
**PRD Requirements**: FR-27
**Priority**: P0
**Status**: Draft

## Story

**As a** Platform owner
**I want** to read the feed position each replica reflects and how old the oldest unapplied change is
**So that** anyone relying on a replica can say how current it is

## Context

A replica is a reader that holds a copy of a module, fed from the providers' stores. A provider (in production Truss, the hot, mutable store on Lakebase) publishes a change feed, and a replica (in production Ashlar, the replica store on Unity Catalog) reflects the feed up to a position. The expected lag is low if the synchronization performs as advertised; Arras reports it and does not assume it.

## Walkthrough

1. Platform owner reads each backend's status.
2. The replica adapter reports the position and when it was recorded.
3. Platform owner reads the lag.
4. The lag is the age of the oldest unapplied change.

## Acceptance Criteria

- [ ] **US-026-AC1** — Given a replica, when its status is read, then it carries the position it reflects and the time it was recorded.
- [ ] **US-026-AC2** — Given a read from a replica, when it returns, then its freshness names that position.
- [ ] **US-026-AC3** — Given unapplied changes in the providers' stores, when lag is read, then it is the age of the oldest.
- [ ] **US-026-AC4** — Given no published position, when status is read, then the replica reports it as unknown, not zero.

## Edge Cases

- A long transaction in a provider's store: lag grows and is reported.
- No consumer registered: no lag is reported.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Position | US-026-AC1 | `memory_replica` has applied the feed to position P | Read status | P and its recorded time |
| Freshness | US-026-AC2 | Same replica | Read a use case at `bulk` | Freshness names P |
| Lag | US-026-AC3 | Three unapplied changes aged 40 s, 10 s and 2 s | Read lag | 40 s |
| Unknown | US-026-AC4 | The replica publishes no position | Read status | Position reported unknown |

## Dependencies

- **Stories**: US-023
- **Feature Spec**: FEAT-004
- **Feature Requirements**: BE-06
- **PRD Requirements**: FR-27
- **External**: CONTRACT-004, Positions and tokens; the provider's change-feed contract (Truss CONTRACT-006).

## Out of Scope

Alerting on lag, and choosing the lag a screen tolerates (a client decision).
