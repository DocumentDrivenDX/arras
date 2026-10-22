---
ddx:
  id: ADR-014
  type: adr
  activity: design
  status: accepted
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: ADR-013
      kind: informed_by
    - id: CONTRACT-001
      kind: informs
    - id: CONTRACT-004
      kind: informs
---

# ADR-014: Every read states its consistency and freshness

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-05 | Accepted | Erik LaBianca (architecture lead) | [ADR-013](ADR-013-arras-is-an-ontology-interface-over-named-backends.md) | Medium |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | Arras is the interface to an ontology, a Python library embedded in praxis (an agent-harness Databricks app). One interface over record stores and their replicas can mislead a client about how current an answer is, and cannot promise that a client sees its own change in the replica. |
| Current State | In production Truss (an open-source, UMF-driven property-graph engine on Postgres; owner: DocumentDrivenDX) on Lakebase (Databricks managed Postgres) is a reader and provider, the system of record for the mutable modules and the source of the change feed, and Ashlar (an open-source toolkit for property-graph ontologies on a warehouse; owner: DocumentDrivenDX), which holds the full ontology on Unity Catalog (Databricks' governance layer for data) is a reader fed from the providers' stores. Arras names neither; it sees backends with the roles reader and provider, and a placement per module. UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions) declares the types. The feed's end-to-end lag is unmeasured; the expectation is that it is low if Lakebase's synchronization performs as advertised. |
| Requirements | Fresh reads of a client's own changes. Large-scale, possibly stale reads where freshness is not needed. A client can always tell how current an answer is. No silent change of the level a client asked for. |
| Decision Drivers | The split of a command side and a query side (CQRS, command query responsibility segregation), and the Ashlar build brief's statement that low-latency visibility of a change comes from the hot store and not from a batch rewrite of the replica. |

## Decision

We will make every read carry a **consistency level** and every answer carry its **freshness**.

**Key Points**:
1. **Two levels.** `latest` is served by the module's record store. `bulk` is served by the first replica, in the placement's preference order, that serves the statement, else by the record store.
2. **Freshness on every answer.** An answer states the backend that served it, `as_of` (for a replica, the feed position it reflects and when that was recorded; for the record store, the time of the read) and the module's revision, a map keyed by backend name (CONTRACT-002).
3. **Receipts.** Every action returns a receipt with an opaque token. A later read can pass `at_least=token`; if the serving backend has not reached it (a replica whose feed has not yet carried another provider's token does not reach it), Arras serves from the module's record store, waits within a stated bound, or reports that the answer is not yet current. It never returns an unlabeled stale answer.
4. **No silent fallback.** If the backend a level requires is unavailable, the read fails with the reason; Arras does not serve `latest` from a replica, and an unavailable replica is not replaced silently by another backend.
5. **Capabilities.** A type's descriptor states what each backend can do (columns, relationships, counts) and its latency class, so a client chooses with knowledge.
6. **Freshness is reported, not promised.** The lag is observable (the replica's position and the age of the oldest unapplied change); no client behavior assumes it is small.

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| Hide the difference and always serve the freshest answer available | Simplest for clients | Cannot offer replica-scale reads; hides cost | Rejected |
| Make clients pick a backend | Explicit | Defeats the interface | Rejected |
| Synchronous replication so replicas are always current | No lag | Not available from the warehouse path; couples the stores | Rejected |
| **Consistency level, `as_of` and receipt tokens** | Honest and cheap; a standard pattern | Clients must handle a not-yet-current answer | **Selected** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | Read-your-write without synchronous replication; every answer is explainable. |
| Negative | A client must carry a token through a flow that spans calls; adapters must expose positions. |
| Neutral | If the measured lag is very low, most `bulk` reads will behave like `latest` in practice without the interface promising it. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| Positions cannot be compared across backends | M | M | The token is opaque to clients; only the adapter that issued it interprets it |
| Waiting for a token hurts latency | M | M | A stated bound; otherwise serve from the record store |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| No read returns an answer without freshness | One does |
| A read with a receipt's token never returns data older than the change | One does |

## References

- [CONTRACT-001](../contracts/CONTRACT-001-ontology-interface.md), [CONTRACT-004](../contracts/CONTRACT-004-backend-contract.md)
