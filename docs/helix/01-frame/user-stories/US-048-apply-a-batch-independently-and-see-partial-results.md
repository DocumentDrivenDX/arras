---
ddx:
  id: US-048
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

# US-048: Apply a batch item by item and see exactly which applied

**Feature**: FEAT-003 — Actions
**Feature Requirements**: ACT-11
**PRD Requirements**: FR-43, FR-17
**Priority**: P0
**Status**: Draft

## Story

**As a** Catalog editor (through a client)
**I want** to send up to 100 corrections where each stands or fails on its own, and be told exactly which applied and which were refused
**So that** one bad item does not hold up the rest, and a retry never repeats what already happened

## Context

`invoke_batch(action, items)` with `atomic` false applies each item as its own atomic group in order. Each item is independently idempotent under the request id `module.Action:key#index`. The `BatchReceipt` carries a token that a later read passes to `query` as `at_least`.

## Walkthrough

1. The editor sends 20 coverage corrections with an idempotency key, and item 7 fails a precondition.
2. The system applies the other items in order.
3. The system returns the `BatchReceipt` with 19 receipts and one refusal at index 7.
4. The editor sends the same batch again.
5. The system returns the original receipts and changes nothing.

## Acceptance Criteria

- [ ] **US-048-AC1** — Given 20 items of which one fails a precondition, when they are sent with `atomic` false, then 19 apply, the refused item is reported with its index and reason, and `succeeded` is 19 and `failed` is 1.
- [ ] **US-048-AC2** — Given the same key and the same items, when they are sent again, then the applied items return their original receipts and nothing changes.
- [ ] **US-048-AC3** — Given `stop_on_error` true, when an item is refused, then later items are not applied and the result says so.
- [ ] **US-048-AC4** — Given an item with an invalid input, when the batch is sent, then `Invalid` reports it against the item's index before any item is applied.
- [ ] **US-048-AC5** — Given the batch's token, when it is passed to `query` as `at_least`, then every applied item's change is visible.

## Edge Cases

- **A connection lost mid-batch**: re-sending with the same key completes the rest without repeating the applied items.
- **Atomicity within one item**: each item is atomic, so a batch never applies part of one item's group.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Partial | US-048-AC1 | 20 items; item 7 fails | Send | 19 applied; index 7 refused; `succeeded` 19, `failed` 1 |
| Repeat | US-048-AC2 | Same key and items | Send again | Original receipts; no change |
| Stop | US-048-AC3 | `stop_on_error` true; item 7 fails | Send | Items 8 to 20 not applied; result says so |
| Invalid | US-048-AC4 | Item 5 has an input of the wrong type | Send | `Invalid` with index 5; nothing applied |
| Read side | US-048-AC5 | The batch's token | Query with `at_least` | Applied items visible |

## Dependencies

- **Stories**: US-014, US-016
- **Feature Spec**: FEAT-003
- **Feature Requirements**: ACT-11
- **PRD Requirements**: FR-43, FR-17
- **External**: [CONTRACT-003](../../02-design/contracts/CONTRACT-003-actions.md), `invoke_batch` and Bulk changes.

## Out of Scope

- Applying the whole batch as one group (US-047).
- Rolling back items that already applied.
