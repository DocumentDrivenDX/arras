---
ddx:
  id: US-034
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-006
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-034: Run Arras and its tests on a local PostgreSQL 18.6

**Feature**: FEAT-006 — Embedding and Lifecycle
**Feature Requirements**: EMB-05
**PRD Requirements**: FR-35
**Priority**: P1
**Status**: Draft

## Story

**As a** Client developer
**I want** to run the Truss adapter, Arras and its tests against a local PostgreSQL with no external database
**So that** tests are fast and isolated and run on the engine and the Truss install Truss qualifies

## Context

Local development and CI use PostgreSQL 18.6 through `pgserver-pg18`, brought in by `truss-toolkit[local]==0.0.45` in the dependency group `truss-test` (never a base or `dev` dependency). The tests are marked `truss` and run with `uv run --extra truss --group truss-test pytest -m truss`. Truss installs itself; the harness builds that install once as a template database and clones it for each case. Lakebase is the deployed target and is PostgreSQL 18.6.

## Walkthrough

1. The developer syncs the `truss` extra and the `truss-test` group.
2. The harness starts a local PostgreSQL and installs Truss.
3. The developer runs the `truss` tests; each case runs in a database cloned from the template.
4. The system reports the results.

## Acceptance Criteria

- [ ] **US-034-AC1** — Given a local PostgreSQL 18.6, when Arras migrates it, then Truss is installed through its own install and the adapter reads and writes as a person.
- [ ] **US-034-AC2** — Given the test users, when they act, then a member of a module's role is served and a non-member is refused by the database.
- [ ] **US-034-AC3** — Given a database cloned per case, when cases run one after another, then none sees another's data.
- [ ] **US-034-AC4** — Given the pinned Truss release and PostgreSQL 18.6, when the `truss`-marked suite runs, then the conformance corpus passes at the adapter's declared capabilities and documented limits.

## Edge Cases

- **A harness that cannot run** (no `pgserver-pg18`): the tests skip with the reason, and fail under `ARRAS_REQUIRE_TRUSS=1`.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Migrate | US-034-AC1 | Empty local PostgreSQL 18.6 | Migrate | Truss installed; the adapter works as a person |
| Access | US-034-AC2 | A member and a non-member | Read the catalog | Served; refused |
| Isolation | US-034-AC3 | Two cases in turn | Run both | The second world holds nothing of the first |
| Corpus | US-034-AC4 | The pinned release | Run `-m truss` | Passes, with each limit pinned |

## Dependencies

- **Stories**: US-031
- **Feature Spec**: FEAT-006
- **Feature Requirements**: EMB-05
- **PRD Requirements**: FR-35
- **External**: [CONTRACT-005](../../02-design/contracts/CONTRACT-005-embedding-and-lifecycle.md); [ADR-012](../../02-design/adr/ADR-012-own-postgres-database-lakebase-deployed-embedded-locally.md).

## Out of Scope

- Running `pgserver-pg18` in production.
- Testing the Ashlar adapter against Unity Catalog.
