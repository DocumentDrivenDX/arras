---
ddx:
  id: US-020
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-003
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-020: Import seed records repeatably with their provenance, as an administrator

**Feature**: FEAT-003 — Actions
**Feature Requirements**: ACT-08
**PRD Requirements**: FR-21, FR-43
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to import the demonstration records with the administrative principal so that repeating the import changes nothing, and each record keeps its original author and date apart from the load's
**So that** the seed is safe to rerun and nobody is credited for another's work

## Context

This is interaction 5 of the client interactions draft (`docs/helix/01-frame/client-interactions-draft.md`). The import loads 30 use cases and their products, versions, assertions and findings (invented demo data); it creates no Solution. Import is for volume and is administrative: it is not offered to clients or agents. The administrative principal is the principal whose `admin` flag is set, chosen explicitly by the host as a deploy identity or an operator's own token (CONTRACT-005, the embedding and lifecycle contract). A load is one run of the import, identified by a load id.

## Walkthrough

1. Administrator imports the records as load `load-1` with the administrative principal.
2. The system creates each record with its original provenance.
3. A user corrects one record and deletes another.
4. Administrator imports again as `load-2`.
5. The system changes nothing.

## Acceptance Criteria

- [ ] **US-020-AC1** — Given the demonstration records, when imported, then each exists with its identity and relationships, its original author and time where the source has them, and the load recorded apart.
- [ ] **US-020-AC2** — Given a repeated import, when it runs, then nothing changes, the correction survives and the deleted record stays deleted.
- [ ] **US-020-AC3** — Given a record with no source author, when imported, then it states the author is absent.
- [ ] **US-020-AC4** — Given the import completes, when Solutions are counted, then the count is 0.
- [ ] **US-020-AC5** — Given a principal that is not administrative, when it calls `import_records`, then `Refused` is returned and nothing is stored.

## Edge Cases

- An interrupted import: running again creates only the missing records.
- A record naming a missing endpoint: rejected and reported; nothing stored for it.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Import | US-020-AC1 | The demonstration records | Import as `load-1` | The same records with identities, relationships and original provenance; `load-1` recorded apart |
| Repeat | US-020-AC2 | One record corrected, one deleted | Import as `load-2` | No change; correction survives; deletion stands |
| Absent | US-020-AC3 | A record with no source author | Import | Author stated as absent |
| No Solutions | US-020-AC4 | Import complete | Count Solutions | 0 |
| Not admin | US-020-AC5 | Ordinary person `jsmith` | Call `import_records` | `Refused`; nothing stored |

## Dependencies

- **Stories**: US-013
- **Feature Spec**: FEAT-003
- **Feature Requirements**: ACT-08
- **PRD Requirements**: FR-21, FR-43
- **External**: CONTRACT-003, Import; Truss's import API.

## Out of Scope

Importing by clients or agents (not offered), creating Solutions from the seed, and importing into a read-only module (US-019).
