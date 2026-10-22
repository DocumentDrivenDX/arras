---
ddx:
  id: US-060
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
    - id: prd
      kind: informed_by
---

# US-060: Browse a module's schema

**Feature**: FEAT-010 — Operator Console
**Feature Requirements**: OPR-01
**PRD Requirements**: FR-48
**Priority**: P1
**Status**: Draft

## Story

**As a** module builder
**I want** to see a module's types, relationships, actions, the host's placement and revision, and the relationships as a diagram
**So that** I can understand what a module holds before I change anything

## Context

A module builder builds modules for readers and needs to read what a module declares, from the registry through the console's meta schema (CONTRACT-006).

## Walkthrough

1. The builder opens the console and sees the modules her principal may read.
2. She opens `catalog` and reads its types, properties and capabilities.
3. She opens the relationship diagram and an action's inputs, preconditions and effects.
4. She sees which backend is the record store and the registry revision.
5. She opens the UMF source view and reads the module's registered UMF document in UMF's schema browser.

## Acceptance Criteria

- [ ] **US-060-AC1** — Given a principal with read access to `catalog` only, when the module list is opened, then only `catalog` appears.
- [ ] **US-060-AC2** — Given a module, when it is opened, then each type shows its properties, relationships and capabilities, and each action its typed inputs.
- [ ] **US-060-AC3** — Given a module with six types, when the diagram is opened, then every relationship between its types is drawn with its multiplicities.
- [ ] **US-060-AC4** — Given a module the viewer cannot read, when its address is opened directly, then the console shows the same not-found answer as for an unknown module.
- [ ] **US-060-AC5** — Given a module the viewer may read, when the UMF source view is opened, then the module's registered UMF document is shown in UMF's schema browser exactly as it was registered, and a viewer who reads no module sees an empty catalog.

## Edge Cases

- **A module whose registry changes while it is open**: the page shows the revision at load and offers a refresh.
- **A relationship end in another module**: the diagram shows the name and no detail.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| the module list is opened | US-060-AC1 | a principal with read access to `catalog` only | the module list is opened | only `catalog` appears |
| it is opened | US-060-AC2 | a module | it is opened | each type shows its properties, relationships and capabilities, and each action  |
| the diagram is opened | US-060-AC3 | a module with six types | the diagram is opened | every relationship between its types is drawn with its multiplicities |
| its address is opened directly | US-060-AC4 | a module the viewer cannot read | its address is opened directly | the console shows the same not-found answer as for an unknown module |
| the UMF source view is opened | US-060-AC5 | a module the viewer may read | the UMF source view is opened | the registered document is shown in UMF's schema browser as registered; a viewer with no module sees an empty catalog |

## Dependencies

- **Stories**: None
- **Feature Spec**: FEAT-010
- **Feature Requirements**: OPR-01, OPR-11
- **PRD Requirements**: FR-48
