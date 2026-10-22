# Glossary

Terms that Arras artifacts use. Each artifact still defines a term on first use; this page is the reference those definitions follow. Arras's own terms are defined by the contracts named in the last column.

## External systems and standards

| Term | Meaning | Owner |
| --- | --- | --- |
| ASGI | Asynchronous Server Gateway Interface, the Python standard for asynchronous web applications. | Python community |
| Ashlar | Toolkit for property-graph ontologies on a warehouse. In Arras its adapter is a reader (used as a replica): it holds the full ontology on Unity Catalog and is fed from the providers' stores. | DocumentDrivenDX |
| Databricks | The platform providing Lakebase, Unity Catalog and optional Apps hosting for an embedding application. | Databricks |
| Delta Lake | Table format on which Ashlar publishes its gold tables. A gold table is a curated table. | Open source |
| GraphQL, GraphiQL | GraphQL is an API query language. GraphiQL is the in-browser explorer that the admin console serves. | GraphQL Foundation |
| Lakebase | Databricks' managed Postgres. Arras's required deployment target for Truss, PostgreSQL 18.6. | Databricks |
| MCP | Model Context Protocol, an open protocol through which agents call tools. Arras's MCP server uses the stdio transport. | Anthropic |
| psycopg | The Python PostgreSQL driver Arras uses (version 3). | Open source |
| stdio | The standard input and output streams of a process. They carry the MCP messages. | |
| Truss | Open-source, UMF-driven property-graph engine on SQL databases. In Arras its adapter is a reader and provider: the hot, mutable store, deployed on Lakebase (Arras's required target). | DocumentDrivenDX |
| UMF | The metamodel that defines Arras's types and actions. | DocumentDrivenDX |
| Unity Catalog | Databricks' governance layer for tables and access. Ashlar publishes on it and enforces the caller's access through it. | Databricks |
| Weft | The SQL project that owns the language Arras's `query` takes. A backend, not Arras, hands the statement to Weft (Truss through its Weft compiler boundary). | DocumentDrivenDX |

## Host and platform

| Term | Meaning |
| --- | --- |

## Arras terms

| Term | Meaning | Defined in |
| --- | --- | --- |
| ADR | Architecture decision record. | `02-design/adr/` |
| Backend | A named store the host configures, with the roles `reader` (serves graph reads) and/or `provider` (applies actions). | CONTRACT-004 |
| Record store | A module's reader that is the system of record for its graph; it serves `latest`. | CONTRACT-002 |
| Provider | A backend that applies actions (and imports, and keeps the journal). A module's actions run on the provider its placement names, the record store by default. | CONTRACT-004 |
| Replica | A reader other than the module's record store that the placement lists; it serves `bulk` and may lag. | CONTRACT-002 |
| Memory adapter | The in-memory reader and provider (`memory`) and reader (`memory_replica`) that ship in the library, for tests, the sandbox and the dev host. | CONTRACT-004 |
| Consistency level | What a read asks for: `latest` (as new as the record store) or `bulk` (a replica's position is acceptable). | CONTRACT-001 |
| Freshness | The backend that served an answer, its position (`as_of`) and the consistency level. Every answer carries it. | CONTRACT-001 |
| Host | The Python application that embeds Arras and registers its backends under names it chooses, places each module and supplies each backend's connection source. | CONTRACT-005 |
| Module | A named set of UMF types and actions, placed by the host on one record store. | CONTRACT-002 |
| Principal | The person a call is made for, with that person's token. Arras keeps no service identity for reads or actions. | CONTRACT-001, ADR-017 |
| Receipt | What an action returns: its outcome, the journal entry and a position a later read can ask to be at least as new as. | CONTRACT-003 |
| Journal | The record of every applied action, attributed to a person. | CONTRACT-003 |
| Idempotency key | A caller-supplied key that makes repeating an action change nothing. | CONTRACT-003 |
| Placement | The host's configuration of a module: its record store, its replicas and the provider of each action. The UMF document carries none. | CONTRACT-002 |
| P0, P1, P2 | Must Have, Should Have and Nice to Have priorities of the PRD. | `01-frame/prd.md` |
| p95 | The 95th-percentile latency: 95 percent of calls finish at or under it. | `01-frame/prd.md` |
