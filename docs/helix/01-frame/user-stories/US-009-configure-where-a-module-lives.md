---
ddx:
  id: US-009
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-002
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-009: Configure where a module lives

**Feature**: FEAT-002 — Type Registry
**Feature Requirements**: REG-02
**PRD Requirements**: FR-10
**Priority**: P0
**Status**: Draft

## Story

**As a** Host developer
**I want** to state in the host's configuration, for each module, which backend is its record store, which are its replicas and which provider applies each action
**So that** reads and actions go to the right store

## Context

Placement is host configuration, not part of the UMF document (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions): the host passes `placement={"<module>": Placement(record, replicas=(), providers={})}` and optionally `default_placement` to `Arras.start` (CONTRACT-002, CONTRACT-005). A backend declares its roles in `describe().roles`: `reader` (serves reads) and/or `provider` (applies actions). The record store is a reader and the module's system of record; it serves `latest`. Replicas are other readers, in preference order, and serve `bulk`. `providers` maps an action name to the provider backend that applies it; an action with no entry runs on the record store, which must then be a provider. In production the catalog's mutable types are placed with the Truss adapter as record store and an Ashlar replica, and playbooks have the Ashlar adapter as record store and no actions; these placements are an assumption the type owners have not yet confirmed (PRD, Open Questions).

## Walkthrough

1. The host registers backends under names it chooses (a reader and provider, a reader) and places `catalog` on them.
2. The system checks the named backends are configured and have the roles the placement needs.
3. The host registers a module with no placement and no default.
4. The system refuses it.

## Acceptance Criteria

- [ ] **US-009-AC1** — Given a placement naming one configured reader as record store, when a module is registered, then reads at `latest` go only to that backend, and an action with no named provider runs on it.
- [ ] **US-009-AC2** — Given replicas, when `bulk` reads are served, then the first replica that serves the statement answers, in the order the placement lists them, else the record store.
- [ ] **US-009-AC3** — Given no placement and no default, a backend that is not configured, a record store or replica without the reader role, a provider without the provider role, or a reader named twice, when the module is registered or attached, then `invalid_placement` is returned and the module is not served.
- [ ] **US-009-AC4** — Given two record stores each placed for their own modules, when each module is read and changed, then each is served by its own record store.
- [ ] **US-009-AC5** — Given a placement that names a provider for an action, when the action is invoked, then it runs on that provider and not on the record store.
- [ ] **US-009-AC6** — Given a module placed on a record store and replicas, when it is described or read, then its revision is an object keyed by backend name, the record store's entry carrying the module's catalog revision.
- [ ] **US-009-AC7** — Given an `expected_revision` that names only some of the module's backends, when an action is invoked, then only the backends named are checked, each at the stated revision.

## Edge Cases

- A record store that is not a provider and no provider named for an action: the action is `Unsupported` and the module has no actions (US-019).
- A provider that is not a reader (an upstream system): it may be named for actions only.
- Several replicas: allowed, tried in order.
- A configured backend that is down is a status, not a refusal of the placement.
- Changing a placement is a host reconfiguration, not a registration; moving a module's record store is a data migration outside Arras.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Placement | US-009-AC1 | Record store `memory`, replica `memory_replica`, both configured | Register | `latest` reads go to `memory`; actions run on `memory` |
| Replica | US-009-AC2 | Same placement, then two replicas | Read at `bulk` | The first replica that serves the statement answers |
| Invalid | US-009-AC3 | A module with no placement; separately a placement naming `unknown_store`; separately a reader-only backend named as a provider | Register | `invalid_placement` each time |
| Two record stores | US-009-AC4 | `catalog` on `memory`, `orders` on `memory_two` | Read and invoke on each | Each is served by its own record store |
| Provider routing | US-009-AC5 | `catalog.Correct` placed on provider `upstream` | Invoke it | Applied on `upstream`; the record store is not asked to apply it |
| Revision map | US-009-AC6 | `catalog` on `memory` with replica `memory_replica` | Describe `catalog` | `revision` is `{"memory": 3}`, with a `memory_replica` entry only if it publishes a release of its own |
| Partial revision | US-009-AC7 | The revision above | Invoke with `expected_revision` `{"memory": 3}`, then `{"memory": 2}` | Applied; then `Conflict` (`revision`) with nothing applied |

## Dependencies

- **Stories**: US-008
- **Feature Spec**: FEAT-002
- **Feature Requirements**: REG-02
- **PRD Requirements**: FR-10
- **External**: CONTRACT-002, Placement semantics.

## Out of Scope

Moving records between backends, and declaring access rules (access belongs to each backend, US-027).
