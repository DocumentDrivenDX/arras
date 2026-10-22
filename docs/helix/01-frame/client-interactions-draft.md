---
ddx:
  id: client-interactions-draft
  type: research-plan
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
---

# Draft client interactions for the ontology interface

**Status**: a draft to provoke correction, not a decision. The call shapes below are illustrative sketches so each interaction can be argued about concretely. Their names are not the interface.

## Purpose

Arras is one interface to the ontology: type definitions as UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions), reads, and mutation commands (UMF actions), served by named backends, each with the roles reader (serves graph reads) and/or provider (applies actions), placed per module by the host as a record store, replicas and providers. The interactions assume the production deployment of two: Truss, the open-source property-graph engine on Lakebase (Databricks managed Postgres), a reader and provider, is the hot store for the mutable types and the source of the changelog feed. Ashlar, the open-source property-graph toolkit on Unity Catalog (Databricks' governance layer for data), a reader that serves as a replica, holds the full ontology on gold Delta tables (Delta is the open table format of Databricks' lakehouse), fed in bulk, so it lags. These twelve interactions are what three clients would actually do, chosen to force the interface to answer its hard questions before it is designed: consistency, staleness, commands, capabilities, identity, authorization and degraded backends.

Clients: the product catalog (the first, writes and reads), the use case inventory (analytic reads over all of the use cases), and a workflow client (an agent-harness app on Databricks, which reads on behalf of the signed-in user on every call and records evaluation findings).

Illustrative call shapes use the library's `ontology.query` (one read operation: the caller names the module and passes a Weft SQL statement, which the serving backend compiles; paging is `ORDER BY`, `LIMIT` and a keyset predicate in the statement), `ontology.invoke`, `ontology.invoke_batch` and `ontology.status`; the same operations are the MCP tools `query` and one tool per action (CONTRACT-007; MCP, the Model Context Protocol, is Anthropic's open protocol for agent tools). Weft is the SQL project that owns the language `query` takes (DocumentDrivenDX/weft). ADR-005 is the architecture decision record (ADR) that defers durable structure over sensitive source records. Every call is made with the signed-in user's own token. `consistency` is `latest` (the record store) or `bulk` (a replica is acceptable). Every answer carries `as_of`, the point in the ontology it reflects. Every action returns a receipt with a `token`, which a later read can pass as `at_least`.

## Summary

| # | Client | Interaction | Operation | Backend path | Consistency | Interface questions it forces |
|---|--------|-------------|-----------|--------------|-------------|-------------------------------|
| 1 | Catalog | Browse and filter use cases | query | Truss | latest | Filters, bounded pages, latency target |
| 2 | Catalog | Open a use case with its Solutions and evidence | query (`alias.*`, `RELATED_KEYS`, `HAS_RELATED`) | Truss | latest | Relationship keys in a row, references to non-ontology ids |
| 3 | Catalog | Create a candidate Solution from a coverage assertion | action | Truss | n/a | Atomic multi-entity action, preconditions, attribution |
| 4 | Catalog | Correct a Solution and see the correction at once | action, read | Truss | latest, then `at_least` | Read-your-write and the change token |
| 5 | Catalog | Seed the demo records, repeatably | import | Truss | n/a | Idempotent import, provenance, deletes |
| 6 | Inventory | Coverage summary by area | query (`COUNT(*)`), deferred | Ashlar | bulk | Weft support for counts, `as_of` |
| 7 | Inventory | Use cases related through a shared Solution | query (`RELATED_KEYS`, `HAS_RELATED`) | Ashlar | bulk | Two queries instead of a traversal; joins deferred |
| 8 | Inventory | What changed since I last looked | not a client operation | n/a | n/a | The change feed feeds the replica; clients compare versions |
| 9 | The embedding host | Read a playbook for a workflow, on behalf of the user | query | Ashlar | bulk | The user's own token, no caching, acceptable age |
| 10 | The embedding host | Check a user's entitlement to a source record | query | to be decided | latest | Fail closed, unavailable versus not entitled (ADR-005) |
| 11 | The embedding host | Record an evaluation finding after a session | action (MCP tool) | Truss | n/a | Idempotency key, the user's token, receipt |
| 12 | All | A backend is down | describe, status | both | n/a | Per-backend availability, partial answers |

## 1. Browse and filter use cases (catalog)

- Who and when: a signed-in product-team user opens the catalog screen.
- Call: `ontology.query("catalog", "SELECT u.code, u.name, u.workArea FROM catalog.UseCase u WHERE u.workArea = :p ORDER BY u.code LIMIT 50", {"p": "data"})`; the next page adds `AND u.code > :last`.
- Expect: up to 50 use cases with key, name and area, ordered by key. The demo has 30 use cases; the screen needs the whole first page in under a second at p95.
- Path: Truss, because `UseCase`'s record store is there.
- Forces: which filters the serving backend's Weft profiles admit (equality on the key and declared properties), that every list is one bounded page in key order, and that the capability descriptor's `columns` tells a client what it can build on without deciding what `query` serves.
- Open: whether a name search is wanted at all; v1 has equality filters only.

## 2. Open a use case with its Solutions and evidence (catalog)

- Call: `ontology.query("catalog", "SELECT u.*, RELATED_KEYS(u.addressedBy, 100) AS addressedBy FROM catalog.UseCase u WHERE u.code = :k ORDER BY u.code LIMIT 1", {"k": "uc-pipeline-mapping"})`, then `SELECT s.* FROM catalog.Solution s WHERE HAS_RELATED(s.addresses, KEY(:k)) ORDER BY s.code LIMIT 100` on the same module, then the findings of each Solution the same way; limit 100 each.
- Expect: the use case with its relationship keys as arrays; the Solutions that address it with status; the product behind each; findings with the product, its version, and whether the finding is primary or adjacent; a version caveat when a finding is about a version that is no longer the product's current one. Workflows appear as references (keys) the caller resolves elsewhere.
- Path: Truss, three round trips.
- Forces: relationship keys in a row (bounded by the statement's `RELATED_KEYS`), references to ids the ontology does not own, and a stable shape a screen can render. Properties on a relationship itself are modelled as a record with two relationships, so a row needs no edge properties.
- Open: are workflow references a declared UMF field type, or plain strings?

## 3. Create a candidate Solution from a coverage assertion (catalog)

- Call: `ontology.invoke("CreateCandidateSolution", {"coverageAssertion": "ca-0042", "useCase": "uc-pipeline-mapping"}, idempotency_key="ui-7f3a")` (as `jsmith`'s own session).
- Expect: one atomic change that creates a Solution carrying the assertion's coverage level and provenance, joins it to the use case and to the assertion, and leaves the assertion unchanged. Precondition: the assertion exists and has no candidate yet. Refused for a user without the writer role. Returns a receipt with the new Solution's identity, a version and a token.
- Path: Truss, one transaction.
- Forces: an action declared as typed inputs, preconditions and effects (the UMF action shape); atomicity across several entities; attribution of the person, never the application; idempotency, so a double click creates one Solution; a refusal that names the failed precondition.
- Open: the action's effects as primitive operations only, or a pluggable handler for logic that does not fit?

## 4. Correct a Solution and see the correction (catalog)

- Call: `ontology.invoke("CorrectSolution", {"solution": "sol-pipeline-01", "coverageLevel": "substantial"}, expected_version=1)`, then `ontology.query("catalog", "SELECT s.* FROM catalog.Solution s WHERE s.code = :k ORDER BY s.code LIMIT 1", {"k": "sol-pipeline-01"}, at_least=receipt.token)`.
- Expect: the read returns the corrected value, from the record store, with its version. If the same page also joins to data that has not yet reached the replica, the page shows that part's `as_of`.
- Path: Truss for both.
- Forces: read-your-write through the token, optimistic concurrency by expected version, and the rule that `latest` is always served by the record store.
- Open: should the interface itself wait for a replica to reach a token, or only report that it has not?

## 5. Seed the demo records, repeatably (catalog)

- Call: `ontology.invoke("ImportRecords", {"load": "load-2026-10-05-01", "records": [...]}, initiated_by="ops")`, run twice, with one record deleted between.
- Expect: first run creates 30 use cases, products, versions, assertions and findings with their original authors and dates; no Solution is created. Second run changes nothing, and the deleted record stays deleted. The load's identity and the initiator are recorded apart from each record's original author.
- Path: Truss.
- Forces: whether import is an action or a separate operation, original provenance versus load provenance, idempotency by identity, and reporting of created, skipped and rejected counts.

## 6. Coverage summary by area (inventory)

- Call: `ontology.query("catalog", "SELECT u.workArea, COUNT(*) FROM catalog.UseCase u GROUP BY u.workArea ORDER BY u.workArea LIMIT 50", consistency="bulk")`.
- Expect: counts per area with `as_of` showing how current the warehouse is. A few seconds is acceptable; the screen shows the age of the data.
- Path: Ashlar.
- Forces: that `COUNT(*) GROUP BY` over one property is the only aggregate in v1, and that it waits on Weft. Until then the screen lists and counts itself.
- Open: counts grouped by a related entity's property are deferred with joins.

## 7. Use cases related through a shared Solution (inventory)

- Call: `ontology.query("catalog", "SELECT s.code, RELATED_KEYS(s.addresses, 100) AS addresses FROM catalog.Solution s WHERE HAS_RELATED(s.addresses, KEY(:k)) ORDER BY s.code LIMIT 100", {"k": "uc-pipeline-mapping"}, consistency="bulk")`, then `SELECT u.* FROM catalog.UseCase u WHERE u.code IN (...) ORDER BY u.code LIMIT 100` on the same module.
- Expect: the other use cases that share a Solution with the one in view, found in two bounded queries, each stating its age.
- Path: Ashlar.
- Forces: a fixed two-hop pattern is one statement with an inner join where the serving backend declares a Weft profile that admits joins (`count-summary`, or the general dialect), and two queries where it does not; recursive traversal is outside Weft SQL 0.2.

## 8. What changed since I last looked (inventory)

- Call: `ontology.changes("catalog", since=last_seen)`, newest first, read from one provider's journal as the person, and `ontology.loads("catalog")` for the imports; a client that wants every provider's changes makes one call per provider (CONTRACT-001, Audit reads).
- Forces: that the history is the providers' own journal, read with the person's grant and paged by its own cursor, and that journals are not merged across providers.

## 9. Read a playbook for a workflow, on behalf of the user (the embedding host)

- Call: `ontology.query("workflows", "SELECT p.* FROM workflows.Playbook p WHERE p.key = :k ORDER BY p.key LIMIT 1", {"k": "pb-example-review"}, consistency="bulk")`, made with the user's own token.
- Expect: the playbook and its steps, each with its approved position, for the session that is about to run the workflow. Not cached by the embedding host; the call repeats each time. If the answer is older than the caller allows, it says so.
- Path: Ashlar, presumably (reference content). Whether it lives in the mutable store is a question for the playbook's owner.
- Forces: that the backend sees the user's own token (a Postgres role for the Truss adapter, Unity Catalog access for the Ashlar adapter), the `as_of` age the caller will accept, and failure modes: unreachable, not permitted and empty are different answers.

## 10. Check a user's entitlement to a source record (the embedding host)

- Call: `ontology.query("workflows", "SELECT e.* FROM workflows.Entitlement e WHERE e.key = :k ORDER BY e.key LIMIT 1", {"k": "reader-a:m-0001"}, consistency="latest")`, made with the user's own token.
- Expect: entitled, not entitled, or unavailable, three distinct results. Unavailable never reads as not entitled and never as entitled; the embedding host fails closed. Low latency, because it runs on every call.
- Path: undecided: this is the data derived from sensitive source records that ADR-005 gates, and its source is an open research question for the embedding host.
- Forces: that a refusal and an outage are different outcomes, a no-cache rule, and the blocking dependency: this interaction cannot be built until ADR-005's preconditions are answered. It is drafted so the interface leaves room for it.

## 11. Record an evaluation finding after a session (the embedding host)

- Call: the MCP tool `catalog_record_finding` with `{"inputs": {"product": "prod-lumen", "version": "2.1", "useCase": "uc-pipeline-mapping", "applicability": "primary", "evidence": "session-8841"}, "idempotency_key": "session-8841-finding-1"}`, from a stdio server launched with the reviewer's token.
- Expect: one finding about the actual product and version, joined to the use case with its applicability, attributed to the reviewer by the token and not to the embedding host. Running it twice creates one. Returns a receipt. A session that records many findings sends them as one batch tool call.
- Path: Truss.
- Forces: the user's own token at launch, idempotency keyed on the caller's own identifier, and the rule that evidence about one product is never recorded as evidence about another (a precondition).

## 12. A backend is down

- Call: `ontology.status()`, and any read or action while one backend is unavailable.
- Expect: per-backend status with a reason. With the record store (here also the provider) down, actions are refused and `latest` reads of the types it holds report unavailable, while replica reads still work and say their age. With the replica down, `latest` reads and actions still work and `bulk` reads fail clearly. The host application keeps starting either way.
- Forces: per-backend availability, partial answers with explicit provenance, and no silent fallback that changes the consistency a caller asked for.

## What these twelve cover

| Interface question | Interactions |
|--------------------|--------------|
| Consistency level and `as_of` | 4, 6, 7, 8, 9 |
| Change token and read-your-write | 3, 4, 11 |
| Actions as UMF actions | 3, 4, 5, 11 |
| Capabilities | 1, 6, 7, 8 |
| Bounded reads and traversal | 1, 2, 7, 9 |
| Principals and authorization | 3, 9, 10, 11 |
| Idempotency and attribution | 3, 5, 11 |
| Degraded backends | 12 |
| History and feed lag | 8 |

## Assumptions to correct

- Which types have their record store where. I assumed `UseCase`, `Solution`, `Product`, `ProductVersion`, `CoverageAssertion` and `Finding` are placed with the Truss adapter as record store, `Playbook` with the Ashlar adapter as record store (read-only, so no actions), and `Entitlement` is undecided.
- That the inventory's analytic reads should go to Ashlar and tolerate staleness.
- That text search on names is wanted at all.
- That the embedding host passes a user token on every call.
- The feed lag from Truss to Ashlar, which sets how often interactions 6 to 8 see stale data. The owner expects it to be very low if Lakebase's hybrid transactional and analytical synchronization performs as advertised. That is unmeasured, so the interface reports freshness (`as_of`, the fed position) and assumes none. A low lag lets most `bulk` reads behave like `latest` in practice, without the interface promising it.

## Requirements sent to the sibling projects

The interface work produced requirements on three projects, proposed as pull requests written without naming this project:

- Truss: grouped operations and a change feed contract, with consumer positions and an observable lag.
- Ashlar: publication semantics, identity, current state and history, a published feed position, read workload shapes and user-scoped access.
- UMF: declarative actions, language-neutral validity fixtures, relationship instance semantics, scalar coverage, key equality.
