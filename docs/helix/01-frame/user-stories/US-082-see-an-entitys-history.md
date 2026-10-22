---
ddx:
  id: US-082
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
    - id: ADR-025
      kind: informed_by
    - id: ADR-029
      kind: informed_by
    - id: ADR-030
      kind: informed_by
    - id: SD-013
      kind: informed_by
    - id: CONTRACT-010
      kind: informed_by
    - id: US-067
      kind: informed_by
    - id: US-072
      kind: informed_by
---

# US-082: See an entity's history

**Feature**: FEAT-011 — Graph Browser
**Feature Requirements**: BRW-30
**PRD Requirements**: FR-69
**Priority**: P2
**Status**: Draft

## Story

**As a** module builder or administrator
**I want** to open an entity's History and read what changed it, who did it and when
**So that** that I can explain how it came to be as it is, without leaving Explore

## Context

History is the operate surface's `changes` read by the entity's type and key, newest first, 20 a page, for an operator (SD-013 Rule 5). The grant to the journal, not the edit offer, decides what it shows: it is shown outside edit mode. A change's group is a deep link to Operate's receipt view. When the backend keeps no journal, or the person lacks the grant, the panel says so in a sentence.

## Walkthrough

1. alice opens a `Solution` page and opens History.
2. The panel lists the latest 20 changes, each with who, when, the action and what it touched.
3. He pages to the next 20, and presses a change's group link; Operate opens at that group's receipt.
4. On a deployment whose backend keeps no journal, the panel says so in a sentence.
5. carol opens the same page; no History control is present.

## Acceptance Criteria

- [ ] **US-082-AC1** — Given an operator on a node page, when History is opened, then the changes by the entity's type and key are listed newest first, 20 a page, each naming who, when, its action and what it touched (either end of a link counts)
- [ ] **US-082-AC2** — Given a change touching other entities, when it is listed, then each touched entity resolves through the normal read, and one the viewer cannot read shows as "not available" with no key
- [ ] **US-082-AC3** — Given more than 20 changes, when the next page is asked for, then the following 20 are listed and the panel shows its place
- [ ] **US-082-AC4** — Given a person without the journal grant, when History is opened, then the panel says so in a sentence (403), and it is not an error panel
- [ ] **US-082-AC5** — Given a backend that keeps no journal, when History is opened, then the panel says so in a sentence (501), and it is not an error panel
- [ ] **US-082-AC6** — Given a change, when its group link is followed, then it opens Operate's receipt view for that group, offered only where the host offers Operate
- [ ] **US-082-AC7** — Given the page outside edit mode, when History is opened, then it works, because the grant and not the edit offer decides what it shows
- [ ] **US-082-AC8** — Given a History panel open, when the address is read, then it names the open panel in the fragment, a refresh restores it, and Back closes it
- [ ] **US-082-AC9** — Given a viewer who is not an operator (`as carol: absent`), when a node page is opened, then History is absent, no text refers to it, and a direct call to `changes` is refused `not_operator`
- [ ] **US-082-AC10** — Given a session that opens an entity's history, when the requests, the log lines, the errors and the address are inspected, then no key and no person is in a path, a query string, a log line or an error, and an entity key appears only in the fragment or in a POST body

## Edge Cases

- **An entity with no changes**: the panel says no change is recorded for it, not an error.
- **A touched entity that was retired**: shown as "not available".
- **A page past the last**: the panel stays on the last page.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| History lists changes | US-082-AC1 | an entity with changes | open History as alice | Newest first, 20 a page; who, when, action, touched |
| Unreadable touched entity | US-082-AC2 | a change touching an entity alice cannot read | open History | "not available", no key |
| Paging | US-082-AC3 | more than 20 changes | next page | The following 20 |
| Missing grant | US-082-AC4 | a person without the journal grant (403) | open History | A sentence, not an error panel |
| No journal | US-082-AC5 | a backend without a journal (501) | open History | A sentence, not an error panel |
| Group link | US-082-AC6 | a listed change | follow its group link | Operate's receipt view for that group |
| Outside edit mode | US-082-AC7 | edit mode off | open History | The panel works |
| Panel in the address | US-082-AC8 | an open panel | refresh; press Back | Restored; closed |
| Reader sees nothing | US-082-AC9 | carol | open a page; call `changes` | No History control or text; 403 `not_operator` |
| No key in a URL | US-082-AC10 | a History read | inspect requests, logs and errors | Key only in the fragment or a POST body |

## Dependencies

- **Stories**: US-067, US-072
- **Feature Spec**: FEAT-011
- **Feature Requirements**: BRW-30
- **PRD Requirements**: FR-69
- **External**: ADR-025, ADR-029, ADR-030, SD-013, CONTRACT-010

## Out of Scope

- Whole-module change lists, filters and import loads (stay in Operate).
- Undo of a change.
