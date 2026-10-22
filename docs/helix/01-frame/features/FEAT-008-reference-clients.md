---
ddx:
  id: FEAT-008
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

# Feature Specification: FEAT-008 — Reference Clients

**Feature ID**: FEAT-008
**Status**: Draft
**Priority**: P0
**Owner**: Erik LaBianca
**Covered PRD Subsystem(s)**: Reference Clients
**Covered PRD Requirements**: FR-38 to FR-41
**Cross-Subsystem Rationale**: None; single subsystem.

## Overview

Reference Clients implements PRD FR-38 to FR-41. They are the first real users of the interface and the source of its requirements: the product catalog, the use case inventory and praxis (the Databricks app that embeds Arras). Each supplies a module or reads the ontology, and each is exercised by the interactions from which the interface was derived (the [client interactions draft](../client-interactions-draft.md)).

## Ideal Future State

The catalog module supplies its UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions) types and actions. An administrator imports its demonstration records, and its screens browse and correct through the interface. The inventory reads related use cases from a replica (in production Ashlar, the warehouse store on Unity Catalog, Databricks' data catalog and access-control layer) and shows their age. Counts follow once Weft (the SQL project that owns the language `query` takes) serves them. Praxis reads context for the signed-in user with the user's own token on every call and records findings through an action.

## Problem Statement

- **Current situation**: The catalog's knowledge is seed data. The inventory and praxis have no shared ontology interface.
- **Pain points**: Each would otherwise build its own data access, freshness handling and attribution.
- **Desired outcome**: Three clients on one interface, meeting their latency targets and failing closed where required.

## Functional Areas

| Area | User question or job | Feature responsibility |
|------|----------------------|------------------------|
| Product catalog | Browse, author, seed | Types and actions from the catalog module; seed import |
| Use case inventory | Related use cases; counts later | Replica reads with a stated age; counts deferred until Weft serves `COUNT(*)` |
| Praxis | Context and findings | Reads with the user's own token; findings through an action |
| Targets | Fast enough? | Latency targets on the catalog |

## Requirements

### Functional Requirements by Area

#### Product catalog

CLI-01. The catalog module supplies its UMF types and actions. The demonstration records are imported. The use case list of 30 meets the latency target. A correction made through an action is visible to its author at once and attributed to them (FR-38).

#### Use case inventory

CLI-02. The inventory reads related use cases from the replica with relationship predicates and shows how current they are. Counts follow when `COUNT(*)` is served (FR-39, FR-4).

#### Praxis

CLI-03. Praxis reads context on behalf of the signed-in user, with the user's own token on every call and without caching it, and records evaluation findings through an action. An entitlement read fails closed and is blocked on ADR-005 (FR-40). ADR-005 defers durable structure over sensitive source records until a named workload, an entitlement rule and a governed write path exist.

#### Targets

CLI-04. Singleton read, action and type enumeration meet their latency targets on the catalog (FR-41).

### Non-Functional Requirements

- **Performance** (proposed): singleton read p95 (95th percentile) ≤ 20 ms; action p95 ≤ 100 ms; type enumeration p95 ≤ 20 ms; the 30-record list p95 ≤ 1 s.
- **Privacy**: no sensitive source records. Demonstration data is invented.
- **Independence**: clients reach Arras only through its public interface.

## User Stories

- [US-038: Browse the product catalog](../user-stories/US-038-browse-the-product-catalog.md)
- [US-039: Correct a Solution and create a candidate](../user-stories/US-039-correct-and-author-in-the-catalog.md)
- [US-040: Seed the catalog from the demonstration records](../user-stories/US-040-seed-the-catalog-from-demonstration-records.md)
- [US-041: Relate use cases in the inventory, with counts when served](../user-stories/US-041-relate-use-cases-in-the-inventory.md)
- [US-042: Read context for the signed-in user in praxis](../user-stories/US-042-read-context-for-the-signed-in-user-in-praxis.md)
- [US-043: Record an evaluation finding from praxis](../user-stories/US-043-record-an-evaluation-finding-from-praxis.md)
- [US-044: Meet the latency targets on the catalog](../user-stories/US-044-meet-the-latency-targets-on-the-catalog.md)

## Edge Cases and Error Handling

- When the catalog's types have their record store elsewhere than assumed, the host's placement changes before records exist.
- Entitlement reads are blocked until ADR-005's preconditions are answered.
- When praxis passes no token, the call is refused.

## Success Metrics

- The catalog runs on the interface inside praxis within the latency targets.
- Each client interaction in the client interactions draft has a passing scenario.

## Constraints and Assumptions

- The catalog and inventory are the first workloads (ADR-005 precondition P1).
- Praxis-harness's own FEAT-007 (its catalog knowledge feature) stores the catalog through Arras.

## Dependencies

- **Other features**: all features.
- **External services**: praxis-harness; Lakebase; Unity Catalog; Weft (counts).
- **PRD requirements**: FR-38 to FR-41 (P0 item 7).

## Out of Scope

- The clients' own screens and business logic.
- Structure derived from sensitive source records.
