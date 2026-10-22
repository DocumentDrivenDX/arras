---
ddx:
  id: FEAT-009
  type: feature-specification
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: concerns
      kind: informed_by
---

# Feature Specification: FEAT-009 — MCP Binding

**Feature ID**: FEAT-009
**Status**: Draft
**Priority**: P0
**Owner**: Erik LaBianca
**Covered PRD Subsystem(s)**: MCP Binding
**Covered PRD Requirements**: FR-44 to FR-46
**Cross-Subsystem Rationale**: None; single subsystem.

## Overview

The MCP Binding implements PRD FR-44 to FR-46. It is a stdio MCP (Model Context Protocol, Anthropic's open protocol for agent tools) server, `python -m arras.mcp`, built on the library. It exposes `describe`, `query`, `validate_action` and one tool per declared action, each taking one item or a batch. Praxis (the Databricks app that embeds Arras, which consumes MCP through a local stdio adapter only) and any MCP client can then read and change the ontology with no Python import. ADR-016 (the architecture decision record for this binding) records the choice.

## Ideal Future State

A host starts one process per signed-in person with that person's token. An agent lists the tools, reads with `query`, and changes data through the action tools, which a host can classify and approve one by one. Answers are compact and bounded. A refusal says what to do next. A backend that is down does not stop the server and is reported through `describe`. A refreshed token is picked up without a restart.

## Problem Statement

- **Current situation**: Praxis may reach Arras only through a local stdio MCP adapter. Python plugins use the library directly.
- **Pain points**: A generic invoke tool cannot be classified or approved per action. An agent in a long session is stalled by one backend or flooded by a large result. A shared identity would let one agent act as another person.
- **Desired outcome**: One implementation behind two bindings, with one tool per action, one person per process and answers an agent can use.

## Functional Areas

| Area | User question or job | Feature responsibility |
|------|----------------------|------------------------|
| Tool set | What can an agent call? | `describe`, `query`, `validate_action` and one tool per declared action, generated from the registry |
| Identity | Whose call is it? | One process, one person's token, refreshable; no principal argument |
| Answers | What comes back? | Compact, bounded answers; instructive refusals |
| Degraded start | What if a backend is down? | The server starts; `describe` reports status; `tools/list_changed` |
| Bulk | Can it change many? | Action tools take `items` with `atomic` |

## Requirements

### Functional Requirements by Area

#### Tool set

MCP-01. The server lists `describe`, `query`, `validate_action` and one tool per declared action named `<module>_<snake_action>`, and no generic invoke tool (FR-44).

MCP-02. An action tool's input schema is JSON Schema derived from the action's UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions) inputs and accepts one `inputs` object or a batch `items` list. Annotations follow the effects: `readOnlyHint` on the read tools, `destructiveHint` when an effect deletes or unlinks, `idempotentHint` on actions (FR-44).

#### Identity

MCP-03. One process serves one person, whose token it is launched with. Tools take no principal. A missing or expired token is refused with an instruction to re-authenticate. The token can be refreshed without restarting. The server cannot migrate, register or import (FR-45).

#### Answers

MCP-04. Answers are compact and bounded. A result over 50 KB is cut at a row boundary and marked `truncated`; the caller continues with a keyset predicate in its statement. A refusal is a tool result with a code and a hint that says what to do next (FR-46).

#### Degraded start

MCP-05. The server starts with a backend down, reports each backend's status through `describe`, returns `unavailable` from tools that need it, and sends `tools/list_changed` when the registry or a status changes (FR-46).

#### Bulk

MCP-06. An action tool accepts up to 100 `items`, applied atomically or independently, and returns a `BatchReceipt` (FR-43, FR-44).

### Non-Functional Requirements

- **Compatibility**: every MCP result equals the library's for the same call. The binding adds no operation, no access decision and no state.
- **Security**: stdout carries only MCP frames. Logs go to stderr and contain no tokens or record contents. The administrative settings are never read.
- **Boundedness**: answers are cut at 50 KB and batches at 100 items.
- **Operability**: the tool list follows the registry's revision.

## User Stories

- [US-050: Expose describe, query and one tool per declared action](../user-stories/US-050-expose-describe-query-and-one-tool-per-action.md)
- [US-051: Serve one person with a token the host can refresh](../user-stories/US-051-serve-one-person-with-a-refreshable-token.md)
- [US-052: Return compact, bounded answers and refusals an agent can act on](../user-stories/US-052-return-compact-answers-and-instructive-refusals.md)
- [US-053: Start with a backend down and report it through describe](../user-stories/US-053-start-degraded-and-report-backend-status.md)
- [US-054: Change many entities through an action tool in one call](../user-stories/US-054-change-many-entities-through-an-mcp-action-tool.md)

## Edge Cases and Error Handling

- When a token file is missing or unreadable at start, the server starts and refuses every tool but `describe` with a hint.
- Two actions whose snake-case names collide are disambiguated by suffix, with the mapping in `describe`.
- A tool called after its action is removed gets an MCP invalid-params protocol error (-32602).
- A malformed MCP request gets a protocol error. Every other failure is a tool result.
- When a precondition fails, the result is `refused` with the failed precondition and a hint to call `validate_action`.

## Success Metrics

- Every MCP result equals the library's for the same call (contract tests).
- A host can approve a single action tool independently of the others.

## Constraints and Assumptions

- The MCP binding is stdio only. A shared HTTP server is deferred (ADR-016).
- How praxis hands a refreshed token to a running process, and the claim that names the user, are open with the praxis owners.

## Dependencies

- **Other features**: FEAT-001 (`query`, `describe`), FEAT-002 (the registry), FEAT-003 (actions and batches), FEAT-005 (the person's own token), FEAT-006 (the only environment reader).
- **External services**: an MCP client such as praxis; the exact surface lives in CONTRACT-007 (MCP binding); ADR-016 and ADR-017 (the architecture decision record on reaching backends with the user's own token).
- **PRD requirements**: FR-44 to FR-46 (P0 item 1; the PRD lists them under the Actions subsystem).

## Out of Scope

- Prompts and resources.
- A multi-user server.
- The host's tool catalog and approval policy.
- Migration, registration and import.
