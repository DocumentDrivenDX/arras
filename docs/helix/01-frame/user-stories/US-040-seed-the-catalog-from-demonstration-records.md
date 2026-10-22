---
ddx:
  id: US-040
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

# US-040: Seed the catalog from the demonstration records

**Feature**: FEAT-008 — Reference Clients
**Feature Requirements**: CLI-01
**PRD Requirements**: FR-38
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to load the demonstration records with their identity, relationships and original provenance, repeatably
**So that** the catalog runs on the interface inside praxis within the latency targets with data to browse, and the load is safe to rerun

## Context

This is interaction 5 of the [client interactions draft](../client-interactions-draft.md). The import is defined in CONTRACT-003 and is administrative: it runs as the administrative principal, not as a person. Praxis is the Databricks app that embeds Arras.

## Walkthrough

1. The administrator runs the import with the administrative principal.
2. The developer counts records by type and reads one finding.
3. The developer corrects one record.
4. The administrator reruns the import.
5. The system keeps the correction and adds no duplicate.

## Acceptance Criteria

- [ ] **US-040-AC1** — Given the records, when they are imported, then each exists with its source identity and each finding keeps its source author and date.
- [ ] **US-040-AC2** — Given a repeated import, when it runs after a correction, then the correction remains and nothing is duplicated.
- [ ] **US-040-AC3** — Given the import completes, when Solutions are counted, then the count is 0.
- [ ] **US-040-AC4** — Given the load's provenance, when it is read, then it names the load and its initiator, not an author.

## Edge Cases

- **A record naming a missing endpoint**: the import reports it and stores nothing for that record.
- **An interrupted import**: rerunning completes it.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Identity | US-040-AC1 | The demonstration records | Import | Each has its source identity; findings keep author and date |
| Repeat | US-040-AC2 | One record corrected after the first import | Rerun | Correction kept; no duplicate |
| No Solutions | US-040-AC3 | Import complete | Count Solutions | 0 |
| Load | US-040-AC4 | The load's provenance | Read | Names the load and the administrator who started it |

## Dependencies

- **Stories**: US-020
- **Feature Spec**: FEAT-008
- **Feature Requirements**: CLI-01
- **PRD Requirements**: FR-38
- **External**: [CONTRACT-003](../../02-design/contracts/CONTRACT-003-actions.md), Import.

## Out of Scope

- Importing real data.
- Creating Solutions. A person creates each candidate (US-039).
