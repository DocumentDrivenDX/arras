---
ddx:
  id: US-011
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-002
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-011: Change types without rewriting records

**Feature**: FEAT-002 — Type Registry
**Feature Requirements**: REG-04
**PRD Requirements**: FR-12
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to add a property or a type and have existing records keep working
**So that** a schema change never needs a data migration

## Context

Registrations are additive. A change that existing records cannot satisfy is refused before it is accepted, and the refusal names the number of records affected (PRD FR-12). A revision is one accepted version of a module's type definitions.

## Walkthrough

1. Developer registers a revision that adds an optional property `notes`.
2. Existing entities read unchanged and state their earlier revision.
3. Developer registers a revision that adds a required property.
4. The system refuses it and names the number of existing records that lack the property.

## Acceptance Criteria

- [ ] **US-011-AC1** — Given records, when an optional property is added, then they read unchanged and no record is rewritten.
- [ ] **US-011-AC2** — Given 40 Solutions, when a required property is added, then the registration is refused with the count 40.
- [ ] **US-011-AC3** — Given a type or property that records use, when its removal is requested, then it is refused with the count.
- [ ] **US-011-AC4** — Given the same document registered twice, when the second runs, then no new revision is created.
- [ ] **US-011-AC5** — Given 40 Solutions, when a property is added optional, filled on every Solution and then made required, then each registration succeeds.

## Edge Cases

- A change of a property's type or of a key: refused.
- Another module registers: this module's types do not change though the revision advances.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Optional | US-011-AC1 | 40 Solutions | Register a revision adding optional `notes` | All 40 read unchanged; no record rewritten |
| Required | US-011-AC2 | 40 Solutions without `riskLevel` | Register a revision adding required `riskLevel` | Refused with count 40 |
| Remove | US-011-AC3 | 40 Solutions use `coverageLevel` | Register a revision removing it | Refused with count 40 |
| Twice | US-011-AC4 | A document already registered | Register the same bytes again | No new revision |
| Fill then require | US-011-AC5 | 40 Solutions without `riskLevel` | Register `riskLevel` optional, set it on all 40, then register it required | Each registration succeeds |

## Dependencies

- **Stories**: US-008
- **Feature Spec**: FEAT-002
- **Feature Requirements**: REG-04
- **PRD Requirements**: FR-12
- **External**: CONTRACT-002, Revisions.

## Out of Scope

Migrating or backfilling record values (a client does that with actions), and renaming types.
