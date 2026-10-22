---
ddx:
  id: US-018
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

# US-018: Return a receipt for every action

**Feature**: FEAT-003 — Actions
**Feature Requirements**: ACT-07
**PRD Requirements**: FR-19
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to get the identities and versions an action changed, and a token for reading my write
**So that** my next read can ask for data at least this new

## Context

A receipt is the bridge between a command and the consistency model. Its token is opaque to the client and is what `query` accepts as `at_least` (US-006).

## Walkthrough

1. Client invokes an action.
2. The system returns the receipt.
3. Client reads with the receipt's token.
4. The answer is at least as new as the receipt's token.

## Acceptance Criteria

- [ ] **US-018-AC1** — Given a successful action, when it returns, then the receipt names the entities created, changed or deleted with their versions and counts per operation.
- [ ] **US-018-AC2** — Given the receipt, when its token is passed to a read, then the answer is at least that new.
- [ ] **US-018-AC3** — Given a replayed invocation, when it returns, then `replayed` is true and the token is the original.
- [ ] **US-018-AC4** — Given a refused action, when it returns, then no receipt exists.

## Edge Cases

- An action with no effects: a receipt with zero counts.
- The token's form: opaque to the client.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Receipt | US-018-AC1 | `CreateCandidateSolution` creating one Solution and two links | Invoke | Receipt names the Solution with its version; counts: 1 created, 2 linked |
| Token | US-018-AC2 | Receipt from that invocation | Read with its token | Answer at least that new |
| Replay | US-018-AC3 | Same idempotency key and inputs | Invoke again | `replayed` true; original token |
| Refused | US-018-AC4 | Failed precondition | Invoke | No receipt |

## Dependencies

- **Stories**: US-014
- **Feature Spec**: FEAT-003
- **Feature Requirements**: ACT-07
- **PRD Requirements**: FR-19
- **External**: CONTRACT-003, Receipt.

## Out of Scope

The batch receipt (US-047, US-048) and the waiting behavior of reads (US-006).
