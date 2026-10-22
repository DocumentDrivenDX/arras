---
ddx:
  id: US-055
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

# US-055: See who changed an entity and when

**Feature**: FEAT-001 — Ontology Reads
**Feature Requirements**: READ-08
**PRD Requirements**: FR-47
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** an opened entity to say who created and last changed it, when, and for an imported entity where it came from
**So that** a screen can show attribution without a history operation, and a loaded record is never mistaken for one a person wrote

## Context

Arras (the interface to an ontology) records the person on every change and the load on every import, and offers no change feed; what changed is read with `changes` (FEAT-010, CONTRACT-001). A client such as the praxis catalog screens (praxis is the Databricks app that embeds Arras) needs the latest attribution on the record it shows. A load is one run of `import_records` (CONTRACT-003).

## Walkthrough

1. A product-team user corrects a Solution through an action.
2. The client opens the Solution with `alias.*`, which carries the fact columns the backend appends.
3. The row names that user and the time as the last change, and the person who first created it.
4. The client opens an imported use case and sees its original author and time and the load that brought it in.

## Acceptance Criteria

- [ ] **US-055-AC1** — Given a Solution created by `ana` and corrected by `ben`, when it is opened with `alias.*`, then `_created_by` is `ana`, `_updated_by` is `ben`, and both times are present.
- [ ] **US-055-AC2** — Given an entity imported with original author `seed-author` by load `L1` initiated by `ops`, when it is opened, then `_original_author` is `seed-author`, `_load_id` is `L1`, and `_created_by` is `ops`.
- [ ] **US-055-AC3** — Given an imported entity whose source held no author, when it is opened, then `_original_author` is `null`, not the load's initiator.
- [ ] **US-055-AC4** — Given the attribution names, when selected as columns, then the statement is refused as unsupported and says to use `alias.*`.

## Edge Cases

- An entity never changed after creation has `_updated_by` and `_updated_at` equal to the creation values.
- After a bulk or batch change, each entity carries the person who invoked it.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Created and changed | US-055-AC1 | `ana` creates, `ben` corrects | Open with `alias.*` | created `ana`; updated `ben` |
| Imported | US-055-AC2 | Load `L1` by `ops`, author `seed-author` | Open | original `seed-author`; load `L1`; created `ops` |
| Absent author | US-055-AC3 | Source without author | Open | `null` |
| Not a column | US-055-AC4 | `SELECT u._updated_by ...` | Query | Unsupported, use `alias.*` |

## Dependencies

- **Stories**: None
- **Feature Spec**: FEAT-001
- **Feature Requirements**: READ-08
- **PRD Requirements**: FR-47
- **External**: CONTRACT-001, `alias.*`; CONTRACT-003, Import.

## Out of Scope

- A history of earlier values or a change feed.
