---
ddx:
  id: US-017
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

# US-017: Attribute every change to the person who made it and the action

**Feature**: FEAT-003 — Actions
**Feature Requirements**: ACT-06
**PRD Requirements**: FR-18
**Priority**: P0
**Status**: Draft

## Story

**As a** Platform owner
**I want** to see that every change names the person whose own token made it and the action, and that no caller can assert an author
**So that** I can see who changed what and trace a change to a human decision

## Context

Every backend call is made with the user's own token (ADR-017, the architecture decision record that backends are reached with the user's own token), so the person on a change is the one the backend authenticated. Praxis (a Databricks app that embeds Arras) calls Arras with the signed-in user's token. The provider (in production Truss, the hot, mutable store on Lakebase, Databricks managed Postgres) records the connecting database role and the person as the change's origin actor.

## Walkthrough

1. `jsmith`'s session invokes an action with her own token.
2. The provider authenticates the connection as her and records her as the origin actor with the action's name.
3. Platform owner reads the change.
4. Platform owner looks for an author parameter in the interface.

## Acceptance Criteria

- [ ] **US-017-AC1** — Given an invocation made with `jsmith`'s own token, when it commits, then the change names `jsmith` and the action.
- [ ] **US-017-AC2** — Given the interface, when invocation parameters are enumerated, then none lets a caller name an author.
- [ ] **US-017-AC3** — Given an import, when it commits, then the change records the load and its initiator, not an author.
- [ ] **US-017-AC4** — Given a change by plain SQL in the provider's database, when it commits, then the provider still records the connecting database role.
- [ ] **US-017-AC5** — Given any change committed through the interface, when the change is read, then it names no service identity.

## Edge Cases

- An expired token: the invocation is refused and nothing is recorded.
- A token for another person: the change is that person's, because the backend authenticated it.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Person | US-017-AC1 | `jsmith`'s own token | Invoke `CreateCandidateSolution` | Change names `jsmith` and `CreateCandidateSolution` |
| No asserted author | US-017-AC2 | The interface's invocation parameters | Enumerate them | No author parameter |
| Import | US-017-AC3 | Import `load-1` started by the administrator | Read the resulting change | Load `load-1` and its initiator, no author |
| Role | US-017-AC4 | Plain SQL change as database role `jsmith_role` | Commit | `jsmith_role` recorded |
| No service identity | US-017-AC5 | `CreateCandidateSolution` committed with `jsmith`'s own token | Read the change | No service identity named |

## Dependencies

- **Stories**: US-014
- **Feature Spec**: FEAT-003
- **Feature Requirements**: ACT-06
- **PRD Requirements**: FR-18
- **External**: CONTRACT-003, Attribution; ADR-017.

## Out of Scope

Deciding who may make a change (each backend's own controls, US-027), and reporting or visualizing the audit trail.
