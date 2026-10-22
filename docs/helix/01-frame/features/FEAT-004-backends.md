---
ddx:
  id: FEAT-004
  type: feature-specification
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: concerns
      kind: informed_by
---

# Feature Specification: FEAT-004 — Backends

**Feature ID**: FEAT-004
**Status**: Draft
**Priority**: P0
**Owner**: Erik LaBianca
**Covered PRD Subsystem(s)**: Backends
**Covered PRD Requirements**: FR-22 to FR-27, FR-51
**Cross-Subsystem Rationale**: None; single subsystem.

## Overview

Backends implement PRD FR-22 to FR-27. They are the stores behind the interface. Each is registered by the host under a name it chooses, declares its roles (`reader`, `provider` or both), and any number may be configured; each module has one record store, zero or more replicas and a provider per action, as the host's placement says (CONTRACT-002). Each implements one contract (`describe`, `status`, and for a reader `query`, `reached` and `catalog`, and for a provider `apply`, `apply_batch`, `import_records` and `register`), advertises what it can do, reports its status and position, and passes a shared conformance corpus.

Three adapters ship. The Truss adapter serves Truss, the hot mutable store on PostgreSQL (Lakebase, Databricks managed Postgres, is the required deployment target), as a reader and provider; its audit reads and text search are `Unsupported`. The Ashlar adapter serves Ashlar, the warehouse store on Unity Catalog (Databricks' data catalog and access-control layer), as a reader that serves as a replica, holds the full ontology and is fed from the providers' stores; the adapter serves bounded reads. The memory adapter is an in-memory reader and provider plus an in-memory reader, registered as `memory` and `memory_replica`; it is a real backend, not a stand-in for a named one.

## Ideal Future State

A client never names a store. Each backend says what it supports, and Arras offers only that. A backend that is down is reported with its reason and never silently replaced. A replica says how far behind it is.

## Problem Statement

- **Current situation**: Each store would need its own client code, and any may change or be added.
- **Pain points**: Without a contract the interface fits whichever store was built first, and a store's outage becomes every client's problem.
- **Desired outcome**: A contract and corpus that every adapter passes, so any can be replaced.

## Functional Areas

| Area | User question or job | Feature responsibility |
|------|----------------------|------------------------|
| Contract | What does a backend do? | Operations, capabilities, tokens, positions |
| Truss adapter | A reader and provider | Parameterized reads as the person; actions and batches over Truss |
| Ashlar adapter | A reader |
| Memory adapter | A reader and provider and a reader, in memory | The same operations over Python data, for tests, the sandbox and the dev host | Bounded reads over gold tables as the user |
| Conformance | Does it behave? | A shared corpus |
| Status | Is it up, and how current? | Per-backend availability and position |

## Requirements

### Functional Requirements by Area

#### Contract

BE-01. Backends implement one contract of operations and a capability descriptor (`read`, `columns`, `relationships`, `count`, `mutable`, `latency_class`), so adapters are interchangeable (FR-22).

#### Truss adapter

BE-02. The Truss adapter serves `query` as parameterized SQL on the Truss tables as the person, and serves actions, batches and imports, for the modules placed on it (FR-23).

#### Ashlar adapter

BE-03. The Ashlar adapter serves bounded `query` for the modules it holds, with the user's own token, and is read-only (FR-24).

#### Conformance

BE-04. Every adapter, the memory adapter included, passes a shared conformance corpus for the backend contract (FR-25).

#### Status

BE-05. Each backend's availability and reason are reported. A partial answer says which backend produced it. No fallback silently changes the consistency level (FR-26).

BE-06. The position that each replica reflects is visible, so freshness can name it and lag can be read (FR-27).

BE-07. The rules of the action and read contracts are checked over arbitrary sequences against an executable model, and the same machine runs over each adapter as part of its acceptance (FR-51, P1).

### Non-Functional Requirements

- **Honesty**: a backend never declares a capability it cannot meet, and Arras never synthesizes one.
- **Performance**: the Truss adapter adds little to Truss's own latency (Truss reads about 0.02 ms on its layout at 1,000 types).
- **Replaceability**: replacing an adapter needs no client change.
- **Safety**: statements reach a backend as parameters, never as concatenated text.

## User Stories

- [US-021: Implement one backend contract with declared capabilities](../user-stories/US-021-implement-one-backend-contract.md)
- [US-022: Serve reads and actions from Truss](../user-stories/US-022-serve-reads-and-actions-from-truss.md)
- [US-023: Serve bounded reads from Ashlar](../user-stories/US-023-serve-bounded-reads-from-ashlar.md)
- [US-024: Pass the shared backend conformance corpus](../user-stories/US-024-pass-the-backend-conformance-corpus.md)
- [US-025: Report each backend's availability and never fall back silently](../user-stories/US-025-report-backend-availability-and-partial-answers.md)
- [US-026: See how far behind a replica is](../user-stories/US-026-see-how-far-behind-a-replica-is.md)
- [US-059: Check the contracts' rules against a model](../user-stories/US-059-check-the-contracts-rules-against-a-model.md)

## Edge Cases and Error Handling

- When a backend is unreachable, it is reported with the reason. Reads that need it fail, and other reads still work.
- Whether a replica is ahead of or behind a token is answered by `reached(token)`.
- When the Truss adapter's layout major version differs, the backend is unavailable with that reason.
- A statement outside the Weft version and read profiles the serving backend declares is refused by that backend as `Unsupported`.

## Success Metrics

- Every adapter passes the corpus for every operation it declares.
- 0 silent fallbacks in the corpus.

## Constraints and Assumptions

- Ashlar is not yet built. Its adapter follows what Ashlar defines.
- Truss's Python implementation may change. The adapter depends on its operations only.

## Dependencies

- **Other features**: FEAT-001 to FEAT-003 (the operations served), FEAT-005 (the person's own token reaches each backend).
- **External services**: Truss and Ashlar; the exact surface lives in CONTRACT-004 (backend contract).
- **PRD requirements**: FR-22 to FR-27 (P0 item 4).

## Out of Scope

- The backends' own storage, feeds and contracts.
- A third backend.
