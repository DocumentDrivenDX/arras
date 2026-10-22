---
ddx:
  id: US-032
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-006
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-032: Keep the host starting when a backend is unusable

**Feature**: FEAT-006 — Embedding and Lifecycle
**Feature Requirements**: EMB-03
**PRD Requirements**: FR-33
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to start the host with a backend unconfigured, unreachable, denying access or failing to migrate, and to see why
**So that** a backend fault never takes the shared app down

## Context

The embedding host must serve its other functions regardless of an Arras backend fault. Every failure case is tested before any host-startup change merges.

## Walkthrough

1. The host starts with a backend's database unreachable.
2. The system reports that backend unavailable, with the reason, within the startup budget.
3. The host serves its other functions.
4. The backend returns, and the next operation that needs it reprobes.
5. The system reports it available.

## Acceptance Criteria

- [ ] **US-032-AC1** — Given an unreachable backend, when Arras starts, then `start` returns within the budget with that backend unavailable and the reason `unreachable`.
- [ ] **US-032-AC2** — Given a backend that refuses the identity, when Arras starts, then the reason is `access_denied`.
- [ ] **US-032-AC3** — Given an unavailable backend, when an operation needs it, then the result is `Unavailable` promptly, with no retry loop.
- [ ] **US-032-AC4** — Given the backend recovers, when an operation runs, then Arras reprobes at most every 5 seconds and the backend becomes available.
- [ ] **US-032-AC5** — Given a failed migration, when Arras starts, then the reason is `migration_failed`.

## Edge Cases

- **Credentials in the status detail**: never included.
- **A transient fault at start**: does not disable the backend until restart.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Unreachable | US-032-AC1 | A backend's database down | Start | Returns within the budget; reason `unreachable` |
| Denied | US-032-AC2 | Backend refuses the identity | Start | Reason `access_denied` |
| Migration failed | US-032-AC5 | Migration raises an error | Start | Reason `migration_failed` |
| Prompt | US-032-AC3 | A backend down | Run an operation that needs it | `Unavailable` at once; no retries |
| Recover | US-032-AC4 | The backend back up; last probe over 5 seconds ago | Run an operation | Backend available |

## Dependencies

- **Stories**: US-030
- **Feature Spec**: FEAT-006
- **Feature Requirements**: EMB-03
- **PRD Requirements**: FR-33
- **External**: [CONTRACT-005](../../02-design/contracts/CONTRACT-005-embedding-and-lifecycle.md), Error Semantics.

## Out of Scope

- Retrying a failed backend in the background.
- Reporting backend status through MCP (US-053).
