---
ddx:
  id: US-039
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-008
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-039: Correct a Solution and create a candidate

**Feature**: FEAT-008 — Reference Clients
**Feature Requirements**: CLI-01
**PRD Requirements**: FR-38
**Priority**: P0
**Status**: Draft

## Story

**As a** Catalog editor (through a client)
**I want** to correct a Solution's coverage level, or create a candidate from one coverage assertion, and see the change at once
**So that** the catalog holds one current answer, attributed to me

## Context

These are interactions 3 and 4 of the [client interactions draft](../client-interactions-draft.md). Each change is a UMF action (UMF is the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions) invoked with the editor's own token. The receipt an action returns carries a token that a later read passes as `at_least`.

## Walkthrough

1. The editor creates a candidate Solution from a coverage assertion.
2. The editor corrects a Solution's coverage level.
3. The screen reads the Solution back with the receipt's token.
4. The system shows the corrected value.
5. The editor opens the change record, and the system shows the editor as the author.

## Acceptance Criteria

- [ ] **US-039-AC1** — Given an assertion, when a candidate is created, then it carries the assertion's coverage level and provenance, links to the use case and the assertion, and leaves the assertion unchanged.
- [ ] **US-039-AC2** — Given a correction, when it is saved and read back with the receipt's token, then the corrected value shows at once.
- [ ] **US-039-AC3** — Given a person whose own grants do not allow authoring, when the person authors, then the action is refused and the client records the refusal.
- [ ] **US-039-AC4** — Given the change record, when it is read, then the change names the editor and the action.

## Edge Cases

- **Candidates are created one at a time by a person**: nothing creates them in bulk.
- **A finding**: never creates or promotes a Solution.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Candidate | US-039-AC1 | One coverage assertion | Create a candidate | Candidate linked to use case and assertion; assertion unchanged |
| Correct | US-039-AC2 | Solution `sol-pipeline-01` | Correct the level, read with the receipt's token | Corrected value shown at once |
| Refused | US-039-AC3 | Person without authoring grants | Author | Refused; refusal recorded by the client |
| Record | US-039-AC4 | A saved correction | Read the change record | Editor and action named |

## Dependencies

- **Stories**: US-014, US-006
- **Feature Spec**: FEAT-008
- **Feature Requirements**: CLI-01
- **PRD Requirements**: FR-38
- **External**: [CONTRACT-003](../../02-design/contracts/CONTRACT-003-actions.md); FR-38 (the upstream catalog reference-client requirement); the host owns its feature implementation.

## Out of Scope

- Bulk creation or bulk correction of Solutions (US-046 to US-048).
- Promoting a finding to a Solution.
