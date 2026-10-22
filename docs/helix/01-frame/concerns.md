---
ddx:
  id: concerns
  type: concerns
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: ADR-005
      kind: constrained_by
    - id: ADR-006
      kind: informed_by
    - id: ADR-009
      kind: informed_by
    - id: ADR-010
      kind: informed_by
    - id: ADR-013
      kind: informed_by
    - id: ADR-018
      kind: informed_by
    - id: ADR-019
      kind: informed_by
    - id: ADR-020
      kind: informed_by
    - id: TD-001
      kind: informed_by
---

# Project Concerns: Arras

**Owner**: Erik LaBianca
**Status**: Draft. Slot rows marked *Assumption* await confirmation.

Project Concerns declare active cross-cutting context for downstream work. They
are not principles, requirements, ADRs, test plans, or implementation tasks.

**Scope.** Arras is the interface through which an organization's applications read and
change the ontology, embedded as a Python library in a host application
(first, praxis, an agent-harness Databricks app). It defines no storage of
its own. Backends are named stores with the roles reader and provider, and a host
configures any number of them. In production a Truss adapter (reader and provider) serves the
mutable modules on Lakebase (Databricks managed Postgres), and an Ashlar adapter (a
reader) serves the full ontology on Unity Catalog (Databricks' governance layer for
data); a memory adapter ships for tests and the sandbox. Truss is an open-source property-graph
engine on SQL databases; Ashlar is an open-source toolkit for property-graph
ontologies on a warehouse (ADR-013; ADR: architecture decision record). Types and
actions are defined in UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions). Agents reach the interface through an MCP
server (MCP, the Model Context Protocol, is Anthropic's open protocol for agent
tools). Arras holds no structure derived from sensitive source records at this time. The [PRD](prd.md) carries the requirements. The fixed constraints below are
project decisions; the rest is derived from the ADRs and spikes
cited per row.

## Fixed platform constraints

| Constraint | Value | Source | Recorded authority |
|---|---|---|---|
| Deployment target | **Databricks Apps** (Databricks' hosting for web applications), embedded in the praxis app | Project decision | [ADR-006](../02-design/adr/ADR-006-embedded-library-on-psycopg-and-the-truss-toolkit.md) |
| Record store (production) | **Lakebase** (managed Postgres), running Truss | Project decision | [ADR-012](../02-design/adr/ADR-012-own-postgres-database-lakebase-deployed-embedded-locally.md); [ADR-013](../02-design/adr/ADR-013-arras-is-an-ontology-interface-over-named-backends.md) |
| Replica store (production) | **Unity Catalog** gold Delta tables, running Ashlar | Project decision | ADR-013 |
| Type and action definitions | **UMF** | Project decision | ADR-013, ADR-015 |
| Backend language | **Python 3.11** with `uv` (a Python package manager), matching the host | Project decision | [ADR-010](../02-design/adr/ADR-010-python-and-uv-as-the-arras-toolchain.md) |
| Database access | **psycopg 3** (the PostgreSQL driver for Python) and the **truss-toolkit** installer for the Truss adapter; Arras keeps no migration history of its own | Project decision | ADR-006 |

## Scale target

- The ontology as a whole may reach **~1 billion entities**, with large volumes of
  typed metadata on entities and relationships alike. That scale lives in Ashlar.
- The mutable modules in Truss are far smaller. Truss's measured size is 200,000
  objects and 400,000 edges in an early benchmark on a local PostgreSQL.
- No benchmark at either scale exists through this interface. Every operation is
  bounded so no client can ask a backend for an unbounded answer.

## The gate: ADR-005

[ADR-005](../02-design/adr/ADR-005-durable-knowledge-state.md) defers durable
structure over sensitive source records until a named workload, an entitlement rule
and a governed write path exist. Arras stays clear of it by holding no structure
derived from sensitive source records. The entitlement read that a host would
need is drafted as an interaction and blocked on that gate. Adding either reopens
ADR-005's preconditions P1 to P3.

## Active Concerns

| Concern | Source | Areas | Why Active | Key Practices |
|---------|--------|-------|------------|---------------|
| `databricks-apps` | library | `area:infra` | Deployment target is fixed; Arras ships inside the praxis app | `pyproject.toml` + `uv.lock` only, never `requirements.txt` (ADR-010). The signed-in user's token supplies every backend connection (ADR-017); the app's service principal is only the named administrative principal for registration, attachment and imports; install and upgrade run on the host's installing connection, which is not a person's identity. |
| `python-uv` | library | all | Backend is Python; fills the `language-runtime` slot | Python 3.11 pinned per project, `uv` with a committed `uv.lock`, one isolated `.venv` per implementation, `ruff` (linter and formatter), `pyright` (type checker). |
| `typescript-biome` | library | `area:interface` | The Operator Console (`ui/`) is handwritten TypeScript and had only the type checker | `tsc` (type checker) and Biome (linter and formatter, `ui/biome.jsonc`) as one CI step, `npm run check`; the same rules for source and tests, every rule on and no suppression comments: a finding is fixed in the code. |
| `lakebase-postgres` | project-local | `area:data` | The hot store is fixed; fills the `datastore` slot, which has no library member | Truss's database is Arras's own, in a Lakebase project of its own, separate from praxis's (ADR-012). PostgreSQL 18.6 locally and in CI through `pgserver-pg18` (a test-only dependency group). |
| `unity-catalog` | library | `area:data`, `area:infra` | The warehouse store; reads on behalf of the user | Row and column policy applies to the user's own access; Arras never substitutes a service identity for a user's read. |
| `umf-fidelity` | project-local | `area:registry`, `area:actions` | Types and actions are UMF; meaning is never silently lost | Documents stored verbatim by the record store and read back unchanged (`Ontology.document`, the explorer catalog); unsupported constructs refused and named, never accepted silently; reader agrees with the reference validator on shared fixtures. |
| `interface-honesty` | project-local | `area:interface` | One interface over a fresh and a replicated store can mislead | Every read states its consistency level and freshness; capabilities are declared and never synthesized; no silent fallback (ADR-014). |
| `admin-console` | library | `area:interface` | An operator-facing UI over mutable domain objects (FEAT-010): administrators and module builders browse the schema, read data, invoke declared actions and read audit | The primary operator workflow (find a type, run a declared correction, read the attributed change) runs green through the UI in a whole-stack test; no write except a declared action; the viewer's own token on every call (ADR-021, CONTRACT-009). |
| `mcp-server` | project-local | `area:interface` | Praxis reaches Arras only through a local stdio MCP server (ADR-016) | One tool per declared action so the host catalog classifies each; one process per person; stdout carries only protocol frames; compact answers and instructive refusals (CONTRACT-007). |
| `authorization-model` | library | `area:access` | Access is the backends' own: database roles per module on Truss, the user's own access on Unity Catalog | Every backend call carries the user's own token (ADR-017); Arras keeps no access decision, no role map and caches nothing; the change record names the authenticated person. |
| `o11y-otel` | library | all | Arras is a library inside a host app and a stdio process; what a read was, which backend served it and why one went down must be visible without Arras owning a sink. Applicable sections: service signals (operations and backend transitions, as events and spans) and agent diagnostics (stderr only for the MCP process); frontend, data-job and GenAI sections do not apply | Named events with allowlisted attributes, emitted once to the host's logger and tracer provider; the OTel API is an optional extra; trace continues over MCP `_meta.traceparent`; never stdout; telemetry never fails an operation (ADR-018, CONTRACT-008). |
| `modularity-and-encapsulation` | library | all | Handwritten source; the host seam was checked but the library's own module rules were not | A Module Boundaries map in the architecture, one checker (`tests/test_modules.py`) with forbidden-edge controls, no cycles, integration owners named, construction in one place per process. |
| `code-shape-ceilings` | library | all | Several modules grew past 900 lines | Complexity ceiling in the lint and a module-length ceiling in the module test, each at today's worst value and lowered, never raised. Python: ruff C901 and `tests/test_modules.py`; TypeScript: Biome's cognitive-complexity rule and `ui/src/test/code-shape.test.ts`. |
| `twelve-factor` | library | `area:interface`, `area:infra` | Applies to the MCP process only: the library takes parameters and praxis owns its own deployment | Config in three layers by owner (ops-injected environment and ops file, a committed per-environment TOML file, committed defaults), read once into one typed object, one owner per key, fail fast naming the file and key; no credential or ops handle committed (`.env.example` lists environment keys only); logs to stderr; disposable process: fast start and SIGTERM/SIGINT finish the frame in flight and exit 0 (ADR-019). |
| `testing` and `verification` | library | all | The interface's strongest promises are rules over sequences, and a library has no running stack to exercise | Property-based tests (`hypothesis`) against an executable model, validated by breaking the fakes; evidence for a change is the suite plus the checks named in CI (ADR-020). |
| `formal-methods` | library | `area:interface`, `area:actions`, `area:data` | Selected for one slice: action invocation and consistency-level reads. Correctness depends on interacting keys, failures, batches, feeds and outages, and a wrong answer misleads every client. Owner Erik LaBianca. Level: precise specification with a randomized check of the implementation against an executable model; not an exhaustive analysis. Unaffected slices (the memory adapter's statement reader and the UMF reader, console, MCP binding, telemetry, configuration) record why no analysis applies in [TD-001](../02-design/TD-001-contract-rules-formal-specification.md) | Properties with stable IDs derived from the contracts (TD-001 P1 to P9); state, transitions, assumptions and bounds recorded; reachable witnesses and negative controls; model-to-code correspondence and residual gaps recorded. Exhaustive analysis (TLA+, Alloy or a state explorer) waits for the Truss adapter's transaction design (ADR-020). |

The generic storage concerns (`relational-data-modeling`, the layout, journal and
feed) are each store's, not Arras's.

## Slot resolution

| Slot | Filler | Source | Authority |
|---|---|---|---|
| `deploy-target` | `databricks-apps` | Project decision | ADR-006 |
| `language-runtime` | `python-uv` | Project decision | ADR-010 |
| `datastore` | `lakebase-postgres` (project-local) for the hot store; Unity Catalog for the warehouse | Project decision | ADR-012, ADR-013 |
| `auth-provider` | The backends' own: Postgres role grants (Truss), Unity Catalog grants (Ashlar), with the host supplying the person's own token (ADR-017) | Project decision | ADR-006, ADR-013 |
| `frontend-framework` | React with TypeScript, Vite, Tailwind and TanStack Query, matching praxis, in the `ui/` package `arras-ui` for the Operator Console (FEAT-010). The read-only console (FEAT-007) and the Python package keep no frontend framework: a GraphiQL page only (GraphiQL is an in-browser GraphQL explorer). | Project decision | PRD (Operator Console); ADR-021 (proposed); ADR-011 |
| `e2e-framework` | None for the library; host-level startup and integration tests. For `arras-ui`, a whole-stack tool is selected at build (the `admin-console` concern requires the primary operator workflow to run green through the UI). | Assumption | PRD acceptance sketches; ADR-021 |
| `architecture-style` | An interface with a backend contract and adapters, driven by the host (ports and adapters) | Project decision | ADR-013 |

## Project Overrides

| Concern | Practice | Override | Authority |
|---------|----------|----------|-----------|
| `python-uv` | Python 3.12+ | Python 3.11, to match the praxis host (`requires-python >=3.11`) | ADR-010 |
| `python-uv`, `databricks-apps` | Dependency manifest | `pyproject.toml` + `uv.lock` only. A `requirements.txt` must never exist in an app directory: on Databricks Apps it takes precedence, switches the install to pip and the interpreter to a different version. | ADR-010 |
| `databricks-apps` | App service principal as the shared identity | None at runtime: every backend call uses the signed-in user's token; the service principal serves only as the named administrative principal for registration, attachment and import; install and upgrade run on the host's installing connection, which is not a person's identity | ADR-006; ADR-017 |
| `o11y-otel` | OpenTelemetry SDK, collector and log files | None owned by Arras: it emits to the host's logger and tracer provider and the OTel API is an optional extra | ADR-018 |
| `twelve-factor` | Config in the environment, three layers | All three layers are in use: ops-injected (environment and the ops file), `config/<env>.toml` and `config/default.toml`. Developer-owned values (placement, log level, user claims) are committed files; handles and the token are never committed | ADR-019 |
| `formal-methods` | Rigor per slice | Precise specification plus randomized checks for the contract-rules slice only; no analyzer is required elsewhere | TD-001; ADR-020 |

## Area Labels

- `area:interface`: the ontology interface and its consistency model
- `area:registry`: UMF documents, the host's placement, capabilities
- `area:actions`: action declarations, invocation, import
- `area:data`: the Truss and Ashlar adapters, migrations of the Truss layout
- `area:access`: the user's token and the backends' controls
- `area:ui`: the minimal read-only administration console
- `area:infra`: Databricks Apps hosting, the app's database resource, role grants, compute sizing, branches

## Concern Conflicts

| Conflict | Resolution |
|----------|------------|
| One interface vs. stores of different freshness | Consistency level and freshness on every read; capability descriptors; no silent fallback (ADR-014) |
| `python-uv` vs. the `pgserver-pg18` test dependency | None: its wheels cover Python 3.11 to 3.13 on manylinux and macOS 14 arm64, so the Truss-marked suite runs on 3.11 |
| Library startup vs. a shared host app | Arras's connection and migration attempts are bounded, and a failing backend leaves the host running (ADR-006) |
| Backend-enforced access vs. a later need for finer entitlement | Writes go only through actions, so an entitlement check can be added in one place without touching callers |

## Open design questions

| # | Question | State | Next artifact |
|---|----------|-------|---------------|
| 1 | The ontology interface and backend contract | Specified in CONTRACT-001 to CONTRACT-004 from twelve client interactions; validation needs a backend corpus that both adapters pass | Backend corpus |
| 2 | Was a Lakebase project named `ontology` ever applied in the workspace? | Open. If so it is deleted by hand and its data dropped (ADR-012); the landing zone already uses `arras` | Platform owner |
| 3 | Role names and grants per module, and who provisions them | Open | Platform repo; ADR |
| 4 | How praxis hands a user's token, and its refresh, to the stdio MCP process | Proposed: a token file the process re-reads (CONTRACT-007) | Host ADR |
| 5 | Admin console data surface | Proposed: read-only GraphQL generated from the registry, GraphiQL explorer ([ADR-011](../02-design/adr/ADR-011-read-only-graphql-generated-from-the-type-registry.md)) | Accept ADR-011 |
| 6 | Synchronous or asynchronous library interface | v1 is synchronous (CONTRACT-001); the host owner's view is open | Host ADR |
| 7 | UMF's action contract | Requested of UMF; Arras uses a minimal subset meanwhile, and placement is host configuration, not part of the document | UMF |
| 8 | Truss-to-Ashlar feed lag, and Ashlar's publication semantics | Requested of Truss and Ashlar; unmeasured | Measurement through a real publisher |
| 9 | Does Arras wait for a replica to reach a receipt's token, or only report it? | Open | CONTRACT-001 |
| 10 | Truss module isolation by role membership, since users connect as themselves | To raise on Truss as a generic requirement | Truss |
| 11 | Weft (the SQL project that owns the language `query` takes, DocumentDrivenDX/weft) read profiles for whole-entity reads (`alias.*` with appended fact columns, `RELATED_KEYS`), relationship predicates (`HAS_RELATED`), keyset paging, `COUNT(*) GROUP BY` and joins, qualified and hosted by Truss and Ashlar | Requested of Weft, Truss and Ashlar; each shape waits until a backend declares its profile | Weft, Truss, Ashlar |
