---
ddx:
  id: US-046
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

# US-046: Change many entities with one action that declares foreach

**Feature**: FEAT-003 — Actions
**Feature Requirements**: ACT-10
**PRD Requirements**: FR-43, FR-16
**Priority**: P0
**Status**: Draft

## Story

**As a** Catalog editor (through a client)
**I want** to correct the coverage level of a list of Solutions with a single invocation of an action whose effects repeat over the list
**So that** a bulk correction is declared, reviewable and either happens in full or not at all

## Context

`foreach(list_input) { effects }` repeats the effects inside it for each item of a list input, naming the item. The action, not the caller, defines the bulk operation, so its preconditions and effects are reviewed once. An action's effects total at most 1,000 after expansion. An action is a named change declared in UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions).

## Walkthrough

1. The developer declares `catalog.SetCoverage` with a list input of solution and level pairs and a `foreach` that updates each Solution.
2. The editor invokes the action with 20 pairs.
3. The system applies the 20 updates as one atomic group.
4. The editor invokes the action with one pair that names a Solution that does not exist.
5. The system applies nothing and names the failing item.

## Acceptance Criteria

- [ ] **US-046-AC1** — Given an action whose effects are a `foreach` over a list input, when it is invoked with 20 items, then all 20 updates apply in one atomic group with one origin and one receipt.
- [ ] **US-046-AC2** — Given one item that fails a precondition or breaks an input type, when the action is invoked, then nothing applies and the failure names the item.
- [ ] **US-046-AC3** — Given a list whose expansion would exceed 1,000 effects, when the action is invoked, then the result is `Invalid`, names the bound, and nothing applies.
- [ ] **US-046-AC4** — Given an empty list, when the action is invoked, then a receipt with zero counts returns.
- [ ] **US-046-AC5** — Given the same idempotency key and inputs, when the action is invoked again, then nothing changes and the original receipt returns.

## Edge Cases

- **An item that names an alias created later**: refused at registration.
- **A list item repeated twice**: the effects apply in order, so the second sees the first.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| All | US-046-AC1 | 20 items | Invoke | One group; one receipt |
| Item fails | US-046-AC2 | 20 items; item 7 names a missing Solution | Invoke | None applied; item 7 named |
| Bound | US-046-AC3 | A list that expands to 1,001 effects | Invoke | `Invalid`; bound named |
| Empty | US-046-AC4 | `[]` | Invoke | Receipt with zero counts |
| Replay | US-046-AC5 | Same key and inputs as an applied call | Invoke | Original receipt; no change |

## Dependencies

- **Stories**: US-013, US-014
- **Feature Spec**: FEAT-003
- **Feature Requirements**: ACT-10
- **PRD Requirements**: FR-43, FR-16
- **External**: [CONTRACT-003](../../02-design/contracts/CONTRACT-003-actions.md), Declaration and Bulk changes.

## Out of Scope

- Sending several invocations of one action together (US-047, US-048).
- Declaring bulk operations in the caller instead of the action.
