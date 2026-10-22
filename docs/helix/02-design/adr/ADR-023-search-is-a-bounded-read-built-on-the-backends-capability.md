---
ddx:
  id: ADR-023
  type: adr
  activity: design
  status: proposed
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: FEAT-011
      kind: informed_by
    - id: FEAT-001
      kind: informed_by
    - id: FEAT-004
      kind: informed_by
    - id: ADR-013
      kind: informed_by
    - id: ADR-014
      kind: informed_by
    - id: ADR-017
      kind: informed_by
    - id: ADR-022
      kind: informed_by
    - id: CONTRACT-001
      kind: informs
    - id: CONTRACT-004
      kind: informs
    - id: CONTRACT-006
      kind: informs
    - id: CONTRACT-010
      kind: informs
---

# ADR-023: Search is a bounded read built on the backends' declared capability

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-11 | Proposed | Erik LaBianca (architecture lead) | [FEAT-011](../../01-frame/features/FEAT-011-graph-browser.md), [ADR-013](ADR-013-arras-is-an-ontology-interface-over-named-backends.md), [ADR-014](ADR-014-reads-state-their-consistency-and-freshness.md), [ADR-017](ADR-017-backends-are-reached-with-the-users-own-token.md), [ADR-022](ADR-022-a-modules-presentation-is-declared-in-a-closed-umf-view-vocabulary.md) | Medium |

Proposed records the direction under review; it does not claim implementation is complete.

## Context

| Aspect | Description |
|--------|-------------|
| Problem | A reader who has words but not a key needs to find an entity across the types of a module. The interface's reads are by key, filtered lists (equality on declared columns and relationships, ordered by key) and counts; none matches text. The console's graph filter only dims entities already loaded (100 per type), so it cannot find what is not loaded. |
| Current State | `query` (CONTRACT-001) takes a module and one read-only Weft SQL statement, which Arras never reads: the serving backend compiles and runs it under the Weft profiles it declares, and paging is the statement's own (`ORDER BY` the key, `LIMIT`, a keyset predicate). Each backend declares per type what it serves (`describe`, `Capabilities`, CONTRACT-004). Every read states a consistency level and freshness (ADR-014) and runs with the viewer's own token (ADR-017). Arras keeps no index, no cache and no state of its own (ADR-013, FEAT-005). |
| Upstream Status | Checked on 2026-10-11 in the owners' repositories. **Weft SQL v0.1** (CONTRACT-001): equality predicates joined by `AND` only; its capability IDs are `scan`, `project`, `innerJoin`, `filter`, `equal`, `and`, `group`, `sum` and `type.<family>`; no `LIKE`, substring or function other than `SUM`. **Truss** (FEAT-005): out of scope are "a query language and filters on properties" and "full-text or analytic queries"; its reads are by key and by edge traversal, and its draft scalar layout has no index on text values. **Ashlar**: no text search in its frame or contract documents. No backend serves text search today, so the first release's adapters declare `none` except the in-memory one. |
| Requirements | Search across the types of one module by text; ranked; bounded in cost; stating its freshness; as the viewer, so a hit is only what the viewer may read and an unavailable backend is never reported as no hits; honest about the types it could not search; no new state. |
| Decision Drivers | The catalog is small (30 use cases, a handful of types), but the interface is for any module and must not promise what a backend cannot serve; the stance of ADR-013 is that Arras states capabilities rather than hiding them. |

## Decision

We will add **search** as a bounded read of the interface, defined in CONTRACT-010: a library operation `Ontology.search` and a field `_search` on a module's GraphQL endpoint (CONTRACT-006's surface, extended additively). It is built on a **backend capability**: for each entity type a backend declares `search` as `none` or `substring` and lists the string properties it can match as `searchable` (`Capabilities`, CONTRACT-004; the levels `word` and `ranked` are reserved for backends that gain them). The text match is a **structured argument beside the statement** (`TextMatch(words, properties)`, the keyword-only `text` of `query`, carried to `Backend.query` next to the Weft statement), not SQL text: Arras reads neither, Weft's language is unchanged, and each adapter renders the match in its own engine's terms. A backend that does not declare `substring` for the type, or a property not in its `searchable`, answers `Unsupported`. Arras composes a search from the capability and ordinary reads:

1. It takes the effective search properties of each requested type from the resolved view (ADR-022; derived default: the label property, the key and the conventional text properties, in that rank order) and keeps those the serving backend lists as `searchable`.
2. For each type whose backend declares `substring`, it issues **one bounded read** as the viewer: an ordinary `query` of the module, `SELECT x.*, RELATED_KEYS(x.r, 100) AS r … FROM module.Type x ORDER BY x.key LIMIT 51` with `limit=50` and a text match over those properties (every word must occur, after one defined fold, in at least one of them), all under one registry revision; a type is capped (`atLeast`) when it returned 50 rows or the answer is `truncated`. `%`, `_` and `\` in the text match literally.
3. It re-checks each candidate with the same fold, ranks by tiers (equal, prefix, word start, substring) scaled by the property's position in the search list, merges across types, and returns at most `limit` hits with an excerpt as marked segments and the matched properties.
4. It reports per-type hit counts, the types it did **not** search and why (no capability, no searchable property, a backend unavailable, budget), and the freshness of each backend that answered. It never reports an unsearched type as having no hits.

Search is a read like any other: it takes `consistency`, its cost counts against the request budget of CONTRACT-006, and it adds no operation to `query` itself.

**Key Points**: Capability declared by the backend, never assumed | one bounded escaped `LIKE` per type, run as the viewer | ranking in the library, no index of Arras's own | honest about what was not searched

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| Filter in the client over the loaded slice (status quo) | Nothing to build | Finds only what is loaded; a hit in the 101st entity is invisible, silently | Rejected: it gives wrong answers without saying so |
| A search index or service of Arras's (Databricks Vector Search, a search engine, a table) | Ranked, fast, typo-tolerant | State of its own that Arras does not keep (ADR-013); a second place that must honour the viewer's grants (ADR-017) and state its freshness (ADR-014); an index of restricted content is a copy of it (ADR-005) | Rejected: it breaks the interface's no-state stance and the access model |
| Native full-text search on each backend (Postgres `tsvector`, `pg_trgm`; Unity Catalog search) | Fast and ranked at scale | Each backend differs; not in Weft's language; a backend-specific path per adapter before the need is shown | Deferred: reserved as the capability levels `word` and `ranked`; adopted per backend when a module's size demands it |
| Have callers write `LIKE` (and `lower`, `OR`) in the Weft statement and compose search themselves | One mechanism | Whether a statement may use them is Weft's and each backend's profiles, not Arras's; escaping and folding differ per engine; callers composing search per type re-implement the merge and the honesty rules | Rejected: a structured text match beside the statement is smaller and leaves the statement alone |
| **A bounded search read built on a declared capability and ordinary reads** | No new state; respects grants and freshness; works on any backend that serves `LIKE`; honest | A scan on large types; ranking is coarse; one query per type | **Selected: smallest design that is correct; scale is handled by the capability, not assumed** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | Search works wherever `LIKE` does, as the viewer, with stated freshness, and tells the viewer what it could not search. The browser's type chips and counts come from the same answer. |
| Negative | A substring match on a large type is a scan, so a backend must declare `substring` only when it accepts that cost; ranking is within at most 50 candidates per type, so a better match beyond them can be missed and the answer says it was truncated. There is no typo tolerance or stemming. |
| Neutral | CONTRACT-004 gains a capability value; the conformance corpus gains cases (the escaped text, the unsupported type, an unavailable backend). Counts per type are counts of candidates read, not totals. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| No real backend serves search, so the browser's search works only on the in-memory backend until upstream adds it | H | M | The capability is honest (`none`, with the type named in `notSearched`); proposals go to Truss (a text read over text properties backed by a trigram index, with the module isolation and the viewer's grants) and to Weft (a `contains` predicate capability); until then a Truss adapter MAY declare `substring` for a type whose size the host accepts, executing a parameterized, escaped, case-insensitive match as the person in its read-only transaction, which is a scan; the node browser and type list work without search |
| An adapter cannot implement the fold or the literal `%`, `_` and `\` in its engine | L | M | The capability is per type: an adapter that cannot declares `none` and the answer says so; the conformance corpus pins the behaviour |
| A scan on Lakebase or Unity Catalog is slow on a large type | M | M | The candidate cap and `limit` bound the result, not the scan; the capability lets a backend decline; a latency target on the catalog is measured (FEAT-011); `word`/`ranked` levels are the upgrade |
| A short or common word matches nearly everything, and the cap hides better hits | H | L | Minimum text length two; all words required; the answer states `truncated` and the type chips let the viewer narrow and page by key |
| Search text reaches logs | M | M | The text is never in a path or query string, is never carried in SQL text, and is excluded from Arras's telemetry attributes (ADR-018, CONTRACT-008) |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| A search on the 51-use-case catalog answers within 1 second at p95 on the record store and on the replica | A module whose type exceeds 100,000 entities is browsed, or p95 exceeds 1 second |
| A search as two principals returns only what each may read, and an unavailable backend is named, never "no hits" (conformance cases) | Any case where an unreadable entity is counted or an outage is shown as empty |
| The text `%`, `_`, `\` and a quote matches literally in every adapter | A backend that treats them as pattern characters |

## Concern Impact

- **No concern impact**: search adds a module to the library (SD-011) under the existing boundary rules and adds no dependency.

## References

- [FEAT-011](../../01-frame/features/FEAT-011-graph-browser.md), [CONTRACT-010](../contracts/CONTRACT-010-graph-browser-view-and-search.md), [SD-011](../solution-designs/SD-011-graph-browser.md)
- [CONTRACT-001](../contracts/CONTRACT-001-ontology-interface.md), [CONTRACT-004](../contracts/CONTRACT-004-backend-contract.md), [CONTRACT-006](../contracts/CONTRACT-006-console-graphql-surface.md)
- [ADR-013](ADR-013-arras-is-an-ontology-interface-over-named-backends.md), [ADR-014](ADR-014-reads-state-their-consistency-and-freshness.md), [ADR-017](ADR-017-backends-are-reached-with-the-users-own-token.md)
