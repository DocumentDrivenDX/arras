---
ddx:
  id: US-081
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
    - id: SD-012
      kind: informed_by
    - id: US-067
      kind: informed_by
    - id: US-079
      kind: informed_by
---

# US-081: Run a declared action on an entity

**Feature**: FEAT-011 — Graph Browser
**Feature Requirements**: BRW-29
**PRD Requirements**: FR-70
**Priority**: P2
**Status**: Draft

## Story

**As a** module builder or administrator
**I want** to choose from an Actions menu on a node page and run a declared action with the entity filled in
**So that** that I use the module's other actions (several effects, record or list inputs) without going to Operate

## Context

The Actions menu lists every other declared action with a `ref` input typed as the entity's type whose inputs and effects the kit's form can ask for and summarise (SD-013 Rule 4). An action an inline plan has claimed (an edit, a link, a retire or a create) is not offered a second time. Batch is not offered. There is no graph picture of the effects; a text summary stands in.

## Walkthrough

1. alice unlocks edit mode on a `Solution` page and opens Actions.
2. He chooses `Assign Owner`; a form opens with the solution already filled in.
3. He fills in the rest; a text summary lists the effects the action will have.
4. He confirms; the action is invoked as him and a receipt links the entities it touched.
5. carol opens the same page; no Actions menu is present.

## Acceptance Criteria

- [ ] **US-081-AC1** — Given a node page in edit mode, when an operator opens Actions, then the menu lists each declared action with a `ref` input typed as the entity's type that no inline plan has claimed, and only those
- [ ] **US-081-AC2** — Given an action claimed by an inline plan (an in-place edit, a link or unlink, Retire or New), when the menu is built, then the action is not offered in it, so no action is offered twice; where two actions qualify for the same property or relationship, the winner drives the inline control and the loser is offered nowhere
- [ ] **US-081-AC3** — Given an action chosen, when the form opens, then the `ref` input is prefilled with the entity, the other inputs are asked for as in New, and a batch form is not offered
- [ ] **US-081-AC4** — Given a valid form, when it is checked, then the action is validated as the viewer and a text summary of its effects is shown before anything is invoked
- [ ] **US-081-AC5** — Given a confirmation, when the action is invoked, then a receipt summary links the entities it touched, an entity the viewer cannot read shows as "not available" without its key, and the page's reads are refreshed
- [ ] **US-081-AC6** — Given a refusal or a violation, when the action is validated or invoked, then it is shown inline, the values are kept, and a 401 offers Sign in again where the host gave `onUnauthorized`
- [ ] **US-081-AC7** — Given a module that declares no such action for the type, when the page is opened, then no Actions menu is shown
- [ ] **US-081-AC8** — Given a viewer who is not an operator (`as carol: absent`), when a node page is opened, then the Actions menu is absent and no text refers to it
- [ ] **US-081-AC9** — Given a session that runs an action on an entity, when the requests, the log lines, the errors and the address are inspected, then no key and no person is in a path, a query string, a log line or an error, and an entity key appears only in the fragment or in a POST body

## Edge Cases

- **An action whose input or effect the form cannot ask for or summarise**: not offered.
- **The same compound action that also creates**: offered in the referenced entity's menu with the reference prefilled.
- **A refusal the browser could not predict**: shown where it was asked; no control is hidden ahead.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Menu lists the unclaimed actions | US-081-AC1 | a type with edit, link and other actions | open Actions as alice | Only unclaimed actions listed |
| Claimed action not offered twice | US-081-AC2 | an action an inline plan claims | open Actions | The action is absent from the menu |
| Competing actions | US-081-AC2 | two actions qualifying for one property | open the page | One drives the inline control; the other is nowhere |
| Entity prefilled | US-081-AC3 | a chosen action | open its form | The ref input holds the entity |
| Effects summary | US-081-AC4 | a valid form | validate | Text summary shown before invoke |
| Receipt links | US-081-AC5 | an invoked action | read the receipt | Touched entities linked; unreadable ones "not available" |
| Refusal inline | US-081-AC6 | a refused action | invoke | Refusal at the form; values kept |
| No such action declared | US-081-AC7 | a type with no entity action | open a page | No Actions menu |
| Reader sees nothing | US-081-AC8 | carol | open a page | No Actions menu, no text for it |
| No key in a URL | US-081-AC9 | an action run | inspect requests, logs and errors | Key only in the fragment or a POST body |

## Dependencies

- **Stories**: US-067, US-079
- **Feature Spec**: FEAT-011
- **Feature Requirements**: BRW-29
- **PRD Requirements**: FR-70
- **External**: ADR-015, ADR-025, ADR-029, ADR-030, SD-013, SD-012

## Out of Scope

- Batch invoke (stays in Operate).
- A graph picture of an action's effects (Operate only).
