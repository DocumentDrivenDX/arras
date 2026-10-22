---
ddx:
  id: US-027
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-005
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-027: Reach every backend as the caller

**Feature**: FEAT-005 — Access
**Feature Requirements**: ACC-01
**PRD Requirements**: FR-28
**Priority**: P0
**Status**: Draft

## Story

**As a** Platform owner
**I want** to have each person's request reach every backend over a connection authenticated as that person, or with the person's own token
**So that** the databases enforce who may do what, and I grant access with ordinary roles and Unity Catalog grants

## Context

Truss is the hot, mutable store on Lakebase (Databricks managed Postgres); Ashlar is the replica store on Unity Catalog (Databricks' catalog and access-control layer). The platform owner grants module reader and writer roles to people. In production the Truss adapter's store decides by the connecting role's membership, and the Ashlar adapter's store (Unity Catalog) applies the user's own policy. The origin actor is the person recorded as the author of a change, and the journal is the provider's record of changes. Arras keeps no mapping from people to roles and no access rule of its own (ADR-017, the architecture decision record that backends are reached with the user's own token). The host (the application that embeds Arras) supplies the connection through `ConnectionSource` (CONTRACT-005).

## Walkthrough

1. Platform owner provisions reader and writer roles for the `catalog` module and grants membership to people.
2. The host yields a connection authenticated as the person for each call.
3. A person with the reader role only invokes an action.
4. The provider refuses it.
5. The person's token reaches the replica's store on a replica read.
6. Unity Catalog applies the person's policy.

## Acceptance Criteria

- [ ] **US-027-AC1** — Given a person with the reader role only, when she invokes an action, then the provider refuses it.
- [ ] **US-027-AC2** — Given a person with the writer role, when she invokes the same action, then it succeeds and the journal records her as the origin actor.
- [ ] **US-027-AC3** — Given a module with no access grant for the person, when she calls any operation on it, then it is refused.
- [ ] **US-027-AC4** — Given the person's token, when a replica read runs, then the replica's store applies her policy.
- [ ] **US-027-AC5** — Given two people using one host, when each calls, then each call uses a connection authenticated as that person and no connection is reused across people.

## Edge Cases

- A role revoked mid-session: the next operation is refused; a committed operation stands.
- A module with no access record: refused.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Reader | US-027-AC1 | `jsmith` holds `catalog` reader role only | Invoke `CreateCandidateSolution` | The provider refuses |
| Writer | US-027-AC2 | `jsmith` holds `catalog` writer role | Invoke the same action | Succeeds; journal names `jsmith` as origin actor |
| No grant | US-027-AC3 | `ana` holds no `catalog` role | Query `catalog.UseCase` | Refused |
| Token | US-027-AC4 | `ana`'s token; Unity Catalog policy denies `playbooks` | Read `playbooks` through the replica | Denied by her policy |
| Per person | US-027-AC5 | `jsmith` and `ana` call through one host | Each queries once | Two connections, each authenticated as its person; neither reused |

## Dependencies

- **Stories**: None
- **Feature Spec**: FEAT-005
- **Feature Requirements**: ACC-01
- **PRD Requirements**: FR-28
- **External**: CONTRACT-004, Principal; CONTRACT-005, `ConnectionSource`; ADR-017.

## Out of Scope

Deciding who should have access (the platform owner's decision, not Arras's), per-record entitlements, and refusing calls that carry no token (US-049).
