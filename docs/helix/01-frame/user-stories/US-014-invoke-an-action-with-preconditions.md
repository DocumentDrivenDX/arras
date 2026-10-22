---
ddx:
  id: US-014
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

# US-014: Invoke an action and have preconditions checked

**Feature**: FEAT-003 — Actions
**Feature Requirements**: ACT-02
**PRD Requirements**: FR-15
**Priority**: P0
**Status**: Draft

## Story

**As a** Catalog editor (through a client)
**I want** to create a candidate Solution from a coverage assertion with one call, and to be told every reason it cannot be done
**So that** I fix what is wrong in one pass

## Context

This is interaction 3 of the client interactions draft (`docs/helix/01-frame/client-interactions-draft.md`). The action creates a Solution and links it to the use case and to the coverage assertion; the assertion is unchanged. Preconditions are conditions an action declares that must hold before its effects apply.

## Walkthrough

1. Editor invokes `CreateCandidateSolution` for an existing assertion and use case.
2. The system validates the inputs and the preconditions.
3. The system applies the effects and returns a receipt.
4. Editor repeats the invocation for an assertion that already has a candidate.
5. The system refuses it, lists the failed precondition and changes nothing.

## Acceptance Criteria

- [ ] **US-014-AC1** — Given valid inputs and true preconditions, when invoked, then a Solution is created and linked and a receipt returns.
- [ ] **US-014-AC2** — Given an invalid input, when invoked, then `Invalid` lists every violation and nothing changes.
- [ ] **US-014-AC3** — Given a false precondition, when invoked, then `PreconditionFailed` lists every failed precondition with its reason and nothing changes.
- [ ] **US-014-AC4** — Given a person whose own grants do not include write access to the module, when invoked, then `Refused` is returned and nothing changes.

## Edge Cases

- Several failures at once: all are reported.
- Preconditions evaluated inside the transaction: a concurrent change cannot make a true check false at commit.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Success | US-014-AC1 | Assertion `ca-17` with no candidate; use case `uc-pipeline-mapping` | Invoke `CreateCandidateSolution` | Solution created and linked to both; receipt returned; `ca-17` unchanged |
| Inputs | US-014-AC2 | Input `useCase` missing and `assertion` of the wrong type | Invoke | `Invalid` listing both violations; nothing changed |
| Precondition | US-014-AC3 | `ca-17` already has a candidate | Invoke | `PreconditionFailed` with the reason; nothing changed |
| Refused | US-014-AC4 | Person with read access only | Invoke | `Refused`; nothing changed |

## Dependencies

- **Stories**: US-013
- **Feature Spec**: FEAT-003
- **Feature Requirements**: ACT-02
- **PRD Requirements**: FR-15
- **External**: CONTRACT-003, Invocation.

## Out of Scope

Atomic application of the effects (US-015), idempotent repetition (US-016), and validating without applying (US-045).
