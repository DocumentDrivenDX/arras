---
ddx:
  id: US-067
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
    - id: CONTRACT-006
      kind: informed_by
    - id: CONTRACT-010
      kind: informed_by
---

# US-067: Open an entity as a node page

**Feature**: FEAT-011 — Graph Browser
**Feature Requirements**: BRW-05, BRW-06, BRW-07, BRW-08, BRW-18
**PRD Requirements**: FR-55
**Priority**: P1
**Status**: Draft

## Story

**As a** graph reader
**I want** an entity presented as a readable page in its module's own terms
**So that** I can understand what it is without reading a property table

## Context

A node page is the card of an entity: a title, a summary, a type icon and tone, grouped properties with fitting formats, and its attribution and freshness. Slice 1 renders it from the derived default (BRW-18); slice 2 renders it from the module's declared view (US-070). The page is the same component in both; only the presentation data differs.

## Walkthrough

1. The reader opens a `Solution` hit.
2. The page shows the title, the summary line, the type's icon and a tone badge, then sections of properties.
3. Long text is set as prose; a launch URL is a link; a timestamp shows as a date and time.
4. A line shows who last changed it and when, and how current the page is.
5. The freshness line shows the backend and how current the page is.

## Acceptance Criteria

- [ ] **US-067-AC1** — Given a type with no declared view, when an entity is opened, then the title is the first conventional name property (`name`, `title`, `label`) or the first string property that is not the key, the summary is the first of `summary`, `description`, `statement`, `problem` or `notes` the type has, and one section lists every other property in declared order
- [ ] **US-067-AC2** — Given a long text property, a URL, a timestamp, a decimal and a boolean, when the page renders, then each is formatted by its declared format or the default of CONTRACT-010 for its name and type (prose, link, date and time with the exact value on demand, grouped number, yes or no)
- [ ] **US-067-AC3** — Given a property with no value, when the page renders, then it shows a consistent "not set" marker rather than being omitted, unless the declared view hides it when empty
- [ ] **US-067-AC4** — Given an entity opened through its own module's endpoint, when the page renders, then it shows who created and who last changed it and when, where the backend supplies them
- [ ] **US-067-AC5** — Given a page, when it renders, then it states the freshness of what it shows (backend and how current), and marks an answer that is behind its backend's current position
- [ ] **US-067-AC6** — Given a key that is absent or an entity the viewer may not read, when the page is requested, then it shows the same "not available" page for both, with no key, type or reason

## Edge Cases

- **A very long title or unbroken string**: wraps or truncates inside its container with the full value reachable; the page never scrolls sideways.
- **A structured (JSON) value**: shown as collapsed formatted data, expandable, never rendered as markup.
- **A value containing markup or script text**: shown as text; nothing is interpreted.
- **A property the viewer's grants hide**: the backend omits it; the page shows no marker for it.
- **The registry changed since the page opened**: the page refreshes under the new revision and keeps its place.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Derived title | US-067-AC1 | `Solution` with `name`, `summary`, no view | open | Title from `name`; summary from `summary`; one section of the rest |
| Formats | US-067-AC2 | a `Solution` with `launchUrl`, `workflow` (long), a timestamp | open | Link, prose, localized date with exact value on hover and focus |
| Empty value | US-067-AC3 | `caveat` unset | open | "Not set" shown in its place |
| Attribution | US-067-AC4 | `Solution` changed by alice | open | "Changed by alice, …" |
| Freshness | US-067-AC5 | a replica behind its feed | open | The statement names the backend and marks the lag |
| Not available | US-067-AC6 | dave (no access) and a missing key | open both | Identical pages |
| Markup in a value | US-067-AC2 | a value `<img src=x onerror=…>` | open | Rendered as text; no element created |

## Dependencies

- **Stories**: none required; US-068 and US-069 extend the page; US-070 changes its presentation data.
- **Feature Spec**: FEAT-011
- **Feature Requirements**: BRW-05 to BRW-08, BRW-18
- **PRD Requirements**: FR-55
- **External**: CONTRACT-006 (`Entity` attribution and freshness), CONTRACT-010 (view, where declared).

## Out of Scope

- Editing any value, or any link to an action.
- Raw property names as the main display when a label is declared (they stay reachable in a "details" disclosure).
