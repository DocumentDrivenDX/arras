---
ddx:
  id: US-029
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-005
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-029: Cache nothing across calls

**Feature**: FEAT-005 — Access
**Feature Requirements**: ACC-03
**PRD Requirements**: FR-30
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to know that Arras keeps no entity data and no access decision from one call to the next
**So that** every read of context runs on behalf of the user at the time of the call, and a revoked grant takes effect on the next read

## Context

This is interaction 9 of the [client interactions draft](../client-interactions-draft.md): praxis (the Databricks app that embeds Arras) reads a playbook for the signed-in user on every call. A cache would let a revoked user keep reading, and would hide a changed registry.

## Walkthrough

1. Praxis reads the playbook `pb-example-review` for a user.
2. The system sends the read to the backend.
3. Praxis reads the same playbook for the same user again.
4. The system sends the second read to the backend as well.
5. An administrator revokes the user's access, and praxis reads the playbook a third time.
6. The system refuses the read.

## Acceptance Criteria

- [ ] **US-029-AC1** — Given two identical reads, when both are made, then two backend reads occur.
- [ ] **US-029-AC2** — Given access revoked between two reads, when the second runs, then it is refused.
- [ ] **US-029-AC3** — Given a registry, when it is read, then the answer reflects the revision in force at the time of the read, not an earlier copy.
- [ ] **US-029-AC4** — Given an access decision made on an earlier call, when a later call is made, then the earlier decision is not reused.

## Edge Cases

- **The host caches results it receives**: the host decides; Arras holds none.
- **Connection pools**: a pool holds connections, not data, and does not count as a cache.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Two reads | US-029-AC1 | `SELECT p.* FROM praxis.Playbook p WHERE p.key = 'pb-example-review'` | Run twice | Two backend reads |
| Revoked | US-029-AC2 | Access revoked after the first read | Run the second read | `Refused` |
| Registry | US-029-AC3 | Registry revision advances between two reads | Read the registry twice | The second read shows the new revision |
| Decision | US-029-AC4 | Earlier call made while access was granted | Make a later call after revocation | Decided afresh; not reused |

## Dependencies

- **Stories**: US-027
- **Feature Spec**: FEAT-005
- **Feature Requirements**: ACC-03
- **PRD Requirements**: FR-30
- **External**: [CONTRACT-001](../../02-design/contracts/CONTRACT-001-ontology-interface.md), Caller context.

## Out of Scope

- Caching in the host application or in a backend.
- Pooling connections. The host owns pools (US-030).
