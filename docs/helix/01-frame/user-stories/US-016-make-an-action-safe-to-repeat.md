---
ddx:
  id: US-016
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

# US-016: Make an action safe to repeat

**Feature**: FEAT-003 — Actions
**Feature Requirements**: ACT-05
**PRD Requirements**: FR-17
**Priority**: P0
**Status**: Draft

## Story

**As a** Catalog editor (through a client)
**I want** to click twice and get one Solution, with the same receipt both times
**So that** a slow screen or a retry never duplicates data

## Context

An idempotency key is a caller-supplied string that identifies one intended invocation. The provider keeps the key with the receipt in the same transaction as the effects.

## Walkthrough

1. Editor invokes the action with key `ui-7f3a`.
2. The system applies it and returns a receipt.
3. Editor invokes it again with the same key and inputs.
4. The system changes nothing and returns the original receipt.
5. Editor invokes it with the same key and different inputs.
6. The system refuses it with `Conflict`.

## Acceptance Criteria

- [ ] **US-016-AC1** — Given the same key and inputs, when invoked again, then nothing changes and the original receipt returns with `replayed` true.
- [ ] **US-016-AC2** — Given the same key and different inputs, when invoked, then `Conflict` (`idempotency_key_reused`) is returned.
- [ ] **US-016-AC3** — Given no key, when invoked twice, then two independent invocations run.
- [ ] **US-016-AC4** — Given a key more than 24 hours old, when invoked, then the key is still honored.

## Edge Cases

- A key reused across actions: keys are scoped to the module and action.
- A failed invocation: leaves no key behind.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Replay | US-016-AC1 | Key `ui-7f3a`, same inputs | Invoke twice | One Solution; second call returns the first receipt with `replayed` true |
| Reuse | US-016-AC2 | Key `ui-7f3a`, different inputs | Invoke | `Conflict` (`idempotency_key_reused`) |
| No key | US-016-AC3 | No key supplied | Invoke twice | Two Solutions |
| Retention | US-016-AC4 | Key used 25 hours earlier | Invoke again with the same inputs | Honored; original receipt returned |

## Dependencies

- **Stories**: US-014
- **Feature Spec**: FEAT-003
- **Feature Requirements**: ACT-05
- **PRD Requirements**: FR-17
- **External**: CONTRACT-003, Idempotency.

## Out of Scope

Idempotency of items inside a batch (US-047, US-048).
