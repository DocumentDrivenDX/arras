---
ddx:
  id: US-080
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
    - id: ADR-015
      kind: informed_by
    - id: ADR-025
      kind: informed_by
    - id: ADR-029
      kind: informed_by
    - id: ADR-030
      kind: informed_by
    - id: SD-013
      kind: informed_by
    - id: CONTRACT-003
      kind: informed_by
    - id: US-067
      kind: informed_by
    - id: US-071
      kind: informed_by
---

# US-080: Retire an entity from its page

**Feature**: FEAT-011 — Graph Browser
**Feature Requirements**: BRW-28
**PRD Requirements**: FR-68
**Priority**: P2
**Status**: Draft

## Story

**As a** module builder or administrator
**I want** to retire an entity from its page after being told what goes with it
**So that** that I remove a wrong or obsolete entity knowing the key cannot be reused and nothing can undo it

## Context

Retire is built from a declared action whose one effect is a `delete` of the type keyed by a `ref` input and whose other inputs are optional (SD-013 Rule 3). It is shown in edit mode only. What a delete does to links is unspecified by CONTRACT-003 and CONTRACT-004, so the confirmation names the entity's links from the node page's own relationship read.

## Walkthrough

1. alice unlocks edit mode on a `Solution` page; `Retire` is shown.
2. He presses it; the confirmation names the entity's links, says the key cannot be used again and that there is no undo.
3. He confirms; the action is validated, then invoked as him.
4. The `Solution` list opens in place of the entity's page; Back does not return to the retired page.
5. carol opens the page; no Retire control is present.

## Acceptance Criteria

- [ ] **US-080-AC1** — Given a type for which a declared action's one effect is a `delete` of that type keyed by a `ref` input and whose other inputs are optional, when an operator opens a node page in edit mode, then **Retire** is offered; for a type with no such action it is not
- [ ] **US-080-AC2** — Given the page outside edit mode, when it is shown, then Retire is not offered
- [ ] **US-080-AC3** — Given Retire pressed, when the confirmation opens, then it names the entity's links from the page's own relationship read, says that the key cannot be used again (a deleted key is tombstoned) and that the interface has no undo
- [ ] **US-080-AC4** — Given a confirmation, when it is cancelled, then nothing is validated or invoked and the page is unchanged
- [ ] **US-080-AC5** — Given a confirmation, when it is confirmed, then the action is validated and invoked as the viewer, and on success the browser opens the type's list by replacing the entity's history entry, so Back does not return to the retired page
- [ ] **US-080-AC6** — Given a retired entity, when its key is opened from a bookmark, then the page reads "not available", and a create with that key is refused at the key field because the key is tombstoned
- [ ] **US-080-AC7** — Given a refusal, when the action is submitted, then it is shown inline in the confirmation and the page stays
- [ ] **US-080-AC8** — Given a viewer who is not an operator (`as carol: absent`), when a node page is opened, then Retire is absent and no text refers to it
- [ ] **US-080-AC9** — Given a session that retires an entity, when the requests, the log lines, the errors and the address are inspected, then no key and no person is in a path, a query string, a log line or an error, and an entity key appears only in the fragment or in a POST body

## Edge Cases

- **An entity with many links**: the confirmation names the first links with a count, within the page's own read.
- **A cost refusal on the relationship read**: the confirmation says the links could not be listed and still asks for the same confirmation.
- **An action with required inputs besides the key**: no retire plan exists for it.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Offered where declared | US-080-AC1 | a delete action for `Solution` | open a page in edit mode as alice | Retire shown |
| Not outside edit mode | US-080-AC2 | edit mode off | open a page | No Retire |
| Confirmation names links and tombstone | US-080-AC3 | an entity with links | press Retire | Links named; key cannot be reused; no undo |
| Cancel changes nothing | US-080-AC4 | the confirmation | cancel | No validate, no invoke |
| Replace navigation | US-080-AC5 | a confirmed retire | confirm; press Back | The list shows; Back does not return to the retired page |
| Tombstoned key | US-080-AC6 | a retired key | open it; create with it | Not available; refusal at the key field |
| Refusal inline | US-080-AC7 | a refused delete | confirm | Refusal in the confirmation; page stays |
| Reader sees nothing | US-080-AC8 | carol | open a page | No Retire control, no text for it |
| No key in a URL | US-080-AC9 | a retire | inspect requests, logs and errors | Key only in the fragment or a POST body |

## Dependencies

- **Stories**: US-067, US-071
- **Feature Spec**: FEAT-011
- **Feature Requirements**: BRW-28
- **PRD Requirements**: FR-68
- **External**: ADR-015, ADR-025, ADR-029, ADR-030, SD-013, CONTRACT-003

## Out of Scope

- Undo or restore of a retired entity (a reversing action is an ordinary action).
- Retiring several entities at once (stays in Operate).
