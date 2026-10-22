---
ddx:
  id: US-044
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-008
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-044: Meet the latency targets on the catalog

**Feature**: FEAT-008 — Reference Clients
**Feature Requirements**: CLI-04
**PRD Requirements**: FR-41
**Priority**: P0
**Status**: Draft

## Story

**As a** Platform owner
**I want** to see the singleton read, the action and the type enumeration meet their targets on the catalog at the host
**So that** screens stay responsive without caching layers

## Context

The targets are proposed, each as a 95th percentile (p95): singleton read at most 20 ms, action at most 100 ms, enumeration at most 20 ms, and the list of 30 records at most 1 s. The host is praxis, the Databricks app that embeds Arras. The benchmark runs against a Lakebase branch (a copy of the Databricks managed Postgres database that backs the Truss adapter).

## Walkthrough

1. The owner runs the benchmark harness at the host on a Lakebase branch.
2. The harness runs 100 sequential reads, 100 invocations of a three-effect action and 100 enumerations.
3. The harness reports the p95 for each.

## Acceptance Criteria

- [ ] **US-044-AC1** — Given 100 sequential singleton reads at the host, when they are measured, then p95 is at most 20 ms.
- [ ] **US-044-AC2** — Given 100 invocations of a three-effect action, when they are measured, then p95 is at most 100 ms including the change record.
- [ ] **US-044-AC3** — Given 100 type enumerations, when they are measured, then p95 is at most 20 ms.
- [ ] **US-044-AC4** — Given the 30-record list, when it is measured, then p95 is at most 1 second.

## Edge Cases

- **The Lakebase network round trip**: part of the measurement.
- **A target is missed**: the targets or the design are revised on the evidence. The Truss adapter's design is not ratified until the harness has run.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Read | US-044-AC1 | 100 sequential singleton reads | Measure | p95 at most 20 ms |
| Action | US-044-AC2 | 100 invocations of a three-effect action | Measure | p95 at most 100 ms |
| Enumerate | US-044-AC3 | 100 type enumerations | Measure | p95 at most 20 ms |
| List | US-044-AC4 | The 30-record list | Measure | p95 at most 1 s |

## Dependencies

- **Stories**: US-038
- **Feature Spec**: FEAT-008
- **Feature Requirements**: CLI-04
- **PRD Requirements**: FR-41
- **External**: Benchmark harness at the host (`tests/bench_latency.py` runs it at the host layer on a local PostgreSQL; the run through praxis on a Lakebase branch is owed).

## Out of Scope

- Latency of `bulk` reads from a replica, which depends on the replica's lag.
- Load testing with concurrent users.
