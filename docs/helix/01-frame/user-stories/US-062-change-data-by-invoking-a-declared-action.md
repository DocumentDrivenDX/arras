---
ddx:
  id: US-062
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

# US-062: Change data by invoking a declared action

**Feature**: FEAT-010 — Operator Console
**Feature Requirements**: OPR-03, OPR-04
**PRD Requirements**: FR-50
**Priority**: P1
**Status**: Draft

## Story

**As a** module builder
**I want** to fill in a form built from a declared action, see what it would do, and confirm it
**So that** I correct data safely, through the module's own rules

## Context

An action is the only write (ADR-015). The form comes from the action's typed inputs; validate shows violations, failed preconditions and the effects; invoke carries an idempotency key and an expected revision (CONTRACT-003, CONTRACT-009).

## Walkthrough

1. The builder opens an entity and chooses `CorrectCoverage`.
2. The form offers the action's inputs, prefilled from the entity.
3. She edits a value; the browser checks its type; validation runs when the field loses focus.
4. She reviews the effects, confirms, and reads the receipt.

## Acceptance Criteria

- [ ] **US-062-AC1** — Given an action with typed inputs, when its form is opened, then one field per input, by type, with a list and a reference input offered as such.
- [ ] **US-062-AC2** — Given invalid inputs, when validation runs, then every violation is shown at its field, and no invoke is offered.
- [ ] **US-062-AC3** — Given valid inputs, when validation runs, then the effects the invoke would apply are shown, and nothing has changed.
- [ ] **US-062-AC4** — Given a confirmed invoke, when it runs, then the receipt shows the entities and versions changed; the same key sent again shows a replay.
- [ ] **US-062-AC5** — Given a module revision that changed since the form was built, when the form is invoked, then the console shows the conflict and rebuilds the form, with nothing applied.
- [ ] **US-062-AC6** — Given a batch of 20 items, one failing a precondition, when it is applied independently, then 19 receipts and one refusal with its index are shown.

## Edge Cases

- **A viewer without write access**: validate returns a refusal, the form shows the reason and offers no invoke.
- **A double click**: one change, the second answer marked a replay.
- A `delete` effect cannot be undone from the console; the preview says so.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| its form is opened | US-062-AC1 | an action with typed inputs | its form is opened | one field per input, by type, with a list and a reference input offered as such |
| validation runs | US-062-AC2 | invalid inputs | validation runs | every violation is shown at its field, and no invoke is offered |
| validation runs | US-062-AC3 | valid inputs | validation runs | the effects the invoke would apply are shown, and nothing has changed |
| it runs | US-062-AC4 | a confirmed invoke | it runs | the receipt shows the entities and versions changed; the same key sent again sho |
| the form is invoked | US-062-AC5 | a module revision that changed since the form was  | the form is invoked | the console shows the conflict and rebuilds the form, with nothing applied |
| it is applied independently | US-062-AC6 | a batch of 20 items, one failing a precondition | it is applied independently | 19 receipts and one refusal with its index are shown |

## Dependencies

- **Stories**: US-061
- **Feature Spec**: FEAT-010
- **Feature Requirements**: OPR-03, OPR-04
- **PRD Requirements**: FR-50
