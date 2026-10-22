---
ddx:
  id: US-061
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-09
  authoring:
    home: repo
  links:
    - id: FEAT-010
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-061: Read a type as a table and follow a relationship

**Feature**: FEAT-010 — Operator Console
**Feature Requirements**: OPR-02
**PRD Requirements**: FR-49
**Priority**: P1
**Status**: Draft

## Story

**As a** module builder
**I want** to open a type as a paged, filterable table, read an entity with its attribution and follow a relationship
**So that** I can inspect real data and how current it is

## Context

The table reads through CONTRACT-006's list fields, so its filters are equality on declared columns and relationships, ordering is by key, a page holds at most the chosen limit (100 at most) and says `truncated` when more follow, the next page is read after the page's last key (`afterKey`), and every page states its freshness.

## Walkthrough

1. The builder opens the `Solution` type as a table.
2. She filters on a column and pages forward.
3. She switches between `LATEST` and `BULK` and sees the freshness change.
4. She opens a row beside the table, reads its properties and attribution, and follows a relationship.

## Acceptance Criteria

- [ ] **US-061-AC1** — Given a type with 250 entities, when its table is opened, then pages of at most 100 appear in key order, Next reading the entities after the page's last key and Previous returning to a page read, each with the page's freshness.
- [ ] **US-061-AC2** — Given a table, when a filter on a declared column is applied, then only matching entries appear; a column that is not declared is not offered.
- [ ] **US-061-AC3** — Given an entity, when it is opened, then its properties, version and who created and last changed it appear.
- [ ] **US-061-AC4** — Given a relationship, when it is followed, then the entity at the other end opens beside the table.
- [ ] **US-061-AC5** — Given a viewer, when `BULK` is chosen, then the freshness shown is the replica's position and lag.

## Edge Cases

- A relationship with more than 100 keys shows the 100 that the `RELATED_KEYS` bound returns.
- A request over the cost limits shows `COST_EXCEEDED` and the table stays usable.
- **The record store is down**: replica rows show, marked not current.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| its table is opened | US-061-AC1 | a type with 250 entities | its table is opened; Next; Next; Previous | pages of 100, 100 and 50 in key order, each after the last key of the page before, with the page's freshness |
| a filter on a declared column is applied | US-061-AC2 | a table | a filter on a declared column is applied | only matching entries appear; a column that is not declared is not offered |
| it is opened | US-061-AC3 | an entity | it is opened | its properties, version and who created and last changed it appear |
| it is followed | US-061-AC4 | a relationship | it is followed | the entity at the other end opens beside the table |
| `BULK` is chosen | US-061-AC5 | a viewer | `BULK` is chosen | the freshness shown is the replica's position and lag |

## Dependencies

- **Stories**: US-060
- **Feature Spec**: FEAT-010
- **Feature Requirements**: OPR-02
- **PRD Requirements**: FR-49
