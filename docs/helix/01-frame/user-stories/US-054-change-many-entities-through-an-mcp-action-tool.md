---
ddx:
  id: US-054
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-009
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-054: Change many entities through an action tool in one call

**Feature**: FEAT-009 — MCP Binding
**Feature Requirements**: MCP-06
**PRD Requirements**: FR-43, FR-44, FR-17
**Priority**: P0
**Status**: Draft

## Story

**As a** Catalog editor (through a client)
**I want** an agent to send a list of corrections to an action tool in one call, all or nothing or item by item, and to see exactly what applied
**So that** an agent's bulk change is bounded, repeatable and visible to its next read

## Context

An action tool of the MCP (Model Context Protocol, Anthropic's open protocol for agent tools) server accepts `{items, atomic?, idempotency_key?}` as an alternative to `{inputs, idempotency_key?}` and returns a `BatchReceipt` (CONTRACT-003). The agent acts with the editor's own token.

## Walkthrough

1. The agent calls `catalog_set_coverage` with 20 items, `atomic` true and a key.
2. The system applies the items as one group and returns the receipt.
3. The agent repeats the call with `atomic` false and one item failing a precondition.
4. The system applies the other items and reports the refusal.
5. The agent reads with the batch token.

## Acceptance Criteria

- [ ] **US-054-AC1** — Given an action tool, when it is called with 1 to 100 `items` and `atomic` true, then all apply as one group or none, and the `BatchReceipt` is returned.
- [ ] **US-054-AC2** — Given `atomic` false and one item failing a precondition, when the tool is called, then the others apply and the result lists each item's receipt or its refusal with its index.
- [ ] **US-054-AC3** — Given more than 100 items, when the tool is called, then the result is `invalid`.
- [ ] **US-054-AC4** — Given the same `idempotency_key` and items, when the tool is called again, then nothing changes and the original receipts return.
- [ ] **US-054-AC5** — Given the batch's `token`, when it is passed to `query` as `at_least`, then every applied item's change is visible.
- [ ] **US-054-AC6** — Given both `inputs` and `items`, when the tool is called, then the result is `invalid`.

## Edge Cases

- **An agent that wants a dry run**: calls `validate_action` for one item first.
- **A connection lost mid-call**: repeating the call with the same key completes the rest.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Atomic | US-054-AC1 | 20 items | Call with `atomic` true | One group; receipt returned |
| Partial | US-054-AC2 | 20 items; item 7 fails | Call with `atomic` false | 19 applied; index 7 refused |
| Bounds | US-054-AC3 | 101 items | Call | `invalid` |
| Both inputs | US-054-AC6 | `inputs` and `items` together | Call | `invalid` |
| Replay | US-054-AC4 | Same key and items | Call again | No change; original receipts |
| Read side | US-054-AC5 | The batch's `token` | `query` with `at_least` | Applied items visible |

## Dependencies

- **Stories**: US-048, US-047, US-051
- **Feature Spec**: FEAT-009
- **Feature Requirements**: MCP-06
- **PRD Requirements**: FR-43, FR-44, FR-17
- **External**: [CONTRACT-007](../../02-design/contracts/CONTRACT-007-mcp-binding.md), Tools; [CONTRACT-003](../../02-design/contracts/CONTRACT-003-actions.md), Bulk changes.

## Out of Scope

- Batches that mix different actions.
- A dry run of the whole batch.
