---
ddx:
  id: US-038
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-008
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-038: Browse the product catalog

**Feature**: FEAT-008 — Reference Clients
**Feature Requirements**: CLI-01, CLI-04
**PRD Requirements**: FR-38, FR-41
**Priority**: P0
**Status**: Draft

## Story

**As a** Catalog editor (through a client)
**I want** to browse use cases, filter by area, and open one with its Solutions, products and findings
**So that** I can see what the catalog holds about a kind of work and the evidence behind it

## Context

These are interactions 1 and 2 of the [client interactions draft](../client-interactions-draft.md), run on the demo catalog: 30 use cases of invented data. The catalog is the first Arras client and runs inside praxis, the Databricks app that embeds Arras.

## Walkthrough

1. The editor opens the catalog and lists use cases.
2. The editor filters by area.
3. The editor opens a use case, and the screen reads it with one `query` of the catalog module: `alias.*` for its fields and `RELATED_KEYS` for its relationship keys.
4. The system reads the Solutions that address the use case with `HAS_RELATED`, then their products and findings.
5. The screen shows each finding as primary or adjacent.

## Acceptance Criteria

- [ ] **US-038-AC1** — Given the 30 demo use cases, when the list is read, then the first page returns within the list target and states its freshness.
- [ ] **US-038-AC2** — Given a use case, when it is opened, then its Solutions, their products and their findings appear, read with `alias.*`, `RELATED_KEYS` and `HAS_RELATED`, with each finding's product, version and applicability.
- [ ] **US-038-AC3** — Given a finding about a version that is no longer current, when it is shown, then the caveat appears.
- [ ] **US-038-AC4** — Given a use case with no Solution, when it is opened, then the screen says none is recorded.

## Edge Cases

- **Evidence about one product**: never shown as evidence about another.
- **Invented data**: labeled as demo data.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| List | US-038-AC1 | 30 demo use cases | List the first page | Returns within the list target (p95 at most 1 s); freshness stated |
| Open | US-038-AC2 | Use case `uc-pipeline-mapping` | Open | Solutions, products, findings with product, version, applicability |
| Caveat | US-038-AC3 | Finding about a superseded product version | Show | Caveat shown |
| None | US-038-AC4 | Use case with no Solution | Open | States none is recorded |

## Dependencies

- **Stories**: US-002, US-003
- **Feature Spec**: FEAT-008
- **Feature Requirements**: CLI-01, CLI-04
- **PRD Requirements**: FR-38, FR-41
- **External**: [CONTRACT-001](../../02-design/contracts/CONTRACT-001-ontology-interface.md); praxis FEAT-007 (the catalog feature in the praxis-harness repository).

## Out of Scope

- Correcting or creating catalog records (US-039).
- Real data. The catalog holds invented demo data.
