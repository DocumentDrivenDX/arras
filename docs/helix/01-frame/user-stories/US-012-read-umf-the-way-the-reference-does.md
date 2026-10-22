---
ddx:
  id: US-012
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-002
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-012: Read UMF the way the reference validator does

**Feature**: FEAT-002 — Type Registry
**Feature Requirements**: REG-05
**PRD Requirements**: FR-13
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to know that Arras accepts and rejects the same UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions) documents, with the same diagnostics, as UMF's own validator
**So that** a document means the same in Arras as everywhere else

## Context

Arras's reader is written in Python, and agreement with UMF's reference validator is shown by the shared corpus cases, not assumed. A diagnostic is one finding the validator reports for a document, with a severity, a code and a path.

## Walkthrough

1. Developer runs the corpus's UMF cases through Arras's reader.
2. The system compares validity and each diagnostic's severity, code and path against the reference's.
3. The system reports any difference.

## Acceptance Criteria

- [ ] **US-012-AC1** — Given a document the reference accepts, when read, then it is accepted.
- [ ] **US-012-AC2** — Given a document the reference rejects, when read, then it is rejected with the same diagnostics by severity, code and path.
- [ ] **US-012-AC3** — Given a feature Arras does not support, when read, then it is rejected and the feature named.
- [ ] **US-012-AC4** — Given a new UMF version, when the corpus is updated, then Arras reports which versions it passes.

## Edge Cases

- A warning-only document: accepted, with the warning reported.
- Message text: not compared.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Accept | US-012-AC1 | A corpus case the reference accepts | Read | Accepted |
| Reject | US-012-AC2 | A corpus case the reference rejects with one error | Read | Rejected with the same severity, code and path |
| Unsupported | US-012-AC3 | A document using a construct Arras lacks | Read | Rejected, construct named |
| Versions | US-012-AC4 | Corpus updated to a new UMF version | Run the corpus | Report lists the UMF versions Arras passes |

## Dependencies

- **Stories**: US-008
- **Feature Spec**: FEAT-002
- **Feature Requirements**: REG-05
- **PRD Requirements**: FR-13
- **External**: CONTRACT-002; Truss CONTRACT-004, `umf` cases; UMF's declarative actions, validity fixtures and relationship semantics.

## Out of Scope

Defining new UMF constructs, and comparing diagnostic message text.
