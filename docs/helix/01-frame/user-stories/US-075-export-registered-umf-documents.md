---
ddx:
  id: US-075
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
    - id: FEAT-001
      kind: informed_by
    - id: ADR-026
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-075: Export registered UMF documents

**Feature**: FEAT-010 — Operator Console
**Feature Requirements**: OPR-14
**PRD Requirements**: FR-52
**Priority**: P1
**Status**: Draft

## Story

**As a** Client developer
**I want** to download a module's registered UMF document, or every one I may read
**So that** that I can keep it in source control, review it, or load it into another deployment

## Context

The registered document is read as the viewer already (`document`, CONTRACT-009 schema catalog); export is a download of that text, with no new operation.

## Walkthrough

1. The developer opens a module's Schema view and chooses Export.
2. The browser saves `<module>.umf.json`, character for character as registered.
3. She chooses Export all and saves the catalog as one file.

## Acceptance Criteria

- [ ] **US-075-AC1** — Given a registered module the viewer may read, when it is exported, then the file holds the text it was registered with, byte for byte, named `<module>.umf.json`.
- [ ] **US-075-AC2** — Given a viewer who reads two of three modules, when everything is exported, then the file holds those two and says nothing of the third.
- [ ] **US-075-AC3** — Given a module with no registered document (attached, not registered), when export is opened, then it is not offered for that module.
- [ ] **US-075-AC4** — Given an exported document, when it is validated against the same deployment, then the plan says nothing would change.

## Edge Cases

- **A document over 1 MiB**: the catalog shows a note instead of the text; export says it is not shown and never saves the note as the document.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| it is exported | US-075-AC1 | a registered module the viewer may read | it is exported | the file holds the text it was registered with, byte for byte, named for the module with t |
| everything is exported | US-075-AC2 | a viewer who reads two of three modules | everything is exported | the file holds those two and says nothing of the third |
| export is opened | US-075-AC3 | a module with no registered document (attached,  | export is opened | it is not offered for that module |
| it is validated against the same deployment | US-075-AC4 | an exported document | it is validated against the same deployment | the plan says nothing would change |

## Dependencies

- **Stories**: US-060
- **Feature Spec**: FEAT-010
- **Feature Requirements**: OPR-14
- **PRD Requirements**: FR-52
