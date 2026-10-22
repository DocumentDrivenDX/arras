---
ddx:
  id: US-002
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-001
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-002: Browse a type's entities with a filtered, bounded query

**Feature**: FEAT-001 — Ontology Reads
**Feature Requirements**: READ-02
**PRD Requirements**: FR-1
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to list the entities of one type in pages, filtered on declared properties, with a marker that says whether more remain
**So that** a screen can browse any type without loading everything

## Context

The demonstration catalog has 30 use cases (invented demo data), and the catalog screen filters them by area. Paging belongs to the statement: `ORDER BY` the type's key, `LIMIT n`, and a keyset predicate (`WHERE u.code > :last`) for the next page. Arras caps each answer at `limit` (1 to 100) and sets `truncated` when the cap cut it; the answer carries no cursor. Capabilities (CONTRACT-002, the type registry and placement contract) describe the columns a client can build on; Weft and the serving backend decide what a statement may select and filter on. The host is the application that embeds Arras.

## Walkthrough

1. Developer runs `query("catalog", "SELECT u.code, u.name FROM catalog.UseCase u WHERE u.workArea = 'data' ORDER BY u.code LIMIT 50")`.
2. The system returns up to 50 rows ordered by key, with `truncated` and freshness.
3. Developer gets the next page by adding `AND u.code > :last` with the last code it saw.
4. Developer filters on a column the type does not declare.
5. The system refuses the statement and names the column.

## Acceptance Criteria

- [ ] **US-002-AC1** — Given 120 use cases, when read in key order with limit 50 and a keyset predicate from each page's last key, then pages of 50, 50 and 20 are returned, and `truncated` is set on each page the cap cut and not on the last.
- [ ] **US-002-AC2** — Given an equality filter on a declared required scalar property, when queried, then only matching entities are returned.
- [ ] **US-002-AC3** — Given a limit below 1 or above 100, when queried, then `Invalid` names the bound.
- [ ] **US-002-AC4** — Given a selected or filtered column the type does not declare, when queried, then the serving backend refuses it with `Unsupported` naming it.
- [ ] **US-002-AC5** — Given the 30-record catalog at the host, when the first page is read, then p95 is at most 1 second.

## Edge Cases

- Entities created during paging: with a keyset predicate on the key, none that existed throughout is repeated or skipped.
- A type with no entities: the answer has no rows and `truncated` false.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Pages | US-002-AC1 | 120 use cases | `ORDER BY u.code`, limit 50, then `WHERE u.code > :last` from each page's last key | Pages of 50, 50 and 20; `truncated` set on the two the cap cut, false on the last |
| Filter | US-002-AC2 | 30 use cases, some with `workArea` `data` | Query with that filter | Only `data` use cases |
| Bounds | US-002-AC3 | Any type | Query with limit 101, then limit 0 | `Invalid` naming the bound each time |
| Undeclared column | US-002-AC4 | Column the type does not declare | Query selecting it | `Unsupported` naming the column |
| Latency | US-002-AC5 | 30-record demonstration catalog at the host | 100 first-page reads | p95 at most 1 s |

## Dependencies

- **Stories**: US-001
- **Feature Spec**: FEAT-001
- **Feature Requirements**: READ-02
- **PRD Requirements**: FR-1
- **External**: CONTRACT-001, `query`; CONTRACT-002, Capabilities.

## Out of Scope

Opening an entity with its relationships (US-003), free-text search (until a backend declares a Weft profile that serves it), and counts (US-004).
