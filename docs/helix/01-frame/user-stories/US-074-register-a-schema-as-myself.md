---
ddx:
  id: US-074
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-010
      kind: informed_by
    - id: FEAT-002
      kind: informed_by
    - id: ADR-026
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-074: Register a schema as myself

**Feature**: FEAT-010 — Operator Console
**Feature Requirements**: OPR-13
**PRD Requirements**: FR-52, FR-61
**Priority**: P1
**Status**: Draft

## Story

**As a** module builder
**I want** to apply a validated schema change as myself, under the permissions the backend already gives me
**So that** that the revision is attributed to me and nobody gets access the backend did not grant

## Context

The record store's `schema` grant decides (ADR-026); Arras has no role table. `expected_revision` ties the apply to the plan (CONTRACT-011).

## Walkthrough

1. The builder reviews a plan and chooses Apply.
2. The console registers the document with the plan's revision.
3. It shows the new revision and refreshes the schema views; the revision's origin actor is her.

## Acceptance Criteria

- [ ] **US-074-AC1** — Given a person with the `schema` grant and a compatible plan, when she applies it, then the module has a new revision whose origin actor is her, and the schema views show it.
- [ ] **US-074-AC2** — Given a person with the `write` grant only, when she validates or applies a plan, then the backend refuses (403 `no_access`) before the host's placement is mentioned, nothing changes, and the console shows the reason and disables Apply.
- [ ] **US-074-AC3** — Given a record store that moved on since the plan, when the plan is applied, then 409 `Conflict` is shown, nothing is applied, and a fresh validate is offered.
- [ ] **US-074-AC4** — Given a host that returns false from `authorize_schema`, when a document is validated or registered, then the answer is 403 and the library is not called.
- [ ] **US-074-AC5** — Given a host that does not mount the schema surface, when the console loads, then no import control is shown and no schema write path exists.
- [ ] **US-074-AC6** — Given the administrative principal, when it calls `session.schema()`, then it is refused as for every user operation.

## Edge Cases

- **Expired token**: 401, and the console asks the host to sign in again.
- **The same document applied twice**: the second changes nothing and creates no revision.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| she applies it | US-074-AC1 | a person with the `schema` grant and a compatibl | she applies it | the module has a new revision whose origin actor is her, and the schema views show it |
| she applies a plan | US-074-AC2 | a person with the `write` grant only | she applies a plan | the backend refuses (403 `no_access`), nothing changes, and the console shows the reason a |
| the plan is applied | US-074-AC3 | a record store that moved on since the plan | the plan is applied | 409 `Conflict` is shown, nothing is applied, and a fresh validate is offered |
| a document is validated or registered | US-074-AC4 | a host that returns false from `authorize_schema | a document is validated or registered | the answer is 403 and the library is not called |
| the console loads | US-074-AC5 | a host that does not mount the schema surface | the console loads | no import control is shown and no schema write path exists |
| it calls `session.schema()` | US-074-AC6 | the administrative principal | it calls `session.schema()` | it is refused as for every user operation |

## Dependencies

- **Stories**: US-073
- **Feature Spec**: FEAT-010
- **Feature Requirements**: OPR-13
- **PRD Requirements**: FR-52, FR-61
