---
ddx:
  id: US-053
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-009
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-053: Start with a backend down and report it through describe

**Feature**: FEAT-009 — MCP Binding
**Feature Requirements**: MCP-05
**PRD Requirements**: FR-46, FR-26, FR-33
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to start the server when a backend is unavailable and see which backend and why through `describe`
**So that** one backend does not stall an agent session, and the tool list follows the registry

## Context

A backend that is unavailable at start does not stop the MCP (Model Context Protocol, Anthropic's open protocol for agent tools) server (CONTRACT-005). The server sends `tools/list_changed` when the registry or a backend's status changes. A backend is a named store with the roles reader and provider; in production Truss (the hot store on Lakebase, Databricks managed Postgres) and Ashlar (a reader on Unity Catalog).

## Walkthrough

1. The host launches the server with a backend unreachable.
2. The system starts the server, and `describe` reports that backend unavailable with its reason.
3. The agent calls an action tool and a replica query.
4. The backend recovers.
5. The system notifies the host.

## Acceptance Criteria

- [ ] **US-053-AC1** — Given a backend unavailable at start, when the server starts, then it starts and each module's `status` from `describe` reports each backend's `available` and `reason`.
- [ ] **US-053-AC2** — Given a backend unavailable, when a tool needs it, then the result is `unavailable` with the backend and reason.
- [ ] **US-053-AC3** — Given the backend recovers or the registry's revision changes, when the server sees the change, then it sends `tools/list_changed`.
- [ ] **US-053-AC4** — Given a tool the registry no longer declares, when it is called, then the server returns an MCP invalid-params protocol error (-32602, as the MCP specification gives for an unknown tool) and a re-list shows the current tools.
- [ ] **US-053-AC5** — Given a backend unavailable, when the server answers, then no fallback silently changes the consistency level asked for.
- [ ] **US-053-AC6** — Given a backend unavailable, when a tool that does not need it is called, then it still works.

## Edge Cases

- **Credentials in a status detail**: never included.
- **A transient fault at start**: does not disable the backend until restart.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Start | US-053-AC1 | `memory` down | Start | Server starts; status and reason in `describe` |
| Unavailable | US-053-AC2 | `memory` down | Call an action tool | Action tool `unavailable` with backend and reason |
| Unaffected tool | US-053-AC6 | `memory` down | Call a replica query | Replica query answers |
| Notify | US-053-AC3 | `memory` recovers | Observe | `tools/list_changed` sent |
| Removed | US-053-AC4 | A tool the registry no longer declares | Call | Method-not-found |
| No swap | US-053-AC5 | `latest` asked; `memory` down; replica up | Query | `unavailable`; replica does not answer |

## Dependencies

- **Stories**: US-032
- **Feature Spec**: FEAT-009
- **Feature Requirements**: MCP-05
- **PRD Requirements**: FR-46, FR-26, FR-33
- **External**: [CONTRACT-007](../../02-design/contracts/CONTRACT-007-mcp-binding.md), Launch and Error Semantics; [CONTRACT-005](../../02-design/contracts/CONTRACT-005-embedding-and-lifecycle.md).

## Out of Scope

- Retrying a failed backend in the background.
- Serving `latest` reads from a replica.
