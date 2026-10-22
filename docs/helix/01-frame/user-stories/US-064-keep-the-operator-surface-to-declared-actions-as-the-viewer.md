---
ddx:
  id: US-064
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-09
  authoring:
    home: repo
  links:
    - id: FEAT-010
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-064: Keep the operator surface to declared actions as the viewer

**Feature**: FEAT-010 — Operator Console
**Feature Requirements**: OPR-07, OPR-08
**PRD Requirements**: FR-52
**Priority**: P1
**Status**: Draft

## Story

**As a** Platform owner
**I want** to know that the operator console writes only by invoking declared actions, as the person using it
**So that** a wider audience cannot change more than the backends allow them to

## Context

Every call carries the viewer's own token (ADR-017) and the host may narrow actions with `authorize_action`. The surface has no raw edit, no SQL, no registration and no import (CONTRACT-009).

## Walkthrough

1. A viewer without write access opens a module and an action.
2. The console tries validate and shows the provider's refusal.
3. The platform owner inspects the surface's published description.

## Acceptance Criteria

- [ ] **US-064-AC1** — Given the published description of the operator surface, when it is inspected, then only validate, invoke and batch of declared actions write; no other path writes.
- [ ] **US-064-AC2** — Given two principals with different grants, when each invokes the same action, then each gets the provider's own answer.
- [ ] **US-064-AC3** — Given a `POST` from a foreign origin or with no origin proof, when it is sent, then it is refused with 403.
- [ ] **US-064-AC4** — Given a backend error whose detail echoes an input, when it is returned, then the body omits the detail.
- [ ] **US-064-AC5** — Given a host that returns false from `authorize_action`, when the action is invoked, then the answer is 403 and the library is not called.

## Edge Cases

- **Expired token**: 401, and the console asks the host to sign in again.
- **More than four requests in flight for one principal**: 429.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| it is inspected | US-064-AC1 | the published description of the operator surface | it is inspected | only validate, invoke and batch of declared actions write; no other path writes |
| each invokes the same action | US-064-AC2 | two principals with different grants | each invokes the same action | each gets the provider's own answer |
| it is sent | US-064-AC3 | a `POST` from a foreign origin or with no origin p | it is sent | it is refused with 403 |
| it is returned | US-064-AC4 | a backend error whose detail echoes an input | it is returned | the body omits the detail |
| the action is invoked | US-064-AC5 | a host that returns false from `authorize_action` | the action is invoked | the answer is 403 and the library is not called |

## Dependencies

- **Stories**: US-062
- **Feature Spec**: FEAT-010
- **Feature Requirements**: OPR-07, OPR-08
- **PRD Requirements**: FR-52
