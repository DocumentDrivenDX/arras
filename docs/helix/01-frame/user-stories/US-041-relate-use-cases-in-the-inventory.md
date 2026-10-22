---
ddx:
  id: US-041
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-008
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-041: Relate use cases in the inventory, with counts when served

**Feature**: FEAT-008 — Reference Clients
**Feature Requirements**: CLI-02
**PRD Requirements**: FR-39, FR-4
**Priority**: P0
**Status**: Draft

## Story

**As an** Analyst (through a client)
**I want** to see the use cases related through a shared Solution or product, how current they are, and counts by area once a replica serves them
**So that** I can see coverage across the catalog

## Context

These are interactions 6 and 7 of the [client interactions draft](../client-interactions-draft.md), served from a replica (in production Ashlar, the warehouse copy of the ontology on Unity Catalog (Databricks' governance and access layer). Relatedness is read with `HAS_RELATED` and `RELATED_KEYS`, one bounded statement on the catalog module per step. Counts depend on Weft (the owner of the SQL language `query` takes) serving `COUNT(*)` with `GROUP BY` (FR-4; Weft support is requested).

## Walkthrough

1. The analyst opens the related use cases for one use case.
2. The screen reads the Solutions that address it, then the use cases those Solutions address, each at consistency `bulk` (a replica may serve it) with its age.
3. The screen shows how current the data is.
4. The analyst opens the coverage summary.

## Acceptance Criteria

- [ ] **US-041-AC1** — Given the replica, when the Solutions that address a use case and then the use cases they address are queried at `bulk`, then bounded results return with `as_of` (the position the answer reflects).
- [ ] **US-041-AC2** — Given a high-degree Solution or product, when its relationships are read, then each `RELATED_KEYS` column holds at most the statement's bound of 100 keys, and the screen says the list is cut when it holds the bound.
- [ ] **US-041-AC3** — Given the screen, when it displays the data, then it shows how current the data is.
- [ ] **US-041-AC4** — Given the replica is unavailable, when the screen loads, then it shows the reason and shows no stale data unlabeled.
- [ ] **US-041-AC5** — Given Weft does not serve `COUNT(*)` with `GROUP BY`, when the coverage summary is requested, then the answer is `Unsupported` and the screen shows no counts.
- [ ] **US-041-AC6** — Given Weft serves `COUNT(*)` with `GROUP BY`, when the coverage summary is requested, then counts by area return with `as_of`.

## Edge Cases

- **A very low lag**: the screen still shows the age.
- **Counts before Weft serves the shape**: the screen shows no counts.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Related | US-041-AC1 | Use case `uc-pipeline-mapping` | Query at `bulk` | Bounded results with `as_of` |
| Cap | US-041-AC2 | Solution addressing 150 use cases | `RELATED_KEYS(s.addresses, 100)` | 100 keys; the screen says the list is cut |
| Age | US-041-AC3 | Any related-use-case screen | Display | Age shown |
| Down | US-041-AC4 | Replica unreachable | Load the screen | Reason shown; no unlabeled stale data |
| Counts unserved | US-041-AC5 | `COUNT(*)` with `GROUP BY` unserved | Request the summary | `Unsupported`; no counts shown |
| Counts served | US-041-AC6 | `COUNT(*)` with `GROUP BY` served | Request the summary | Counts by area with `as_of` |

## Dependencies

- **Stories**: US-004, US-003
- **Feature Spec**: FEAT-008
- **Feature Requirements**: CLI-02
- **PRD Requirements**: FR-39, FR-4
- **External**: [CONTRACT-001](../../02-design/contracts/CONTRACT-001-ontology-interface.md).

## Out of Scope

- Recursive traversal; a join is available only where the serving backend declares a Weft profile that admits it, and the story's steps do not depend on one.
- Aggregates other than `COUNT(*)` grouped by one property.
