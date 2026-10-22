---
ddx:
  id: US-019
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-003
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-019: Refuse actions on read-only modules and offer no other write path

**Feature**: FEAT-003 — Actions
**Feature Requirements**: ACT-04
**PRD Requirements**: FR-20
**Priority**: P0
**Status**: Draft

## Story

**As a** Platform owner
**I want** to know that a read-only module cannot be changed through Arras and that no other write path exists
**So that** changes reach a replica only through the feed from the providers' stores

## Context

A module that only a replica (in production Ashlar: gold Delta tables on Unity Catalog, Databricks' catalog and access-control layer) holds has no provider for its actions. Arras exposes three write operations: `invoke`, `invoke_batch` and `import_records`.

## Walkthrough

1. Client invokes an action on a module only a replica serves.
2. The system refuses it as read-only.
3. Platform owner searches the interface for any other write.
4. The interface offers none.

## Acceptance Criteria

- [ ] **US-019-AC1** — Given a module whose record store is not a provider and whose placement names none, when an action is invoked, then `Unsupported` is returned and nothing changes.
- [ ] **US-019-AC2** — Given the interface, when its operations are enumerated, then no operation writes except `invoke`, `invoke_batch` and `import_records`.
- [ ] **US-019-AC3** — Given `import_records` on a read-only module, when called, then `Unsupported` is returned.
- [ ] **US-019-AC4** — Given a module with a provider for the action, when it is invoked, then it runs there and not on a replica.

## Edge Cases

- A replica that receives a change: only through the provider's feed.
- A module with no actions: nothing to invoke.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Read-only | US-019-AC1 | `playbooks`, held only by a replica | Invoke any action | `Unsupported`; nothing changed |
| No other write | US-019-AC2 | The interface's operations | Enumerate them | Only `invoke`, `invoke_batch`, `import_records` write |
| Import | US-019-AC3 | `playbooks` | `import_records` | `Unsupported` |
| Provider | US-019-AC4 | `catalog`, placed on provider `memory`, replicated to `memory_replica` | Invoke an action | Applied on `memory`; `memory_replica` not written |

## Dependencies

- **Stories**: US-013
- **Feature Spec**: FEAT-003
- **Feature Requirements**: ACT-04
- **PRD Requirements**: FR-20
- **External**: CONTRACT-003, Refusals.

## Out of Scope

Writing to a replica by any route other than the feed from the providers' stores, and the authorization of write access (US-027).
