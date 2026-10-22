---
ddx:
  id: US-051
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

# US-051: Serve one person with a token the host can refresh

**Feature**: FEAT-009 — MCP Binding
**Feature Requirements**: MCP-03
**PRD Requirements**: FR-45, FR-18, FR-28
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to launch one server process per signed-in person with that person's token, and refresh the token without restarting the process
**So that** every call is the person's own and a long session survives token expiry

## Context

One MCP (Model Context Protocol, Anthropic's open protocol for agent tools) server process serves one `Principal` (user, token and groups): the user whose token it was launched with. The token comes from `ARRAS_TOKEN_FILE`, which the process re-reads when the token nears expiry, or from `ARRAS_TOKEN`. The user name and groups are read from the token's claims. Tools take no principal.

## Walkthrough

1. The host launches the server with `ARRAS_TOKEN_FILE`.
2. The person queries and invokes an action.
3. The token nears expiry, and the host rewrites the file.
4. The system uses the new token for the next call.

## Acceptance Criteria

- [ ] **US-051-AC1** — Given a token file, when the server starts, then the user and groups come from the token's claims and no tool takes a principal, so a caller cannot name another user.
- [ ] **US-051-AC2** — Given a token near expiry, when the host rewrites the file, then the process re-reads it and the next call uses the new token without a restart.
- [ ] **US-051-AC3** — Given no token, an expired token or a malformed token, when a tool other than `describe` is called, then the result is `refused` with a hint to re-authenticate.
- [ ] **US-051-AC4** — Given an action tool called with the person's token, when it commits, then the change names that person and the action and no service identity.
- [ ] **US-051-AC5** — Given the server, when it starts, then it reads no `ARRAS_ADMIN_*` setting and offers no migration, registration or import.
- [ ] **US-051-AC6** — Given no token, an expired token or a malformed token, when `describe` is called, then `describe` still answers.

## Edge Cases

- **A token for a person with no access**: the backends refuse, not the server.
- **A token file replaced mid-call**: the call in flight completes with the token it started with.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Claims | US-051-AC1 | Token file for `jsmith` with group `catalog-editors` | Start | User and groups from the claims; no principal argument |
| Refresh | US-051-AC2 | File rewritten with a new token | Call | New token used; no restart |
| Refused | US-051-AC3 | Expired token | Call `query` | `refused` with a hint |
| Describe answers | US-051-AC6 | Expired token | Call `describe` | `describe` answers |
| Attribution | US-051-AC4 | `catalog_set_coverage` called with `jsmith`'s token | Call | Change names `jsmith` and the action |
| No admin | US-051-AC5 | `ARRAS_ADMIN_*` set in the environment | Start | Not read; no migration, registration or import offered |

## Dependencies

- **Stories**: US-049
- **Feature Spec**: FEAT-009
- **Feature Requirements**: MCP-03
- **PRD Requirements**: FR-45, FR-18, FR-28
- **External**: [CONTRACT-007](../../02-design/contracts/CONTRACT-007-mcp-binding.md), Launch; [ADR-017](../../02-design/adr/ADR-017-backends-are-reached-with-the-users-own-token.md); open with praxis (the Databricks app that embeds Arras): how a refreshed token reaches the process.

## Out of Scope

- Serving several people from one process.
- Issuing tokens.
