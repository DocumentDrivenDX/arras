---
ddx:
  id: US-028
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

# US-028: Tell empty, not permitted and unavailable apart

**Feature**: FEAT-005 — Access
**Feature Requirements**: ACC-02
**PRD Requirements**: FR-29
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to know whether a read found nothing, was refused, or could not be answered
**So that** my client fails closed on every outcome except a found record

## Context

This is interaction 10 of the [client interactions draft](../client-interactions-draft.md): the embedding host reads an entitlement for a user and a source record and denies access unless the read finds one. The entitlement source depends on the preconditions in ADR-005 (the architecture decision on durable knowledge state, which gates structure derived from sensitive source records). This story is drafted so the interface leaves room for that source.

## Walkthrough

1. The client developer's client reads the entitlement `reader-a:m-0001` through Arras, as the signed-in person.
2. The source is reachable and holds no such record. The system returns no rows.
3. The person lacks access to the entitlement data. The system returns `Refused`.
4. The source is unreachable. The system returns `Unavailable`.
5. The client denies access on `Refused` and on `Unavailable`.

## Acceptance Criteria

- [ ] **US-028-AC1** — Given a reachable source with no matching record, when the entitlement is queried, then the result has no rows.
- [ ] **US-028-AC2** — Given a person without access, or with an expired token, when the entitlement is queried, then the result is `Refused`.
- [ ] **US-028-AC3** — Given an unreachable source, when the entitlement is queried, then the result is `Unavailable`, never an empty result and never `Refused`.
- [ ] **US-028-AC4** — Given each of the three outcomes, when a client that fails closed receives it, then the client treats `Unavailable` and `Refused` as a denial.

## Edge Cases

- **An outage during a refused read**: the result is `Unavailable`, because Arras cannot tell whether the person would have been refused.
- **The entitlement source is not yet decided**: the criteria are exercised against a test source until ADR-005's preconditions are answered.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Empty | US-028-AC1 | Source up; no record for `reader-a:m-0001` | Query the entitlement | No rows |
| Refused | US-028-AC2 | Person without access to the entitlement data | Query the entitlement | `Refused` |
| Expired token | US-028-AC2 | Token past its expiry | Query the entitlement | `Refused` |
| Unavailable | US-028-AC3 | Source unreachable | Query the entitlement | `Unavailable` |
| Fail closed | US-028-AC4 | One result of each kind | Client checks access | Denied on `Refused` and `Unavailable` |

## Dependencies

- **Stories**: US-001
- **Feature Spec**: FEAT-005
- **Feature Requirements**: ACC-02
- **PRD Requirements**: FR-29
- **External**: [CONTRACT-001](../../02-design/contracts/CONTRACT-001-ontology-interface.md), Access; [CONTRACT-004](../../02-design/contracts/CONTRACT-004-backend-contract.md), Outcomes; [ADR-005](../../02-design/adr/ADR-005-durable-knowledge-state.md).

## Out of Scope

- Choosing or building the entitlement source and its data, which wait on ADR-005's preconditions.
- Deciding who has access. The backends decide (ADR-017).
