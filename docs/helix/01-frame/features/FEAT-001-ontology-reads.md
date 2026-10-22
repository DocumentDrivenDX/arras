---
ddx:
  id: FEAT-001
  type: feature-specification
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: concerns
      kind: informed_by
---

# Feature Specification: FEAT-001 — Ontology Reads

**Feature ID**: FEAT-001
**Status**: Draft
**Priority**: P0
**Owner**: Erik LaBianca
**Covered PRD Subsystem(s)**: Ontology Reads
**Covered PRD Requirements**: FR-1, FR-2, FR-4, FR-6 to FR-8, FR-47
**Cross-Subsystem Rationale**: None; single subsystem.

## Overview

Ontology Reads implements PRD FR-1 to FR-8: a client reads the ontology with one operation, `query`, naming the module it reads. A `query` statement is Weft SQL; the serving backend compiles and runs it, and Arras neither defines a dialect nor reads the statement: it routes by the named module's placement and the consistency level. It looks up an entity by key, lists a type's entities in bounded pages, opens an entity with the keys it relates to, finds the entities connected to a key and, when a backend serves it, counts by a property. Every answer states which backend served it and how current it is.

Terms used in this spec:

- Arras is the interface through which an organization's applications read and change the ontology.
- A backend is a named store, with the roles reader (serves graph reads) and provider (applies actions). A module's record store is the reader that is its system of record; a replica is another reader that serves `bulk`. Truss is the hot mutable store on Lakebase (Databricks managed Postgres), a reader and provider and the record store of the mutable modules.
- Ashlar is the warehouse store on Unity Catalog (Databricks' data catalog and access-control layer) and is a reader that holds the full ontology as a replica, fed from the providers' stores.
- Weft owns the SQL language `query` takes (DocumentDrivenDX/weft); backends host it.
- UMF is the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions.
- A receipt is what an action returns; its token lets a later read ask for an answer at least as new as that change (FEAT-003).

## Ideal Future State

A client states what it needs and how fresh it must be in one statement. Key lookups and lists answer in interactive time from the module's record store. Counts answer from a replica and state how old they are. A client that has just changed something passes its receipt's token and sees the change, wherever the answer comes from.

## Problem Statement

- **Current situation**: The catalog's knowledge sits in seed data. No application reads it through a shared interface, and the warehouse and the hot store would each need their own client code.
- **Pain points**: Clients cannot tell how current an answer is, cannot ask for read-your-write, would have to learn each store, and would face a family of overlapping read operations.
- **Desired outcome**: One bounded read operation that states a consistency level and freshness on every answer.

## Functional Areas

| Area | User question or job | Feature responsibility |
|------|----------------------|------------------------|
| Entity by key | Fetch one entity | A statement with a key predicate, answered with version, ontology revision and freshness |
| Lists | Browse a type | Bounded pages written in the statement (`ORDER BY`, `LIMIT`, a keyset predicate), equality filters on declared properties |
| Relationships | What is connected to this? | `RELATED_KEYS(alias.relationship, n)` returns relationship keys; `HAS_RELATED` finds connected entities |
| Counts | How many? | `COUNT(*)` with `GROUP BY`, where a backend declares it |
| Consistency | How current is this? | Levels, freshness, receipt tokens, references as keys |

## Requirements

### Functional Requirements by Area

#### Entity by key

READ-01. A caller reads one entity by key with `query`. The row carries the entity's properties and version, and the answer states the ontology revision and freshness. A key that does not exist returns no rows (FR-1).

#### Lists

READ-02. A caller lists the entities of one type in pages it writes in the statement: `ORDER BY alias.key`, `LIMIT n` and, for the next page, a keyset predicate (`WHERE alias.key > :last`), with equality filters on declared properties. Arras caps each answer at `limit` (1 to 100) and marks it `truncated` when the cap cut it; the answer carries no cursor (FR-1).

#### Relationships

READ-03. A caller opens an entity with `alias.*` and reads each relationship's keys with `RELATED_KEYS(alias.relationship, n)`, the statement bounding `n`, and finds the entities connected to a key with `HAS_RELATED(alias.relationship, KEY(:k))` (FR-2). A caller discovers what `query` accepts for each type from `describe` (FR-3, FEAT-002).

#### Attribution

READ-08. An entity opened with `alias.*` carries, as columns the backend appends, its version and who created and last changed it and when, and for an imported entity its original author and time and its load; an absent source fact is `null`, never defaulted (FR-47).

#### Counts

READ-04. A caller can count entities grouped by one property with `COUNT(*)` and `GROUP BY` from a backend that declares the `count` capability (FR-4). This depends on Weft serving the statement shape.

#### Consistency

READ-05. Every read states a consistency level, `latest` or `bulk`. The answer states its backend and freshness. Arras never serves a different level than the one asked (FR-6).

READ-06. A read can require an answer at least as new as a receipt's token. If the serving backend has not reached the token, Arras serves from the record store, waits within a bound, or reports that the answer is not yet current. It never returns a stale answer unlabeled (FR-7).

READ-07. A relationship to an entity held by another backend, or outside the ontology, is returned as its key and is never fetched implicitly; the key's type is available from `describe` (FR-8).

### Non-Functional Requirements

- **Performance** (proposed): key lookup p95 (95th percentile) ≤ 20 ms at the host; the 30-record use case list p95 ≤ 1 s; counts within a few seconds from a replica.
- **Boundedness**: no statement is unbounded. A deployment may lower the maxima and may not raise them.
- **Honesty**: a read never returns a stale answer without saying so, and never silently changes its level.
- **Safety**: Arras never reads or builds a statement; the serving backend compiles it with Weft and executes it with parameters. No backend statement is built by concatenation.

## User Stories

- [US-001: Read an entity by key with one query and see how current it is](../user-stories/US-001-read-an-entity-by-key-with-its-freshness.md)
- [US-002: Browse a type's entities with a filtered, bounded query](../user-stories/US-002-list-a-types-entities.md)
- [US-003: Open an entity with its relationships and find what connects to it](../user-stories/US-003-open-an-entity-with-its-relationships.md)
- [US-004: Count entities grouped by a property](../user-stories/US-004-count-with-a-grouped-query.md)
- [US-005: Choose a consistency level and always see the answer's freshness](../user-stories/US-005-choose-and-state-consistency.md)
- [US-006: See my own change immediately by passing a receipt's token to `query`](../user-stories/US-006-see-my-change-immediately.md)
- [US-007: See references to entities held elsewhere as keys](../user-stories/US-007-see-references-to-other-stores-as-keys.md)
- [US-055: See who changed an entity and when](../user-stories/US-055-see-who-changed-an-entity-and-when.md)

## Edge Cases and Error Handling

- A statement Weft or the serving backend does not serve is refused as unsupported, naming the construct and what the backend supports.
- A statement that reads outside the named module is refused as unsupported by the serving backend.
- A module the principal may not read, or that does not exist, is invalid (`unknown_type`), so its existence is not revealed.
- A key that does not exist returns no rows. There is no not-found error.
- When the required backend is down, the read fails with the backend and the reason. It never answers from a replica instead.
- When a receipt's token has not been reached, Arras serves from the record store, waits within a bound, or reports not yet current (READ-06).

## Success Metrics

- 100% of reads state their freshness (contract tests).
- 0 reads are served at a level other than the one requested.

## Constraints and Assumptions

- Consistency, freshness and receipts follow ADR-014 (the architecture decision record on read consistency and freshness).
- The language is Weft's. The page limit of 100 is a proposed starting value.
- Traversal and change feeds are not operations. `changes` and `loads` read the backends' own records of what changed (CONTRACT-001, Audit reads).

## Dependencies

- **Other features**: FEAT-002 (types and capabilities), FEAT-003 (receipts), FEAT-004 (backends), FEAT-005 (access).
- **External services**: Truss, Ashlar and Weft; the exact surface lives in CONTRACT-001 (ontology interface).
- **PRD requirements**: FR-1, FR-2, FR-4, FR-6, FR-7, FR-8 (P0 item 1).

## Out of Scope

- Any statement shape Weft or the serving backend's declared profiles do not admit (for example `OR`); joins and expressions are available only where a profile admits them.
- Full-text search.
- Multi-hop traversal. A client reads further with further statements. What changed is read with `changes` and `loads` (FEAT-010, CONTRACT-001), not with `query`.
- Writes (FEAT-003).
