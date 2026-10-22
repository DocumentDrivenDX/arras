---
ddx:
  id: US-001
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

# US-001: Read an entity by key with one query and see how current it is

**Feature**: FEAT-001 — Ontology Reads
**Feature Requirements**: READ-01, READ-05
**PRD Requirements**: FR-1, FR-6
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to read one entity by its key with a single statement and see its version, the ontology revision and how current the answer is
**So that** I know what I am looking at and which store answered

## Context

Arras is the interface through which an organization's applications read and change the ontology. Reads use one operation, `query`: the caller names the module and passes a Weft SQL statement, which the serving backend compiles and runs; a key lookup is one of its statements (CONTRACT-001, the ontology interface contract). An entity is identified by its module-qualified type and key. `latest` is served by the record store and `bulk` may be served by a replica (ADR-014, the architecture decision record on consistency and freshness). The record store of the catalog module is the backend the host's placement names for it, the system of record for it; a replica is a backend that holds a copy fed from the record store (in production, Truss on Lakebase and Ashlar on Unity Catalog; in the sandbox, `memory` and `memory_replica`). The running example is a catalog Solution.

## Walkthrough

1. Developer runs `query("catalog", "SELECT s.* FROM catalog.Solution s WHERE s.code = 'sol-pipeline-01' ORDER BY s.code LIMIT 1")` at `latest`.
2. Arras serves it from the module's record store.
3. The answer carries one row with the declared properties and the `_version` column the backend appends, plus the ontology revision, the backend and `as_of`.
4. Developer queries a key that does not exist.
5. The answer carries no rows and raises no error.

## Acceptance Criteria

- [ ] **US-001-AC1** — Given a Solution, when it is queried by key at `latest`, then one row carries its properties and version and the answer states the ontology revision and a freshness that names the record store.
- [ ] **US-001-AC2** — Given a key that does not exist, when it is queried, then no rows are returned and no error is raised.
- [ ] **US-001-AC3** — Given `bulk`, when a replica serves the type, then the freshness names the replica and its `as_of` position.
- [ ] **US-001-AC4** — Given `latest`, when only a replica is reachable, then `Unavailable` is raised and the replica never answers.
- [ ] **US-001-AC5** — Given a statement Weft or the serving backend does not serve, when it runs, then `Unsupported` names the construct and what the backend supports.

## Edge Cases

- A key in another module: the caller names that module, and the statement's types are qualified by it; a statement that reads outside the named module is `Unsupported`.
- An entity deleted since a replica was fed: `latest` returns no rows; `bulk` may still return it and says how old the answer is.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Read | US-001-AC1 | `catalog.Solution` `sol-pipeline-01` exists | Query by key at `latest` | One row with properties and `_version`; ontology revision; freshness names the record store |
| Absent | US-001-AC2 | No Solution with code `sol-missing` | Query that key | Zero rows, no error |
| Replica | US-001-AC3 | `sol-pipeline-01` has been fed to the replica | Query it at `bulk` | Freshness names the replica and its `as_of` position |
| No fallback | US-001-AC4 | The record store unreachable, the replica reachable | Query at `latest` | `Unavailable`; the replica is not called |
| Language | US-001-AC5 | Statement with `WHERE s.code = 'a' OR s.code = 'b'` | Query | `Unsupported` naming `OR` and listing the supported shapes |

## Dependencies

- **Stories**: None
- **Feature Spec**: FEAT-001
- **Feature Requirements**: READ-01, READ-05
- **PRD Requirements**: FR-1, FR-6
- **External**: CONTRACT-001, `query`, and Weft for the language; ADR-014.

## Out of Scope

Listing a type's entities (US-002), reading relationships (US-003), counting (US-004), and requiring an answer at least as new as a receipt (US-006).
