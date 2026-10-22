---
ddx:
  id: US-023
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-004
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-023: Serve bounded reads from Ashlar

**Feature**: FEAT-004 — Backends
**Feature Requirements**: BE-03
**PRD Requirements**: FR-24
**Priority**: P0
**Status**: Draft

## Story

**As an** Analyst (through a client)
**I want** to have key lookups, filtered lists, relationships and counts answered from the warehouse, with the age of the data
**So that** large-scale reads do not depend on the hot store

## Context

Ashlar is the replica store: gold Delta tables on Unity Catalog (Databricks' catalog and access-control layer), fed from Truss (the hot, mutable store on Lakebase, Databricks managed Postgres). The Ashlar adapter runs bounded SQL over the gold Delta tables through a SQL warehouse as the user and is read-only. Ashlar is not yet built, and its adapter follows what Ashlar defines.

## Walkthrough

1. Analyst asks for use case counts by area at `bulk`.
2. The adapter reads the gold tables as the analyst.
3. The answer states the feed position it reflects.

## Acceptance Criteria

- [ ] **US-023-AC1** — Given a replica-served type, when queried at `bulk`, then the warehouse answers with the published feed position and its time.
- [ ] **US-023-AC2** — Given the user's own token, when the adapter queries, then Unity Catalog's policy for that user applies.
- [ ] **US-023-AC3** — Given an action, an import or a registration on an Ashlar-only module, when attempted, then `Unsupported` is returned; the module is read-only.
- [ ] **US-023-AC4** — Given Ashlar's published position, when `reached(token)` is asked, then it reflects whether the token's change has been fed.

## Edge Cases

- Ashlar not yet built: capabilities follow what Ashlar defines.
- No token for the warehouse: the read is refused, not served by a service identity.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Bulk | US-023-AC1 | Gold tables for `catalog.UseCase` | Count use cases by area at `bulk` | Counts, feed position and its time |
| User access | US-023-AC2 | Analyst `ana` with Unity Catalog access to `catalog` only | Read `playbooks` and `catalog` | `playbooks` denied by her policy; `catalog` answered |
| Read-only | US-023-AC3 | `playbooks`, Ashlar-only | Invoke an action | `Unsupported` |
| Reached | US-023-AC4 | Token of a change not yet fed; later, the same token after the feed | `reached(token)` | False, then true |

## Dependencies

- **Stories**: US-021
- **Feature Spec**: FEAT-004
- **Feature Requirements**: BE-03
- **PRD Requirements**: FR-24
- **External**: CONTRACT-004, Ashlar adapter; Ashlar's publication semantics, identity, feed position and user-scoped reads.

## Out of Scope

Writing to Ashlar by any route (changes arrive through Truss's feed), and Truss-served reads (US-022).
