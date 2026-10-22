---
ddx:
  id: US-045
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

# US-045: Validate an action before applying it

**Feature**: FEAT-003 — Actions
**Feature Requirements**: ACT-09
**PRD Requirements**: FR-42
**Priority**: P0
**Status**: Draft

## Story

**As a** Catalog editor (through a client)
**I want** to see what an action would do and every reason it cannot be done, before I confirm it
**So that** I confirm with full knowledge and the screen can disable a button that cannot work

## Context

A dry run runs the same checks as an invocation, with nothing applied, recorded or locked. An action is a named change declared in UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions), with inputs, preconditions and effects.

## Walkthrough

1. The editor opens the candidate form for an assertion.
2. The screen validates the action with the form's inputs.
3. The system returns the effects it would apply, or the failures.
4. The editor confirms.
5. The screen invokes the action.

## Acceptance Criteria

- [ ] **US-045-AC1** — Given valid inputs and true preconditions, when the action is validated, then `ok` is true and the effects it would apply return, with a generated key shown as generated.
- [ ] **US-045-AC2** — Given invalid inputs or a false precondition, when the action is validated, then `ok` is false and every violation and failed precondition is listed, with no effects.
- [ ] **US-045-AC3** — Given a validation, when it returns, then no entity, change record or idempotency key was written and no lock remains.
- [ ] **US-045-AC4** — Given the same idempotency key already used with these inputs, when the action is validated, then the original receipt is returned as `replay`.
- [ ] **US-045-AC5** — Given a validation that passed, when the state changes before the invocation, then `invoke` checks again and may refuse.

## Edge Cases

- **A principal without write access**: refused, because validation reads the provider's state as a writer.
- **Validation under load**: advisory only; it promises nothing about the later invocation.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Ok | US-045-AC1 | Valid inputs, true preconditions | Validate | `ok` true; effects returned |
| Not ok | US-045-AC2 | Input of the wrong type and a false precondition | Validate | `ok` false; both failures listed; no effects |
| Writes nothing | US-045-AC3 | Any validation | Validate, then inspect the store | No entity, change record or idempotency key; no lock |
| Replay | US-045-AC4 | Key already used with the same inputs | Validate | Original receipt as `replay` |
| Advisory | US-045-AC5 | Validation passed; a precondition becomes false | Invoke | Checked again; refused |

## Dependencies

- **Stories**: US-014
- **Feature Spec**: FEAT-003
- **Feature Requirements**: ACT-09
- **PRD Requirements**: FR-42
- **External**: [CONTRACT-003](../../02-design/contracts/CONTRACT-003-actions.md), `validate`; [CONTRACT-004](../../02-design/contracts/CONTRACT-004-backend-contract.md), `apply` with `dry_run`.

## Out of Scope

- Validating a batch of invocations as a whole.
- Reserving state for the later invocation.
