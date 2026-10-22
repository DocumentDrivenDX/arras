---
ddx:
  id: FEAT-005
  type: feature-specification
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: concerns
      kind: informed_by
---

# Feature Specification: FEAT-005 — Access

**Feature ID**: FEAT-005
**Status**: Draft
**Priority**: P0
**Owner**: Erik LaBianca
**Covered PRD Subsystem(s)**: Access
**Covered PRD Requirements**: FR-28 to FR-30
**Cross-Subsystem Rationale**: None; single subsystem.

## Overview

Access implements PRD FR-28 to FR-30. Every backend is reached with the caller's own token. Arras applies no access rule of its own, holds no role map and no service identity for a user's read or action, keeps no entity data or access decision across calls, and refuses a call that has no token. A read's three outcomes, empty, not permitted and unavailable, stay distinguishable.

Each backend decides access by its own controls. In production the backends are Truss, the hot mutable store on Lakebase (Databricks managed Postgres), where Postgres role grants decide access per module, and Ashlar, the warehouse store on Unity Catalog (Databricks' data catalog and access-control layer), where the person's own Unity Catalog access decides. ADR-017 (the architecture decision record on reaching backends with the user's own token) records the decision.

## Ideal Future State

A person's request reaches Truss over a connection authenticated as that person, so Postgres role grants decide. It reaches Ashlar with the person's own token, so Unity Catalog applies the person's policy. The backends refuse what the person may not do. A client that fails closed can tell a refusal from an outage.

## Problem Statement

- **Current situation**: The catalog and praxis (the Databricks app Arras is embedded in) need role-based writes and user-scoped reads, and the two stores have different identity systems.
- **Pain points**: A shared identity makes the application the access control and lets a caller assert who made a change. An outage mistaken for not permitted, or the reverse, breaks fail-closed behavior. Cached decisions go stale.
- **Desired outcome**: Backend-enforced access under the person's own token, authenticated attribution, distinguishable outcomes and nothing cached.

## Functional Areas

| Area | User question or job | Feature responsibility |
|------|----------------------|------------------------|
| Own token | Who is this to each backend? | The person's own connection for Truss; the person's own token for Ashlar |
| No token | What if there is none? | Refused before any backend is contacted |
| Outcomes | What happened? | Empty, not permitted, unavailable |
| No cache | Is it current? | No entity data or access decisions kept |

## Requirements

### Functional Requirements by Area

#### Own token

ACC-01. Every backend call is made with the caller's own token: a connection authenticated as the person for Truss, whose module reader and writer roles decide, and the person's own token for Ashlar. Arras keeps no access decision of its own and no mapping from people to roles (FR-28).

#### No token

ACC-04. A call that carries no valid token is refused before any backend is contacted. No service identity serves a user's read or action, and the administrative principal never does (FR-28, FR-29).

#### Outcomes

ACC-02. Results tell apart empty, not permitted and unavailable (FR-29).

#### No cache

ACC-03. Arras caches no entity data and no access decision across calls (FR-30).

### Non-Functional Requirements

- **Security**: the databases and Unity Catalog enforce access on the person's own identity. The person on a change is the one the backend authenticated.
- **Reliability**: the access decision does not depend on state outside the backend.
- **Scalability**: connections are per person. The host pools them per principal with short idle times.

## User Stories

- [US-027: Reach every backend as the caller](../user-stories/US-027-reach-every-backend-as-the-caller.md)
- [US-028: Tell empty, not permitted and unavailable apart](../user-stories/US-028-tell-empty-refused-and-unavailable-apart.md)
- [US-029: Cache nothing across calls](../user-stories/US-029-keep-no-cache-of-data-or-decisions.md)
- [US-049: Refuse any call that has no user token](../user-stories/US-049-refuse-a-call-without-a-user-token.md)

## Edge Cases and Error Handling

- When a role is revoked mid-session, the next operation is refused and a committed operation stands.
- When a principal has no token for the warehouse, Ashlar reads are refused and Truss reads are unaffected.
- A module with no access record has every operation refused until one exists.
- An expired token is refused and is not reported as unavailable.
- A read by the administrative principal is refused.

## Success Metrics

- 0 operations succeed without the backend's grant (test matrix).
- 100% of outages are reported as unavailable, never as empty or refused.

## Constraints and Assumptions

- The platform owner provisions roles and Unity Catalog grants. Role names are an open question (PRD Open Questions).
- Truss's isolation layer must decide by role membership and not by an exact role (a requirement on Truss).
- Per-record entitlements are out of scope.

## Dependencies

- **Other features**: FEAT-001 and FEAT-003 (the operations governed), FEAT-006 (the connection sources that carry the principal), FEAT-009 (one process serves one person's token).
- **External services**: Postgres roles (Truss module isolation); Unity Catalog; the exact surface lives in CONTRACT-004 (backend contract) and CONTRACT-005 (embedding and lifecycle); ADR-017.
- **PRD requirements**: FR-28 to FR-30 (P0 items 1 and 5).

## Out of Scope

- Deciding who should hold a role.
- Per-record or per-user entitlement.
- Authenticating end users or issuing tokens.
