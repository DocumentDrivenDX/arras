---
ddx:
  id: US-056
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-09
  authoring:
    home: repo
  links:
    - id: FEAT-006
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-056: Keep the library's modules to their dependency rules

**Feature**: FEAT-006 — Embedding and Lifecycle
**Feature Requirements**: EMB-06
**PRD Requirements**: FR-48
**Priority**: P1
**Status**: Draft

## Story

**As a** Client developer
**I want** a change that adds a forbidden or circular import between Arras's own modules to fail the build
**So that** the core never depends on a transport and the structure in the architecture is the structure of the code

## Context

The Module Boundaries section of the architecture names each module's group and the groups it may import. The check reads every module's imports, lazy ones included, and ignores those under `if TYPE_CHECKING:`. It also bounds a module's length, so a module is split before it becomes several.

## Walkthrough

1. A change makes `core` import the console.
2. The check names the module, the line and the groups.
3. The author restructures; the check passes.

## Acceptance Criteria

- [ ] **US-056-AC1** — Given a module importing a group it may not, when the check runs, then it fails naming the module, line and groups.
- [ ] **US-056-AC2** — Given two modules importing each other, when the check runs, then it fails with the cycle.
- [ ] **US-056-AC3** — Given a lazy import inside a function, when the check runs, then it counts as an edge.
- [ ] **US-056-AC4** — Given an import under `if TYPE_CHECKING:`, when the check runs, then it is not an edge.
- [ ] **US-056-AC5** — Given a module longer than the ceiling, when the check runs, then it fails.

## Edge Cases

- **A new module in no group**: reported, so the table is kept complete
- **Raising a ceiling**: not done to admit a change; ceilings are lowered as code is split

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Core to console | US-056-AC1 | core imports `arras.console` | Run the check | Fails |
| Cycle | US-056-AC2 | two modules import each other | Run the check | Fails |
| Lazy import | US-056-AC3 | `core` imports `mcp` inside a function | Run the check | Fails |
| Type-only import | US-056-AC4 | `gqlschema` imports `core` under `TYPE_CHECKING` | Run the check | Passes |
| Long module | US-056-AC5 | a module over the ceiling | Run the check | Fails |
