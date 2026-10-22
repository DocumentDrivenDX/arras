---
ddx:
  id: US-013
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-003
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-013: Declare actions in UMF and discover them

**Feature**: FEAT-003 — Actions
**Feature Requirements**: ACT-01
**PRD Requirements**: FR-14
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to declare an action with typed inputs, preconditions and effects, and have clients discover it
**So that** what may be done to my module's data is stated once

## Context

Actions are a minimal subset of the action contract that UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions) is to define. An action's effects are a closed list of primitive operations: create, update, delete, link, unlink and `foreach` over a list input. An optional handler hook, bound by name, carries what the list cannot express (CONTRACT-003, the actions contract).

## Walkthrough

1. Developer declares `CreateCandidateSolution` in the catalog document.
2. Developer registers the document.
3. A client enumerates the module's actions.
4. The enumeration lists `CreateCandidateSolution` with its description, inputs, preconditions and effects.

## Acceptance Criteria

- [ ] **US-013-AC1** — Given an action with typed inputs, preconditions and effects, when registered, then it appears in the module's enumeration with its description, inputs, preconditions and effects.
- [ ] **US-013-AC2** — Given an effect outside the closed list, when registered, then it is refused unless a handler supplies it.
- [ ] **US-013-AC3** — Given a handler bound by name, when the action is declared with it, then the declaration is accepted.
- [ ] **US-013-AC4** — Given a precondition predicate outside the version 1 forms in CONTRACT-003, when registered, then it is refused naming the predicate.

## Edge Cases

- An action naming an undefined type: refused.
- An action on a read-only module: refused.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Declare | US-013-AC1 | `CreateCandidateSolution` with three effects | Register, then enumerate actions | Listed with description, inputs, preconditions and effects |
| Effect | US-013-AC2 | Action with an effect named `sendEmail` | Register | Refused |
| Handler | US-013-AC3 | Action bound to handler `normalizeCoverage` | Register | Accepted |
| Predicate | US-013-AC4 | Precondition using a predicate not in the version 1 forms | Register | Refused, predicate named |

## Dependencies

- **Stories**: US-008
- **Feature Spec**: FEAT-003
- **Feature Requirements**: ACT-01
- **PRD Requirements**: FR-14
- **External**: CONTRACT-003, Declaration.

## Out of Scope

Invoking actions (US-014), compensation for a failed action, and effects that span backends.
