---
ddx:
  id: US-033
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-006
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-033: Fail the build on a boundary violation

**Feature**: FEAT-006 — Embedding and Lifecycle
**Feature Requirements**: EMB-04
**PRD Requirements**: FR-34
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** the build to fail if Arras imports the host or the host imports an Arras internal
**So that** the independence both sides rely on is enforced on every change

## Context

The public names are those listed in `arras.__all__`. The check runs in each repository: Arras's and the host's (the embedding host).

## Walkthrough

1. A change in Arras imports a host module.
2. The system fails the build in the check.
3. A host change imports an Arras internal.
4. The system fails the build in the check.

## Acceptance Criteria

- [ ] **US-033-AC1** — Given Arras importing a host module, when the check runs, then it fails.
- [ ] **US-033-AC2** — Given the host importing a name outside `__all__`, when the check runs, then it fails.
- [ ] **US-033-AC3** — Given only public names in use, when the check runs, then it passes.
- [ ] **US-033-AC4** — Given a new public name, when it is added, then it is listed in `__all__` and documented.

## Edge Cases

- **A type-only import**: counted as an import.
- **A test helper**: sits outside the package boundary and is not checked.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Arras to host | US-033-AC1 | An Arras module imports a the embedding host module | Run the check | Fails |
| Host to internal | US-033-AC2 | The host imports a name not in `__all__` | Run the check | Fails |
| Public | US-033-AC3 | The host imports only names in `__all__` | Run the check | Passes |
| New name | US-033-AC4 | A name added to the public interface | Run the check and review the documentation | Name is in `__all__` and documented |

## Dependencies

- **Stories**: None
- **Feature Spec**: FEAT-006
- **Feature Requirements**: EMB-04
- **PRD Requirements**: FR-34
- **External**: [CONTRACT-005](../../02-design/contracts/CONTRACT-005-embedding-and-lifecycle.md), Public names.

## Out of Scope

- Runtime isolation between Arras and the host.
- Boundary checks on the backends' own code.
