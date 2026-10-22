---
ddx:
  id: US-047
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

# US-047: Apply a batch of invocations as one atomic group

**Feature**: FEAT-003 — Actions
**Feature Requirements**: ACT-11
**PRD Requirements**: FR-43, FR-17
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to send up to 100 invocations of one action together and have all of them apply or none
**So that** a correction that must stand as a whole is never half applied

## Context

`invoke_batch(action, items, atomic=True)` applies every item as one atomic group of at most 1,000 effects in all, and returns a `BatchReceipt`. The receipt carries a token that a later read passes to `query` as `at_least`. An action is a named change declared in UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions).

## Walkthrough

1. The developer sends 30 coverage corrections with `atomic` true and an idempotency key.
2. The system validates every item's inputs before applying any.
3. The system applies all 30 as one group and returns the `BatchReceipt`.
4. The developer sends a batch in which item 12 fails a precondition.
5. The system applies nothing and reports the failure at index 12.

## Acceptance Criteria

- [ ] **US-047-AC1** — Given 30 valid items, when they are sent with `atomic` true, then all apply in one group and the `BatchReceipt` carries each item's receipt and one token.
- [ ] **US-047-AC2** — Given item 12 fails a precondition, when the batch is sent atomically, then none applies and the failure is reported against index 12.
- [ ] **US-047-AC3** — Given an item with an invalid input, when the batch is sent, then `Invalid` reports the violation against the item's index before anything is applied.
- [ ] **US-047-AC4** — Given more than 100 items or more than 1,000 effects in all, when the batch is sent, then `Invalid` names the bound.
- [ ] **US-047-AC5** — Given the same key and inputs, when the batch is sent again, then nothing changes and the original `BatchReceipt` returns.
- [ ] **US-047-AC6** — Given the batch's token passed to `query` as `at_least`, when the read runs, then every item's change is visible.

## Edge Cases

- **A connection lost after commit was requested**: re-sending with the same key returns the receipt.
- **An empty batch**: `Invalid`, because at least one item is required.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| All | US-047-AC1 | 30 valid items | Send atomic | One group; every item's receipt; one token |
| One fails | US-047-AC2 | 30 items; item 12 fails a precondition | Send atomic | None applied; failure at index 12 |
| Invalid | US-047-AC3 | Item 5 has an input of the wrong type | Send | `Invalid` with index 5; nothing applied |
| Bounds | US-047-AC4 | 101 items | Send | `Invalid`; bound named |
| Replay | US-047-AC5 | Same key and inputs | Send again | Original `BatchReceipt` |
| Read side | US-047-AC6 | The batch's token | Query with `at_least` | Every item's change visible |

## Dependencies

- **Stories**: US-014
- **Feature Spec**: FEAT-003
- **Feature Requirements**: ACT-11
- **PRD Requirements**: FR-43, FR-17
- **External**: [CONTRACT-003](../../02-design/contracts/CONTRACT-003-actions.md), `invoke_batch` and Bulk changes.

## Out of Scope

- Applying items independently (US-048).
- Batches that mix different actions.
