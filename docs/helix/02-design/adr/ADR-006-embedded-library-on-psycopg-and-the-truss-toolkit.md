---
ddx:
  id: ADR-006
  type: adr
  status: accepted
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
---

# ADR-006: Arras is an embeddable Python library on psycopg 3 and the Truss toolkit

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-04 | Accepted | Erik LaBianca (architecture lead) | [ADR-010](ADR-010-python-and-uv-as-the-arras-toolchain.md), [PRD](../../01-frame/prd.md) | Medium |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | Arras is the interface to an ontology. It has a Truss adapter (Truss is an open-source, UMF-driven property-graph engine on SQL databases, owner DocumentDrivenDX) on Lakebase (Databricks managed Postgres) and an Ashlar adapter (Ashlar is an open-source toolkit for property-graph ontologies on a warehouse, owner DocumentDrivenDX) on Unity Catalog (Databricks' governance layer for data). UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions) declares the types. Arras's first host is praxis, an agent-harness Databricks app, which embeds Arras and runs no second app. The data layer, the way the store is installed and the packaging shape must fit that host. |
| Current State | Databricks Apps hosting, Lakebase and Python are fixed. Praxis already uses psycopg 3 (the PostgreSQL driver for Python) for its data path (praxis ADR-028, held in the praxis-harness repository). Truss ships a public Python toolkit that installs its own store, applies actions and answers reads inside a transaction the caller begins on a connection the caller owns, and that toolkit qualifies one driver tuple (psycopg 3.3.6, PostgreSQL 18.6). Praxis requires Python 3.11 or later and keeps `psycopg` out of its core (praxis ADR-004, same repository). |
| Requirements | Run inside a host Python application with host-supplied connection settings. Install or verify its store through Truss's installer, keeping no migration history. Reach Lakebase, pooled or direct (praxis connects direct). Report each backend unavailable, with a reason, when it is not usable, without stopping the host. Leave end-user screens and the host's own API surface to the host. Arras's only UI is a minimal read-only administration console (PRD, Admin Console). |
| Decision Drivers | One database driver across the host and the library avoids two drivers and two pools in one process, and the store's installer and layout are Truss's, not Arras's. Embedding rules out a library-owned service; the only UI is a small console the host mounts. |

## Decision

We will build Arras as a **Python library**, with **psycopg 3** connections the host supplies, one per person, over which the Truss adapter calls **Truss's public toolkit** (`truss-toolkit`). The adapter composes no SQL: Truss owns the store's SQL, its layout, its installer and its upgrade, and the adapter installs an absent Truss or verifies a present one through the toolkit, on a separate trusted installing connection. The Ashlar adapter reaches Unity Catalog through a Databricks SQL warehouse, which this decision leaves to its own record. The host app supplies connection settings and the installing connection, calls install-or-verify on request, and exposes whatever API or end-user screens it needs. Arras owns no end-user API or screens; its administration console and the data surface behind it are decided in [ADR-011](ADR-011-read-only-graphql-generated-from-the-type-registry.md).

**Key Points**: Connection settings come from the host, never from ambient `PG*` variables | Each person's calls run on a connection authenticated as that person, which the host owns and pools | Arras keeps no migration history, schema or version table: install-or-verify is Truss's installer behind an advisory lock taken in the install transaction, so concurrent `migrate()` calls run one install, and `start` does not install, and an upgrade is a separate explicit call (CONTRACT-005) | The installing connection is trusted, separate from every person's, and never serves a read, an action or a registration | Arras calls only Truss's public toolkit and imports nothing private to it | The adapter composes no SQL and builds nothing by string interpolation | The base install requires no Truss or psycopg; the adapter is an optional extra | Arras has its own database, separate from the host's (ADR-012) | Arras imports nothing from the host and the host imports only Arras's public interface, with a check that fails the build on a violation | A standalone service is a thin wrapper around the same library, added when a second host needs it

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| FastAPI service owning the API and Pydantic schemas | Matches Databricks' reference architecture for Lakebase; auto-generated OpenAPI | A second app to deploy; Arras would own a surface the host already owns; async stack differs from the host's data path | Rejected: wrong shape for an embedded library |
| asyncpg for the data path | Fast async driver | A second driver beside the host's psycopg; a different pooling model in one process | Rejected: two drivers in one process |
| SQLAlchemy ORM for the data path | Mature mapping layer | Mapping overhead and typing friction on a generic graph; the host's ADR-028 already rejected it for the data path | Rejected |
| Arras's own SQL and migration tool for the Truss layout | Full control of the layout | Duplicates Truss's installer and layout, and drifts from the store Truss qualifies | Rejected: Truss owns its store, and the adapter calls its installer |
| **Library on psycopg 3 and the Truss toolkit** | Same driver as the host; one pool; the store and its installer are Truss's; embeds without a second app | The public interface is a Python binding, so a host in another language needs another binding | **Selected** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | Praxis deploys Arras inside its own app with no extra service. The host's pooling and identity conventions apply unchanged. |
| Negative | Arras's startup and install-or-verify run inside the host's startup path, so a failure there can affect a shared app. Bounded handling (see Validation) is a requirement. |
| Negative | Truss qualifies one driver tuple (psycopg 3.3.6, libpq 18.6, PostgreSQL 18.6), so the host aligns its driver with it. |
| Neutral | A REST surface is the host's decision. The MCP (Model Context Protocol, Anthropic's open protocol for agent tools) binding is decided in [ADR-016](ADR-016-mcp-stdio-binding-over-the-library.md). |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| Slow or failing database delays host startup | M | H | Bounded connection and install attempts; tests for each failure case |
| Two instances install at once | M | M | Advisory lock taken in the install transaction before the status read; test with two concurrent `migrate()` calls |
| The library reads the wrong database once the host has its own | M | H | Host-supplied settings only; a test fails if Arras falls back to default variables |
| A poisoned connection is reused | L | H | Arras closes a connection Truss quarantines and the host's pool discards it (CONTRACT-005) |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| Praxis starts and serves with Arras embedded, and still serves when the Arras database is unconfigured, unreachable, denied or fails to install | Any host startup failure attributable to Arras |
| One install under two concurrent `migrate()` calls | Two installs observed |
| The boundary check fails the build on an import in either direction | A violation merges |

## Concern Impact

- **Concern selection**: Recorded in [`../../01-frame/concerns.md`](../../01-frame/concerns.md): `python-uv`, `databricks-apps`, `lakebase-postgres`.
- **Practice override**: None.

## References

- [Databricks Lakebase Postgres docs](https://docs.databricks.com/aws/en/oltp/projects/)
- ADR-028 (sessions in Postgres, psycopg conventions) and ADR-004 (ports and adapters), both in the praxis-harness repository
