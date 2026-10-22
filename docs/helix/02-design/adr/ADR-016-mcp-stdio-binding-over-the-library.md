---
ddx:
  id: ADR-016
  type: adr
  activity: design
  status: accepted
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: ADR-013
      kind: informed_by
    - id: CONTRACT-007
      kind: informs
---

# ADR-016: A stdio MCP binding over the Python library, one tool per action

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-05 | Accepted | Erik LaBianca (architecture lead) | [ADR-013](ADR-013-arras-is-an-ontology-interface-over-named-backends.md), [ADR-017](ADR-017-backends-are-reached-with-the-users-own-token.md) | Medium |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | Arras is the interface to an ontology, a Python library. Its first host, praxis (an agent-harness Databricks app), consumes MCP (Model Context Protocol, Anthropic's open protocol for agent tools) through a local stdio adapter only, and may reach Arras only that way. Other Python plugins want the library directly. The interface must serve both without two implementations. |
| Requirements | One implementation of reads and actions. An agent-facing surface whose tools the host can classify and approve by name. A small, simple read surface. |
| Decision Drivers | Praxis takes tool class and reversibility from an operator catalog per tool name, fails closed, and lets annotations only tighten (ADR-024 in the praxis-harness repository). |

## Decision

We will keep the **Python library as the interface** and implement an **MCP server on top of it**, run as `python -m arras.mcp` over stdio (CONTRACT-007).

**Key Points**:
1. **Library first.** The library is the contract (CONTRACT-001 to CONTRACT-005); the MCP server translates and adds nothing, so one implementation serves both and Python callers keep full access.
2. **Reads are one `query`** plus `describe`. Key lookups, filtered lists, relationships and counts are shapes of one statement, not separate operations.
3. **One tool per declared action**, generated from the registry, with a batch form; no generic invoke tool, so a host catalog can classify each by name.
4. **One process, one person.** The process holds one user's token; tools take no principal.
5. **Degraded start and compact answers** so an agent in a long session is not stalled by one backend or flooded by a large result.

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| Generic `invoke(action, inputs)` tool | Constant tool list | A host cannot classify or approve one action differently from another | Rejected |
| Separate tools for get, list, traverse, aggregate, changes | Familiar | Many tools and overlapping semantics; a statement does all of them | Rejected |
| MCP only, no library API | Smaller surface | Python plugins lose direct use; testing through a protocol | Rejected |
| HTTP MCP server | Shared process | Praxis only adopts local stdio; multi-user token handling | Rejected for the first release |
| **Library plus a stdio binding, per-action tools** | One implementation, host-classifiable | Tool list changes with registry revisions | **Selected** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | One behavior to test; praxis integration is configuration. |
| Negative | A tool list that follows the registry needs `tools/list_changed` handling (the MCP notification that the tool list changed). |
| Neutral | The console (CONTRACT-006) is a separate, human-facing binding. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| Token refresh in a long-lived process | M | M | The token file is re-read near expiry; how praxis hands over and refreshes the token is open (concerns.md, open question 4) |
| Many actions bloat the tool list | L | M | A module declares few actions; `describe` lists them |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| Every MCP result equals the library's for the same call | A divergence is found |
| A host can approve a single action tool independently | It cannot |

## References

- [CONTRACT-007](../contracts/CONTRACT-007-mcp-binding.md), [CONTRACT-001](../contracts/CONTRACT-001-ontology-interface.md)
