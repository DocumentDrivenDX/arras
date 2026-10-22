---
ddx:
  id: US-021
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-004
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-021: Implement one backend contract with declared capabilities

**Feature**: FEAT-004 — Backends
**Feature Requirements**: BE-01
**PRD Requirements**: FR-22
**Priority**: P0
**Status**: Draft

## Story

**As a** Backend implementer
**I want** to implement the backend contract and declare exactly what my backend can do
**So that** Arras offers clients only what is true of my store

## Context

The backend contract (CONTRACT-004) is the same for every adapter: the Truss adapter, the Ashlar adapter and the memory adapter. Truss is the hot, mutable store on Lakebase (Databricks managed Postgres); Ashlar is the replica store on Unity Catalog (Databricks' catalog and access-control layer). An adapter declares its roles in `describe().roles`. A reader implements `describe`, `status`, `query`, `reached`, `catalog` and `attach`. A provider also implements `apply`, `apply_batch`, `import_records` and `register`. The Truss and memory adapters are both; the Ashlar adapter is a reader. Each adapter declares capabilities per type.

## Walkthrough

1. Implementer builds an adapter's `describe()` with per-type capabilities.
2. Implementer implements the operations it declares and no others.
3. Arras registers the adapter.
4. A client asks for a capability the adapter did not declare.
5. The system refuses the request without calling the adapter.

## Acceptance Criteria

- [ ] **US-021-AC1** — Given an adapter, when described, then it declares per type: `read`, `columns`, `relationships`, `count`, `mutable` and `latency_class`, and implements `describe`, `status`, `query` and `reached`.
- [ ] **US-021-AC2** — Given a statement outside the Weft version and read profiles the adapter declares, when a client runs it, then the adapter answers `Unsupported` and runs nothing.
- [ ] **US-021-AC3** — Given an adapter that declares a capability it cannot meet, when the corpus runs, then the case fails.
- [ ] **US-021-AC4** — Given an adapter replaced by another that passes the corpus, when a client queries, then no client change is needed.
- [ ] **US-021-AC5** — Given a backend that declares the provider role, when described, then it also implements `apply`, `apply_batch`, `import_records` and `register`.
- [ ] **US-021-AC6** — Given a replica, when described, then it raises `Unsupported` for `apply`, `apply_batch`, `import_records` and `register` and implements `attach`.

## Edge Cases

- A backend that is a reader only: `mutable` is false.
- A backend serving only `bulk`: `latest` is never routed to it.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Describe | US-021-AC1 | Adapter declaring `read`, `columns`, `relationships`, `count`, `mutable`, `latency_class` for `catalog.UseCase` | `describe()` | All six capabilities per type; four operations present |
| Undeclared | US-021-AC2 | Adapter that does not declare `count-summary` | Client runs a grouped count | `Unsupported`; nothing is run |
| Overclaim | US-021-AC3 | Adapter declares the `count-summary` profile but cannot serve it | Run the corpus | Count case fails |
| Replace | US-021-AC4 | Second adapter passing the corpus | Same client query | Same answer shape; no client change |
| Provider operations | US-021-AC5 | One adapter with the provider role | Describe it | Has `apply`, `apply_batch`, `import_records`, `register` |
| Replica operations | US-021-AC6 | One replica adapter | Describe it | Raises `Unsupported` for `apply`, `apply_batch`, `import_records`, `register`; has `attach` |

## Dependencies

- **Stories**: None
- **Feature Spec**: FEAT-004
- **Feature Requirements**: BE-01
- **PRD Requirements**: FR-22
- **External**: CONTRACT-004, Adapter operations and Capabilities.

## Out of Scope

Choosing a module's record store and providers (US-009), and the adapters' own storage layouts.
