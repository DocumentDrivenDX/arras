---
ddx:
  id: prd
  type: prd
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-12
  authoring:
    home: repo
  links:
    - id: product-vision
      kind: informed_by
    - id: concerns
      kind: informed_by
    - id: ADR-005
      kind: constrained_by
    - id: ADR-006
      kind: informed_by
    - id: ADR-010
      kind: informed_by
    - id: ADR-013
      kind: informed_by
    - id: client-interactions-draft
      kind: informed_by
kind: product
---

# Product Requirements Document: Arras

## Summary

Arras is the interface through which an organization's applications read and change the ontology. It is a Python library embedded in a host app such as praxis (an agent-harness app on Databricks), with a backend contract that two adapters implement.

Types are defined in UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions). Every read states a consistency level and how current its answer is. Every change is a named UMF action, attributed to a person and applied atomically by the provider the host's placement names for the action. Two stores sit behind the interface:

- Truss, the open-source property-graph engine on Lakebase (Databricks managed Postgres). It holds the mutable types and is their system of record: a reader and provider.
- Ashlar, the open-source toolkit for property-graph ontologies on a warehouse, running on Unity Catalog (Databricks' governance layer for data). It holds the full ontology and is a reader that serves as a replica, fed from the providers' stores. Arras names neither: it works over any number of named backends with the roles reader and provider, and ships an in-memory third adapter.

Agents reach the same operations through an MCP server (MCP, the Model Context Protocol, is Anthropic's open protocol for agent tools). The first client is the product catalog (use cases, Solutions, products, findings), then the use case inventory and praxis. The top measures: every read states its freshness, every change names a person or a load, and the catalog meets its latency targets inside the praxis app.

## Problem and Goals

### Problem

The first module that needs durable, editable, audited knowledge, the catalog, has no store. Its use cases, products and findings exist as seed data that no application can correct. Praxis-harness (the repository that builds praxis) ADR-027 (ADR: architecture decision record) proposes a database for that one module. A second client would repeat the decisions about where data lives, how current a read is, and how a change is validated and attributed. The ontology itself will be served by stores of different size and freshness (today a hot mutable store and a warehouse, and there can be more); a client that talks to them directly takes on that complexity and breaks when any changes.

### Goals

1. A client reads and changes the ontology through one interface that does not name a store.
2. Each answer says which backend served it and how current it is, and a client can ask for an answer at least as new as its own last change.
3. Every change is a declared action, atomic, attributed to a person and recorded.
4. Types and actions are defined once, in UMF, and every client discovers them.
5. The catalog runs on the interface inside the praxis app, within the latency targets.

### Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|--------------------|
| Singleton read latency | p95 (95th percentile) ≤ 20 ms | Benchmark harness at the host, 100 sequential reads against the record store, warm connection |
| Action latency | p95 ≤ 100 ms | Same harness, 100 invocations of a three-effect action including its change record |
| Type enumeration latency | p95 ≤ 20 ms | Same harness |
| Use case list | p95 ≤ 1 s | The 30-record demonstration catalog at the host |
| Reads that state their freshness | 100% | Contract tests over every read operation |
| Changes attributed to a named person or a load | 100% | Audit reconciliation over all action paths |
| Host integration | Praxis starts and serves with Arras embedded, with either backend unavailable | Startup tests in the host |

*All targets are proposed. They are not yet validated on Unity Catalog through the host. Truss's embedded-PostgreSQL measurements (200,000 objects) put reads on its layout at about 0.02 ms, so the targets leave headroom for the network round trip.*

### Non-Goals

- Durable structure derived from sensitive source records, at this time (ADR-005).
- Domain meaning. The interface carries typed entities, relationships and actions; what a Solution is belongs to the catalog module.
- A bespoke application screen for a module's users. A module's own workflow screens belong to that module; Arras ships a minimal read-only administration console (Admin Console), an operator console that changes data only by invoking declared actions (Operator Console, `arras-ui`), and a generic browser of the graph that any module can style through its UMF document and whose writes, offered to operators, are declared actions invoked as the viewer (Graph Browser).
- An authorization model for the organization. Arras maps a caller to each backend's own access controls; it does not decide who should have them.
- Per-record or per-user entitlements inside the interface.
- A new graph query language or a native graph engine. Reads are the bounded operations listed here.
- Writing to a replica. Changes reach it only through the feed from the providers' stores.
- Actions whose effects span backends.
- Replacing retrieval over documents.

## Users and Scope

### Primary Persona: Host developer

**Role**: Developer of a host application or module that uses the ontology; first the catalog, then the use case inventory and praxis.
**Goals**: Declare types and actions, read with a stated freshness, invoke actions, import seed records, and ship it all inside the host app.
**Pain Points**: Must decide where each kind of data lives, how fresh a read is, and how a change is validated and audited. *(Inferred from ADR-027; not interview-validated.)*

### Secondary Persona: Administrator

**Role**: Owner of the Databricks deployment, its database resources and Unity Catalog access.
**Goals**: Grant read and write access with ordinary database roles and Unity Catalog grants, see who changed what, and browse what the ontology holds.
**Pain Points**: Per-module databases multiply grants, migrations and startup risk in a shared app. *(From ADR-027's risks.)*

### Tertiary Persona: Catalog editor (through a client)

**Role**: Maintains catalog knowledge through the catalog screens.
**Goals**: Correct a record once and see it at once, attributed to them.
**Pain Points**: Records live in seed data that cannot be edited. *(From praxis-harness FEAT-007.)*

### Quaternary Persona: Analyst (through a client)

**Role**: Reads the use cases in aggregate through the use case inventory.
**Goals**: See counts and related use cases across the whole ontology, and know how current they are.
**Pain Points**: No shared view across stores. *(Inferred.)*

### Senary Persona: Module builder

**Role**: Builds modules and systems for readers to use, and runs them. The group may grow to include more people.
**Goals**: See a module's types, relationships and actions, run a declared correction, and find who changed what.
**Pain Points**: No interface shows the registry or the audit trail; every check needs code or database access. *(Inferred; not interview-validated.)*

### Septenary Persona: Graph reader

**Role**: A person who reads what the ontology holds without building on it: a team member checking what a Solution is provided by, or an analyst following a use case to the Solutions that address it. They are not operators and never change data here.
**Goals**: Find a thing by typing a few words, see it presented as a readable page that follows its module's own conventions, follow its links to related things, and see at a glance how it fits in the graph.
**Pain Points**: The only views are GraphiQL and the operator console, both built for people who know the schema; the console presents every type as the same property table. *(Inferred; not interview-validated.)*

### Quinary Persona: Backend implementer

**Role**: Author of a backend adapter (Truss, Ashlar or another): the DocumentDrivenDX maintainers named in the stakeholder map.
**Goals**: Implement one backend contract and declare exactly what the backend can do, and prove the adapter against a shared conformance corpus so backends are interchangeable.
**Pain Points**: Clients that assume capabilities an adapter does not have, and no shared evidence that adapters behave the same. *(Inferred.)*

## Requirements

### Must Have (P0)

1. Read with one `query` over a named module (entity by key, filtered bounded lists paged by the statement, relationship keys through `RELATED_KEYS`), each answer stating its consistency level and freshness, with counts, references to other stores returned as keys, and read-your-write by receipt (Ontology Reads).
2. Change many entities in one request with bulk actions (Actions).
3. Offer an MCP binding with one tool per action (MCP Binding).
4. Reach every backend with the user's own token (Access).
5. Define types in UMF documents only, with the host's placement for each module, and enumerate them (Type Registry).
6. Declare actions in UMF, invoke them with validation, atomic effects, idempotency, attribution and receipts, validate an action without applying it, and import records idempotently (Actions).
7. A backend contract, a Truss adapter that serves reads and actions, and an Ashlar adapter with visible replica positions (Backends).
8. Map callers to each backend's access controls, and tell empty, not permitted and unavailable apart (Access).
9. Embed in a host application with host-supplied connections, an install of its own store and safe startup (Embedding and Lifecycle).
10. Serve the product catalog as the first client within the latency targets, with the use case inventory and praxis as further clients (Reference Clients).

### Should Have (P1)

1. A minimal read-only administration console (Admin Console).
2. Development and test against a local PostgreSQL 18.6 (Embedding and Lifecycle).
3. An operator console for administrators and module builders: schema, data, declared actions and audit (Operator Console).
4. A graph browser for people who use the ontology rather than build it: search, filter by type, a node page that a module's UMF document can style, links to follow, a picture of the node's relationships, and, for operators, an in-place edit of properties and relationships by declared actions and an export of the graph (Graph Browser).

### Nice to Have (P2)

1. A GraphQL read binding (GraphQL is a query language for APIs) for clients other than the console.
2. Loading external vocabularies as modules.
3. Action compensation.

## Functional Requirements

### Subsystem: Ontology Reads

- **FR-1** — A caller reads entities and relationships with one operation, `query`, naming the module it reads and passing a Weft SQL statement that the serving backend compiles and runs: an entity by key, or a type's entities filtered by declared properties, in pages the statement writes (`ORDER BY` the key, `LIMIT` and a keyset predicate), under a limit of 1 to 100 and a `truncated` marker that says the limit cut the answer. Arras defines no dialect and never reads the statement; it routes by the module's placement, and what a statement may contain is what Weft and the backend's declared profiles admit. The answer states the ontology revision and freshness.
- **FR-2** — A statement can select `alias.*` (the entity's declared fields), read a relationship's keys with `RELATED_KEYS(alias.relationship, n)` bounded by the statement, and filter by a relationship to a key with `HAS_RELATED`, so one call answers "this entity and what it connects to" and "the entities connected to this one".
- **FR-4** — A statement can count grouped by one property (`COUNT(*)` with `GROUP BY`) from a backend that declares it. *(Depends on Weft, the SQL project that owns the language `query` takes, DocumentDrivenDX/weft, and on a backend that declares the profile)*
- **FR-6** — Every read states a consistency level, `latest` or `bulk`; the answer states which backend served it and its freshness; Arras never serves a different level than was asked.
- **FR-7** — A read can require an answer at least as new as a receipt's token; if the serving backend has not reached it, Arras serves from the record store, waits within a bound, or reports that the answer is not yet current, and never returns a stale answer unlabeled.
- **FR-8** — A relationship to an entity held by another backend, or outside the ontology, is returned as its key, never fetched implicitly; the key's type is available from `describe`.
- **FR-47** — A row opened with `alias.*` carries, as columns the backend appends, the entity's version and who created and last changed it and when, and, for an imported entity, its original author and time and the load that brought it in; a fact the source did not have is stated as absent, never defaulted.

### Subsystem: Type Registry

- **FR-3** — A caller discovers what `query` accepts for each type from `describe`: columns, relationships, whether counts are served, mutability and latency class.
- **FR-9** — Types are defined by UMF documents and by nothing else; each document defines one module; a document carries no placement, which is host configuration; a document is accepted as a revision by the module's provider, and unsupported constructs are refused naming the construct.
- **FR-10** — The host's configuration, not the module's UMF, places each module: its record store (the system of record, which serves `latest`), its replicas (which serve `bulk`) and, per action, the provider that applies it (the record store by default); an invalid placement is refused as `invalid_placement`.
- **FR-11** — A caller can enumerate modules, entity types, properties, keys, relationships, actions, the host's placement and capabilities, all from one ontology revision, a map keyed by backend name.
- **FR-12** — Changing a type definition does not require rewriting existing records; a change that would is refused, naming the records or the count affected.
- **FR-13** — Arras's reading of UMF accepts and rejects the same documents, with the same diagnostics, as the reference validator on the shared corpus cases.
- **FR-61** — A person holding the record store's own `schema` grant can validate a UMF document without applying it, seeing what it would add, change or retire and every compatibility refusal with its count, and can register it as themselves, so the revision's origin actor is that person; Arras defines no role and decides no access. *(P1)*

### Subsystem: Actions

- **FR-14** — A module declares actions in UMF: a name, a description, typed inputs, preconditions, effects, and an optional handler hook; clients discover them through the registry.
- **FR-15** — A caller invokes an action with inputs; Arras validates the inputs and the preconditions and reports every failure with its reason; a refused action changes nothing.
- **FR-16** — An action's effects apply as one atomic unit on the action's provider; the effects are limited to creating, updating and deleting entities and linking and unlinking them.
- **FR-17** — A caller can pass an idempotency key; invoking again with the same key and inputs changes nothing and returns the original receipt. A bulk invocation's items are each idempotent under the key and their index.
- **FR-18** — Each invocation is attributed to the person whose own token the backend authenticated, and records the action's name; no service identity is ever recorded as the author.
- **FR-19** — An invocation returns a receipt: the identities created or changed, their versions and a token.
- **FR-20** — Actions are refused for a module whose capabilities say it is read-only, and no other write path is exposed to clients.
- **FR-21** — A host can import records into a module idempotently, preserving each record's identity and relationships and its original provenance, apart from the provenance of the load itself; importing the same records again changes nothing.
- **FR-42** — A caller can validate an action without applying it: Arras checks the inputs and preconditions against the provider's current state, returns every violation and failed precondition and the effects it would apply, and changes nothing, records nothing and leaves nothing locked.
- **FR-43** — A caller can change many entities in one request: an action may repeat its effects over a list input; up to 100 invocations of one action can be sent together, applied atomically as one group or independently with a result per item; and an administrator can import records in volume. A batch never partially applies inside one atomic group.

### Subsystem: MCP Binding

- **FR-44** — Arras can run as an MCP server over stdio (standard input and output), built on the library, with tools `describe`, `query`, `validate_action` and one tool per declared action, each taking one item or a batch.
- **FR-45** — The MCP server serves one person, whose token it is launched with; tools take no principal; a missing or expired token is refused with an instruction to re-authenticate; the token can be refreshed without restarting.
- **FR-46** — MCP answers are compact and bounded, refusals say what to do next, and the server starts with a backend down and reports it through `describe`.

### Subsystem: Backends

- **FR-22** — Backends implement one contract of operations and a capability descriptor, so adapters are interchangeable behind the interface.
- **FR-23** — A Truss adapter, a reader and provider, serves reads and actions for the modules placed on it; a host may configure several record stores, one per module, and providers that are not readers.
- **FR-24** — A reader adapter (the Ashlar adapter) serves bounded reads for the modules placed on it and is read-only; a host may configure several replicas, tried in order.
- **FR-25** — Every adapter passes a shared conformance corpus for the backend contract.
- **FR-26** — Each backend's availability and the reason for any outage are reported; a partial answer says which backend produced it; no fallback silently changes the consistency level that was asked for.
- **FR-27** — The position of the feed that each replica reflects is visible, so a freshness statement can name it and the lag can be read.
- **FR-51** — The rules of the action and read contracts (idempotency, atomicity, validation without effect, read-your-writes, outage honesty) are checked over arbitrary sequences of operations against an executable model, and the same check can be run over each adapter. *(P1)*

### Subsystem: Access

- **FR-28** — Every backend call is made with the caller's own token: Postgres roles per module for the Truss adapter, the user's own access for the Ashlar adapter; Arras keeps no access decision, no role map and no service-identity read path, and refuses a call that has no token.
- **FR-29** — Results tell apart empty, not permitted and unavailable, so a caller that fails closed can rely on it.
- **FR-30** — Arras caches no entity data and no access decision across calls.

### Subsystem: Embedding and Lifecycle

- **FR-31** — Arras runs inside a host Python application as a library; the host supplies the connection configuration for each backend; Arras reads no ambient connection variables.
- **FR-32** — Arras installs or verifies the Truss store through Truss's own installer, on a separate installing connection the host supplies, on request; concurrent attempts result in one install (a transaction-scoped advisory lock), and Arras keeps no migration history of its own.
- **FR-33** — If a backend is unconfigured, unreachable, denies access or fails to migrate, Arras reports it unavailable with a reason and the host continues to start.
- **FR-34** — Arras imports nothing from the host, and the host imports only Arras's public interface; a check fails the build on a violation.
- **FR-35** — A developer can run Arras and its test suite against a local PostgreSQL with no external database. *(P1)*
- **FR-48** — The library's own modules follow declared dependency rules, with no cycle and no module above a length ceiling, and a check fails the build on a violation. *(P1)*
- **FR-49** — Arras emits named events and, when OpenTelemetry is installed, spans for reads, changes, refusals and backend availability changes to the host's own logger and tracer provider, with default-deny attributes that never carry inputs, keys, query text, tokens or user names, and continues a caller's trace across the MCP boundary. *(P1)*
- **FR-50** — The MCP process reads its configuration once into one typed object from a published schema, in three layers by owner (ops-injected environment and ops file, a committed per-environment file, committed defaults) with one owner per key, and stops at start naming the file and key it cannot use, never its value; it stops cleanly on SIGTERM or SIGINT. *(P1)*

### Subsystem: Admin Console

- **FR-36** — An administrator can list the modules they may read and browse their types, placement, capabilities and entries by type, including an entity's relationships. *(P1)*
- **FR-37** — The Admin Console (FEAT-007) performs no write, shows only what the viewer's principal permits, reads through the interface, and is available when Arras is embedded. *(P1)*

### Subsystem: Operator Console

- **FR-48** — An operator can list the modules their principal may read and browse each module's types, properties, relationships, actions, placement, capabilities and registry revision, and see the relationships as a diagram, and the module's registered UMF document in UMF's schema browser. *(P1)*
- **FR-49** — An operator can browse a type's entries as a filtered table, one page of up to the chosen limit per request and marked when truncated, with the consistency chosen and the page's freshness shown, open an entity with its attribution, follow a relationship to the entity at its end, and see the module's graph of entities and relationships, through the console's read surface. *(P1)*
- **FR-50** — An operator changes data only by invoking an action the module declares: the console builds a form from the action's inputs, validates, shows the effects, shows the effects on the graph before confirmation, asks for confirmation, invokes with an idempotency key and shows the receipt; up to 100 items can be applied as one batch with each item's result. *(P1)*
- **FR-51** — An operator can read the change history of an entity, the changes of a module by person, action and time, a receipt by id, and the loads that imported records, from the providers' own records, naming the provider whose journal is read (the module's record store by default); Arras keeps no audit table and does not merge providers' journals. *(P1)*
- **FR-52** — The Operator Console holds no credential, runs every call as the viewer's principal with the viewer's own token, offers no write except invoking a declared action and, where the host mounts the schema surface, registering a UMF document as the viewer (FR-61), and runs both inside the host and standalone. An operator can import a UMF document with a preview and export any module's registered document. *(P1)*
- **FR-62** — The development host lets a developer pick a role and give it any name, with no identity provider, and break and mend the sandbox's backends from the console, so every operator flow is exercised without a Databricks dependency. *(P2)*
- **FR-63** — An operator can run one read-only Weft SQL statement over a module they choose from the console at the consistency they choose, read the answer as a grid with its freshness, and reuse queries from a session-only history; the query runs as the operator with their own token, and neither the text nor the history is stored, logged or put in a URL. *(P2)*

### Subsystem: Graph Browser

- **FR-53** — A viewer can search a module's entities by text and receive ranked hits across the types that declare searchable properties, each hit naming its type, its label and what matched, with the answer's freshness, through the console's read surface and bounded like every other read. *(P1)*
- **FR-54** — A viewer can narrow search to one or more entity types, with the number of hits per type shown, and can list a type's entities without a search. *(P1)*
- **FR-55** — A viewer opens an entity as a node page whose title, summary, grouped properties, value formatting, icon and tone come from the module's declared view, with a derived default for a module that declares none. *(P1)*
- **FR-56** — A node page lists every relationship of the entity grouped by relationship name, and each related entity is a link that opens it, including an entity of another module that the viewer may read; an entity the viewer may not read shows as unavailable without saying why. *(P1)*
- **FR-57** — A node page shows a picture of the entity and its neighbours, bounded in size, in which selecting a neighbour opens its node page, styled with the same declared view. *(P1)*
- **FR-58** — A module declares its view in a UMF extension that Arras checks when the module is registered: a closed vocabulary of data (label, summary, sections, formats, icons, tones, search properties), never script or markup. A reference to a property or relationship that does not exist is refused at registration. *(P1)*
- **FR-60** — One interface offers Explore (the Graph Browser) and Operate (the Operator Console) with a switch between them; Operate is offered only to the people the host names as operators (module builders and administrators), is absent, not disabled, for everyone else, and the operator surface refuses a non-operator on the server. Arras decides nothing about who is an operator: in praxis the host names them as the members of its `admins` group and its `builders` group. *(P1)*
- **FR-59** — The Graph Browser holds no credential, runs every call as the viewer's principal, writes only by validating and invoking a declared action as the viewer, where the host offers Operate (an edit, a link, a new entity, a retirement or an entity action: FR-64, FR-65, FR-67, FR-68, FR-70), states the freshness of what it shows, and gives each node page a location that can be shared without placing a key in anything a server sees. *(P1)*
- **FR-64** — Where the host offers a viewer Operate, the Graph Browser offers an edit beside a property of a node page for which the module declares an action whose one effect updates that property of that type, behind an edit mode the reader turns on. A property that its action can only change together with others opens a popup form for them all. A change is that action, validated and then invoked as the viewer with an idempotency key, and refused as the backend or the action refuses it. It is one of the browser's writes (FR-59). *(P2)*
- **FR-65** — Where the host offers a viewer Operate, a relationship group on a Graph Browser node page offers adding a link, and each member offers removing it, where the module declares an action that does it: one `link` (or `unlink`) effect of that relationship between two reference inputs. A change is that action, validated then invoked as the viewer; a relationship the module declares no action for has no control. *(P2)*
- **FR-66** — An operator can export a module's graph from the interface as records, every entity the viewer may read and every link between them, with its original author and time where it has them, in the shape the library's import takes, so that loading the file into a fresh graph reproduces it. The file is the same bytes for the same graph (it holds no time, person or revision), so it can be kept in version control and shipped as a fixture, and it states whether it is complete. The export is a read as the viewer and adds no write path. *(P2)*
- **FR-67** — Where the host offers edits, Explore offers **New <type>** on a type's list, built from a declared action that creates that type. *(P2)*
- **FR-68** — Explore offers **Retire** on a node page, in edit mode, where a declared action deletes that type. *(P2)*
- **FR-69** — Explore shows an entity's history to an operator. *(P2)*
- **FR-70** — Explore offers an **Actions** menu, in edit mode, of the other declared actions that take this entity. *(P2)*
- **FR-71** — Operate and Explore link to each other at the entity, the type and the module (area-specific targets: History, Actions with prefill, a change group), offered only to operators. *(P2)*
- **FR-72** — Quality requirement: an entity has the same title, search results, vocabulary and shortcuts in both modes, and a mode switch keeps what the operator was doing. *(P2)*
- **FR-73** — The interface's name and branding are replaceable: the application name, an optional wordmark or logo, the document title and the strings that name the product are taken from one `brand` configuration, defaulting to Arras, with no product name hard-coded in a user-visible string. *(P2)*
- **FR-74** — Every page is bookmarkable: the address names the mode, module, area, type, entity and the view state that selects what is shown (a list's filter, sort and position, the model's selected type, the changes filters, the open history panel, a chosen action with entity keys); a refresh or a pasted link restores it; the document title names it; Back and Forward move through it; an address that does not parse falls back to the module's area (Operate) or shows "Not available" (Explore), and an Operate address that parses but names nothing the viewer can open shows one "Not found" page that links to the module's Model. *(P2)*

### Subsystem: Reference Clients

- **FR-38** — The product catalog's module supplies its UMF types and actions; the demonstration records are imported; the use case list of 30 meets the latency target; a correction made through an action is visible to its author at once and attributed to them.
- **FR-39** — The use case inventory reads use cases and their related use cases from the replica and shows how current they are; counts follow when `COUNT(*)` is served.
- **FR-40** — Praxis reads context on behalf of the signed-in user on every call without caching it, and records evaluation findings through an action; an entitlement read fails closed and is blocked on ADR-005.
- **FR-41** — Singleton read, action and type enumeration meet their latency targets on the catalog.

## Acceptance Test Sketches

| Requirement | Scenario | Input | Expected Output |
|-------------|----------|-------|-----------------|
| FR-1, FR-6 | Read with a stated freshness | Query a Solution by key at `latest` | Properties, version, ontology revision, backend and `as_of` returned |
| FR-1 | Browse use cases | List 30 use cases, filter by area, `ORDER BY` the key, `LIMIT 50` | Up to 50, ordered by key, the next page read with a keyset predicate; within the list latency target |
| FR-2 | Open a use case | Query the use case with `alias.*` and `RELATED_KEYS` for its relationships, then the Solutions that address it with `HAS_RELATED`, limit 100 | The use case with its fields, appended fact columns and relationship keys, then its Solutions, each stating freshness |
| FR-15, FR-16, FR-19 | Create a candidate Solution | Invoke `CreateCandidateSolution` for an existing coverage assertion | One atomic change creates a Solution and links it to the use case and the assertion; the assertion is unchanged; a receipt returns the new identity and a token |
| FR-15 | Failed precondition | Invoke it for an assertion that already has a candidate | Refused naming the failed precondition; nothing changes |
| FR-42 | Validate first | Validate `CreateCandidateSolution` for an assertion that already has a candidate, then for one that does not | The first returns the failed precondition and no effects; the second returns the effects it would apply; neither changes anything or reserves a key |
| FR-17 | Double click | Invoke it twice with one idempotency key | One Solution; the second call returns the first receipt |
| FR-18 | Attribution | Invoke it with `jsmith`'s own token | The change names `jsmith` and the action; no service identity appears |
| FR-43 | Bulk correction | Send 20 coverage corrections in one batch, `atomic` false, one failing a precondition | 19 applied, one refused with its index; sending the batch again changes nothing |
| FR-44, FR-45 | Agent use | Launch the stdio server with a user's token; list tools; call `query` and an action tool | One tool per action; the change is attributed to the user; no tool names another principal |
| FR-7 | Read your write | Correct a Solution, then read it with the receipt's token | The corrected value, from a backend that has reached the token |
| FR-20 | Read-only module | Invoke an action on a module only a replica serves | Refused as read-only; nothing changes |
| FR-21 | Seed import | Import the demo records, correct one, delete one, import again | Identity and original provenance kept; the second run changes nothing; the deleted record stays deleted |
| FR-4 | Coverage summary | `COUNT(*) GROUP BY workArea` at `bulk` | Counts with `as_of`; a backend whose declared Weft profiles do not serve the statement refuses with `Unsupported` |
| FR-26 | A backend is down | Stop the record store; read a type it holds, invoke an action, read a replica type | Unavailable with a reason; refused; the replica read answers and states its age |
| FR-29 | Entitlement read | The record store unreachable during an entitlement read | Unavailable, never not entitled and never entitled |
| FR-30 | No cache | Read the same playbook twice | Two backend reads |
| FR-33 | Database down | Start the host with an unreachable backend | Arras reports unavailable with a reason; the host serves its other functions |
| FR-3, FR-11 | Discover a type | Call `describe` for the catalog's `Solution` type | Columns, relationships, whether counts are served, mutability, latency class, placement and one ontology revision |
| FR-9, FR-12 | Refuse a bad type document | Submit a UMF document with an unsupported construct, then a revision that would need existing records rewritten | The first is refused naming the construct; the second is refused naming the records or their count; the stored types are unchanged |
| FR-28 | No token | Call `query` and an action with no token | Both refused before any backend is contacted |
| FR-32 | Concurrent install | Start two processes that request the install at once | One installs Truss; the other finds it present and verifies it |
| FR-45 | Expired token | Call an MCP tool after the launch token has expired, then refresh the token and call again | The first call is refused with an instruction to re-authenticate; the second succeeds without a restart |
| FR-46 | MCP with a backend down | Launch the stdio server while the record store is unreachable and call `describe` | The server starts; `describe` reports it unavailable with a reason; answers stay compact and bounded |
| FR-13 | UMF reading | Run the corpus's UMF cases | Same validity and diagnostics as the reference |
| FR-48, FR-49 | Browse a module | Sign in as a module builder, open `catalog`, read its types and relationships, open the Solution table and follow a relationship | Only readable modules appear; each page shows its freshness; the relationship opens the related entity |
| FR-50 | Declared correction | Open `CorrectCoverage`, enter a value, validate, confirm and invoke | The effects are shown before the change; the receipt is shown; a repeat with the same key is a replay |
| FR-51 | Who changed this | Open the corrected Solution's history | One change by the builder, with the time and the action; no input values; a person without the journal grant gets a refusal |
| FR-53, FR-54 | Search and filter | Sign in as a graph reader, type `lumen` in the search box, then narrow to `Solution` | Ranked hits across types, each with its matched text and the answer's freshness; per-type counts; narrowing keeps only `Solution` hits |
| FR-55, FR-56 | Open and follow | Open a `Solution` hit, then follow its `Product` link | The page shows the module's declared title, summary and sections; each relationship is grouped and linked; the link opens the `Product` page |
| FR-57 | See the relationships | Open a node with more neighbours than the picture holds | The picture is capped with a count of those left out; selecting a neighbour opens its page |
| FR-58 | Declare a view | Register a module whose view names a property that does not exist, then one that is valid | The first is refused naming the property; the second registers and its pages follow the declaration |
| FR-59 | Reads and writes as the viewer | Inspect the browser's requests as two principals, one an operator who edits, creates and retires | Reads, and for the operator only validate and invoke of declared actions; each as the viewer's token; no key or search text in a path or query string |
| FR-64 | Edit in place | As an operator edit a property of a Solution that a declared action updates, then open a property no action updates, then repeat as carol (not an operator) | The edit validates, invokes the action with the key and the new value, and the page shows the new value; no edit is offered beside the other property, and carol is offered none |
| FR-65 | Edit a link | As an operator unlock edit mode, remove a solution's link to a use case, then add it back; try a link the module declares no action for | Each change is the module's action, validated then invoked; the group updates; no control beside the undeclared link |
| FR-66 | Export the graph | As an operator export the catalog, load the file into a fresh dev host, and compare | Every entity, property and link matches; a viewer who cannot read a type gets a file that says it is incomplete |
| FR-67 | New | As an operator open a type's list and choose New, fill the form from the declared create action, and submit; try a type with no create action; repeat as carol | The action validates and invokes; the created entity's page opens; no New beside a type with no create action; carol is offered none |
| FR-68 | Retire | As an operator in edit mode open a Solution and Retire it, confirming; open a type no action deletes; repeat as carol | The confirmation names the links, the declared delete validates and invokes, and the type's list opens; no Retire for the other type; carol is offered none |
| FR-69 | History | As an operator open an entity's History, then repeat against a role without the journal grant and a backend with no journal, and as carol | Changes by type and key, newest first, 20 a page, each naming who, when, the action and what it touched; a sentence for each refusal; carol is offered none |
| FR-70 | Actions menu | As an operator in edit mode open an entity's Actions, choose a multi-effect action, validate and invoke; open a property action | The form is prefilled with the entity, the effects are summarised, the receipt links the touched entities; an action an inline control already claims is not in the menu |
| FR-71 | Cross-mode links | As an operator follow Open in Operate from an entity and View in Explore from a change; repeat as carol | Each lands on the same entity, type or module in the other mode and Back returns; carol sees no cross-mode link |
| FR-72 | Same entity, both modes (quality) | Search, open an entity and press `/` and `?` in each mode; switch mode mid-draft | The same title, hits, words and keys in both; the draft, history and lock survive the switch |
| FR-73 | Brand | Serve the interface with a custom brand | The page title, top bar and the strings that name the product show the brand; the default reads Arras |
| FR-74 | Bookmarkable pages | Open each kind of page, refresh, paste its address as another person, press Back and Forward, and open an address that names nothing | Each restores the same state, the title names it and history moves through it; a malformed Operate address falls back to the module's area, an Operate address naming nothing real shows one Not found page linking to the module's Model, and an Explore address naming nothing real shows Not available |
| FR-60 | Modes | Sign in as alice (an operator) and as carol (not), open the interface, then call an operate endpoint as carol | alice sees an Explore/Operate switch and can open the console; carol sees no switch and no mention of Operate; the endpoint refuses carol with `not_operator` |
| FR-52 | One write path | Inspect the operator surface | Only validate, invoke and batch of declared actions write; the console holds no credential

## Technical Context

- **Language/Runtime**: Python 3.11 with `uv` (a Python package manager) and a committed `uv.lock` (ADR-010). The host, praxis, requires Python ≥ 3.11.
- **Database access**: psycopg 3.3.6 (the PostgreSQL driver for Python, binary, libpq 18.6) for the Truss adapter's data path, in the optional `truss` extra (ADR-006, ADR-010). Arras has no migrations of its own: Truss installs itself, install-or-verify, on a trusted installing connection the host supplies (ADR-006). Registering a document runs Truss's bundled UMF producer under Bun 1.4.2, so the host image carries Bun (about 0.5 to 0.9 s of preparation per registration); writes, imports and key lookups run no Bun.
- **Truss adapter's store**: Arras's own Postgres database, separate from praxis's (ADR-012). Deployed: a Lakebase project dedicated to Arras, Postgres 18, on Databricks: the required deployment target, which Arras treats as PostgreSQL 18.6. Locally and in CI: PostgreSQL 18.6 through `pgserver-pg18`, a test-only dependency group. The layout, import identity, unique edges, revision origin, module isolation and change feed are Truss's contracts.
- **Ashlar adapter's store**: gold Delta tables on Unity Catalog, read through a Databricks SQL warehouse on behalf of the user. Ashlar is a sibling project whose requirements are being defined jointly. Delta is the open table format of Databricks' lakehouse.
- **Types and actions**: UMF documents. UMF's declarative action contract is requested of UMF. Arras uses a minimal subset of it (CONTRACT-003) and tracks UMF's.
- **Packaging**: a library deployable inside the praxis Databricks app; no dependency on the praxis internals (praxis ADR-004 keeps `psycopg` out of its core, so the host reaches Arras through an adapter).
- **Platform**: Databricks Apps (Databricks' hosting for web applications); the app's database resource and service principal supply the Truss connection, and the signed-in user's token supplies Unity Catalog access.
- **Admin console**: no frontend framework; a read-only GraphQL schema generated from the registry and explored through GraphiQL, an in-browser GraphQL explorer (ADR-011; CONTRACT-006).
- **Operator console**: a React package, `arras-ui`, in this repository's `ui/` directory (ADR-021), that reaches Arras over HTTP: GraphQL for reads (CONTRACT-006) and JSON for declared actions and audit (CONTRACT-009).
- **Interfaces**: CONTRACT-001 (ontology interface), CONTRACT-002 (type registry and placement), CONTRACT-003 (actions), CONTRACT-004 (backend contract), CONTRACT-005 (embedding and lifecycle), CONTRACT-006 (console), CONTRACT-007 (MCP binding), CONTRACT-009 (operator action and audit surface).
- **Scale**: Ashlar is meant to reach about a billion entities; Truss holds the far smaller mutable set. No measurement at either scale exists through this interface.

## Constraints, Assumptions, Dependencies

### Constraints

- **Technical**: Python 3.11, uv, psycopg, Truss (an optional extra), Postgres on Lakebase, Databricks Apps hosting. The design works over a pooled (transaction-mode) or a direct connection; praxis connects direct (its ADR-028). No session state is kept.
- **Business**: ADR-005 still defers durable structure over sensitive source records until its preconditions are answered; this PRD holds no such structure.
- **Compliance**: No sensitive source records are stored.

### Assumptions

- Truss feeds Ashlar quickly enough that most `bulk` reads are close to current. *(Falsifiable: measure the feed lag through a real publisher; the expectation is low if Lakebase's synchronization performs as advertised.)*
- The module types in the demonstration are placed with the Truss adapter as record store, the playbooks with the Ashlar adapter as record store, and the entitlement source is undecided. *(Falsifiable: the owners of those types say otherwise.)*
- The host assigns the right identity to each person; the backends' own controls do not know the person, and the change record names the person whose own token authenticated the change (ADR-017). *(Falsifiable: an audit finds a role used for a person it was not meant for.)*
- The catalog contains no sensitive source records. *(Falsifiable: the data governance owner or the catalog owner reviews the demonstration records.)*
- Praxis passes a user token on every call. *(Falsifiable: the praxis maintainers confirm.)*
- Arras's Lakebase database is separate from praxis's (ADR-012), and the installing connection the host supplies on it holds what Truss's installer needs (`CREATEROLE`, database `CREATE` with grant option). *(Falsifiable: the deployed host's `migrate` on the `arras` database.)*

### Dependencies

- Truss: the layout, protocols and change feed; a Python implementation that passes its conformance corpus.
- Ashlar: publication semantics, identity, current state and history, a published feed position and user-scoped reads.
- UMF: declarative actions, validity fixtures and relationship semantics.
- Praxis-harness FEAT-007, the catalog feature, which stores the catalog through Arras, and the praxis catalog developer for the host integration and the catalog's types.
- A Lakebase database and grants for Arras, managed by the host's platform owner.

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Praxis builds a catalog database of its own although the catalog runs on Arras | Medium | High | Agree with the praxis owners which database holds the catalog before either ships |
| The interface hides the difference between a fresh and a replicated read and misleads clients | Medium | High | Consistency level and `as_of` on every read; capability descriptors; contract tests that a stale answer is never unlabeled |
| The interface is designed before two real implementations exist and fits none | Medium | High | Derive it from the twelve client interactions; run the shared backend corpus on both adapters before ratifying |
| Declarative actions grow into a workflow engine | Medium | Medium | Effects are a closed list of primitive operations on one store; a named handler hook carries the rest; compensation is deferred |
| UMF's action contract diverges from the subset used here | Medium | Medium | Track UMF's requirements; keep Arras's subset minimal and mapped one-to-one |
| Truss-to-Ashlar lag is larger than expected | Medium | Medium | Report freshness; read-your-write by receipt; measure through a real publisher before relying on `bulk` for freshness-sensitive screens |
| The host's `migrate` call blocks or fails (for example on an unreachable database or a held install lock) | Medium | High | `migrate(timeout=)` bounds the install or verify; a failed migrate is reported per backend as `migration_failed` and the host continues to start (FR-33); `start` installs nothing; tests for each failure case before any merge that changes host startup |
| Latency targets fail on Lakebase through the host path | Medium | High | Run the harness on a Lakebase branch before ratifying the Truss adapter's design |
| The console grows into an end-user product | Medium | Medium | Keep the Admin Console read-only (FR-37) and the Operator Console administrator- and module builder-facing, writing only through declared actions (FR-50, FR-52) |
| The Operator Console becomes the governed-write path by default (ADR-005 P3) | Medium | High | No approval or reversal is claimed; widening beyond administrators and module builders waits for P3 to have an owner |

## Open Questions

- [ ] Which types have their record store where, beyond the assumptions above? Blocks FR-10; ask the owners of each type.
- [ ] How does praxis hand a user's token, and its refresh, to a per-session stdio process, and does Ashlar accept it? Blocks FR-28 and FR-45; ask the praxis owners and the platform owner.
- [ ] Which counts are required, and which Weft read profiles will Truss and Ashlar qualify for whole-entity reads, relationship predicates, `COUNT(*) GROUP BY` and joins? Blocks FR-2, FR-4 and any broader join; ask the Weft and Truss maintainers.
- [ ] What is the measured Truss-to-Ashlar lag through the chosen publisher? Blocks any promise that `bulk` reads are fresh; ask the platform owner and the Ashlar project.
- [ ] Should the interface itself wait for a replica to reach a receipt's token, or only report that it has not? Blocks FR-7; ask Erik LaBianca.
- [ ] Is an action's effect list enough, or is a handler hook needed in the first release? Blocks CONTRACT-003; ask the catalog developer.
- [ ] Which role names and grants does the platform owner provision for each module, and will Truss decide by role membership? Blocks FR-28; ask the platform owner and Truss.
- [ ] Can the platform create a NOLOGIN owner role and grant module roles to the app identity with set-role only on Lakebase? Blocks the Truss adapter's isolation; ask the platform owner.
- [ ] Who owns governed writes (ADR-005 P3) for the catalog? Blocks ADR-005 scoping; ask the data governance owner.
- [ ] Verify the Azure CU-hour (Lakebase capacity-unit hour) and storage rates and the standard rate after 31 Jan 2027. ask the platform owner (SPIKE-005).
- [ ] Who may read whose audit rows: is the journal grant a module reader's, a module writer's or an administrator's? Blocks the audit area of FEAT-010 (FR-51); ask the platform owner and Truss.
- [ ] Will the praxis owners mount a write-capable operator surface, and under which per-action approval (ADR-016, praxis ADR-024)? Blocks FR-50 inside praxis; ask the praxis owners.
- [ ] Will Truss expose a documented journal read and an import-load read? Blocks FR-51; ask the Truss maintainers.
- [ ] No backend serves text search today (Weft v0.1 has equality predicates only; Truss lists full-text and property filters out of scope; Ashlar is silent). Which will add it, and at what strength (substring, word match, ranked)? Blocks FR-53 on any store but the in-memory one; ask the Weft, Truss and Ashlar maintainers (ADR-023).
- [ ] Accept ADR-011 (read-only GraphQL for the console)? Should the same surface later serve agents? Blocks the Admin Console (FEAT-007) build; ask Erik LaBianca.

## Success Criteria

- Praxis starts with Arras embedded, and serves its sessions when either backend is down.
- The catalog is read and changed through the interface, loaded from demonstration records, and a correction made by a named user appears in history under that user.
- Every read states its freshness, and no stale answer is ever unlabeled.
- A caller without access is refused by the backend's own controls on read and on action.
- The latency targets are met on a Lakebase branch.
