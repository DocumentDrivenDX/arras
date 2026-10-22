---
ddx:
  id: US-010
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-002
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-010: Enumerate types and what each backend supports

**Feature**: FEAT-002 — Type Registry
**Feature Requirements**: REG-03
**PRD Requirements**: FR-3, FR-11
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to list modules, entity types, properties, keys, relationships, actions and per-backend capabilities from one revision, and to see which columns and relationships `query` accepts for each type
**So that** I can build a browse screen and write statements without hardcoding types or guessing what a store does

## Context

`describe` is the only discovery operation (CONTRACT-001, the ontology interface contract; CONTRACT-002, the type registry and placement contract). A capability is what a backend declares per type: the `columns` and `relationships` a statement may use, whether `count` is served, whether the type is `mutable`, and the `latency_class`. Types are defined in UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions) documents. A principal is the person a call is made for.

## Walkthrough

1. Developer calls `describe` for the modules the principal may read.
2. The system returns the modules, their types and each backend's capabilities, and states the ontology revision.
3. Developer reads one module's types and each backend's capabilities.
4. Developer builds a statement from a type's declared `columns` and `relationships` and runs it.
5. The system accepts the statement.

## Acceptance Criteria

- [ ] **US-010-AC1** — Given six entity types in `catalog`, when described, then six types, their relationships, actions and per-backend capabilities (`columns`, `relationships`, `count`, `mutable`, `latency_class`) return from one revision.
- [ ] **US-010-AC2** — Given a registration during the call, when it answers, then the whole answer is from one revision.
- [ ] **US-010-AC3** — Given 100 sequential `describe` calls at the host (the application that embeds Arras), when measured, then p95 is at most 20 ms.
- [ ] **US-010-AC4** — Given a module the principal cannot read, when described, then it is absent.
- [ ] **US-010-AC5** — Given a type's `columns` and `relationships`, when a client builds a statement from them, then `query` accepts it.

## Edge Cases

- An unknown module: not found.
- A module with no types: an empty list and the current revision.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| List | US-010-AC1 | `catalog` with 6 entity types | `describe` | 6 types with relationships, actions and capabilities, one revision |
| One revision | US-010-AC2 | A new revision registered while `describe` runs | `describe` | Every part of the answer carries the same revision |
| Latency | US-010-AC3 | 100 sequential calls at the host | `describe` | p95 at most 20 ms |
| Hidden | US-010-AC4 | Principal without read access to `playbooks` | `describe` | `playbooks` is absent |
| Usable | US-010-AC5 | Declared `columns` of `catalog.UseCase` | Build and run a statement from them | Statement accepted |

## Dependencies

- **Stories**: US-008
- **Feature Spec**: FEAT-002
- **Feature Requirements**: REG-03
- **PRD Requirements**: FR-3, FR-11
- **External**: CONTRACT-002, `types`; CONTRACT-001, `describe`.

## Out of Scope

Registering or changing types (US-008, US-011), and the administration console's browsing screens (US-035).
