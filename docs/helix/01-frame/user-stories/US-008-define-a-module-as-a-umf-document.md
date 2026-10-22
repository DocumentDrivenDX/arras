---
ddx:
  id: US-008
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

# US-008: Define a module's types as a UMF document

**Feature**: FEAT-002 — Type Registry
**Feature Requirements**: REG-01
**PRD Requirements**: FR-9
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to register one UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions) document that defines my module's entity types, relationships and actions
**So that** the schema I maintain in UMF is the only schema

## Context

Arras defines no schema format of its own. The catalog module's document follows the shape in `docs/helix/02-design/contracts/examples/catalog.umf.json`, which names no Record or Field (UMF permits that); Truss requires an authored name on each, so its revised copy `catalog.named.umf.json` (the same document with every Record and Field named by the last segment of its id) is the one that registers there. A module is a named group of entity types, and registration is an administrative act on the module's record store (CONTRACT-002, the type registry and placement contract).

## Walkthrough

1. Developer registers the `catalog` document.
2. The system validates it and the module's record store accepts it as a revision.
3. Developer registers a document that defines two modules.
4. The system refuses it.

## Acceptance Criteria

- [ ] **US-008-AC1** — Given a valid UMF document defining only `catalog`, when registered, then it is accepted as a revision and the acceptance report is returned.
- [ ] **US-008-AC2** — Given anything that is not a UMF document, when registered, then it is refused as `invalid_document`.
- [ ] **US-008-AC3** — Given a document that defines two modules, when registered, then it is refused.
- [ ] **US-008-AC4** — Given a UMF construct the backend does not support, when registered, then it is refused naming the construct.

## Edge Cases

- An entity type with no key, or a key that is not a required string: refused as `missing_key`.
- A relationship naming a type no document defines: refused, or provisional by policy.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Accept | US-008-AC1 | `catalog.umf.json` | Register | New revision and acceptance report |
| Not UMF | US-008-AC2 | A JSON object `{"a": 1}` | Register | `invalid_document` |
| Two modules | US-008-AC3 | Document defining `catalog` and `playbooks` | Register | Refused |
| Unsupported | US-008-AC4 | Document using a construct the backend lacks | Register | Refused, naming the construct |

## Dependencies

- **Stories**: None
- **Feature Spec**: FEAT-002
- **Feature Requirements**: REG-01
- **PRD Requirements**: FR-9
- **External**: CONTRACT-002, Module document.

## Out of Scope

Placing the module (US-009), changing a registered type (US-011), and defining actions (US-013).
