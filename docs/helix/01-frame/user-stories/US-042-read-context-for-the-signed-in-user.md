---
ddx:
  id: US-042
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-008
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-042: Read context for the signed-in user in the embedding host

**Feature**: FEAT-008 — Reference Clients
**Feature Requirements**: CLI-03
**PRD Requirements**: FR-40
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to read a playbook on behalf of the signed-in user on every call without caching it
**So that** the embedding host never holds a second copy of context

## Context

This is interaction 9 of the [client interactions draft](../client-interactions-draft.md). The embedding host owns its deployment and session identity. It passes the user's own token on every call, and Unity Catalog (Databricks' governance and access layer) applies the user's policy on a replica (in production Ashlar).

## Walkthrough

1. The embedding host starts a workflow that needs the playbook `pb-example-review`.
2. The workflow host reads the playbook as the user, with the user's own token.
3. The system returns the playbook with its age.
4. A second session reads the playbook again.
5. The system sends the second read to the backend.

## Acceptance Criteria

- [ ] **US-042-AC1** — Given the signed-in user, when the workflow host reads a playbook, then the read runs with that user's own token and states its age.
- [ ] **US-042-AC2** — Given two reads, when both are made, then each reaches the backend.
- [ ] **US-042-AC3** — Given a user who is not permitted, when the playbook is read, then the result is `Refused`.
- [ ] **US-042-AC4** — Given a playbook older than the caller allows, when it is read, then the answer says so and the caller decides.
- [ ] **US-042-AC5** — Given the source is down, when the playbook is read, then the result is `Unavailable`.

## Edge Cases

- **An entitlement read**: fails closed (US-028) and depends on the preconditions in ADR-005 (durable knowledge state).
- **No token from the embedding host**: Arras refuses the call.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| As user | US-042-AC1 | Signed-in user `jsmith` | Read `pb-example-review` | Read under `jsmith`'s access; age stated |
| No cache | US-042-AC2 | Same playbook, two sessions | Read twice | Two backend reads |
| Not permitted | US-042-AC3 | User without access | Read | `Refused` |
| Source down | US-042-AC5 | Replica unreachable | Read | `Unavailable` |
| Age | US-042-AC4 | Playbook older than the caller's limit | Read | Age stated; caller decides |

## Dependencies

- **Stories**: US-023, US-028
- **Feature Spec**: FEAT-008
- **Feature Requirements**: CLI-03
- **PRD Requirements**: FR-40
- **External**: [CONTRACT-001](../../02-design/contracts/CONTRACT-001-ontology-interface.md); the downstream host's own product requirements.

## Out of Scope

- Authoring or changing playbooks.
- Building the entitlement source (US-028).
