---
ddx:
  id: FEAT-002
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

# Feature Specification: FEAT-002 — Type Registry

**Feature ID**: FEAT-002
**Status**: Draft
**Priority**: P0
**Owner**: Erik LaBianca
**Covered PRD Subsystem(s)**: Type Registry
**Covered PRD Requirements**: FR-3, FR-9 to FR-13
**Cross-Subsystem Rationale**: None; single subsystem.

## Overview

The Type Registry implements PRD FR-3 and FR-9 to FR-13. A module defines its entity types, relationships and actions as a UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions) document. The host's configuration, not the document, places the module: its record store, its replicas and, per action, its provider (its placement). A client enumerates with `describe` what the ontology holds and what each backend can do with it. A backend is a named store with the roles reader and provider; in production they are Truss (the hot mutable store on Lakebase, Databricks managed Postgres) and Ashlar (the warehouse store on Unity Catalog, Databricks' data catalog and access-control layer).

## Ideal Future State

A module owner writes one UMF document; the host's placement names the module's record store, replicas and providers. The registry accepts it on the record store, and every client sees the types, relationships, actions and per-backend capabilities from one ontology revision. Changing a type never rewrites records.

## Problem Statement

- **Current situation**: The catalog's shapes live implicitly in seed data.
- **Pain points**: Without declared types nothing can check a change, and no screen can discover what the ontology holds or what a store supports.
- **Desired outcome**: One declaration per module, in UMF only, from which clients and the console are generated.

## Functional Areas

| Area | User question or job | Feature responsibility |
|------|----------------------|------------------------|
| Definition | How does a module say what it holds? | A UMF document defining one module |
| Placement | Where does it live? | The host's placement: record store, replicas and providers per module |
| Enumeration | What is here, and what can `query` do with it? | Types, relationships, actions and capabilities, from one revision |
| Evolution | Can it change safely? | Additive changes only; refusals with counts |
| Reading UMF | Does Arras agree with UMF? | Corpus cases for UMF validity |

## Requirements

### Functional Requirements by Area

#### Definition

REG-01. Types are defined by UMF documents and by nothing else. Each document defines one module. Unsupported constructs are refused, naming the construct (FR-9).

#### Placement

REG-02. Each module's record store, replicas and providers are the host's configuration (a placement per module, or a default), never part of the UMF document (FR-10).

#### Enumeration

REG-03. A caller enumerates modules, entity types, properties, keys, relationships, actions, placement and per-backend capabilities (`columns`, `relationships`, `count`, `mutable`, `latency_class`) from one ontology revision with `describe`, and so learns what `query` accepts for each type (FR-3, FR-11).

#### Evolution

REG-04. Changing a type does not require rewriting records. A change that would is refused with the count or the offending records (FR-12).

#### Validating a change

REG-06. A person holding the record store's `schema` grant validates a document without applying it and sees what it would add, change or retire and every refusal with its rule and count, then registers it as themselves; the backend, not Arras, decides who holds the grant (FR-61; ADR-026; CONTRACT-002).

#### Reading UMF

REG-05. Arras's reading of UMF agrees with the reference validator on the shared corpus cases (FR-13).

### Non-Functional Requirements

- **Performance** (proposed): type enumeration p95 (95th percentile) ≤ 20 ms at the host.
- **Reliability**: a failed registration leaves the previous revision in force.
- **Consistency**: an enumeration is read from one ontology revision.

## User Stories

- [US-008: Define a module's types as a UMF document](../user-stories/US-008-define-a-module-as-a-umf-document.md)
- [US-009: Configure where a module lives](../user-stories/US-009-configure-where-a-module-lives.md)
- [US-010: Enumerate types and what each backend supports](../user-stories/US-010-enumerate-types-and-what-backends-support.md)
- [US-011: Change types without rewriting records](../user-stories/US-011-change-types-without-rewriting-records.md)
- [US-012: Read UMF the way the reference validator does](../user-stories/US-012-read-umf-the-way-the-reference-does.md)

## Edge Cases and Error Handling

- A document that defines two modules is refused.
- A relationship that names a module the registrant cannot read is refused.
- A relationship that names a type no document defines is refused, or accepted as provisional by policy.
- A module with no placement, or whose placement names a backend that is not configured or is of the wrong kind, is refused as `invalid_placement`.
- When a registration happens while a write is in flight, the write is checked against one consistent revision.

## Success Metrics

- 0 records are rewritten by any accepted registration.
- 100% of the corpus's UMF cases give the reference diagnostics.

## Constraints and Assumptions

- Documents are UMF core 0.10.0 at the time of writing.
- A Python UMF reader does not yet exist.

## Dependencies

- **Other features**: FEAT-004 (the record store, as provider, accepts the revision), FEAT-001 (reads use the enumerated capabilities).
- **External services**: UMF; the backends' catalog acceptance; the exact surface lives in CONTRACT-002 (type registry and placement).
- **PRD requirements**: FR-3, FR-9 to FR-13 (P0 item 2).

## Out of Scope

- Defining or extending UMF.
- Moving a module's record store while it has records.
