---
ddx:
  id: US-065
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-011
      kind: informed_by
    - id: prd
      kind: informed_by
    - id: CONTRACT-010
      kind: informed_by
---

# US-065: Search for an entity by text

**Feature**: FEAT-011 — Graph Browser
**Feature Requirements**: BRW-01, BRW-02
**PRD Requirements**: FR-53
**Priority**: P1
**Status**: Draft

## Story

**As a** graph reader (a person who uses the ontology without building on it)
**I want** to type a few words and see ranked hits across the module's types
**So that** I reach the thing I am thinking of without knowing which type it is or what its key is

## Context

Today a text box only dims entities that the operator console already loaded (the first 100 of each type), so it cannot find what is not loaded. This story is the search read of CONTRACT-010, which asks each backend that can to match text on the properties a module declares searchable, and ranks the hits. Each answer states its freshness like every other read.

## Walkthrough

1. The reader opens the `catalog` module in the browser and sees the search box focused.
2. She types `lumen`; after a 250 ms pause the browser sends one search.
3. The results list ranks hits across `Solution`, `Product` and `Finding`; each row shows the type, the label and an excerpt with `lumen` marked.
4. She keeps typing `lumen runbook`; the earlier answer is replaced by the answer for the new text, never shown after it.
5. She opens a hit, and its node page opens (US-067).

## Acceptance Criteria

Exact search surface, ranking tiers, bounds and errors are in CONTRACT-010.

- [ ] **US-065-AC1** — Given a module with searchable properties on three types, when the reader types two or more characters and pauses, then one search is issued and the hits of all three types appear in rank order, each with its type, label and marked excerpt
- [ ] **US-065-AC2** — Given a search in flight, when the reader changes the text, then the answer to the earlier text is discarded and never displayed
- [ ] **US-065-AC3** — Given a search answer, when it is shown, then the answer's freshness (backend, how current, consistency) is shown with it
- [ ] **US-065-AC4** — Given text with no hit, when the answer arrives, then the page names the text and the types searched and, when a type is selected, says that `All` searches every type
- [ ] **US-065-AC5** — Given one character of text, when the reader pauses, then no search is sent and the page says two characters are needed
- [ ] **US-065-AC6** — Given a type whose backend does not serve text search, when a search runs, then the page names that type as not searched and still shows the hits of the others

## Edge Cases

- **A backend is unavailable**: the hits from the reachable backends show with their freshness, the page names the backend that is not, and it does not say there were no more hits.
- **More hits than a page**: the page shows the first `limit` hits and says the answer was truncated, with each type's count marked "or more"; narrowing to one type (US-066) pages that type in key order with a "show more" control.
- **Text with SQL or pattern characters**: `%`, `_` and quotes match literally; they never alter the query (CONTRACT-010).
- **The viewer's token expires mid-search**: the host's session-expired state shows; the typed text is kept.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Ranked hits | US-065-AC1 | catalog; `Solution.name` and `Product.name` searchable | type `lumen`, pause | Hits from both types; an exact-name hit above a substring hit; each row carries type, label, marked excerpt; one request sent |
| Stale answer dropped | US-065-AC2 | First search held open | type another character; answer the first, then the second | Only the second answer is displayed |
| Freshness shown | US-065-AC3 | Hits from record store and replica | search | Freshness line names each backend and how current |
| No hit | US-065-AC4 | text `zzzz` | search | "No results for zzzz in Solution, Product, Finding", with a note that `All` searches every type when one is selected |
| Too short | US-065-AC5 | text `h` | pause | No request sent; hint shown |
| Unsupported type | US-065-AC6 | `Finding` backend has no search | search `lumen` | `Finding` listed as not searched; `Solution` hits shown |

## Dependencies

- **Stories**: none; US-066 and US-067 build on it.
- **Feature Spec**: FEAT-011
- **Feature Requirements**: BRW-01, BRW-02
- **PRD Requirements**: FR-53
- **External**: CONTRACT-010 (the search read), CONTRACT-004 (the backend `search` capability), ADR-023.

## Out of Scope

- Saved or remembered searches.
- Searching more than one module in one request.
- Search over documents or the corpus.
- Operators, quoted phrases and fielded search (`name:lumen`) in the first release.
