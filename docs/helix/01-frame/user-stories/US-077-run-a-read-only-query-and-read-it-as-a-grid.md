---
ddx:
  id: US-077
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
    - id: FEAT-001
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-077: Run a read-only query and read it as a grid

**Feature**: FEAT-010 — Operator Console
**Feature Requirements**: OPR-16
**PRD Requirements**: FR-63
**Priority**: P2
**Status**: Draft

## Story

**As a** module builder
**I want** to write a read-only query, choose how current the answer must be, and read the result as a grid
**So that** that I can answer a question about the data in my own words, as myself, without a developer

## Context

The query is the library's `query` (CONTRACT-001): one read-only Weft SQL statement over a module chosen in the console, reached by `POST /query` on the operator surface (CONTRACT-009). Arras does not parse it; the serving backend compiles and runs it as the viewer, so the backends' grants decide what comes back, and a statement that writes is refused. Paging is the statement's own: `ORDER BY` the key, `LIMIT`, and a keyset predicate for the next page.

## Walkthrough

1. The builder opens the Query tab, chooses a module and types a `SELECT` over one of its types.
2. She chooses `BULK` and runs it (a button, or Ctrl or Cmd with Enter).
3. The grid shows the columns, the rows, the row count, the freshness and the revision.
4. The answer is truncated: she adds `WHERE x.code > :last` with the last key shown and runs it again for the next rows.

## Acceptance Criteria

- [ ] **US-077-AC1** — Given a valid query, when it is run, then the answer is a grid with one column per selected column, the row count, whether it was truncated, and the freshness and revision it was computed at.
- [ ] **US-077-AC2** — Given `BULK` is chosen, when the query is run, then the freshness names the replica and its position; with `LATEST`, the record store.
- [ ] **US-077-AC3** — Given an answer cut by the limit, when the grid is shown, then it says the answer is truncated, at most 100 rows are shown, and there is no next-page control: the next page is a keyset predicate the operator writes in the statement.
- [ ] **US-077-AC4** — Given a statement the backend cannot read, when it is run, then every violation is shown and no grid.
- [ ] **US-077-AC5** — Given a construct the backend does not serve, an outage or a refusal, when the query is run, then the console shows that, never an empty grid.
- [ ] **US-077-AC6** — Given a person who may read only some modules, when they query another, then the answer is the same as for an unknown module and reveals nothing.
- [ ] **US-077-AC7** — Given a query run, when the request and the console's logs are inspected, then the text is only in a `POST` body: not in a URL, an error message, a log or browser storage.
- [ ] **US-077-AC8** — Given the query surface, when its published description is inspected, then `POST /query` is a read: no statement writes, and `test_only_declared_actions_write` still holds for the writes.

## Edge Cases

- **A statement that reads outside the chosen module**: refused as unsupported (501), and the grid is not changed.
- **A query over 4,000 characters**: refused 400 before it is run.
- **An expired token**: 401, and the console asks the host to sign in again; the history is kept.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| it is run | US-077-AC1 | a valid query | it is run | the answer is a grid with one column per selected column, the row count, whether it was tr |
| the query is run | US-077-AC2 | `BULK` is chosen | the query is run | the freshness names the replica and its position; with `LATEST`, the record store |
| the grid is shown | US-077-AC3 | an answer cut by the limit | the grid is shown | marked truncated, at most 100 rows, no next-page control |
| it is run | US-077-AC4 | a statement the backend cannot read | it is run | every violation is shown and no grid |
| the query is run | US-077-AC5 | a construct the backend does not serve, an outag | the query is run | the console shows that, never an empty grid |
| they query another | US-077-AC6 | a person who may read only some modules | they query another | the answer is the same as for an unknown module and reveals nothing |
| the request and the console's logs are inspected | US-077-AC7 | a query run | the request and the console's logs are inspected | the text is only in a `POST` body: not in a URL, an error message, a log or browser storag |
| its published description is inspected | US-077-AC8 | the query surface | its published description is inspected | `POST /query` is a read: no statement writes, and `test_only_declared_actions_write` still |

## Dependencies

- **Stories**: US-061
- **Feature Spec**: FEAT-010
- **Feature Requirements**: OPR-16
- **PRD Requirements**: FR-63
