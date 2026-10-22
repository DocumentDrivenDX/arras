---
ddx:
  id: US-049
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

# US-049: Refuse any call that has no user token

**Feature**: FEAT-005 — Access
**Feature Requirements**: ACC-04
**PRD Requirements**: FR-28, FR-29
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** Arras to refuse a call that carries no valid token of the person making it, and never to substitute a service identity
**So that** no read or change is ever made under an identity the person did not present

## Context

A `Principal` (the person making a call: user, token and groups) carries a token, which is required (CONTRACT-001). Arras does not validate the token; the backends do. The administrative principal exists only for attachment, handler binding, imports and startup registration, and never serves a read or an action; install and upgrade run on the host's installing connection, not as the administrative principal (CONTRACT-005). Each backend is reached with the person's own credential; in production they are Truss (a reader and provider on Lakebase, Databricks managed Postgres) and Ashlar (a reader on Unity Catalog).

## Walkthrough

1. A host creates a session for a person whose token is missing.
2. The person queries and invokes an action.
3. The system refuses each call before it contacts a backend.
4. The host supplies a renewed token.
5. The calls succeed.

## Acceptance Criteria

- [ ] **US-049-AC1** — Given a principal with no token, when any operation is called, then the result is `Refused` before any backend is contacted.
- [ ] **US-049-AC2** — Given an expired token, when an operation is called, then the result is `Refused`, not `Unavailable`, and tells the caller to renew the token.
- [ ] **US-049-AC3** — Given the administrative principal, when it is used for a read or an action, then the result is `Refused`.
- [ ] **US-049-AC4** — Given a host whose connection source is asked for a principal, when the source is called, then it receives that principal and Arras never asks for a shared connection.
- [ ] **US-049-AC5** — Given a person with a credential for one backend but none for another, when a read of the other is made, then it is refused.
- [ ] **US-049-AC6** — Given a person with a credential for one backend but none for another, when a read of the first is made after a read of the other is refused, then the first read is unaffected.

## Edge Cases

- **A token a backend rejects as invalid**: `Refused`, the same as an expired token.
- **A retry with a service identity**: no operation offers one.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| No token | US-049-AC1 | Principal `jsmith` with no token | Any call | `Refused`; no backend call |
| Expired | US-049-AC2 | Token past its expiry | Call | `Refused` with a renewal instruction |
| Admin | US-049-AC3 | Administrative principal | Read | `Refused` |
| Per principal | US-049-AC4 | Connection source | Call | The calling principal is passed |
| Missing credential | US-049-AC5 | A credential for `memory` only | `memory_replica` read | The `memory_replica` read is refused |
| Other backend unaffected | US-049-AC6 | A credential for `memory` only; a `memory_replica` read already refused | `memory` read | The `memory` read succeeds |

## Dependencies

- **Stories**: US-027
- **Feature Spec**: FEAT-005
- **Feature Requirements**: ACC-04
- **PRD Requirements**: FR-28, FR-29
- **External**: [CONTRACT-001](../../02-design/contracts/CONTRACT-001-ontology-interface.md), Caller context and Access; [CONTRACT-005](../../02-design/contracts/CONTRACT-005-embedding-and-lifecycle.md); [ADR-017](../../02-design/adr/ADR-017-backends-are-reached-with-the-users-own-token.md).

## Out of Scope

- Validating the token's signature or claims. The backends do that.
- Issuing or renewing tokens, which the host does.
