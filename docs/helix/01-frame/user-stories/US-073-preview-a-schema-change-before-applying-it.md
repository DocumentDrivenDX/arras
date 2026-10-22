---
ddx:
  id: US-073
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-010
      kind: informed_by
    - id: FEAT-002
      kind: informed_by
    - id: ADR-026
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-073: Preview a schema change before applying it

**Feature**: FEAT-010 — Operator Console
**Feature Requirements**: OPR-12
**PRD Requirements**: FR-61
**Priority**: P1
**Status**: Draft

## Story

**As a** module builder
**I want** to choose a UMF document and see what it would change, and what would refuse it, before anything is applied
**So that** that I never find out a change is incompatible by attempting it

## Context

Validate-only registration runs the rules registration runs and applies nothing (CONTRACT-002, CONTRACT-011). A compatibility refusal names its rule and the count or the offending records (US-011).

## Walkthrough

1. The builder opens a module's Schema view and chooses a file.
2. The console sends it for validation and shows the types, properties, relationships and actions it would add, change or retire.
3. She chooses a file that adds a required property while 40 records exist; the console shows the refusal with the count 40 and offers no apply.

## Acceptance Criteria

- [ ] **US-073-AC1** — Given a compatible document, when it is validated, then the plan lists what it would add, change and retire, nothing is applied, and no revision or journal row is created.
- [ ] **US-073-AC2** — Given a document that adds a required property while 40 records exist, when it is validated, then `ok` is false with the rule and the count 40, and no apply is offered.
- [ ] **US-073-AC3** — Given a document that does not parse, when it is validated, then every violation is shown (400) and no apply is offered; and given a parsed document for a module the host placed nowhere, when it is validated, then it is refused as `invalid_placement` (400); and given a placed module whose document breaks a host rule, when a person with the grant validates it, then the plan is `ok: false` with the violation.
- [ ] **US-073-AC4** — Given a document equal in meaning to the one in force, when it is validated, then the plan says nothing would change.
- [ ] **US-073-AC5** — Given a record store with no dry run, when a document is validated, then the console says import is not offered for that module (501).

## Edge Cases

- **A very large document**: over 1 MiB is refused with a clear message (413).
- **A document for another module**: the plan names the module it holds, never the contents of one the viewer cannot read.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| it is validated | US-073-AC1 | a compatible document | it is validated | the plan lists what it would add, change and retire, nothing is applied, and no revision o |
| it is validated | US-073-AC2 | a document that adds a required property while 4 | it is validated | `ok` is false with the rule and the count 40, and no apply is offered |
| it is validated | US-073-AC3 | a document that does not parse; one for a module the host placed nowhere; one that breaks a host rule | it is validated | 400 with violations; 400 `invalid_placement`; a plan `ok: false` |
| it is validated | US-073-AC4 | a document equal in meaning to the one in force | it is validated | the plan says nothing would change |
| a document is validated | US-073-AC5 | a record store with no dry run | a document is validated | the console says import is not offered for that module (501) |

## Dependencies

- **Stories**: US-060
- **Feature Spec**: FEAT-010
- **Feature Requirements**: OPR-12
- **PRD Requirements**: FR-61
