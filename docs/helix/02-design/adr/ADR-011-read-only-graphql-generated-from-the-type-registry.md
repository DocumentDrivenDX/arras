---
ddx:
  id: ADR-011
  type: adr
  activity: design
  status: accepted
  owner: Erik LaBianca
  updated: 2026-10-04
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: FEAT-007
      kind: informed_by
    - id: ADR-006
      kind: informed_by
    - id: SPIKE-002
      kind: informed_by
    - id: CONTRACT-006
      kind: informs
---

# ADR-011: A read-only GraphQL surface, generated from the type registry, built on graphql-core

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-04 | Accepted | Erik LaBianca (architecture lead) | [ADR-006](ADR-006-embedded-library-on-psycopg-and-the-truss-toolkit.md), [PRD](../../01-frame/prd.md), [FEAT-007](../../01-frame/features/FEAT-007-admin-console.md), [SPIKE-002](../spikes/SPIKE-002-how-the-field-exposes-an-ontology.md) | Medium |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | The admin console (FEAT-007) needs a data surface that lets an administrator browse modules, their declared types and the entries of each type, in the style of GraphiQL (a browser-based GraphQL schema browser and query editor), and it must perform no write (FR-37 in the PRD). Arras is the interface to an ontology, a Python library embedded in the praxis Databricks app (praxis is an agent-harness app). Its types are declared at runtime in UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions) documents, one per module, so the surface must follow the registry without code changes. GraphQL is a query language for APIs; graphql-core is the reference Python implementation. |
| Current State | SPIKE-002 (Finding 5) records REST with OpenAPI (a machine-readable REST API description) as the default for applications and GraphQL as suited to a complex internal data graph; Hasura and OntoBricks are the prior art for GraphQL over Postgres. ADR-006 makes Arras a library on psycopg 3 (the PostgreSQL driver for Python) and leaves the console's data surface to this decision. |
| Requirements | Browse by type; read-only by construction; follow runtime type declarations; run inside a host Python app (praxis, Python 3.11, FastAPI/Starlette) and standalone; enforce the viewer's own access (FR-28); bound every list (CONTRACT-006). |
| Decision Drivers | The registry already declares entity types, relationships, properties, actions and placement, which is the information a GraphQL schema needs. GraphiQL gives a schema browser and query editor with no UI of our own. A library cannot own a separate service. |

## Decision

We will expose a **read-only GraphQL surface** generated at runtime from each module's type registry, implemented directly on **graphql-core** with a thin ASGI (Python's asynchronous web-server interface) handler, and explored through a **GraphiQL** page. The surface has no Mutation or Subscription type. Writes, and all host integration, go through the Python library interface (CONTRACT-001); this GraphQL surface carries neither. The operator console's action and audit endpoints are a separate HTTP surface decided in ADR-021 (CONTRACT-009).

**Key Points**: One generated schema per module plus one small meta schema that lists modules and their types (CONTRACT-006) | The schema is rebuilt when a module's registry version changes | Type and property names are constrained to valid GraphQL names at declaration time (CONTRACT-002) | Every list field is bounded, with a maximum limit and a truncation flag; query depth is capped | The host maps its signed-in viewer to a `Principal` (CONTRACT-006); each request reads through the interface with the viewer's own token, so the backends decide what the viewer sees| GraphiQL is loaded as pinned assets, with an option to serve them from the host's own origin | Agent exposure is the MCP (Model Context Protocol) binding of ADR-016, and this surface does not preclude it

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| REST/OpenAPI generated from the registry | The SPIKE-002 default for applications; broad tooling | Needs a hand-built UI for schema and entry browsing; one endpoint per type and relationship; no free explorer | Rejected for the console: GraphiQL is the stated goal |
| Ariadne (schema-first) | Ships an ASGI app and GraphiQL page; mature | Its current release (1.1.0) fails to import against graphql-core 3.3.0, which a plain install resolves to (observed 2026-10-04: `ExecutionContext` import error), so it needs a pin below 3.3; adds Starlette as a dependency; schema-first means generating SDL text from the registry | Rejected: more moving parts for what graphql-core already does |
| Strawberry (code-first) | Typed Python classes; supports graphql-core 3.3 | Types are Python classes defined at import time; building them dynamically from a runtime registry fights the library | Rejected: wrong shape for runtime types |
| Graphene | Long-standing | Pins graphql-core below 3.3; code-first like Strawberry | Rejected: same shape problem, older core |
| Hasura or PostGraphile (products that generate a GraphQL API over Postgres) as a separate service | Generates GraphQL over Postgres tables | A second service to deploy, contradicting embedding (ADR-006); exposes tables where Arras has registry types; its permissions model is separate from the backends' own access control (ADR-017) | Rejected: breaks embedding |
| GraphQL with mutations | One surface for reads and writes | Violates FR-37 structurally; a second write path beside the library | Rejected |
| **graphql-core directly, read-only, registry-generated** | The core library the Python GraphQL frameworks use; builds a schema programmatically from the registry at runtime; synchronous execution fits psycopg; no framework dependency beyond a small ASGI handler | We write the handler, depth limit and page types ourselves | **Selected** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | The console needs no UI beyond GraphiQL. A new module is browsable the moment its types are registered. The absence of a Mutation type enforces FR-37 in the schema itself. |
| Negative | Arras depends on graphql-core (3.3.x, read 2026-10-04) and a GraphiQL asset source. Names are constrained, which limits what a module can call a type. A generated schema per module is rebuilt on version change. |
| Neutral | A GraphQL surface for agents or applications is possible later by mounting the same handler in a host. Agents use the MCP binding (ADR-016). |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| The GraphiQL page loads its assets from a public CDN (the common default, and what Ariadne's page does with esm.sh), and the Databricks Apps network or content policy blocks it | M | M | Pin asset versions; support a host-served asset base; verify on a deployed app before relying on it |
| Deep or wide queries load the database | M | M | Maximum page size 100, depth cap 6, no unbounded lists; reject over-limit queries with a stated code |
| graphql-core's 3.3 line changes API before a stable pin | L | M | Pin a compatible range; contract tests run the generated schema in CI |
| Mounting the console in praxis crosses its ports-and-adapters rule that the HTTP adapter does not call a driven adapter directly (praxis ADR-004), and `principal_for_request` hands the viewer's own token to the library, which is an identity decision in that adapter | H | M | Record the exception in a praxis ADR before mounting; keep the mapping in one reviewed function |
| Generated names collide or are invalid | M | L | Declaration-time validation refuses invalid or colliding names (CONTRACT-002) |
| Introspection exposes type names to a viewer | L | L | Viewers already hold read access to that module; unreadable modules are absent |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| The console opens in GraphiQL on the praxis app and standalone, lists readable modules, and browses the catalog by type | The page fails to load its assets on Databricks Apps |
| A schema-introspection test finds no Mutation or Subscription type for any module | One appears |
| Over-limit queries are refused and the database sees only bounded reads | A query returns an unbounded list |
| Schema generation from the catalog's six types completes and answers a page and an entry detail within 1 second at p95 | The generated schema misses the console's latency target |

## Concern Impact

- **Concern selection**: Fills no library concern slot. This read-only console and the Python package keep no frontend framework; GraphiQL is a third-party page. The `frontend-framework` slot is filled by ADR-021 for the separate `arras-ui` package. Recorded in [`../../01-frame/concerns.md`](../../01-frame/concerns.md).
- **Practice override**: None.

## References

- [SPIKE-002](../spikes/SPIKE-002-how-the-field-exposes-an-ontology.md) Finding 5: REST/OpenAPI default for applications; GraphQL for complex internal graphs
- Hasura and OntoBricks as prior art for GraphQL over Postgres
- PyPI package metadata read 2026-10-04: graphql-core 3.3.0 (Python ≥ 3.10), ariadne 1.1.0, strawberry-graphql 0.331.1 (requires graphql-core ≥ 3.3.0, < 3.4.0), graphene 3.4.3 (requires graphql-core < 3.3)
- Ariadne 1.1.0 explorer templates, inspected 2026-10-04: GraphiQL assets load from `esm.sh`
- [CONTRACT-006](../contracts/CONTRACT-006-console-graphql-surface.md), [CONTRACT-002](../contracts/CONTRACT-002-type-registry-and-placement.md)
