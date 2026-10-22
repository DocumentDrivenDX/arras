---
ddx:
  id: US-037
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-007
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-037: Keep the console read-only and scoped to the viewer

**Feature**: FEAT-007 — Admin Console
**Feature Requirements**: CON-03
**PRD Requirements**: FR-37
**Priority**: P1
**Status**: Draft

## Story

**As a** Platform owner
**I want** to know that the console cannot change data and shows only what the viewer's principal may see
**So that** I can give it to administrators without granting them write access or wider read access

## Context

The generated GraphQL schema has no Mutation or Subscription type, and every field is read as the viewer's principal (the person's user, token and groups). The console is mounted in the embedding application.

## Walkthrough

1. The owner introspects the schema.
2. The owner opens the console as two different principals.
3. The system shows each principal only what the backends allow that person.
4. The owner mounts the console in the embedded app.

## Acceptance Criteria

- [ ] **US-037-AC1** — Given any module's schema, when it is introspected, then no Mutation or Subscription type exists.
- [ ] **US-037-AC2** — Given two principals, when each browses, then each sees only what the backends allow that person, because every field is read by one `query` with the viewer's own token.
- [ ] **US-037-AC3** — Given a viewer who is not signed in, when a request is made, then the response is HTTP 401.
- [ ] **US-037-AC4** — Given the app embedded in the embedding host, when the console is mounted, then it needs no frontend framework of Arras's own.

## Edge Cases

- **A request over the depth or cost limit**: refused with the limit's code.
- **GET on a GraphQL path**: HTTP 405.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Introspect | US-037-AC1 | The `catalog` schema | Introspect | No Mutation or Subscription type |
| Scoped | US-037-AC2 | Principal A reads `catalog`; principal B reads `archive` | Browse as each | Each sees only its own module |
| 401 | US-037-AC3 | No sign-in | Request | HTTP 401 |
| Embedded | US-037-AC4 | Embedding application | Mount the console | Works with GraphiQL only |

## Dependencies

- **Stories**: US-035
- **Feature Spec**: FEAT-007
- **Feature Requirements**: CON-03
- **PRD Requirements**: FR-37
- **External**: [CONTRACT-006](../../02-design/contracts/CONTRACT-006-console-graphql-surface.md), Mounting and Limits.

## Out of Scope

- Writes of any kind, which go through the library's actions.
- End-user screens, which the host owns.
