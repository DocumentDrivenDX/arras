---
ddx:
  id: ADR-013
  type: adr
  activity: design
  status: accepted
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: ADR-006
      kind: informed_by
    - id: ADR-012
      kind: informed_by
    - id: client-interactions-draft
      kind: informed_by
    - id: CONTRACT-001
      kind: informs
    - id: CONTRACT-002
      kind: informs
    - id: CONTRACT-004
      kind: informs
---

# ADR-013: Arras is an ontology interface over named backends

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-05 | Accepted | Erik LaBianca (architecture lead) | [ADR-006](ADR-006-embedded-library-on-psycopg-and-the-truss-toolkit.md), [ADR-012](ADR-012-own-postgres-database-lakebase-deployed-embedded-locally.md), [ADR-014](ADR-014-reads-state-their-consistency-and-freshness.md), [ADR-015](ADR-015-writes-are-umf-actions-applied-by-providers.md), [ADR-016](ADR-016-mcp-stdio-binding-over-the-library.md), [ADR-017](ADR-017-backends-are-reached-with-the-users-own-token.md), Truss ADR-001 to ADR-003 (DocumentDrivenDX/truss repository), Ashlar vision (DocumentDrivenDX/ashlar repository) | Medium |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | Arras is the interface to an ontology: a Python library embedded in praxis, an agent-harness Databricks app. Applications need to read and change that ontology. The ontology is served by stores of different size and freshness (any number of mutation providers and readers), and each client would otherwise have to choose between them, learn each, and break when any changes. |
| Current State | Truss (owner: DocumentDrivenDX) is an open-source, UMF-driven property-graph engine on SQL databases; its layout, journal, import, edge uniqueness, revision origin, module isolation and change feed are specified as contracts, and a Python implementation can pass its conformance corpus. Ashlar (owner: DocumentDrivenDX) is an open-source toolkit for property-graph ontologies on a warehouse, with gold Delta tables on Unity Catalog (Databricks' governance layer for data) as the official ontology; it is not built, and its requirements are being defined jointly. Truss is meant to be one of the bulk feeds into Ashlar. They are the two production adapters; the interface does not depend on there being exactly these two. UMF (the metamodel, owned by DocumentDrivenDX) is the metamodel for types, and is to define actions. Lakebase is Databricks' managed Postgres, where Truss runs. Praxis needs the catalog (the use cases, products and findings it holds as seed data) first, and playbooks and entitlements next. |
| Requirements | One interface for clients that does not name a store. UMF-defined types and actions. Fresh, authoritative reads and atomic, attributed changes for the mutable types; bounded, large-scale reads over the whole ontology. Embedding in the praxis Databricks app on Python 3.11. Backends that change, or are added, without client rewrites. |
| Decision Drivers | The generic storage, layout and feed semantics belong to the stores; Arras's value is the interface and its wiring to the stores. The stores may change and some are not built, so what clients do defines the interface. |

## Decision

We will build Arras as a **interface to the ontology**: one set of operations (a single `query` read, actions with a bulk form, import, registry), UMF-defined types and actions, a consistency level and freshness statement on every read, and a **backend contract** that adapters implement. A backend is a named store that declares its roles: a **reader** (serves graph reads) and/or a **provider** (applies actions); a host configures any number of backends. A module's placement, which is host configuration, names its **record store** (the reader that is its system of record and serves `latest`), its **replicas** (other readers, which serve `bulk` and may lag) and, per action, the provider that applies it (the record store by default). Three adapters ship: a **Truss adapter** (reader and provider on Lakebase), an **Ashlar adapter** (a reader on Unity Catalog, serving the full ontology for bounded reads) and a **memory adapter** (an in-memory reader and provider and an in-memory reader, real backends that pass the same corpus). Clients depend only on the interface; Arras defines no backend name.

**Key Points**:
1. **Interfaces first.** The interface, registry, actions and backend contract are specified language-neutrally (CONTRACT-001 to CONTRACT-004) and derived from concrete client interactions, with a Python binding first.
2. **Record store, replicas and providers.** The host's placement (not the module's document) says which backend is the record store for each module, which are its replicas, in preference order, and which provider applies each action; each module has one record store and different modules may have different ones. Changes reach a replica only through the feed from the providers' stores, never directly.
3. **No live cross-backend relationships.** A relationship to an entity held by another backend is a reference by key, resolved by a bounded read; the feed materializes it as a real relationship inside a replica.
4. **An adapter uses its store's contracts as the store specifies them.** The Truss adapter uses Truss's layout, import, isolation and feed and adds no storage of its own; the store's installer, layout and upgrades are Truss's (ADR-006). Where a gap appears it is raised on the store as a generic requirement.
5. **Arras is a library embedded in the host** (ADR-006), with per-backend connection sources and per-backend availability.
6. **UMF only.** Types and actions are declared by UMF documents; Arras defines no schema format of its own.

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| A graph store of Arras's own design, or a Python reimplementation of Truss owned by Arras | Full control | A second design to maintain beside the stores'; the generic parts would be reviewed as Arras's | Rejected: the generic engine belongs with Truss |
| Clients use the stores directly | No new layer | Every client learns each store, their consistency and their identity rules; a backend change breaks all clients | Rejected |
| Arras as a service that wraps the TypeScript Truss engine | Reuses code | A second runtime and service in a Databricks app deployed as one unit | Rejected |
| Live cross-backend relationships, with stub entities | Single graph at read time | Two sources of truth to reconcile; the feed makes it unnecessary | Rejected |
| **An interface with a backend contract and several adapters** | Clients are insulated; each backend evolves behind the contract; the interface clarifies every backend's requirements | The interface must express capabilities and freshness honestly, or it hides what matters | **Selected** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | Clients are written once. Each store and Arras own one thing. Requirements flow from the interface to the backends and to UMF. |
| Negative | The interface cannot be validated until more than one adapter exists (the memory adapter is the first). Arras depends on Truss's Python implementation and on Ashlar. Actions depend on UMF's action contract, which UMF has not defined. |
| Neutral | The Truss adapter's database lifecycle follows ADR-006 and ADR-012; the console follows ADR-011. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| The interface hides differences between backends and misleads clients | M | H | Capability descriptors, consistency levels and `as_of` on every read (ADR-014) |
| The interface fits one backend and not another | M | H | A shared backend conformance corpus run against every adapter before the contract is ratified |
| Truss's Python implementation or Ashlar is late | M | H | Interface and corpus first; the catalog needs only the Truss adapter |
| Truss's or UMF's contracts change after Arras depends on them | M | M | Pin exact revisions; re-pin by a recorded decision |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| The catalog is read and changed only through the interface | A client reads a backend directly |
| Every adapter passes the backend corpus | A case fails on any |
| Replacing an adapter needs no client change | A client change is needed |

## Concern Impact

- **Concern selection**: `python-uv`, `databricks-apps` and `lakebase-postgres` stay; `relational-data-modeling` and the authorization concern apply to the Truss adapter's store and are Truss's (concerns.md).
- **Practice override**: none.

## References

- [PRD](../../01-frame/prd.md), [client interactions](../../01-frame/client-interactions-draft.md)
- Truss: DocumentDrivenDX/truss repository (contracts; its spike on partitioning, locks and prepared statements; the change feed)
- Ashlar: DocumentDrivenDX/ashlar repository (vision, PRD, build brief)
- UMF: DocumentDrivenDX/umf repository (the action contract Arras requests of UMF)
