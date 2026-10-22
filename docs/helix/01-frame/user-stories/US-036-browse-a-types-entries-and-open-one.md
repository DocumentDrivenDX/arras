---
ddx:
  id: US-036
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-007
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-036: Browse a type's entries and open one

**Feature**: FEAT-007 — Admin Console
**Feature Requirements**: CON-02
**PRD Requirements**: FR-36
**Priority**: P1
**Status**: Draft

## Story

**As a** Platform owner
**I want** to page through the entries of one type, open one, and follow its relationships
**So that** I can inspect real data and the links between entities

## Context

Entries show their freshness (how current the answer is). Relationship fields are the keys that `RELATED_KEYS(x.relationship, 100)` returns in the entry's own `query` row, and following one opens the related entry. The console reads every field with one `query` call (the single read operation of CONTRACT-001, Arras's ontology interface).

## Walkthrough

1. The owner picks the `Solution` type.
2. The system pages the entries in key order with one `query` per page, each page after the last key of the one before.
3. The owner opens one entry and follows a relationship.
4. The system opens the related entry.
5. The owner returns to the list.

## Acceptance Criteria

- [ ] **US-036-AC1** — Given a type, when its entries are listed, then pages of at most 100 appear in key order, `truncated` when more follow, the next read with `afterKey` set to the page's last key, each with its freshness.
- [ ] **US-036-AC2** — Given an entry, when it is opened, then its properties and relationship fields appear from one `query` row, each relationship as at most 100 keys.
- [ ] **US-036-AC3** — Given a relationship, when it is followed, then the related entry opens.
- [ ] **US-036-AC4** — Given a request over 1,000 entities, when it is made, then the result is `COST_EXCEEDED`.
- [ ] **US-036-AC5** — Given a schema, when it is inspected, then it has no field beyond entries and their relationships.

## Edge Cases

- **An entity with a reference outside the module**: the console shows the reference as a key.
- **A relationship with more than 100 keys**: the console shows the 100 that the statement's `RELATED_KEYS` bound returns.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Page | US-036-AC1 | `Solution` type with 250 entries | List, then the next page with `afterKey` | Pages of at most 100 in key order, `truncated` until the last, freshness |
| Detail | US-036-AC2 | One `Solution` | Open | Properties and relationship keys |
| Follow | US-036-AC3 | A Solution's link to a use case | Follow | The use case opens |
| Cost | US-036-AC4 | Request over 1,001 entities | Request | `COST_EXCEEDED` |
| Fields | US-036-AC5 | The generated schema | Inspect | Only entries and relationships |

## Dependencies

- **Stories**: US-035
- **Feature Spec**: FEAT-007
- **Feature Requirements**: CON-02
- **PRD Requirements**: FR-36
- **External**: [CONTRACT-006](../../02-design/contracts/CONTRACT-006-console-graphql-surface.md), Generated schema.

## Out of Scope

- Searching or filtering entries beyond paging.
- Following a reference into another backend's entity as a live relationship. The reference stays a key.
