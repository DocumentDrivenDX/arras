---
ddx:
  id: product-vision
  type: product-vision
  activity: discover
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: ADR-005
      kind: informed_by
    - id: ADR-009
      kind: informed_by
    - id: ADR-013
      kind: informed_by
---

# Product Vision

> Catalog records cited here are invented demo data.

## Mission Statement

Arras gives an organization's applications one interface to its ontology. Types are defined once in UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions), reads say how current they are, and named actions are the only way to change anything. A module such as the use-case catalog, or an embedding application, then never depends on where the data is kept.

## Positioning

For host-app developers and module builders who need to read and maintain an organization's typed knowledge, Arras is an interface to the ontology. Unlike reading the warehouse directly, or building a database per module, Arras presents one set of UMF-defined types and one set of operations over two stores:

- Truss, the open-source property-graph engine that runs on Lakebase (Databricks managed Postgres). It is the fresh, authoritative home of the types that people maintain.
- Ashlar, the open-source toolkit for property-graph ontologies on a warehouse, which runs on Unity Catalog (Databricks' governance layer for tables and access). It holds the full ontology that Truss feeds.

Clients say what they need to know and how fresh it must be; Arras decides which store answers.

## Vision

Each module that holds knowledge about its domain defines its types in a UMF document and its changes as UMF actions. Applications read through one interface, with a consistency level on every read and the age of every answer stated with it. A correction made through an action is visible to its author at once, and reaches the warehouse behind it a moment later. Clients are written once against the interface. The adapters (Truss and Ashlar in production, plus an in-memory one) are the only code that knows a store, and any can be replaced or added behind the interface, with several record stores and replicas if the organization needs them.

**North Star**: Every application reads the ontology and changes it only through Arras's interface, with each answer stating its freshness and each change attributed to a named person.

## User Experience

A host developer adds Arras to the host application as a library, gives it connections for each store, and declares the catalog module's types and actions in a UMF document. Loading the demonstration records is an idempotent import that keeps each record's original author apart from the load that brought it in.

An end user corrects a Solution's coverage level through the catalog screen. The catalog calls the `CorrectSolution` action with the user's name. Arras validates the call against the declared preconditions, applies it atomically on the record store, and returns a receipt. The next read, passing the receipt, shows the correction.

A use case inventory screen reads counts by area from the warehouse and shows how current they are. The workflow host reads a playbook on behalf of the signed-in user on every call and records an evaluation finding through an action.

## Target Market

| Attribute | Description |
|-----------|-------------|
| Who | Host-app developers and module builders: the catalog first, then the use case inventory and a workflow client |
| Pain | Each client would otherwise decide where its data lives, how fresh a read is, and how a change is validated, attributed and audited. Without an interface, a module's knowledge lives in seed data that no application can edit |
| Current Solution | Seed files; a per-module database; direct warehouse reads |
| Why They Switch | The catalog needs an editable store now, and two more clients need the same ontology without each learning two stores |

## Key Value Propositions

| Value Proposition | Customer Benefit |
|-------------------|------------------|
| One interface over fresh and bulk stores | A client states the freshness it needs and gets an answer that says how current it is |
| Types and actions in UMF | A module declares what its entities are and what may be done to them once; every client discovers it |
| Actions as the only writes | Every change is validated, atomic, attributed to a person and auditable |
| Replaceable backends | Backends (Truss and Ashlar today) can evolve, and more can be added, behind stable interfaces without client rewrites |
| Embeds in the host app | A host app ships Arras in its own deployment, with no second app to run |
| A read-only console | Administrators check what the ontology holds without writing queries |

## Success Definition

| Metric | Target |
|--------|--------|
| Clients using the interface | 1 (the catalog, running inside a host within the latency targets below); 3 (adding the inventory and a workflow client) *(proposed)* |
| Singleton read p95 (95th-percentile latency) | ≤ 20 ms at the host, measured by the benchmark harness *(proposed)* |
| Action p95, including its change record | ≤ 100 ms at the host *(proposed)* |
| Use case list, 30 records | p95 ≤ 1 s *(proposed)* |
| Reads that state their freshness | 100% *(proposed)* |
| Changes attributed to a named person or a load | 100%, by audit reconciliation *(proposed)* |

## Why Now

The catalog needs a durable, editable store, and a module may later publish to a shared ontology. Truss now specifies the hot store's layout, change feed and import semantics, and Ashlar is being framed as the warehouse side. The interface that joins them can therefore be settled before either has code, in a way that gives both clear requirements. Waiting would leave each module on a database of its own, which later clients would then have to reconcile with the ontology.

## Scale

The ontology may reach on the order of a billion entities, with rich properties on entities and relationships alike. That scale lives in Ashlar, and the mutable types in Truss are far smaller. No benchmark at either scale exists yet. Every operation in the interface is bounded (page sizes, traversal depth, result limits), so no client can ask a backend for an unbounded answer.

## The gate: ADR-005

[ADR-005](../02-design/adr/ADR-005-durable-knowledge-state.md) defers durable structure over sensitive source records until a named workload, an entitlement rule and a governed write path exist. Arras stays clear of it by holding no structure derived from sensitive source records. The entitlement read that a host would need is drafted as an interaction and blocked on that gate. Adding either reopens ADR-005's preconditions P1 to P3.
