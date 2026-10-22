---
ddx:
  id: US-078
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
    - id: prd
      kind: informed_by
---

# US-078: Reuse a query from this session's history

**Feature**: FEAT-010 — Operator Console
**Feature Requirements**: OPR-17
**PRD Requirements**: FR-63
**Priority**: P2
**Status**: Draft

## Story

**As a** module builder
**I want** to see the queries I ran in this session and put one back in the editor or run it again
**So that** that I can refine a query without retyping it, and leave nothing behind when I close the page

## Context

The history is held in memory only (OPR-07): it survives moving between the console's tabs, and is gone on reload and when another person is chosen.

## Walkthrough

1. The builder runs three queries.
2. The history lists them newest first, each with its module, consistency, time and row count or the reason it failed.
3. She chooses the first, edits it and runs it; it joins the history.
4. She clears the history.

## Acceptance Criteria

- [ ] **US-078-AC1** — Given queries run in this session, when the history is opened, then each is listed newest first with its module, consistency, when it ran, and its row count or failure.
- [ ] **US-078-AC2** — Given a history entry, when it is chosen, then its module, text and consistency are put in the editor, and nothing is run until the operator runs it.
- [ ] **US-078-AC3** — Given a history entry, when Run again is chosen, then the query runs as the current person at the current time.
- [ ] **US-078-AC4** — Given a history, when it is cleared, then it is empty and stays so.
- [ ] **US-078-AC5** — Given a page reload or another person chosen, when the Query tab opens, then the history is empty.
- [ ] **US-078-AC6** — Given the console, when it is inspected after queries ran, then nothing is in `localStorage`, `sessionStorage`, IndexedDB, a cookie or a URL.

## Edge Cases

- **The same query twice in a row**: listed once, with the latest time.
- **A very long history**: at most the last 50 are kept; the oldest is dropped.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| the history is opened | US-078-AC1 | queries run in this session | the history is opened | each is listed newest first with its module, consistency, when it ran, and its row count or failur |
| it is chosen | US-078-AC2 | a history entry | it is chosen | its module, text and consistency are put in the editor, and nothing is run until the operator runs |
| Run again is chosen | US-078-AC3 | a history entry | Run again is chosen | the query runs as the current person at the current time |
| it is cleared | US-078-AC4 | a history | it is cleared | it is empty and stays so |
| the Query tab opens | US-078-AC5 | a page reload or another person chosen | the Query tab opens | the history is empty |
| it is inspected after queries ran | US-078-AC6 | the console | it is inspected after queries ran | nothing is in `localStorage`, `sessionStorage`, IndexedDB, a cookie or a URL |

## Dependencies

- **Stories**: US-077
- **Feature Spec**: FEAT-010
- **Feature Requirements**: OPR-17
- **PRD Requirements**: FR-63
