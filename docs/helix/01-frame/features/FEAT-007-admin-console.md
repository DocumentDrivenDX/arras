---
ddx:
  id: FEAT-007
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

# Feature Specification: FEAT-007 — Admin Console

**Feature ID**: FEAT-007
**Status**: Draft
**Priority**: P1
**Owner**: Erik LaBianca
**Covered PRD Subsystem(s)**: Admin Console
**Covered PRD Requirements**: FR-36 to FR-37
**Cross-Subsystem Rationale**: None; single subsystem.

## Overview

The Admin Console implements PRD FR-36 and FR-37: a minimal read-only interface for administrators and module developers to see what the ontology holds. It shows modules, their types, placement and capabilities, and the entities of each type with their relationships. It is a GraphQL (a query language for APIs) read binding of the interface, explored through GraphiQL (a browser-based GraphQL explorer). Every field is read by one `query`. ADR-011 (the architecture decision record for this surface) records the choice.

## Ideal Future State

An administrator opens the console and sees the modules her principal may read. She picks one, reads its types and what each backend supports, picks a type, pages through its entries, and opens one to see its relationships and follow them. Nothing in the console changes data.

## Problem Statement

- **Current situation**: Nobody can see what the ontology holds without writing queries.
- **Pain points**: Checking a module's types and entries needs backend access and knowledge of each store.
- **Desired outcome**: A read-only browse surface generated from the registry, with no frontend framework of Arras's own.

## Functional Areas

| Area | User question or job | Feature responsibility |
|------|----------------------|------------------------|
| Modules and types | What can this module hold? | Types, placement, capabilities |
| Entries | What is in it? | Paged lists by type, each page after the last key of the one before, with freshness |
| Detail | What is this one? | Properties and relationship fields |
| Safety | Can it change anything? | No writes; only what the viewer may read |

## Requirements

### Functional Requirements by Area

#### Modules and types

CON-01. An administrator lists the modules they may read and browses their types, placement and capabilities (FR-36).

#### Entries

CON-02. An administrator browses the entries of one type as a paged list in key order (the next page read after the last key shown, CONTRACT-006 `afterKey`), opens one to see its properties and relationships, and moves between related entries. Every field is read by one `query`, and the schema has no field beyond entries and their relationships (FR-36).

#### Safety

CON-03. The console performs no write, shows only what the viewer's principal permits, reads through the interface with the viewer's own token, and is available when Arras is embedded (FR-37).

### Non-Functional Requirements

- **Security**: no Mutation or Subscription type exists in any generated schema. Each request runs as the viewer's principal with the viewer's own token.
- **Performance** (proposed): schema generation and an entry page complete within 1 second at p95 (95th percentile) for the catalog's six types.
- **Cost**: a request reads at most 1,000 entities. Relationship fields come from the same `query` row, with no query per entity.

## User Stories

- [US-035: Browse modules and their types](../user-stories/US-035-browse-modules-and-their-types.md)
- [US-036: Browse a type's entries and open one](../user-stories/US-036-browse-a-types-entries-and-open-one.md)
- [US-037: Keep the console read-only and scoped to the viewer](../user-stories/US-037-keep-the-console-read-only-and-principal-scoped.md)

## Edge Cases and Error Handling

- A module the viewer cannot read is absent, and a direct request for it returns 404.
- When the registry changes while the viewer browses, the page shows the revision at load and can be refreshed.
- When one backend is down, only the fields that need it error.

## Success Metrics

- The console lists only readable modules in tests with two principals.
- An introspection test finds no Mutation for any module.

## Constraints and Assumptions

- ADR-011 (read-only GraphQL on graphql-core, a Python GraphQL library, with GraphiQL assets pinned) is accepted or revised before build.
- The console is for administrators, not end users.

## Dependencies

- **Other features**: FEAT-001 (reads), FEAT-002 (the registry), FEAT-005 (the principal).
- **External services**: graphql-core and GraphiQL assets; the exact surface lives in CONTRACT-006 (console GraphQL surface).
- **PRD requirements**: FR-36 and FR-37 (P1 item 1).

## Out of Scope

- Writes, actions or any end-user screens. Actions through an interface are FEAT-010's, on a separate surface.
- A frontend framework.
