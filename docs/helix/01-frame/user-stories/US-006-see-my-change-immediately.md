---
ddx:
  id: US-006
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

# US-006: See my own change immediately by passing a receipt's token to `query`

**Feature**: FEAT-001 — Ontology Reads
**Feature Requirements**: READ-06
**PRD Requirements**: FR-7
**Priority**: P0
**Status**: Draft

## Story

**As a** Catalog editor (through a client)
**I want** to correct a Solution and then read it with my receipt, so I see the correction wherever the answer comes from
**So that** the screen never shows me an older value after I saved

## Context

After an action, a replica lags the record store by the delay of the change feed (the stream that carries a provider's changes into the replica). The action's receipt carries a token. Passing that token to `query` as `at_least` demands an answer at least that new. Whether Arras waits for the replica or only reports that it has not yet reached the token is an open question in the PRD.

## Walkthrough

1. Editor corrects a Solution's coverage level and receives a receipt.
2. The screen queries the Solution with `at_least` set to the receipt's token.
3. The serving backend has not yet reached the token.
4. The answer comes from the record store, or Arras waits within a bound, or the answer says it is not yet current.

## Acceptance Criteria

- [ ] **US-006-AC1** — Given a receipt, when a query passes its token and the serving backend has reached it, then the answer reflects the change.
- [ ] **US-006-AC2** — Given the replica has not reached the token, when queried, then Arras serves from the record store, waits within a bound, or raises `NotYetCurrent`, and never returns older data.
- [ ] **US-006-AC3** — Given the record store serves the query, when the token is passed, then the token counts as reached at once.
- [ ] **US-006-AC4** — Given a token from another deployment, when passed, then it is refused.

## Edge Cases

- The bound is set by the deployment; whether Arras waits or only reports is an open question (PRD, Open Questions).
- A very low feed lag: most reads reach the token at once.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Reached | US-006-AC1 | Replica has applied the correction | Read with the receipt's token | Answer shows the corrected coverage level |
| Not reached | US-006-AC2 | Replica behind the receipt's token | Read with the token | Record store answer, a bounded wait, or `NotYetCurrent`; never the old value |
| Record store | US-006-AC3 | The record store serves the read | Read with the token | Token reached; corrected value |
| Foreign | US-006-AC4 | Token minted by another deployment | Read with it | Refused |

## Dependencies

- **Stories**: US-014
- **Feature Spec**: FEAT-001
- **Feature Requirements**: READ-06
- **PRD Requirements**: FR-7
- **External**: CONTRACT-001, Consistency; ADR-014.

## Out of Scope

Producing the receipt (US-018) and choosing a consistency level (US-005).
