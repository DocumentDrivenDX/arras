---
ddx:
  id: US-076
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-010
      kind: informed_by
    - id: FEAT-005
      kind: informed_by
    - id: ADR-026
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-076: Try every role in the development host

**Feature**: FEAT-010 — Operator Console
**Feature Requirements**: OPR-15
**PRD Requirements**: FR-62
**Priority**: P1
**Status**: Draft

## Story

**As a** Client developer
**I want** to pick a role and a made-up name in the development host and break and mend its backends from the console
**So that** that I exercise every flow, including refusals, with no Databricks and no sign-in

## Context

The development host serves the sandbox's fakes on loopback only and authenticates nobody (FEAT-010). A made-up person is an operator (the group `builders`), so the backends' grants decide, not the host's operator hook; a role is a set of grants on the fake backends (`read`, `write`, `journal`, `schema`); the dev host (`python -m arras.devhost`) serves the console with these roles.

## Walkthrough

1. The developer opens the console on the development host.
2. She picks the role `schema author` and the name `ana`.
3. She imports a schema; she switches to `viewer`, tries again, and is refused.
4. She sets an outage on the record store and sees the console's unavailable states.

## Acceptance Criteria

- [ ] **US-076-AC1** — Given the development host, when a role and a name are chosen, then the console runs as that person with the grants the role implies, and every change is attributed to the name.
- [ ] **US-076-AC2** — Given the role `viewer`, when an action or an import is attempted, then the backend refuses it and the console shows the reason.
- [ ] **US-076-AC3** — Given the role `none`, when the console loads, then it shows no module, as for a person with no access.
- [ ] **US-076-AC4** — Given the administrative principal's name or a name that is not allowed, when it is chosen, then it is refused and no principal is created.
- [ ] **US-076-AC5** — Given the toolbar's controls, when an outage, token expiry or the replica's feed is set, then the console shows the state and mending it restores it.
- [ ] **US-076-AC6** — Given a request that reaches the development host with a `Host` that is not loopback (the server binds loopback only), when it arrives, then it is refused.
- [ ] **US-076-AC7** — Given the library build and the page the Python package serves, when the exports are listed and the page's entry is read, then the sandbox toolbar is in neither: `arras.ui` serves the built UI page and its branded embed (ADR-027) with no toolbar, and the toolbar is the development host's alone (`arras.devhost`).

## Edge Cases

- **A name reused with another role**: that name's grants are replaced by the role chosen, never added to.
- **A name that is `root` or one of the sandbox's own people**: refused, so a role cannot change what a fixed person holds.
- **A name that tries to be a header injection or an unbounded string**: refused by the name rule (lower-case letters, digits, `-` and `_`, 1 to 32).

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| a role and a name are chosen | US-076-AC1 | the development host | a role and a name are chosen | the console runs as that person with the grants the role implies, and every change is attr |
| an action or an import is attempted | US-076-AC2 | the role `viewer` | an action or an import is attempted | the backend refuses it and the console shows the reason |
| the console loads | US-076-AC3 | the role `none` | the console loads | it shows no module, as for a person with no access |
| it is chosen | US-076-AC4 | the administrative principal's name or a name th | it is chosen | it is refused and no principal is created |
| an outage, token expiry or the replica's feed is | US-076-AC5 | the toolbar's controls | an outage, token expiry or the replica's feed is | the console shows the state and mending it restores it |
| it arrives | US-076-AC6 | a request that reaches the development host from | it arrives | it is refused |
| the exports are listed and the page's entry is read | US-076-AC7 | the library build and the page the Python package serves | the exports are listed and the page's entry is read | the sandbox toolbar is in neither: `arras.ui` serves the built UI page and its branded embed with no toolbar, and the toolbar is the development host's alone |

## Dependencies

- **Stories**: US-064
- **Feature Spec**: FEAT-010
- **Feature Requirements**: OPR-15
- **PRD Requirements**: FR-62
