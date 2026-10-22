---
ddx:
  id: FEAT-003
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

# Feature Specification: FEAT-003 — Actions

**Feature ID**: FEAT-003
**Status**: Draft
**Priority**: P0
**Owner**: Erik LaBianca
**Covered PRD Subsystem(s)**: Actions
**Covered PRD Requirements**: FR-14 to FR-21, FR-42, FR-43
**Cross-Subsystem Rationale**: None; single subsystem.

## Overview

Actions implement PRD FR-14 to FR-21, FR-42 and FR-43. They are the only way a client changes the ontology. A module declares them in UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions). A client invokes one, singly or in a batch. Arras validates it, applies its effects as one atomic unit on the module's provider (in production for the mutable modules, Truss, the hot store on Lakebase, Databricks managed Postgres), attributes it to the person whose own token made the call, and returns a receipt.

## Ideal Future State

A product-team editor creates a candidate Solution from a coverage assertion by calling one action. Either everything the action declares happens or nothing does. A failed precondition says why. A double click makes one Solution. The change names the editor and the action. A receipt lets the next read see the change. A list of corrections goes in one call, applied all or nothing or item by item, and the result says exactly what applied.

## Problem Statement

- **Current situation**: Nobody can change the catalog's knowledge in an application.
- **Pain points**: Exposing create and update would let every client re-implement invariants and attribution, and would leave multi-entity changes half applied.
- **Desired outcome**: One discoverable write path with validation, atomicity, attribution, idempotency and audit.

## Functional Areas

| Area | User question or job | Feature responsibility |
|------|----------------------|------------------------|
| Declaration | What can be done? | Named UMF actions with typed inputs, preconditions and effects, including `foreach` |
| Invocation | Do it | Validate, check preconditions, apply atomically |
| Bulk changes | Do many | `foreach` in an action; `invoke_batch` atomic or per item |
| Idempotency and attribution | Safe to repeat; who did it | Caller key; the person and the action recorded |
| Receipts | What happened? | Identities, versions and a token |
| Import | Seed records | Administrative, idempotent, with original and load provenance |

## Requirements

### Functional Requirements by Area

#### Declaration

ACT-01. A module declares actions in UMF: name, description, typed inputs, preconditions, effects (create, update, delete, link, unlink and `foreach`) and an optional handler hook. Clients discover them (FR-14).

#### Invocation

ACT-02. A caller invokes an action. Arras validates inputs and preconditions and reports every failure with its reason. A refused action changes nothing (FR-15).

ACT-03. An action's effects apply as one atomic unit on the action's provider, limited to creating, updating and deleting entities and linking and unlinking them (FR-16).

ACT-04. Actions are refused for a read-only module, and no other write path is exposed (FR-20).

#### Bulk changes

ACT-10. An action may repeat its effects over a list input with `foreach`. The expansion is one atomic group of at most 1,000 effects (FR-43, FR-16).

ACT-11. A caller can send up to 100 invocations of one action together, applied atomically as one group or independently with a result per item, each idempotent under the key and its index (FR-43, FR-17).

#### Idempotency and attribution

ACT-05. A caller can pass an idempotency key. Repeating the invocation changes nothing and returns the original receipt (FR-17).

ACT-06. Each invocation is attributed to the person whose own token the provider authenticated, and records the action's name. No caller can assert an author, and no service identity is ever the author (FR-18).

#### Receipts

ACT-07. An invocation returns a receipt of identities, versions and a token. A batch returns a `BatchReceipt` (FR-19, FR-43).

#### Import

ACT-08. An administrator can import records idempotently, in volume, keeping each record's identity, relationships and original provenance apart from the load's own provenance (FR-21, FR-43).

#### Validation

ACT-09. A caller can validate an action without applying it. The caller receives every violation and failed precondition and the effects the action would apply, with nothing written, recorded or locked (FR-42).

### Non-Functional Requirements

- **Performance** (proposed): action p95 (95th percentile) ≤ 100 ms at the host for a three-effect action, including its change record.
- **Atomicity**: effects, the idempotency record and the change record commit together or not at all. A batch never partially applies inside one atomic group.
- **Concurrency**: preconditions are evaluated inside the transaction, against locked entities.
- **Boundedness**: at most 100 items per batch and 1,000 effects per atomic group.

## User Stories

- [US-013: Declare actions in UMF and discover them](../user-stories/US-013-declare-actions-in-umf.md)
- [US-014: Invoke an action and have preconditions checked](../user-stories/US-014-invoke-an-action-with-preconditions.md)
- [US-015: Apply an action's effects atomically on the provider](../user-stories/US-015-apply-an-actions-effects-atomically.md)
- [US-016: Make an action safe to repeat](../user-stories/US-016-make-an-action-safe-to-repeat.md)
- [US-017: Attribute every change to the person who made it and the action](../user-stories/US-017-attribute-every-change-to-a-person.md)
- [US-018: Return a receipt for every action](../user-stories/US-018-return-a-receipt.md)
- [US-019: Refuse actions on read-only modules and offer no other write path](../user-stories/US-019-refuse-actions-on-read-only-modules.md)
- [US-020: Import seed records repeatably with their provenance, as an administrator](../user-stories/US-020-import-seed-records-repeatably.md)
- [US-045: Validate an action before applying it](../user-stories/US-045-validate-an-action-before-applying-it.md)
- [US-046: Change many entities with one action that declares foreach](../user-stories/US-046-apply-one-action-to-many-entities-with-foreach.md)
- [US-047: Apply a batch of invocations as one atomic group](../user-stories/US-047-apply-a-batch-of-invocations-atomically.md)
- [US-048: Apply a batch item by item and see exactly which applied](../user-stories/US-048-apply-a-batch-independently-and-see-partial-results.md)

## Edge Cases and Error Handling

- Two invocations with one key and different inputs are refused as a key reuse.
- When a connection is lost after commit was requested, the outcome is unknown. Invoking again with the key returns the receipt.
- An effect that names an alias created later is refused.
- A handler that returns an effect outside the closed list is refused.
- An action on a module that only a replica (in production Ashlar, the warehouse store on Unity Catalog) serves is refused as read-only.
- In a batch with one refused item, an atomic batch applies none, and an independent batch applies the others and reports the refusal with its index.
- An import by a client is refused. Import is administrative.

## Success Metrics

- 0 changes without a named person or a load (audit reconciliation).
- 0 changes follow a refused action.
- 0 batches partially applied inside one atomic group.

## Constraints and Assumptions

- Actions are a minimal subset of UMF's coming action contract (CONTRACT-003).
- Compensation and long-running work are deferred.
- The batch and effect bounds are proposed starting values.

## Dependencies

- **Other features**: FEAT-002 (declarations), FEAT-004 (the provider applies the group), FEAT-005 (the person's own grants decide write access), FEAT-009 (the MCP binding exposes each action as a tool).
- **External services**: UMF's action contract; the provider; the exact surface lives in CONTRACT-003 (actions).
- **PRD requirements**: FR-14 to FR-21, FR-42, FR-43 (P0 item 3).

## Out of Scope

- Actions that span backends.
- Compensation and sagas.
- Authorization richer than the provider's module write access.
- Import by clients or agents.
