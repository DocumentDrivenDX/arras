---
ddx:
  id: US-072
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-011
      kind: informed_by
    - id: prd
      kind: informed_by
    - id: ADR-025
      kind: informed_by
    - id: CONTRACT-010
      kind: informed_by
    - id: US-037
      kind: informed_by
---

# US-072: Switch between Explore and Operate

**Feature**: FEAT-011 — Graph Browser
**Feature Requirements**: BRW-24, BRW-25, BRW-26
**PRD Requirements**: FR-60
**Priority**: P1
**Status**: Draft

## Story

**As a** module builder or administrator
**I want** to switch the same interface between Explore and Operate
**So that** I can look at a thing as a reader does, then open the operator tools on it, without a second sign-in or app

## Context

The interface has two modes: Explore (the Graph Browser) and Operate (the Operator Console). Only operators get the switch; for everyone else Operate is absent, and the server refuses the operator surface to them (ADR-025). Who an operator is, is the host's decision. The switch is an offer, not a permission: what a person may read or change is still what the backends allow.

## Walkthrough

1. A module builder opens the interface; it opens in Explore on the module entry.
2. The top bar shows a two-option switch, `Explore` and `Operate`, with `Explore` pressed.
3. She opens a `Solution` page, presses `Operate`, and the Operator Console opens with the Solution's type in Entities.
4. She presses `Explore` and returns to the same node page.
5. A reader opens the same interface; the top bar has no switch, and no part of the page mentions Operate.
6. The reader pastes an Operate address (`#/operate/catalog/entities/catalog.Solution/sol-1`) into the browser and sees Explore's entry.

## Acceptance Criteria

- [ ] **US-072-AC1** — Given an operator, when the interface loads, then it opens in Explore and the top bar shows a switch with `Explore` pressed (`aria-pressed="true"`) and `Operate` not pressed
- [ ] **US-072-AC2** — Given an operator in Explore on a node page, when she presses `Operate`, then the Operator Console opens, the address's prefix becomes `operate`, and the node's module, type and key carry over to the console's Entities area, with that type shown and that entity open
- [ ] **US-072-AC3** — Given an operator in Operate, when she presses `Explore`, then the browser page for the entity open in the console is shown (its type's list when none is open, the module's entry when no type is shown)
- [ ] **US-072-AC4** — Given a viewer who is not an operator, when the interface loads, then no switch, link, button or text refers to Operate anywhere in the page, and the operator surface is not called except for the viewer's modes
- [ ] **US-072-AC5** — Given a viewer who is not an operator, when each operator endpoint is called directly with the viewer's token, then each answers 403 `REFUSED` with reason `not_operator` before doing any work, and the viewer's modes endpoint answers `["user"]`
- [ ] **US-072-AC6** — Given a viewer who is not an operator, when an Operate address is opened, then Explore's entry is shown
- [ ] **US-072-AC7** — Given a host that supplies no operator decision, when the interface loads for any accepted viewer, then the behaviour is that of the operate surface before this feature (every accepted viewer is an operator) and the host's log says so once at start
- [ ] **US-072-AC8** — Given the switch, when it is operated by keyboard, then both options are reachable with Tab, activated with Enter or Space, and the state is conveyed by `aria-pressed` and a visible cue, not colour alone

## Edge Cases

- **The viewers endpoint fails or is slow**: the interface shows Explore and no switch until it answers; a failure leaves Explore only (it never assumes operator).
- **An operator whose grant is later withdrawn**: the next operate call is refused with `not_operator`; the console shows its "no access" state and the switch disappears on the next viewer read.
- **No module is readable**: Explore shows "No access" as the Operator Console does.
- **The host passes an `authorize_operator` that raises**: the viewer is treated as not an operator and the fault is logged by the host's own telemetry, never shown.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Switch offered | US-072-AC1 | alice (operator) | load | Explore; switch with `Explore` pressed |
| To Operate | US-072-AC2 | alice on `Solution` page | press Operate | Console opens on Entities for `Solution` with the node open; fragment starts `#/operate/` |
| Back to Explore | US-072-AC3 | alice in Operate | press Explore | The page for the entity open in the console |
| No trace for a reader | US-072-AC4 | carol (not operator) | load; inspect DOM and requests | No Operate text or control; no call to the operate surface besides the viewer read |
| Server refusal | US-072-AC5 | carol | call each operate endpoint | 403 `not_operator`; viewer read gives `["user"]` |
| Operate link as a reader | US-072-AC6 | carol | open `#/operate/catalog/entities/Solution` | Explore entry |
| Default hook | US-072-AC7 | operate app built with no hook | load as carol | Treated as operator; start log names the default |
| Keyboard | US-072-AC8 | alice | Tab to the switch, press Enter | Mode changes; `aria-pressed` follows |

## Dependencies

- **Stories**: US-067 (the node page the mode switch returns to), US-037 (the console's principal scoping).
- **Feature Spec**: FEAT-011
- **Feature Requirements**: BRW-24 to BRW-26
- **PRD Requirements**: FR-60
- **External**: ADR-025, CONTRACT-010 section E, CONTRACT-009.

## Out of Scope

- Defining who is a module builder or an administrator: the host's directory and hook do.
- Per-module or per-area modes, or more than two modes.
- Granting any read or write: the backends do.
