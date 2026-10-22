---
ddx:
  id: US-043
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-008
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-043: Record an evaluation finding from the embedding host

**Feature**: FEAT-008 — Reference Clients
**Feature Requirements**: CLI-03
**PRD Requirements**: FR-40
**Priority**: P0
**Status**: Draft

## Story

**As a** Catalog editor (through a client)
**I want** the embedding host to record my evaluation finding about a product and version after a session, attributed to me
**So that** evidence accumulates against the right product and version

## Context

This is interaction 11 of the [client interactions draft](../client-interactions-draft.md). The embedding host owns its deployment and session identity. The finding is recorded by a UMF action (UMF is the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions) invoked with the reviewer's own token.

## Walkthrough

1. The reviewer finishes a session and records a finding.
2. The workflow host invokes `RecordFinding` with the product, version, use case, applicability and the session as evidence.
3. The system applies the action and returns a receipt.

## Acceptance Criteria

- [ ] **US-043-AC1** — Given the inputs, when `RecordFinding` is invoked, then one finding about the actual product and version is created and joined to the use case with its applicability.
- [ ] **US-043-AC2** — Given the same session's idempotency key, when the action is invoked twice, then one finding results.
- [ ] **US-043-AC3** — Given the embedding host invokes the action with the reviewer's own token, when it commits, then the change names the reviewer and no service identity.
- [ ] **US-043-AC4** — Given a finding that names a different product than its evidence, when the action is invoked, then a precondition refuses it.

## Edge Cases

- **Evidence about one product**: never recorded as evidence about another.
- **An unknown product or version**: a precondition refuses it.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Record | US-043-AC1 | Product `prod-lumen`, version `2.1`, use case `uc-pipeline-mapping`, applicability `primary`, evidence `session-8841` | Invoke | One finding joined to the use case |
| Once | US-043-AC2 | Key `session-8841-finding-1` | Invoke twice | One finding |
| Reviewer | US-043-AC3 | The reviewer's token | Commit | Change names the reviewer |
| Precondition | US-043-AC4 | Finding names `prod-lumen`; evidence concerns another product | Invoke | Refused by a precondition |

## Dependencies

- **Stories**: US-014
- **Feature Spec**: FEAT-008
- **Feature Requirements**: CLI-03
- **PRD Requirements**: FR-40
- **External**: [CONTRACT-003](../../02-design/contracts/CONTRACT-003-actions.md); the embedding host.

## Out of Scope

- Recording many findings in one call (US-046 to US-048).
- Creating or promoting a Solution from a finding.
