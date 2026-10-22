---
ddx:
  id: US-035
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-007
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-035: Browse modules and their types

**Feature**: FEAT-007 — Admin Console
**Feature Requirements**: CON-01
**PRD Requirements**: FR-36
**Priority**: P1
**Status**: Draft

## Story

**As a** Platform owner
**I want** to open the console, see the modules my principal can read, and read one module's types, placement and capabilities
**So that** I can check what the ontology holds without writing queries

## Context

The console is a read-only GraphQL binding (GraphQL is a query language for APIs) explored through GraphiQL (an in-browser GraphQL explorer). A module is a named set of UMF types and actions (UMF is the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions). A principal is the person's user, token and groups.

## Walkthrough

1. The owner opens the console with a principal that reads `catalog` only.
2. The system lists `catalog` and not `archive`.
3. The owner selects `catalog`.
4. The system shows the module's types, placement and capabilities.

## Acceptance Criteria

- [ ] **US-035-AC1** — Given a principal that reads `catalog` only, when the console lists modules, then `catalog` is listed and `archive` is not.
- [ ] **US-035-AC2** — Given `catalog`, when its schema is shown, then each entity type, relationship, action, the placement and the capabilities appear, all from one registry revision.
- [ ] **US-035-AC3** — Given no readable module, when the console opens, then the module list is empty.
- [ ] **US-035-AC4** — Given a direct request for an unreadable module, when the request is made, then the response is HTTP 404.

## Edge Cases

- **The revision changes while browsing**: the page shows the revision at load and can be refreshed.
- **A backend is down**: only the fields that need it return an error.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| List | US-035-AC1 | Principal reads `catalog` only | List modules | `catalog` only |
| Schema | US-035-AC2 | `catalog` | Show the schema | Types, relationships, actions, placement, capabilities from one revision |
| Empty | US-035-AC3 | Principal reads no module | Open the console | Empty list |
| 404 | US-035-AC4 | Principal cannot read `archive` | Request `archive` directly | HTTP 404 |

## Dependencies

- **Stories**: None
- **Feature Spec**: FEAT-007
- **Feature Requirements**: CON-01
- **PRD Requirements**: FR-36
- **External**: [CONTRACT-006](../../02-design/contracts/CONTRACT-006-console-graphql-surface.md), Meta schema.

## Out of Scope

- Browsing a type's entries (US-036).
- Any write from the console (US-037).
