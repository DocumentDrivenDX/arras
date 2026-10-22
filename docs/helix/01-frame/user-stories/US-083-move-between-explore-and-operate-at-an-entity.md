---
ddx:
  id: US-083
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-12
  authoring:
    home: repo
  links:
    - id: FEAT-011
      kind: informed_by
    - id: prd
      kind: informed_by
    - id: ADR-024
      kind: informed_by
    - id: ADR-025
      kind: informed_by
    - id: ADR-030
      kind: informed_by
    - id: SD-013
      kind: informed_by
    - id: CONTRACT-010
      kind: informed_by
    - id: US-072
      kind: informed_by
    - id: US-082
      kind: informed_by
---

# US-083: Move between Explore and Operate at an entity

**Feature**: FEAT-011 — Graph Browser
**Feature Requirements**: BRW-31
**PRD Requirements**: FR-71
**Priority**: P2
**Status**: Draft

## Story

**As a** module builder or administrator
**I want** to jump from an entity, a type or a module in Explore to the same place in Operate, and back
**So that** that I take the operator tools to the thing I am looking at, and return to the page a reader sees

## Context

Cross-mode links are one primitive the shell hands each mode (SD-013 Rule 7): an anchor where an `href` exists, and a function that switches mode and sets the other mode's route where the host owns the location. A mode given none shows no cross-mode links. They are offered only where the host offers Operate.

## Walkthrough

1. alice opens a `Solution` page and presses Open in Operate; Operate opens on the same entity.
2. From History, the link opens Operate at the entity's History; from Actions, Operate's Actions with the entity prefilled.
3. On a type's list he presses Model; Operate opens the model at that type.
4. In Operate he presses View in Explore on a receipt's entity; Explore shows its page.
5. carol opens the same pages; no link to Operate is present.

## Acceptance Criteria

- [ ] **US-083-AC1** — Given an operator on a node page, when she looks for a link to Operate, then **Open in Operate** is offered with targets for Entities, History and Actions, and following one opens Operate at the entity in that area (Actions with the entity prefilled)
- [ ] **US-083-AC2** — Given an operator on a type's list, when she follows **Model**, then Operate's Model area opens at that type
- [ ] **US-083-AC3** — Given Operate's context bar, Changes rows, receipts and model cards, when an entity, type or module is shown, then **View in Explore** is offered and opens Explore at it; a change group opens Operate's receipt view
- [ ] **US-083-AC4** — Given a host that owns the location, when a link is followed, then the host's navigation runs the mode switch and sets the other mode's route; given hash mode, then the link is an anchor with an `href`
- [ ] **US-083-AC5** — Given a mode handed no link primitive, when its pages are shown, then no cross-mode link is rendered
- [ ] **US-083-AC6** — Given a host that offers no Operate, when a page is shown, then no cross-mode link is rendered
- [ ] **US-083-AC7** — Given a followed link, when the other mode opens, then its address names the mode, module, area, type and entity, so the page can be bookmarked and restored on refresh
- [ ] **US-083-AC8** — Given a viewer who is not an operator (`as carol: absent`), when any page is opened, then no link, button or text refers to Operate, and an Operate address shows Explore's entry
- [ ] **US-083-AC9** — Given a session that moves between the modes, when the requests, the log lines, the errors and the address are inspected, then no key and no person is in a path, a query string, a log line or an error, and an entity key appears only in the fragment or in a POST body

## Edge Cases

- **A link to an entity the viewer cannot read**: the target shows "not available".
- **A module that has no area for the target**: the link opens the module's entry.
- **A host that owns the location**: its `go()` carries the target; no address is written by Arras.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Open in Operate | US-083-AC1 | alice on a node page | follow each target | Operate opens at Entities, History or Actions for the entity |
| Model from a list | US-083-AC2 | a type's list | follow Model | Operate's Model at the type |
| View in Explore | US-083-AC3 | Operate's context bar, a Changes row, a receipt | follow View in Explore | Explore page for that entity, type or module |
| Host-owned location | US-083-AC4 | a host passing `onLocation` | follow a link | The host's go() switches mode and sets the route |
| No primitive | US-083-AC5 | a mode given none | render | No cross-mode links |
| No Operate offered | US-083-AC6 | a host that offers no Operate | render | No cross-mode links |
| Address names the page | US-083-AC7 | a followed link | read the address; refresh | Mode, module, area, type, entity; restored |
| Reader sees nothing | US-083-AC8 | carol | open pages; open an Operate address | No Operate link or text; Explore's entry |
| No key in a URL | US-083-AC9 | a mode switch | inspect requests, logs and errors | Key only in the fragment or a POST body |

## Dependencies

- **Stories**: US-072, US-082
- **Feature Spec**: FEAT-011
- **Feature Requirements**: BRW-31
- **PRD Requirements**: FR-71
- **External**: ADR-024, ADR-025, ADR-030, SD-013, CONTRACT-010

## Out of Scope

- Cross-host links (to another Arras deployment).
- A link into Operate for a non-operator.
