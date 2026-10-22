---
ddx:
  id: US-004
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-001
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-004: Count entities grouped by a property

**Feature**: FEAT-001 — Ontology Reads
**Feature Requirements**: READ-04
**PRD Requirements**: FR-4
**Priority**: P0
**Status**: Draft

## Story

**As an** Analyst (through a client)
**I want** to count use cases grouped by area with one statement and see how current the counts are
**So that** I can show a coverage summary without scanning every entity

## Context

Counts are `COUNT(*)` with `GROUP BY` over one declared property. Weft owns the shape (DocumentDrivenDX/weft; its `count-summary` read profile), and a backend serves it only when it declares that profile. The use case inventory reads counts from the replica, which in production is Ashlar (the replica store: gold Delta tables on Unity Catalog, Databricks' catalog and access-control layer, fed from a provider); a few seconds of age is acceptable and the screen shows the age of the data.

## Walkthrough

1. Analyst runs `query("catalog", "SELECT u.workArea, COUNT(*) FROM catalog.UseCase u GROUP BY u.workArea ORDER BY u.workArea LIMIT 50", consistency="bulk")`.
2. Arras routes it by the catalog module's placement to the first replica that accepts it, and the replica answers with the groups, their counts and `as_of`.
3. Analyst asks for the same counts from a backend that does not declare the `count-summary` profile.
4. The system refuses the statement with `Unsupported`.

## Acceptance Criteria

- [ ] **US-004-AC1** — Given a replica that declares Weft's `count-summary` profile, when the grouped statement runs, then the groups and exact integer counts return with the replica's freshness.
- [ ] **US-004-AC2** — Given a property that is not a declared required scalar, when it is grouped, then `Unsupported` names it.
- [ ] **US-004-AC3** — Given more groups than the call's `limit`, when the statement runs, then at most `limit` rows return and `truncated` is set.
- [ ] **US-004-AC4** — Given no backend of the module's placement serves the statement, when it runs at `bulk`, then each replica's `Unsupported` falls through to the record store and the record store's `Unsupported` is raised.

## Edge Cases

- An empty type: the answer has no groups.
- Counts that change between calls: each answer states its own `as_of`.
- Weft does not serve the shape: counts stay unsupported and clients that need them wait.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Group | US-004-AC1 | Replica declares `count-summary`; 30 use cases | `GROUP BY u.workArea` at `bulk` | One row per area with an integer count; `as_of` present |
| Property | US-004-AC2 | `notes`, an optional property | Group by `notes` | `Unsupported` naming `notes` |
| Bound | US-004-AC3 | 150 distinct values of the grouped property | Count with limit 100 | 100 rows; `truncated` set |
| Profile | US-004-AC4 | No backend declares `count-summary` | Count of `catalog.UseCase` | `Unsupported` |

## Dependencies

- **Stories**: US-001
- **Feature Spec**: FEAT-001
- **Feature Requirements**: READ-04
- **PRD Requirements**: FR-4
- **External**: CONTRACT-001, `query`; Weft's `count-summary` profile.

## Out of Scope

Aggregates other than `COUNT(*)` with one `GROUP BY` property, such as sums, multi-property groupings and joins.
