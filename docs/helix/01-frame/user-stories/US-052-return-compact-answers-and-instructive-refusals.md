---
ddx:
  id: US-052
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-009
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-052: Return compact, bounded answers and refusals an agent can act on

**Feature**: FEAT-009 — MCP Binding
**Feature Requirements**: MCP-04
**PRD Requirements**: FR-46
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** answers that are compact and bounded, and refusals that say what to do next
**So that** an agent is not flooded by a large result and does not guess at a failed call

## Context

The MCP (Model Context Protocol, Anthropic's open protocol for agent tools) server returns compact JSON: rows as objects, no echo of the request, relationship columns as arrays of keys, and `freshness` as `{backend, as_of: {value, at}, consistency}`, the same fields as the library's.

## Walkthrough

1. The agent queries a type with a large result.
2. The system cuts the answer at a row boundary and marks it `truncated`; the agent continues with a keyset predicate in its statement.
3. The agent names an unknown column.
4. The system answers with a refusal and a hint.

## Acceptance Criteria

- [ ] **US-052-AC1** — Given a result larger than 50 KB, when it is returned, then it is cut at a row boundary and marked `truncated`, and the caller continues with a keyset predicate in its statement.
- [ ] **US-052-AC2** — Given any answer, when it is returned, then rows are objects.
- [ ] **US-052-AC3** — Given a refusal, when it is returned, then it is a tool result with `isError` true and a body `{code, message, hint}`, where `code` is `invalid`, `refused`, `unavailable`, `unsupported` or `not_yet_current` and `hint` says what to do next.
- [ ] **US-052-AC4** — Given an unknown column, when it is queried, then the hint names the closest column.
- [ ] **US-052-AC5** — Given a malformed MCP request, when it is received, then a protocol error is returned.
- [ ] **US-052-AC6** — Given the server running, when it writes, then stdout carries only MCP frames and stderr logs contain no tokens or record contents.
- [ ] **US-052-AC7** — Given any answer, when it is returned, then the request is not echoed.
- [ ] **US-052-AC8** — Given any answer, when it is returned, then relationship columns are arrays of keys.
- [ ] **US-052-AC9** — Given any answer, when it is returned, then nothing is returned that the person's token could not read.
- [ ] **US-052-AC10** — Given a failed precondition, when the refusal is returned, then the hint says to call `validate_action` first.
- [ ] **US-052-AC11** — Given any failure other than a malformed MCP request, when it is returned, then no protocol error is returned.

## Edge Cases

- **A violation**: carries its field or precondition and the value that failed.
- **A tool the registry no longer declares**: the server returns an MCP invalid-params protocol error (-32602), as the MCP specification gives for an unknown tool.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Cut | US-052-AC1 | 60 KB result | Query | Cut at a row boundary; `truncated` set; no cursor |
| Compact | US-052-AC2 | A query returning `Solution` rows | Query | Rows as objects; `freshness` present |
| No echo | US-052-AC7 | A query returning `Solution` rows | Query | The request is absent from the answer |
| Key arrays | US-052-AC8 | A query returning `Solution` rows with relationships | Query | Relationship columns are arrays of keys |
| Token scope | US-052-AC9 | A person whose token cannot read the `archive` module | Query an entity linked into it | No `archive` data returned |
| Shape | US-052-AC3 | A refused call | Call | `isError` true; `code` `refused`; `hint` present |
| Hint | US-052-AC4 | Column `covrage` on `Solution` | Query | Hint names `coverage` |
| Precondition hint | US-052-AC10 | An action call failing a precondition | Call | Hint says to call `validate_action` first |
| Protocol | US-052-AC5 | Malformed request | Send | Protocol error |
| Not protocol | US-052-AC11 | A refused call | Call | Tool result with `isError` true; no protocol error |
| Streams | US-052-AC6 | Server running | Write | Frames on stdout only; no tokens in stderr |

## Dependencies

- **Stories**: None
- **Feature Spec**: FEAT-009
- **Feature Requirements**: MCP-04
- **PRD Requirements**: FR-46
- **External**: [CONTRACT-007](../../02-design/contracts/CONTRACT-007-mcp-binding.md), Answers and Errors.

## Out of Scope

- Listing tools (US-050) and launching with a token (US-051).
