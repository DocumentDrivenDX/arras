---
ddx:
  id: US-007
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

# US-007: See references to entities held elsewhere as keys

**Feature**: FEAT-001 — Ontology Reads
**Feature Requirements**: READ-07
**PRD Requirements**: FR-8
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to see relationships to entities that another backend holds, or that the ontology does not own, as keys, with each key's type available from `describe`
**So that** I pay for a cross-store read only when I ask for it with a further statement

## Context

A catalog finding points at a the embedding host workflow id that the ontology does not own, and a Solution may point at an entity that the replica holds. The embedding host owns application/session behavior. Arras returns such a reference as its key, with the key's type available from `describe`, and never fetches it implicitly.

## Walkthrough

1. Developer opens a use case that references the embedding host workflows, projecting the relationship with `RELATED_KEYS(u.relationship, 100)`.
2. The `RELATED_KEYS` column carries the references as keys.
3. Arras reads no other backend to fill them.
4. Developer queries one referenced key in the module that holds it, naming that module.
5. The answer states its own freshness.

## Acceptance Criteria

- [ ] **US-007-AC1** — Given a relationship to an entity the serving backend does not hold, when the relationship is read with `RELATED_KEYS`, then its key appears in that column, its type is available from `describe`, and nothing else is fetched.
- [ ] **US-007-AC2** — Given a reference outside the ontology, such as a the embedding host workflow id, when it is returned, then it is returned as its key and Arras does not interpret its meaning.
- [ ] **US-007-AC3** — Given a referenced entity that no longer exists, when its key is queried, then no rows return and the reference in the earlier answer is unchanged.
- [ ] **US-007-AC4** — Given a reference to an entity the serving backend does hold, when the entity is read, then the key is returned in the same form.

## Edge Cases

- More references than the statement's `RELATED_KEYS` bound: the column holds at most that many, as for any relationship.
- Reading the referenced entity: a further `query`, which states its own freshness.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Reference | US-007-AC1 | Solution linked to an entity only another backend holds | `RELATED_KEYS` on the Solution | Key in the column; no other backend called |
| External | US-007-AC2 | Use case referencing the embedding host workflow id `wf-1042` | `RELATED_KEYS` | `wf-1042` returned as a key |
| Dangling | US-007-AC3 | Referenced entity deleted | Query its key | No rows; the earlier answer's reference is unchanged |
| Local | US-007-AC4 | Referenced entity held by the serving backend | `RELATED_KEYS` | Key returned in the same form |

## Dependencies

- **Stories**: US-001, US-003
- **Feature Spec**: FEAT-001
- **Feature Requirements**: READ-07
- **PRD Requirements**: FR-8
- **External**: CONTRACT-001, `query` and `RELATED_KEYS`.

## Out of Scope

Resolving a reference automatically, interpreting a reference outside the ontology, and joins across backends.
