---
ddx:
  id: US-015
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-003
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-015: Apply an action's effects atomically on the provider

**Feature**: FEAT-003 — Actions
**Feature Requirements**: ACT-03
**PRD Requirements**: FR-16
**Priority**: P0
**Status**: Draft

## Story

**As a** Platform owner
**I want** to be certain an action either does everything it declares or nothing
**So that** no record is ever left half changed

## Context

The provider applies the whole action as one transaction with one origin, which is the record of who made the change and why, and one catalog check, which is the check of the change against the accepted catalog revision. The provider is the backend the host's placement names for the action, the record store by default (in production Truss, the hot, mutable store on Lakebase, Databricks managed Postgres).

## Walkthrough

1. An action creates a Solution and two links.
2. The second link fails for a missing endpoint.
3. The system rolls the action back.
4. The same action runs again with a valid endpoint.
5. All three effects apply together.

## Acceptance Criteria

- [ ] **US-015-AC1** — Given an action with three effects, when it succeeds, then all three took effect together and share one origin.
- [ ] **US-015-AC2** — Given the second effect fails, when the action runs, then none took effect.
- [ ] **US-015-AC3** — Given a catalog revision accepted while the action runs, when it commits, then it is not accepted against the old revision.
- [ ] **US-015-AC4** — Given the connection is lost after commit was requested, when the outcome is unknown, then re-invoking with the same idempotency key returns the receipt.

## Edge Cases

- Effects naming an alias created later: refused.
- Two actions on the same entities concurrently: one waits; neither deadlocks.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Together | US-015-AC1 | Action with 3 effects | Invoke | All 3 applied under one origin |
| Roll back | US-015-AC2 | Second link names a missing endpoint | Invoke | No effect applied, including the Solution |
| Revision | US-015-AC3 | A new catalog revision accepted mid-action | Commit | Action not accepted against the old revision |
| Unknown outcome | US-015-AC4 | Connection drops after commit is requested | Re-invoke with the same idempotency key | The original receipt |

## Dependencies

- **Stories**: US-014
- **Feature Spec**: FEAT-003
- **Feature Requirements**: ACT-03
- **PRD Requirements**: FR-16
- **External**: CONTRACT-003, Atomicity; CONTRACT-004, `apply`.

## Out of Scope

Actions whose effects span backends, and compensation for effects already committed.
