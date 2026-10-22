---
ddx:
  id: US-003
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

# US-003: Open an entity with its relationships and find what connects to it

**Feature**: FEAT-001 — Ontology Reads
**Feature Requirements**: READ-03
**PRD Requirements**: FR-2
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to read an entity together with the keys it relates to, and to list the entities that relate to a given key
**So that** I can open a use case with its Solutions in one call and find the Solutions that address it in another

## Context

The catalog screen opens a use case and shows the Solutions that address it. Weft SQL has no traversal operation: `RELATED_KEYS(alias.relationship, n)` projects a relationship's keys as a column, the statement bounding `n`, and `HAS_RELATED` filters by a related key. `alias.*` carries the entity's declared fields and the fact columns the backend appends. The backend declares the Weft profile that serves them (Weft, DocumentDrivenDX/weft, owns the language), and until it does the read is `Unsupported`.

## Walkthrough

1. Developer runs `query("catalog", "SELECT u.*, RELATED_KEYS(u.addressedBy, 100) AS addressedBy FROM catalog.UseCase u WHERE u.code = 'uc-pipeline-mapping' ORDER BY u.code LIMIT 1")`.
2. The row carries the use case's properties and `addressedBy`, an array of at most 100 keys.
3. Developer runs, for the same module, `SELECT s.code, s.name FROM catalog.Solution s WHERE HAS_RELATED(s.addresses, KEY('uc-pipeline-mapping'))`.
4. The system returns the Solutions connected to that use case, paged by the statement.

## Acceptance Criteria

- [ ] **US-003-AC1** — Given a use case with Solutions, when it is queried with `alias.*` and `RELATED_KEYS` for a relationship, then the row carries every declared property that has a value and, for that relationship, the keys of the entities on the other end.
- [ ] **US-003-AC2** — Given a relationship with more keys than the statement's `RELATED_KEYS` bound `n`, when it is returned, then the column holds at most `n` keys.
- [ ] **US-003-AC3** — Given a relationship predicate naming a key, when queried, then only entities that have that relationship to the key are returned.
- [ ] **US-003-AC4** — Given a relationship the serving backend does not serve, when it is used in a predicate, then `Unsupported` names it.
- [ ] **US-003-AC5** — Given a relationship that crosses modules, when the viewer cannot read the other module, then its keys are not returned.
- [ ] **US-003-AC6** — Given a relationship predicate naming the inverse name of a relationship and a key, when queried, then the same entities are returned as with the relationship's own name.

## Edge Cases

- A high-degree entity: the answer is bounded by the statement's `RELATED_KEYS` bound and by the page limit.
- Following a key: a further statement; the client decides how far to go.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Open | US-003-AC1 | `uc-pipeline-mapping` with Solutions | `u.*, RELATED_KEYS(u.addressedBy, 100)` by code | Properties and the `addressedBy` key array |
| Bound | US-003-AC2 | A use case addressed by 150 Solutions | `RELATED_KEYS(u.addressedBy, 100)` | 100 keys in `addressedBy` |
| Predicate | US-003-AC3 | `uc-pipeline-mapping` exists | `WHERE HAS_RELATED(s.addresses, KEY('uc-pipeline-mapping'))` | Only Solutions that address it |
| Inverse | US-003-AC6 | Inverse name declared for `addresses` | Filter by the inverse name | Same entities as the relationship's own name |
| Not served | US-003-AC4 | Relationship the serving backend does not serve | Filter by it | `Unsupported` naming the relationship |
| Cross-module | US-003-AC5 | Viewer without read access to the other module | `RELATED_KEYS` on an entity that links into it | Those keys are withheld |

## Dependencies

- **Stories**: US-001
- **Feature Spec**: FEAT-001
- **Feature Requirements**: READ-03
- **PRD Requirements**: FR-2
- **External**: CONTRACT-001, `query`, `alias.*`, `RELATED_KEYS` and `HAS_RELATED`; Weft owns all three.

## Out of Scope

Multi-hop traversal and joins (each hop is a further statement), and fetching entities held by another backend (US-007).
