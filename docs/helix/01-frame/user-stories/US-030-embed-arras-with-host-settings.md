---
ddx:
  id: US-030
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-006
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-030: Embed Arras with host-supplied, per-person connections

**Feature**: FEAT-006 — Embedding and Lifecycle
**Feature Requirements**: EMB-01
**PRD Requirements**: FR-31
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to start Arras inside the praxis app with one connection source per backend, each yielding a connection for a given person
**So that** Arras never reads my environment, never creates its own connections and never reuses one across people

## Context

Praxis is the Databricks app that embeds Arras, and it owns pooling and credentials. Arras takes backends the host registers under names it chooses, with each module's placement; the Truss adapter (a reader and provider on Lakebase, Databricks managed Postgres) is built from a connection source and the Ashlar adapter (a reader on Unity Catalog) from a warehouse source, each called with the principal (the person making the call: user, token and groups). It also takes an explicit administrative principal for registration, attachment and imports and, for the Truss adapter, an installing connection used only to install, verify and upgrade. The MCP binding (Model Context Protocol, Anthropic's open protocol for agent tools) is the only code that reads the environment.

## Walkthrough

1. The developer calls `Arras.start` with named backends built from a connection source and a warehouse source, the placement and an administrative principal; the Truss factory takes the installing connection, `create_backend(name, source, installing=None, *, module_access=None)` (CONTRACT-005).
2. The system connects each backend within the startup budget.
3. The developer reads the status.
4. A person's request reaches a source, and the source yields a connection as that person.

## Acceptance Criteria

- [ ] **US-030-AC1** — Given host-supplied sources, when Arras starts, then it uses them and creates no connection of its own.
- [ ] **US-030-AC2** — Given ambient `PG*` variables (the standard Postgres client environment variables) are set, when Arras starts, then it ignores them.
- [ ] **US-030-AC3** — Given a source called for a principal, when Arras uses the connection, then the connection is that principal's and is never reused for another.
- [ ] **US-030-AC4** — Given a source returns a connection with autocommit on, when Arras uses it, then Arras refuses it.
- [ ] **US-030-AC5** — Given the host's pool, when Arras finishes with a connection, then the connection is returned and no session state is left on it.
- [ ] **US-030-AC6** — Given the library, when its modules are inspected, then only the MCP binding (`python -m arras.mcp`) reads the environment.

## Edge Cases

- **A missing source**: that backend is reported as not configured.
- **A transaction-mode pooler** (a pool that assigns a connection per transaction) sits in front of the Truss adapter's database: Arras works through it.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Sources | US-030-AC1 | A connection source and a warehouse source | Start | Both used; none created |
| Ambient | US-030-AC2 | `PGHOST=db.example.invalid` set | Start | Ignored |
| Per person | US-030-AC3 | Two people, `jsmith` and `akhan` | Use | Separate connections |
| Autocommit | US-030-AC4 | Source returns autocommit on | Use | Refused |
| Return | US-030-AC5 | A finished request | Close | Connection returned, session state clean |
| Environment | US-030-AC6 | The library's modules | Inspect | Only the MCP binding reads it |

## Dependencies

- **Stories**: None
- **Feature Spec**: FEAT-006
- **Feature Requirements**: EMB-01
- **PRD Requirements**: FR-31
- **External**: [CONTRACT-005](../../02-design/contracts/CONTRACT-005-embedding-and-lifecycle.md); [CONTRACT-007](../../02-design/contracts/CONTRACT-007-mcp-binding.md); [ADR-017](../../02-design/adr/ADR-017-backends-are-reached-with-the-users-own-token.md).

## Out of Scope

- Pooling and credential management, which the host owns.
- Migrating the Truss database (US-031).
