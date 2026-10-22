---
ddx:
  id: US-050
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

# US-050: Expose describe, query and one tool per declared action

**Feature**: FEAT-009 — MCP Binding
**Feature Requirements**: MCP-01, MCP-02
**PRD Requirements**: FR-44
**Priority**: P0
**Status**: Draft

## Story

**As a** Client developer
**I want** to start the stdio server and see `describe`, `query`, `validate_action` and one tool per declared action, each with a schema derived from the registry
**So that** a host can list, classify and approve each tool by name, and an agent has typed inputs

## Context

MCP (Model Context Protocol) is Anthropic's open protocol for agent tools, and stdio is its standard-input-and-output transport. `python -m arras.mcp` is a binding of the library: it adds no operation and no access decision. `describe` returns the registry, the tool-name mapping and each backend's status. Praxis (the Databricks app that embeds Arras) consumes MCP through a local stdio adapter and takes a tool's class and reversibility from its operator catalog by name (praxis ADR-024, an architecture decision record in the praxis-harness repository), so no generic invoke tool exists.

## Walkthrough

1. The host launches the server for a signed-in person.
2. The host lists the tools.
3. The host reads the schema of `catalog_set_coverage` and the annotations of each tool.
4. The host calls `query` with a module and a statement taken from `describe`.

## Acceptance Criteria

- [ ] **US-050-AC1** — Given the registry, when the host lists tools, then it lists `describe`, `query` and `validate_action` and one tool per declared action named `<module>_<snake_action>` (`catalog_set_coverage` for `catalog.SetCoverage`), and no generic invoke tool.
- [ ] **US-050-AC2** — Given an action's UMF inputs, when its tool is listed, then its input schema is JSON Schema derived from them, required inputs are `required`, and `inputs` or a batch `items` list of 1 to 100 is accepted.
- [ ] **US-050-AC3** — Given the tools, when annotations are read, then `describe`, `query` and `validate_action` have `readOnlyHint`; an action tool has `destructiveHint` only when an effect is `delete` or `unlink`, `idempotentHint` always, and `openWorldHint` false.
- [ ] **US-050-AC4** — Given two actions whose tool names collide, when tools are listed, then a suffix disambiguates them and `describe` lists the mapping.
- [ ] **US-050-AC5** — Given the `query` tool, when its description and input schema are read, then it says the statement is Weft SQL, carries one worked example drawn from the registry, and requires `module` and `sql`.

## Edge Cases

- **An integer wider than 53 bits**: a decimal string in the schema.
- **A decimal, timestamp or binary input**: a decimal string, RFC 3339 text or base64 text.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Tool set | US-050-AC1 | Registry with `catalog.SetCoverage` | List tools | `describe`, `query`, `validate_action`, `catalog_set_coverage`; no generic invoke |
| Schema | US-050-AC2 | `catalog.SetCoverage` inputs | Read the schema | JSON Schema; `inputs` or `items` (1 to 100) accepted |
| Annotations | US-050-AC3 | An action with a `delete` effect and one without | Read annotations | `destructiveHint` only on the first; `idempotentHint` on both |
| Collision | US-050-AC4 | Two actions with the same snake name | List | Suffix added; mapping in `describe` |
| Description | US-050-AC5 | `query` tool | Read the description and schema | Weft SQL, one registry example; `module` and `sql` required |

## Dependencies

- **Stories**: None
- **Feature Spec**: FEAT-009
- **Feature Requirements**: MCP-01, MCP-02
- **PRD Requirements**: FR-44
- **External**: [CONTRACT-007](../../02-design/contracts/CONTRACT-007-mcp-binding.md), Tools and Annotations; [ADR-016](../../02-design/adr/ADR-016-mcp-stdio-binding-over-the-library.md).

## Out of Scope

- Serving MCP over HTTP.
- A generic tool that invokes any action by name.
