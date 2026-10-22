---
ddx:
  id: US-022
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

# US-022: Serve reads and actions from Truss

**Feature**: FEAT-004 — Backends
**Feature Requirements**: BE-02
**PRD Requirements**: FR-23
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to have reads and actions for my module served by Truss, as the person, as the module's system of record
**So that** I get fresh reads and atomic changes without knowing the store

## Context

Truss is the hot, mutable store on PostgreSQL (Lakebase, Databricks managed Postgres, is the required deployment target, not yet established by Truss). The Truss adapter receives the module the caller named and the Weft statement and runs it through Truss's query call over a connection authenticated as the person, in a read-only transaction. It maps an action to one Truss group applied as the person, a batch to one group or one group per item, and an import to Truss's import API in chunks of 32 (not atomic across chunks) (CONTRACT-004, the backend contract). The origin actor is the person recorded as the author of a change. Truss 0.0.45 has no journal read, so the audit reads (`changes`, `loads`) are `Unsupported`, and so is text search.

## Walkthrough

1. Developer queries the catalog module by key, by filter, by relationship (`RELATED_KEYS`, `HAS_RELATED`) and with `alias.*`.
2. Truss serves each statement and the freshness names Truss.
3. Developer invokes an action and a batch.
4. Truss applies each as the person.
5. Developer's administrator imports records.
6. Truss applies the import through its import API.

## Acceptance Criteria

- [ ] **US-022-AC1** — Given a module placed on a Truss adapter as record store and provider, when Weft statements are queried (key lookup, equality filters, relationship predicates, whole-entity reads, keyset paging, grouped counts), then Truss compiles and runs each as parameterized SQL when the Weft profile it needs is among those Truss declares, `Unsupported` otherwise, and the freshness names Truss.
- [ ] **US-022-AC2** — Given an action, when invoked, then the adapter applies it as one Truss group with the person as origin actor and the idempotency key as the group's request id, and builds the receipt from the group's results and the replay of its token.
- [ ] **US-022-AC3** — Given a batch, when `atomic`, then one group applies; otherwise one group per item, each with its own request id `module.Action:key#index`.
- [ ] **US-022-AC4** — Given a person whose database role is not in the module's reader or writer role, when the adapter acts as them, then the database refuses.
- [ ] **US-022-AC5** — Given a literal in a statement, when it runs, then it travels as a parameter and is never concatenated into SQL.

## Edge Cases

- Truss's layout at another major version: the backend is unavailable with that reason.
- Prepared statements off: the adapter still works, at a small cost.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Reads | US-022-AC1 | `catalog` placed on the Truss adapter | Key lookup, equality filter, `HAS_RELATED`, `RELATED_KEYS`, `alias.*` with appended fact columns, keyset-paged list, grouped count | Each compiled by Weft in Truss and served as parameterized SQL where Truss declares the profile; freshness names Truss |
| Action | US-022-AC2 | `CreateCandidateSolution` with key `ui-7f3a`, token of `jsmith` | Invoke | One Truss group; origin actor `jsmith`; request id `catalog.CreateCandidateSolution:ui-7f3a`; receipt from the group's results |
| Batch | US-022-AC3 | Batch of 3 items, key `k1` | Apply with `atomic` true, then false | One group; then three groups with request ids ending `#0`, `#1`, `#2` |
| No role | US-022-AC4 | Person outside the `catalog` reader and writer roles | Query or invoke | Database refuses |
| Parameters | US-022-AC5 | Statement containing literal `'sol-pipeline-01'` | Query | Literal sent as a parameter; SQL text contains none |

## Dependencies

- **Stories**: US-021
- **Feature Spec**: FEAT-004
- **Feature Requirements**: BE-02
- **PRD Requirements**: FR-23
- **External**: CONTRACT-004, Truss adapter; Truss CONTRACT-004.

## Out of Scope

Reads served by replicas (US-023), and Truss's own storage layout and feed (owned by Truss).
