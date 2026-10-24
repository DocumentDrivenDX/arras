---
ddx:
  id: TP-001
  type: test-plan
  activity: test
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-23
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: concerns
      kind: informed_by
    - id: architecture
      kind: informed_by
    - id: FEAT-001
      kind: informed_by
    - id: FEAT-002
      kind: informed_by
    - id: FEAT-003
      kind: informed_by
    - id: FEAT-004
      kind: informed_by
    - id: FEAT-005
      kind: informed_by
    - id: FEAT-006
      kind: informed_by
    - id: FEAT-007
      kind: informed_by
    - id: FEAT-008
      kind: informed_by
    - id: FEAT-009
      kind: informed_by
    - id: CONTRACT-001
      kind: informed_by
    - id: CONTRACT-002
      kind: informed_by
    - id: CONTRACT-003
      kind: informed_by
    - id: CONTRACT-004
      kind: informed_by
    - id: CONTRACT-005
      kind: informed_by
    - id: CONTRACT-006
      kind: informed_by
    - id: CONTRACT-007
      kind: informed_by
    - id: CONTRACT-008
      kind: informed_by
    - id: ADR-018
      kind: informed_by
    - id: ADR-019
      kind: informed_by
    - id: ADR-012
      kind: informed_by
    - id: TD-001
      kind: informed_by
---

# Test Plan

## Testing Strategy

**Goals**: Show that every read states its freshness, every change is a declared, atomic, attributed action, every backend call is made with the person's own token, and the catalog meets its latency targets inside the host. Quality gates are in Build Handoff.

The repository holds no test code, conformance corpus or benchmark harness yet. This plan states what must be built and what each part proves; it makes no claim that any test exists or passes.

Arras is the interface through which an organization's applications read and change the ontology. It is a Python library embedded in a host app such as a workflow application (a Databricks app) over named backends; in production Truss (an open-source property-graph engine on Lakebase, Databricks' managed Postgres) and Ashlar (an open-source toolkit for property-graph ontologies on Unity Catalog, Databricks' governance layer for tables and access). Types and actions are defined in UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions). MCP is the Model Context Protocol, Anthropic's open protocol for agent tools. ADR means architecture decision record; p95 is the 95th-percentile latency.

**Out of Scope**:

- The internals of Truss, Ashlar and UMF, which their own corpora and fixtures cover (ADR-013).
- The clients' own screens and business logic (FEAT-008).
- Structure derived from sensitive source records, which Arras does not hold (ADR-005).
- Throughput and capacity at Ashlar's scale of about a billion entities; no benchmark at that scale is planned in the sources.
- Penetration testing, vulnerability assessment and dependency scanning; no requirement is recorded.

**Traceability Source**: the PRD (FR-1 to FR-51 and the acceptance test sketches), FEAT-001 to FEAT-009, the user stories US-001 to US-059 and their acceptance criteria (`US-<n>-AC<m>`), CONTRACT-001 to CONTRACT-007.

### Test Levels

| Level | What it proves | Coverage Target | Priority |
|-------|----------------|-----------------|----------|
| Contract | An adapter implements the backend contract, and the interface honors its contract, independent of any store: every read states freshness; `latest` never comes from a replica; empty, `Refused` and `Unavailable` stay distinct; actions are atomic, idempotent and attributed; a call without a token or with another person's token is refused | Every operation and error in CONTRACT-001, CONTRACT-003 and CONTRACT-004, through the shared conformance corpus; 100% of read operations tested for freshness (PRD) | P0 |
| Integration | Arras works against a real PostgreSQL 18.6 with Truss: install-or-verify through Truss's own install, the registry accepts UMF documents, startup and availability behave per CONTRACT-005, the MCP process and the console behave per CONTRACT-006 and CONTRACT-007 | Each failure case of CONTRACT-005 (not configured, unreachable, access denied, migration failed, unsupported version); each fixed MCP tool; each console endpoint and status code | P0 (console P1) |
| Unit | Pure logic is correct without a database: the statement hand-off, bound checks, name rules, effect resolution, receipt and token handling, MCP schema and annotation derivation | Each construct and bound named in CONTRACT-001 and CONTRACT-002; each effect and precondition form in CONTRACT-003 | P0 |
| Performance | The catalog meets its latency targets through the host path | The four targets of US-044: singleton read, action, type enumeration, 30-record list | P0 |
| E2E | The catalog, the inventory and a workflow client work through the interface inside the host: seed import, browse, correct, read your write, degraded startup | The PRD acceptance sketches that need the host (see below) | P0 |
| Contract (operate) | `arras.operate` honors CONTRACT-009's tables: status codes, origin and preflight rules, error scrubbing, the one-write-path rule, `expected_revision`, `Receipt.group`, `changes` and `loads` (each naming a provider: `test_operate_audit::test_audit_routes_accept_a_provider`); the executable model (ADR-020) holds the audit and group rules. The published OpenAPI document is checked against the answers the real app gives (`tests/test_openapi_contract.py`), the typed-input rules against the vectors the UI shares (`tests/vectors/inputs.json`), and the dev host is run under `uvicorn` on a loopback socket and called over real HTTP (`tests/test_devhost_server.py`, skipped where `uvicorn` is not installed) | Every row of CONTRACT-009's tables | P1 |
| UI | `arras-ui` components and the whole-stack operator workflow (find a type, run a declared correction, see the attributed change) against the dev host | Each US-060 to US-078 criterion | P1 |
| Contract (schema) | `arras.operate.create_schema_app` honors CONTRACT-011's tables (status codes, `authorize_schema`, `expected_revision`, the scrubbed error body, absence when not mounted), and `session.schema()` honors CONTRACT-002's `validate` and `register` | US-073 and US-074 | P1 |

The PRD priorities are P0 (must have), P1 (should have) and P2 (nice to have). P2 items (a GraphQL read binding for other clients, external vocabularies, action compensation) have no tests planned.

### Frameworks

| Type | Framework | Reason |
|------|-----------|--------|
| Unit, Contract, Integration | `pytest`, with `ruff` and `pyright` as gates | ADR-010 names them as the toolchain |
| Contract (rules over sequences) | `hypothesis` stateful tests against an executable model | ADR-020; the same machine is each adapter's acceptance suite |
| Telemetry | The OpenTelemetry SDK's in-memory exporter | CONTRACT-008; proves spans through a real receiver, not only log lines |
| Contract | A corpus held as data (setup, calls, expected results, errors, freshness, tagged by backend kind) run by a `pytest` runner | CONTRACT-004; the runner design is open |
| Integration | A local PostgreSQL 18.6 through `pgserver-pg18`, brought in by `truss-toolkit[local]==0.0.45` in the dependency group `truss-test` (never `dev`); tests marked `truss`, run with `uv run --extra truss --group truss-test pytest -m truss`; a Lakebase branch (PostgreSQL 18) for what the local server cannot prove | ADR-010, ADR-012, the Truss adapter plan |
| Performance | The benchmark harness at the host (100 sequential reads, 100 invocations of a three-effect action, 100 type enumerations, the 30-record list) | PRD success metrics; the harness technology is open |
| E2E | Host-level startup and integration tests in the embedding host; no E2E framework for the library | concerns.md slot `e2e-framework` (an assumption awaiting confirmation) |

## Test Data

| Type | Strategy |
|------|----------|
| Fixtures | The 30-record demonstration catalog (invented demo data) for the catalog journeys and the list-latency test; `docs/helix/02-design/contracts/examples/catalog.umf.json` as the example module document; the corpus's own setup data (modules, entities, relationships, principals, positions) |
| Factories | Not recorded. Open question. |
| Mocks | Ashlar is not yet built, so replica behavior is exercised through corpus cases that set positions and through an Ashlar adapter test double; the double's design is open. The host's connection sources are test sources that yield a connection per principal. Truss and PostgreSQL are real (a local PostgreSQL 18.6) rather than mocked; the `truss` marker keeps those tests out of a default run. |

Roles: each test user has a local PostgreSQL LOGIN role named as the user (Truss records `session_user` as the actor) whose password is the user's token, so another person's token and an expired role fail at connect as in production. Truss's own install, the registered corpus module and module access are built once per document in a template database that each case clones (about 0.3 s, where installing Truss and registering the module cost about 7 s, about 0.5 to 0.9 s of it preparing the module); the roles a person holds are the module's reader and writer roles and, for `schema`, the installation's registrar role (ADR-017, US-034-AC2). The harness (`tests/truss_harness.py`) seeds through Truss's own import API as the person, so a read case does not wait for the adapter's import; `write` goes through the backend under test; `outage` is a real failure (a socket that is not there, a revoked CONNECT, an install marker no supported release matches, the last a test-only tamper because Truss 0.0.45 installs no other release). The stub-fails-every-case assertion and the harness self-tests need that server: they skip with the reason where the `truss-test` group is not synced, and fail instead when `ARRAS_REQUIRE_TRUSS=1` (the `truss` CI job sets it). `tests/test_truss_harness.py` also checks, with no server, that a harness that cannot build its world passes no case.

## Coverage Requirements

| Metric | Target | Minimum | Enforcement |
|--------|--------|---------|-------------|
| Reads that state their freshness | 100% | 100% | Contract tests over every read operation (PRD) |
| Changes attributed to a named person or a load | 100% | 100% | Audit reconciliation over all action paths (PRD) |
| P0 acceptance criteria allocated to a layer | 100% | 100% | Allocation table below; each P0 story has an owner layer |
| Conformance corpus cases for the operations an adapter declares | All pass | All pass | Pass rule of CONTRACT-004; a host-specific case is tagged and outside it |
| Line coverage | Not recorded | Not recorded | Open question |

### Critical Paths (P0)

1. Read with a stated freshness (FR-1, FR-6; FEAT-001).
2. Action with preconditions, atomic effects, idempotency, attribution and a receipt (FR-15 to FR-19; FEAT-003).
3. Access with the person's own token, and refusal without one (FR-28, FR-29; FEAT-005).
4. Backend unavailable: the host starts and serves, and operations that need the backend raise `Unavailable` (FR-26, FR-33; FEAT-004, FEAT-006).
5. MCP identity: one process, one person, no principal argument, no administrative operation (FR-44, FR-45; FEAT-009).
6. Catalog latency targets (FR-41; FEAT-008).

### Secondary Paths (P1-P2)

- P1: the console and local PostgreSQL development (PRD, Should Have). Counts, references, read-your-write by receipt, validate without applying, the Ashlar adapter and replica positions, and the inventory and workflow clients are P0 and covered under Critical Paths and the allocation table.
- P2: not planned.

## Acceptance Criteria Layer Allocation

This plan allocates criterion classes to layers. Per-criterion rows belong in the story test plans keyed by `US-<n>-AC<m>`; none is authored yet, so the stories' own Test Scenarios tables hold the scenarios for now. Every P0 story is allocated to one primary layer below; a story's criteria share its layer unless noted.

| AC class and stories | Primary Layer | Why this layer |
|----------------------|---------------|----------------|
| Reads, freshness, bounds, pages, consistency, counts, references as keys, read-your-write by receipt, attribution of an opened entity: US-001, US-002, US-003, US-004, US-005, US-006, US-007, US-055 | Contract | The corpus proves every adapter behaves the same, including `Unsupported` and `latest` never served by a replica |
| Rules over arbitrary sequences: US-059 | Contract | The model and the machine are independent of any store and reused by each adapter |
| Module rules, telemetry and configuration: US-056, US-057, US-058 | Unit | Each is checked on the package's own source or in-process, with the process-level cases run as a subprocess |
| Dialect of the statement reader: US-001-AC5 | Unit | Pure parsing and bound checks need no store |
| Registry, enumeration, record-safe type change: US-008, US-010, US-011 | Integration | The record store, as provider, accepts a revision in a real Postgres transaction |
| Placement: US-009 (`tests/test_placement.py`) | Unit | Placement is host configuration, so it runs over the memory adapter: `test_modules_have_their_own_record_stores`, `test_replicas_are_tried_in_order`, `test_action_is_routed_to_its_provider`, `test_latest_is_served_only_by_the_record_store`, `test_provider_only_backend_runs_actions`, `test_reader_only_backend_cannot_be_a_provider`, `test_module_without_placement_is_refused`, `test_placement_names_must_be_configured_and_of_the_right_kind`, `test_revision_is_keyed_by_backend`, `test_expected_revision_checks_only_the_backends_named` |
| UMF agreement with the reference validator: US-012 | Contract | The corpus's `umf` cases compare validity and diagnostics (FR-13) |
| Action declaration and discovery: US-013 | Integration | The registry exposes the declaration |
| Preconditions, atomicity, idempotency, attribution, receipts, read-only refusal, validate without applying: US-014, US-015, US-016, US-017, US-018, US-019, US-045 | Contract | Corpus cases on the provider prove them for any adapter with the provider role |
| Import with provenance: US-020 | Contract | Corpus cases tagged for providers |
| Backend contract and adapters, the Ashlar adapter, replica positions: US-021, US-022, US-023, US-024, US-026 | Contract | The corpus is the evidence that adapters are interchangeable (FR-25) |
| Availability and partial answers: US-025 | Integration | Needs a stopped backend |
| Empty, refused and unavailable told apart; no cache of data or decisions: US-028, US-029 | Contract | Corpus cases repeat the three outcomes and a second read after a change |
| Access as the caller: US-027; a credential for one backend but none for another: US-049-AC5 and US-049-AC6 | Integration | Real role grants decide; a person with the reader role cannot invoke an action |
| No token, expired token, administrative principal refused: US-049-AC1 to US-049-AC4 | Unit | Refusal precedes any backend call, observable with a spy source; the corpus repeats the no-token case |
| Host-supplied sources, per-person connections: US-030 | Integration | A test host supplies the sources |
| Migration once, layout check, version refusal, no installing connection (status follows the last per-person call): US-031 | Integration | `test_truss_lifecycle` (a scripted assembly, always on) and its `truss`-marked tests on empty databases: two instances migrate once, the lock timeout, an installer without `CREATEROLE`, the explicit upgrade |
| Host keeps starting: US-032 | Integration | `start` never connects; unreachable, denied and failed-migration backends report their reason, and the install is bounded by `migrate`'s `timeout`; E2E in the host repeats it (PRD sketch, FR-33) |
| Boundary check on public names: US-033 | Unit | A static build check |
| Bulk changes: US-046, US-047, US-048 | Contract | Corpus cases for atomic and per-item groups, partial results and repeats |
| MCP tool set, identity, answers, degraded start, batch tool: US-050, US-051, US-052, US-053, US-054 | Integration | A stdio MCP client against the process; schema derivation is covered by Unit tests |
| Catalog browse, correct, seed; inventory and workflow clients: US-038, US-039, US-040, US-041, US-042, US-043 | E2E | Host-level journeys on the catalog, inventory and a workflow client |
| Latency targets: US-044 | Performance | `tests/bench_latency.py` at the host layer on a local PostgreSQL 18.6 (the Latency benchmark harness section); the run through the embedding host on a Lakebase branch is owed |

P1 stories (US-034 to US-037) are allocated when their story test plans are written, with these defaults: Integration for US-034 to US-037.

**Allocation rule**: no P0 acceptance criterion is left unallocated. Every `US-<n>-AC<m>` from an in-scope P0 story maps to one primary layer here and, once authored, to concrete tests in its story test plan.

### PRD acceptance sketches by feature

| Feature | PRD sketches (requirements) | Level | What it proves |
|---------|-----------------------------|-------|----------------|
| FEAT-001 | Read with a stated freshness (FR-1, FR-6); browse use cases (FR-1); open a use case (FR-2); read your write (FR-7); coverage summary (FR-4) | Contract; browse also Performance | Freshness, bounded pages, relationships as keys, receipt tokens, `Unsupported` on a backend without counts |
| FEAT-002 | UMF reading (FR-13) | Contract | The same validity and diagnostics as the reference validator |
| FEAT-003 | Create a candidate Solution, failed precondition, validate first, double click, bulk correction, read-only module, seed import (FR-15 to FR-17, FR-19 to FR-21, FR-42, FR-43) | Contract | Atomic effects, refusal changes nothing, validation writes nothing, idempotency, partial batch results, import identity and provenance |
| FEAT-003, FEAT-005 | Attribution (FR-18) | Contract and Integration | The change names the person whose token the backend authenticated, never a service identity |
| FEAT-004 | A backend is down (FR-26) | Integration | Unavailable with a reason; a replica read answers and states its age |
| FEAT-005 | Entitlement read (FR-29); no cache (FR-30) | Contract; Integration | `Unavailable`, never "not entitled" or "entitled"; two reads reach the backend twice |
| FEAT-006 | Database down (FR-33) | Integration, then E2E | The host serves its other functions while a backend is unavailable |
| FEAT-009 | Agent use (FR-44, FR-45) | Integration | One tool per action; the change is attributed to the user; no tool names another principal |

### Backend conformance corpus

The corpus is data shared by every adapter (CONTRACT-004). An adapter with the provider role runs the cases for the operations it declares; a reader runs the read cases. The memory adapter runs the same corpus (`tests/test_placement.py::test_memory_adapter_passes_the_corpus`). It proves that adapters are interchangeable by evidence (US-024), and it covers key lookups, bounded lists, filters, relationship predicates, `alias.*`, counts, the page contract, `latest` and `bulk`, `at_least`, the three outcomes, actions, bulk changes, calls without a token, import, and replica position and lag. A corpus newer than the adapter is reported, never silently passed. The Truss adapter must pass it before the contract is ratified, and the Ashlar adapter when Ashlar exists; the memory adapter passes it now.

Corpus version 2 adds receipt groups and the journal. A receipt step may expect `has_group` and `group_is` (a group saved with `save: {group: name}`), and a batch step `groups` (the number of distinct groups: 1 for an atomic batch, one per item otherwise). Two step operations read the journal: `changes` (`module` is the corpus module unless the step names a `group`; optional `by`, `action`, `limit`, `after`) and `loads` (`limit`, `after`), each expecting `changes` or `loads` with `ids` (groups or load ids, newest first), `by`, `actions` and `next_cursor`. The `journal` fixture is `basic` with alice also holding the `journal` grant; a harness maps that grant to whatever the backend's journal read needs (on Truss, membership in the module's audit role, Truss's own `ModuleAuditGrant`, which is separate from the reader and writer roles), and to nothing for a backend that declares `audit` false. Such a backend answers `Unsupported` to the `changes` and `loads` steps of the two journal cases, the runner expects exactly that, and every other step of the cases still runs; `tests/test_conformance.py` holds a backend that declares no audit and serves it, and one that claims an audit and answers `Unsupported`, to a failure. `expected_revision` is not in the corpus: the backend contract has no such parameter, because the interface checks the named backends' revisions before it plans (CONTRACT-003), so `tests/test_operator_library.py` and `tests/test_operate.py` prove it.

Corpus version 3 adds the registered document. A `document` step (optional `module`, else the corpus module) expects `document` with `verbatim` (the text is the installed document, character for character), `format`, `module` and `has_revision`. `registry.document-is-verbatim` reads it as a reader and again after registering the same document; `registry.document-is-refused-without-read` expects `Refused` (`no_access`, `token_expired`) and `Unavailable`; `replica.holds-no-document` holds a replica to `Unsupported`. The explorer catalog built on it (CONTRACT-009) is tested at every tier: `tests/test_operate.py` and `tests/test_openapi_contract.py` in process, `tests/test_devhost_server.py` over a socket, `ui/src/integration/explorer.int.test.ts` and `umf-source.int.test.tsx` against the dev host, and `ui/e2e/umf-explorer.spec.ts` in Chromium with UMF's schema browser (the npm package, pinned exactly) mounted by the console under the dev host's page policy, UMF's strict profile with no `'unsafe-eval'` (its srcdoc frame inherits it; any violation fails the test). The Playwright tests also cover what the console takes from the package's host contract: annotations from the live registry and their in-place replacement after a real Ashlar outage, the selection line and its Open in Data / Show in Graph buttons, `select()` across two registered modules in one frame (the dev host's `register` control), the frame following the console's scheme, `focus()` by keyboard, and the failure state with Retry for a narrowed policy and a failed asset. axe runs inside the frame in light and dark. `ui/src/test/umf-package.test.ts` checks the exact pin, the lockfile entry, the installed package and the build's byte-for-byte copy of its assets offline; CI's `npm run check:umf -- --download` checks the registry's integrity and the release digest.

Corpus version 4 carries the statement as written: a `query` step passes `sql` and `params` to the backend as a `Statement`, over the module the step names (the corpus module by default), and the runner parses nothing. Relationship keys are Weft's `RELATED_KEYS(alias.relationship, n)` and relationship predicates `HAS_RELATED(alias.relationship, KEY(...))`; a page is the statement's own (`ORDER BY` the key, `LIMIT`, a keyset predicate), and `truncated` says the `limit` cap cut the result. A step's `requires` names the Weft read profiles it needs (`entity-page`, `related-entity-page`, `count-summary`, `general`); a backend whose `describe().weft` declares neither them nor `general` (which covers every profile) is held to `Unsupported`. A whole-entity step (`whole`) must carry every fact column the backend appends (`_version`, attribution, provenance) in each row and in the result descriptor, for every adapter. `read.the-named-module-scopes-the-statement` holds a backend to `unknown_type` for a module it does not hold and `Unsupported` for a statement that reads outside the named one, and `access.no-grant-is-refused-not-empty` to `unknown_type` for a module the person may not read, before any profile refusal. `describe` expects `weft` with a version. Routing is Arras's and is not in the corpus: `tests/test_routing.py` covers the module check, `latest` from the record store, `bulk` through the replicas in placement order with `Unsupported` falling through and every other outcome raised, the wait for `at_least` before each `query`, and a reader the host did not configure. `tests/test_weft_parser.py` collects every statement the corpus, the GraphQL layer, the MCP tool description and the catalog example send and runs each through Weft's own parser when `weft` is importable, under the read profile the statement is written to (a corpus step's `requires`, `general` sending none; for a caller, the named profile its shape takes, and `test_every_caller_writes_to_a_named_profile` asserts no caller's statement is `general`); it is skipped, with the reason, when it is not. `tests/test_weft_relational.py` is the differential test for the memory adapter's relational subset (CONTRACT-004, Memory adapter), over a test module `shop` (`tests/shop_module.py`) with string, integer and decimal fields: one battery of statements the memory adapter serves (inner joins, `SUM`, multi-column `GROUP BY`, `ORDER BY`, tuple keysets, `HAS_RELATED`, `RELATED_KEYS`, `AS`), each of which Weft must read with no parse-stage fault, and one of statements Weft refuses at the parse stage (`OR`, `DISTINCT`, `OFFSET`, outer joins, subqueries, a bare `*`, syntax errors, unknown names and types, repeated aliases and output names, ungrouped projections), each of which the memory adapter must refuse; the batteries are data in the test, and the Weft half skips, saying so, without `weft`. The refused battery includes Weft's numeric typing (no integer-decimal comparison, no integer parameter for a decimal, literals and parameters outside the field's precision, scale or integer width) and its lexical rules (NUL, whitespace other than space, tab, CR, LF and form feed, reserved words as parameters, `count` and `related_keys` as aliases, case-folded output and parameter names); `KNOWN_NARROWER` holds the differences known to remain, each refused by the memory adapter and read by Weft. The same file checks the answers: bag joins and `COUNT(*)` over them, exact `SUM` at its argument's scale, numbers held at their domain on import, ordering, the tuple keyset, the 16-join cap, the `general` profile's `LIMIT` and work bound (`Unsupported`, charged before a join with no linking pair; a 2,000-row join runs in well under a second), and a declaration without `general` refusing it. `test_conformance::test_a_replica_that_declares_less_is_held_to_its_descriptor` holds that a declared `general` covers every named profile in the corpus. `tests/test_reserved_names.py` registers a module whose properties and relationships are named `order`, `group`, `limit` and `in` and reads them through GraphQL (by key, a filtered list, an inverse and an `afterKey` page), search and the console's template statements, on the memory adapter and through Weft's parser: every name Arras writes into a statement is a Weft quoted identifier (`arras.names.quoted`; `weftName` in the UI, `weftNames.test.ts`). The Weft checks skip visibly without the wheel; CI installs it (pinned, checked against the release's `SHA256SUMS`) and sets `ARRAS_REQUIRE_WEFT=1`, so in CI a missing parser fails the run (`test_a_missing_parser_skips_visibly_or_fails_when_required`).

Corpus version 5 adds validate-only registration and the `schema` grant (Schema administration, below). Corpus version 6 adds text search: a `query` step may carry `text` (`{words, properties}`), which the runner passes to the backend as a `TextMatch` beside the statement, never in the SQL; the rows are those of the statement's own order and bounds in which every word occurs, case-folded, in some named property, with `%`, `_` and `\` literal. A case's `requires` names `search` for its type, and a backend that does not declare `substring`, or a property not in its `searchable`, is held to `Unsupported`; refused and unavailable stay distinct. Corpus version 7 adds relational reads: `read.inner-join-is-a-bag` (an inner join keeps every matching combination and drops the unmatched, and an order by several columns, under `general`) and `read.count-over-a-join-by-several-columns` (`COUNT(*)` over a self join counts the bag, grouped by two columns and ordered by the whole grouping, under `count-summary`). The catalog module has no numeric field, so `SUM` is proven in `tests/test_weft_relational.py`, not in the corpus. Corpus version 8 makes every `reached` step name a person (`as`), because a backend answers `reached` for a person: a step without `as` fails, and a person who holds no grant is `Refused`. Corpus version 9 adds the cases a Truss adapter needs: `access.non-member-write-is-refused` (a person who is a member of no module is `Refused` a write and a dry run, and nothing changes), `freshness.non-member-reached-is-refused` (`reached` for a non-member is `Refused`, for a reader it is answered), `registry.rewritten-equal-document-registers-unchanged` (a document that is the registered one re-serialized, edit `rewrite`, is unchanged: no revision, the registered text stays verbatim, and writes still apply) and `action.retry-with-generated-keys-matches` (the module's `DraftSolution` generates its key; a retry under the same idempotency key and inputs returns the original receipt, replayed, and other inputs under the key are a `Conflict`). An undeterminable token already has its case (`freshness.undeterminable-token-is-unavailable-not-false`, an outage). Corpus version 10 adds `registry.registers-a-new-record-type` (a document that adds a record type, edit `add-record-type`, is a compatible change: the dry run says so and applies nothing, registering it makes a new revision readers see, and registering it again changes nothing) and gives the `add-optional-property` and `add-required-property` edits the authored `name` Truss requires of every field. The Truss registry (`tests/test_truss_registry.py`): always-on tests drive the adapter over a scripted fake of Truss's assembly (outcome mapping by code, the request key, equality before accept, `expected_revision` order and race, unknown-commit replay, cache hit and invalidation, status and describe); the Truss-marked tests check (the registry corpus cases run in `tests/test_truss_conformance.py`; Truss 0.0.45 accepts an optional property added to an existing record and refuses a required one, so one case ends at an `Unsupported` registration) the first registration on an install with nothing registered (catalog head 0), a rewritten equal document makes no revision, a dry run leaves no catalog row, a non-registrar is `Refused`, a reader sees exactly their modules, each call runs as its person, a reverted action edit registers again and a stale `expected_revision` conflicts. The Truss detected-race limit (no `expected_revision` on accept) is recorded in the `limits` field of the corpus case `registry.register-checks-the-revision-it-was-planned-against`, which the runner holds to the step the harness declares (`TrussHarness.LIMITS`, R16.1 and R16.5), and proved by the always-on `test_a_registration_that_lands_between_the_read_and_the_accept_is_a_conflict` and its repeat-after-unknown-commit variant. The Truss query (`tests/test_truss_query.py`): always-on tests drive the adapter over a scripted fake of Truss's assembly (the statement and parameters passed unchanged over the module's document id, `maximum_rows` 10,000 with rows capped at `limit` and `truncated`, the module checked before text and parameters, parameter types, the `complete-entity` profile for `alias.*` and the page-profile ladder for a keyset, the error map by Truss code and Weft diagnostic with the pinned message, absent values, related keys, fact timestamps, column typing, the declared profiles and capabilities); the read corpus cases run in `tests/test_truss_conformance.py`, where two end at a Truss limit (`read.relationship-columns-follow-ends`, whose explicit alias Weft refuses beside the relationship column Truss appends, and `read.relationship-columns-are-capped`, which Truss refuses for an entity with more than 100 related keys; both recorded in the case's `limits` and in truss-requirements R17), and the Truss-marked tests run a differential battery of statements on the memory adapter and on Truss comparing columns, types, rows and error classes, a non-member's statement as `Invalid` (`unknown_type`), and each query running as its person, read-only and rolled back. Corpus version 11 adds export: a `export` step (`limit`, `after`) reads a page of `export_records` and expects `export` (`records` exactly, `more`, `omitted`); the cases hold canonical order and the absent-property rule, `Refused` without a read grant (never an empty page) and `Unavailable` in an outage, and paging by the last record's place with a write between pages; a replica is held to `Unsupported`. Corpus version 12 adds the idempotency cases a Truss adapter diverges on: `action.keyed-retry-of-a-delete-replays`, `action.keyed-retry-of-an-unlink-replays` (the corpus action `catalog.UnlinkSolution`), `action.keyed-retry-after-its-target-was-deleted-replays` and `action.same-key-from-another-person-replays`. Each returns the original receipt, replayed, on the memory adapter; Truss ends the first three at `Conflict(idempotency_key_reused)` and the last at the second person's `PreconditionFailed`, each pinned in `TrussHarness.LIMITS` (truss-requirements R18.3). Corpus version 13 adds `import.original-time-names-its-offset`: an `original_at` with no offset, a bare date or a non-time rejects its entity record and stores nothing, and one that names its offset is kept, on both adapters (CONTRACT-003). The conformance corpus is version 13.

### Official admission and metadata profile — bounded A2

These gates govern the bounded feature and remain separate from generic release
qualification. The completed source and installed proof below belongs to an
unreleased 0.5.1 candidate and is not evidence for the 0.6.0 package. Each release
with the optional UMF extra must qualify its exact final wheel and repeat the gate
from its public download; source proofs and prior candidate receipts do not carry
forward. Governing adoption alone does not satisfy either gate.
CONTRACT-002/003/004 separate official validity/completeness, source fidelity,
projection support, provider qualification and executable capability.

- Admission compares exact source bytes/SHA, `not_run`/null/null versus completed
  official booleans, lexical versus structural-negative ordering, immutable
  ordered diagnostics, unknown meaning, missing-engine refusal and unexpected
  failure. Direct and nested repr tests use a valid source-only description
  sentinel; source is `field(repr=False)`, not a comment. Diagnostic text is not
  thereby safe for logs. Returned metadata or caller mutation cannot invalidate
  later independent re-admission.
- Projection has a documented STRING-primary derivative positive and unchanged
  integer-primary/alternate-key valid-but-unsupported controls. Test actual IDs,
  all members, requiredness/cardinality, unsupported semantics and source paths;
  no title/namespace identity inference, silent member loss or evaluator.
- Registration proves `RegisteredDocument.text.encode("utf-8")` equals admitted
  bytes; equal/changed revisions and profile-transition refusal; existing
  authentication, parse, placement, schema, GraphQL and CAS precedence. Unqualified
  custom store and replica acceptance/dry-run/attach/CAS counters remain zero.
  Missing profile capability is legacy-only; malformed carriers refuse, and the
  exact qualified memory tuple is a positive control.
- Host registration rederives metadata from source, never a caller's constructed
  AdmissionReport/ModuleInfo or a mutable prior summary. Direct provider tests
  retain authorization-first behavior and explicitly label the trusted
  host-supplied pairing; they claim no independent official admission.
- Metadata-only direct apply, dry run, both batch modes and import refuse after
  authorization and before clock/replay/iteration/effects. Use uniterable input
  and compare source/revision/graph/versions/journal/loads/position/replay state.
  Legacy CRUD and unsupported-semantic safeguards remain intact.
- The preparatory catalog extraction retains public identities/signatures,
  token-before-call, failure priority, placement and copy selection, no cache,
  exact module edges and unchanged 926-line ceiling. Forbidden-edge/cycle and
  host-private-import negative controls remain meaningful.

Vendor the exact 139-case official data from public `umf-v0.5.4`, commit
`53de049136c7e41b482d1a73665d031cd5fbaec6`, fixture
`fixtures/metamodel/current-conformance.json`, SHA-256
`bb008a98b8448050748e65f867e7863475ccad9501a5b9229ae9e6d336691544`.
Retain derivedFrom/source/corrections metadata and the tag's MIT OR Apache-2.0
license/third-party notices. Independent tag/blob/digest/license evidence is
sufficient; resolve actual ambiguities without adding an approval gate. Compare
`validate_document(raw, upstream_case_registry)` valid/complete and every ordered
diagnostic for all 139 IDs. Special callbacks are TEST ONLY; separately test the
production fresh EMPTY Registry, where DDD/view declarations remain incomplete.
No external worktree or generated baseline is a CI dependency.

Quality and semantic CI explicitly install `--extra truss --extra umf` for honest
SDK typing. A dedicated `ARRAS_REQUIRE_UMF=1` gate executes the nonempty exact
139-ID set and admission/projection/registration tests without skips; no missing
engine or module-level `importorskip` may make it green. Only the engine bridge
imports the exact released pure wheel; no broad ignores or copied interpreter.

Two fresh installed-wheel environments outside the checkout are mandatory:
base-only proves official UMF absent, legacy behavior works and the explicit new
route refuses without fallback; extra-enabled verifies wheel SHA before install,
installed RECORD/payload/origins before API execution, then public admission,
projection, memory metadata registration/readback, original bytes and refusal
controls. Neither uses shared site packages/PTH/source aliases. Record observed
versions/platform/scope; these proofs establish no native, UI or production
semantics. `tools/verify_umf_admission.py --wheel PATH --output-json PATH`
implements this selected-wheel gate; CI invokes it after the wheel build.
Coordinate any feature release with the distribution owner; do not amend
published 0.5.1 artifacts or receipts.

For Arras 0.6.0 and later, the exact candidate wheel must additionally pass this
gate before publication: install the official UMF 0.10.0 wheel from its pinned
public URL into a fresh extra-enabled environment; verify the Arras wheel and
installed payload before import; run all 139 ordered reference and separate
fresh-empty production Registry comparisons, six base controls and ten
extra-enabled controls with zero skips; verify cleanup; then repeat the same
qualification against the exact public-download wheel in a fresh environment.
Keep these results separate from the historical 0.5.1 source/wheel proof. The
139 rows compare admission results, not 139 metadata execution cases.

**Execution checkpoint.** The [bounded A2 execution record](../04-build/arras-integration-plan-20261022.md#bounded-a2-execution-checkpoint)
and [safe installed receipt](../04-build/evidence/umf-admission-projection-20261023/installed-proof.json)
bind the unreleased source candidate `11c3dd0711ff6d556fed4fbea99cff1951506588`.
The required source suite passes 3,031 tests with 199 Truss tests deselected;
configured strict source/test typing, Ruff, formatting and content checks pass.
The preceding source attempt passed 3,028 tests and failed two MCP subprocess
cases because the new required-test flag was treated as configuration. The
test-only ignored-prefix fix retains unknown-key refusal, and the final complete
source run passes; the failed attempt remains recorded in the execution plan.

The first actual installed attempt passes on CPython 3.11.17, macOS ARM64, for
the exact unreleased 0.5.1 candidate wheel identified in the checkpoint.
Both fresh environments verify the selected Arras payload before import; the
extra-enabled environment also verifies the selected official SDK payload.
All 139 unique ordered reference cases match both the official TEST-ONLY case
registries and separate fresh EMPTY production registries, with zero skips.
Six base controls and ten extra-enabled controls pass, including original-byte
readback, provider refusal, immutable metadata and write refusal without effects.
The receipt records cleanup of both environments, no shared site packages and
no source aliases. This is an unreleased 0.5.1 installed feature proof, not a 0.6.0 package
qualification or public-download repeat. It establishes no native, browser,
production or complete constraint/action-runtime qualification.

### The Truss adapter's conformance (TR-12)

Three checks decide whether the adapter is conformant, beside the always-on adapter tests. First, `tests/test_truss_conformance.py` runs the whole corpus (every `store` and `reader` case) on the Truss harness once, about eleven minutes, and requires it to pass at the declared capabilities: each case passes or ends at the step, and in the refusal, of a documented Truss limit. The limits are the harness's own declaration (`TrussHarness.LIMITS`, ten cases: the whole-entity read of related keys, R17.2, the registration of a new property on an existing record, R16.5, and the four idempotency cases a keyed retry diverges on, R18.3; each case carries the ask in its corpus `limits` note), the runner records such a case as `limit` and fails it when it passes, ends at another step or names no case (CONTRACT-004), and `tests/test_conformance.py` proves the runner rule. Second, the executable model runs the Truss adapter (below). Third, `tests/test_truss_mutants.py` runs hand-written mutants of the adapter's pure mapping tables (plan to operation, result to receipt, the failure and refusal maps, the numeric domains, the bounds) against the suite that needs no Truss, each in a temporary copy of the package in a subprocess, and requires every one to be killed; a survivor names a rule no test pins, and a mutant whose text is not found exactly once fails the file. No mutation tool is added. A Truss-marked test in `tests/test_truss_reached.py` pins that a non-member with a malformed token is `Invalid` on Truss and `Refused` on memory, because Truss decodes before it authorizes.

### Property-based machine

`tests/test_properties.py` holds an executable model of the action and read rules and a `hypothesis` state machine that drives invocations, validations, batches, replica feeds and outages and compares the interface with the model after every step (US-059, ADR-020). It runs over the in-memory backends (`tests/test_properties.py`) and over the Truss adapter (`tests/test_truss_properties.py`, Truss-marked), beside the conformance corpus; the Truss run subclasses the machine and drives it through the interface as a writer who is not an administrator. The properties carry the identifiers P1 to P9 of [TD-001](../02-design/TD-001-contract-rules-formal-specification.md), which also records the state, bounds, assumptions and residual gaps. The journal is part of the model: each applied change is one record, newest first, naming alice, the action and a `create` op per code it created, and reading it a page at a time (pages of 1 and of 3) gives the same rows in the same order. A witness test requires the machine to have reached each case it claims to check, and a test breaks a rule for each of P1, P2, P4 to P9 (a forgotten idempotency key, a replica answering before it reached a token, an outage that does not raise, a `validate` that applies, batch items sharing a key, one failed item refusing the rest, an atomic batch applied item by item, a `latest` read served by the replica, a `bulk` read served by the record store, and for the journal a change recorded twice, a validation that leaves a record, a change that names another person, a cursor that skips a row) and requires the machine to fail, the later ones in the rule that checks it, so a green run means something. The result is a completed randomized check, not an exhaustive search. Concurrent interleavings are out of its reach; a model checker covers concurrent same-key invocation when the Truss adapter's transaction design exists. On Truss there is no replica and no journal, so the machine drops the feed, read-your-writes and mirror rules and replaces the journal rules by one: `changes` is `Unsupported` and no two applied changes share a group. The outage rule names the host's registered backend, and an outage lasts the one step that checks it. The Truss witness test requires an applied change, a replay, a key conflict, a failed precondition, a valid and a refused validation, a partly applied batch, an atomic batch applied and refused, an outage refusal and the unsupported journal, within a budget of 12 examples of up to 16 steps (a step costs seconds), and three controls (a retried key that is a new request, batch items that share one request, every change naming one group) must fail the machine in a named rule.

### Bindings on Truss

`tests/test_truss_endpoint.py` (always on) proves the endpoint handle: a credential-free `postgresql://` URI, every refusal without echoing the handle, and the person's connection (role, token as password, every keyword libpq reads from the environment given, closed after the call). `tests/test_truss_bindings.py` (Truss-marked, one `TrussBox` per module: the dev host's own world) proves the MCP server built by `build_backends` reads and writes as the person and reports `not_configured` for want of an installing connection, the database refuses a reader's write and a non-member's read, an unreachable database is an error and not a crash, the process ignores `PG*` variables, the console and the operator surface serve registered modules (the audit reads answer 501 on Truss, which the console hides) and the dev host browses a module from Truss and its controls are real role changes or a 400. The `--truss` option is checked with a stand-in server (`tests/test_devhost_main.py`). The persistent-attach baseline has scripted tests in `tests/test_devhost_truss_attach.py` and `tests/test_truss_local_attach.py`, and native tests in `tests/test_truss_persistent.py` over an owned throwaway server with a non-superuser installer and unrelated roles/databases. Their old takeover/password-rotation/regrant expectations are superseded by the EX-06 cases below. Retain source selection, scrubbed startup text, state/no-reseed and explicit reset ownership coverage; qualify the new credential/grant behavior separately before claiming it passes.

### Structure, telemetry and configuration checks

`tests/test_modules.py` enforces the Module Boundaries of the architecture with forbidden-edge, cycle, lazy-import and type-only controls and a module-length ceiling (US-056). `tests/test_telemetry.py` proves CONTRACT-008 through a real OpenTelemetry receiver, with injected sensitive values asserted absent from every sink (US-057). `tests/test_config.py` proves the MCP process's three configuration layers (the committed default and environment files, ops values over both, the ops file, placement from the files only), the one-owner refusals naming file and key, its fail-fast exit, and that `.env.example` and `config/default.toml` equal the schema (US-058); `tests/test_mcp_process.py::test_sigterm_ends_the_process_cleanly` starts the real process, sends a frame, signals it and asserts a clean exit. Ceilings are set at today's worst value and lowered, never raised.

### Scoped signal naming acceptance — EX-02 completion

This is a required naming/release gate, not evidence that the new seam already
passes. CONTRACT-005/008 and ADR-018/019 own the interfaces. Use the actual OTel
SDK and in-memory span exporters with two independently constructed providers,
matching Resource `service.name` values and different attribute/event/log prefixes.
Run interleaved async hosts, nested scopes and an operation finishing after its
inner scope changes. Assert each receiver/log route gets only its own projected
signals, no duplicate emission, canonical origin keys and `error.type` survive,
default output is unchanged, and the global provider is not mutated. Verify reset
on normal exit, cancellation and exceptions. Exercise whole ASGI invocation,
streamed sends and awaited background work. Real console/operator worker-backed
requests must exercise explicit fresh context copying at every Arras-owned executor
submission, including principal/operator callbacks and cancellation-shielded work;
an outer ASGI context test alone is insufficient. External detached work needs
explicit context.

Configuration tests prove field-wise bootstrap/default/environment precedence,
shared strict value validation and no new environment/provider-import mechanism.
A factory sees effective names exactly once before backend/token-source/build work;
help, invalid arguments and invalid configuration never invoke it. Bad names,
wrong factory result or missing/mismatched service Resource refuse before work
with redacted diagnostics. Offline doctor checks only names and invokes no factory.

Default-deny tests inject unknown keys and sensitive sentinel values into both
projected logs and actual exported spans. Failing logger, provider/tracer and
exporter paths must leave business outcomes intact and never use another host's
provider. Capture DEBUG diagnostics from actual principal/operator callback and
execution/provider faults, including a sentinel in exception text/detail, and
assert class-only diagnostics with no traceback on canonical or projected routes.
Preserve traceparent, severity, status and no-exception-text behavior.
A fresh installed consumer imports only public names, constructs two host-owned
SDK providers and exercises direct-library context, actual MCP frame handling and
ASGI dispatch. Record wheel hash, exact SDK/API/Python/platform versions and receiver
observations; a source checkout or span `service.name` field is insufficient.
Final exact-artifact/release gates rerun this proof on their selected cohort.

### Portable canonical UI acceptance suite — EX-03/EX-07

CONTRACT-005 binds separate optional Node `testkit` and browser `testkit/host`
subpaths. The source and packed consumer run the same canonical e2e specs and
assertions, parameterizing fixture origins/resources and expected Brand/surfaces.
The acceptance backend is the standard synthetic upstream fixture; the consumer
wraps the shipped AcceptanceHost in its actual packed theme/provider. Production
entries remain importable without test peers, and the browser graph must not
include Node/Playwright or another React/context. The host supplies two isolated
main/schema fixtures and browser/tools explicitly; no implicit installs or source
web servers are part of the portable factory.

Compare canonical and packed spec/resource inventories, digests and discovered
per-project test counts. Run every nonvisual project with zero unexpected skips;
run existing visual assertions on Darwin with reviewed per-theme baselines and
report visual-only exclusion elsewhere. Missing/tampered fixtures, unknown or
malformed config/origins, an empty/subset inventory and a controlled assertion
failure must fail closed. Execute the actual packed suite outside the checkout
against the selected wheel/npm/theme cohort; retain artifact hashes, runtime
versions, per-project results and screenshots. The narrower public checker and
previous default-theme source suite receipts remain separately scoped evidence.

### Distribution public boundary and exact artifacts — EX-01

`tests/test_public_api_manifest.py` compares the explicit schema-versioned
`src/arras/public-api.json` with root `__all__`, selected callable parameters, all eleven contract
document versions and the nine runtime keys, configuration keys/ownership/precedence sources,
launch options, conformance/vocabulary versions, CSS tokens, and telemetry declarations. Deliberate
mutations prove removed/added exports, stale CLI/environment entries, omitted tokens/events and a
wrong contract version fail. The separate UI checker compares the catalog with packed ESM and
TypeScript declarations and peer/export metadata; the packed consumer imports the actual namespace.

After the UI build and `uv build`, run:

```sh
python tools/verify_distribution.py --output artifacts/distribution-verification.json dist/arras-*.whl dist/arras-*.tar.gz
```

The verifier rejects missing, duplicate, stale or corrupt artifacts; validates METADATA, licenses,
`py.typed`, the catalog, conformance corpus, page and referenced assets; rebuilds a wheel from the
sdist; compares the complete `arras/` payload and exact npm tarball bytes; then performs isolated
normal dependency installs of both wheels and runs the packed consumer on each extracted tarball.
The external Python probe uses only installed artifacts and checks the public imports, an InMemory
operation, resources, and the composed UI brand/schema callback without Truss or psycopg. Its report
records a stable JSON SHA256 inventory, actual Python/platform, declared versus observed interpreter
scope, and the workspace-linked UI dependency cohort. `npm run check:public-manifest` is part of `npm run build:wheel`.
CI and release build jobs run the verifier after artifact creation. This is artifact and consumer
qualification for the observed cohort; it does not imply unrun Python 3.12/3.13, Linux/macOS,
registry, managed-host, official UMF or native PostgreSQL behavior.

### EX-05/EX-07 external overlay and provenance

The [bounded execution plan](../04-build/ex05-ex07-external-overlay-20261022.md)
requires an own-namespace Python consumer installed outside the Arras checkout,
using only declared public imports and explicitly selected module/seed/graph
resources. Assert empty startup, absence of bundled modules, exact document bytes,
administrative import provenance, action/read behavior and independent worlds.
The consumer's graph envelope is not a new public format. No private registry or
copied upstream test code may be required.

The installed corpus command/job must report store/reader roles, corpus version,
case outcomes, skips and documented limits separately. Negative controls prove a
failing/empty/newer corpus cannot produce success. Custom adapters use explicit
callable factories under `Harness`; native fixtures/jobs need independent owned
resource and exact-cohort evidence. Memory runs do not close native/theme gates.

Optional harness cleanup is checked on probe/newer-version, successful case,
setup/step failure and cleanup failure. Every acquired harness closes once;
legacy factories without close still work. Cleanup errors cannot pass or mask a
primary failure. The packaged native helper uses only owned fresh local resources,
real per-person credentials and an actual foreign receipt. Unit dependency/import
controls prove the base package imports without native extras; the installed
native corpus is qualified separately on an exact released cohort. A testing-only
installation-marker change is documented and confined to the owned database.


The strict installed-native verifier (`tools/verify_native.py`,
`tests/test_verify_native.py`) is tested independently of an available native
cohort. Negative controls cover malformed/duplicate cohort identities, mismatched
index/asset digests, wrong wheel metadata/runtime, alternative installed payload,
missing/duplicate/applicably skipped corpus cases, mismatched role/version/limit
maps and outcome counts, nonzero CLI exit, failed/harness-error outcomes and an
empty report. Output/input alias controls include failure paths; nonzero or
invalid CLI results retain their partial receipt/stdout/stderr. Timeout tests
check bounded owned-process cancellation and leftover owned PostgreSQL detection,
without touching unrelated resources. Undeclared transitive native binaries fail complete qualification;
all selected wheels receive independent installed-payload comparison and the
receipt inventories distribution-declared current-platform native paths/hashes.
An executed probe control distinguishes extensionless ELF/Mach-O runtime files
from foreign-platform bundled installer launchers; no package-name exemption is
substituted for format/platform classification. The applicable/complement sets come from the installed corpus,
not repository case counts. A reviewed empty limit map is strict all-pass;
explicit documented limits stay separate. Successful unit mocks do not qualify
native behavior. Actual qualification requires the exact public selected wheels,
a fresh unprivileged external Python 3.11 environment, installed CLI execution,
payload/native inventory and retained outcome receipt. Input integrity is not
prior qualification, and candidate or other-platform results cannot close it.

The private release evidence assembler
(`.github/scripts/assemble_release_evidence.py`, `tests/test_release_evidence.py`)
is tested with synthetic producer receipts independently of hosted execution.
Require exact build wheel/version/digest and wheel-carried npm linkage across
the distribution, doctor, consumer, native and full portable UI evidence. Missing,
failed, stale, duplicate-key or incompatible receipts, native cohort/index/binding
mismatches and a narrow UI receipt offered as full-suite proof must fail. Path
controls reject symlinks, escapes and output/input aliases. Assert unchanged
artifact/build-receipt bytes, a selected safe evidence inventory and complete
regenerated checksums; raw logs, environments and PostgreSQL state are excluded.
The aggregate must leave public-download checks pending until those checks
actually run. Offline assembler tests do not qualify their synthetic cohorts.

Explicit optional consumer/theme Python setup paths are bounded to the workspace
and recorded by digest. Consumer setup precedes `--no-deps` consumer installation;
theme setup requires a selected target. Record installed distribution names and
versions after provisioning; no claim of universal dependency resolution or
browser bootstrap follows from running a caller script. The source dependency
gate also rejects production imports outside the standard library, Arras and its
explicitly declared external import-root/distribution map, without a host-name
deny-list. A new arbitrary consumer import is a negative control.

Reusable optional jobs have failure controls for failed pytest followed by a
successful logging command, zero selected tests, skipped-only tests, JUnit errors
and workspace-escaping setup/target paths. Native setup is an explicit trusted
caller Python file with a recorded digest/cohort; `ARRAS_REQUIRE_TRUSS=1` and
missing-dependency refusal are mandatory. A selected job passes only with positive
test count and zero failure/error/skip counts. Omitted jobs are `not_run`; caller
theme pytest does not substitute for a rendered browser/accessibility receipt.

A generic repository check verifies declared dependency/import origins and
fixture/document provenance/integrity, with negative controls for undeclared
consumer imports, credential-bearing content, missing fixture provenance and
stale digests. It does not prove remote public accessibility, recognize customer
names or grant third-party redistribution rights. Semantic documentation review
preserves artifact IDs/links and distinguishes active requirements from dated
source evidence. Reserved UI/configuration files remain with their owners.

### Audit reads by provider

`changes` and `loads` take an optional `provider` (CONTRACT-001, Which provider). `tests/test_operator_library.py` proves it with a module whose actions are applied by two providers: `test_changes_can_name_the_provider_whose_journal_is_read`, `test_loads_can_name_the_provider`, `test_a_provider_outside_the_placement_is_refused` and `test_a_provider_without_a_module_is_refused` (US-063-AC6, AC7). `tests/test_operate_audit.py::test_audit_routes_accept_a_provider` proves the same on `POST /audit/changes` and `POST /audit/loads` (CONTRACT-009), and `ui/src/test/audit.test.tsx` ("lists each provider's journal and reads the chosen one") proves the console's provider selector (US-063-AC8). A merged feed across providers is not specified and not tested (CONTRACT-001, Open Questions).

### Embedded UMF schema browser

The console's UMF source view embeds UMF's npm package at an exact version. `npm run check:umf` proves the pin, the lockfile, the installed package and, with `--download`, the registry's integrity and the release digest. The browser itself runs only in Playwright, in its real frame against the dev host under the strict CSP, where any CSP violation or page error fails the test. What the console relies on is measured there, not read from the package's notes: axe inside the frame in light and dark; each annotation tone's contrast where the browser draws it (entry heading, record map as SVG text, relationship legend), computed from the rendered colours against what is behind them and held at 4.5:1 or more in both schemes, the console's own badges and every tone in a probe frame built from the same srcdoc; record annotations clear of the property count by bounding box; keyboard reach of the source pane; the frame's requests. Tests that depend on the frame or the dev host wait for what the browser shows, never for a number or order of events. A version bump re-runs every tier and re-measures.

### Persistent development credentials and grants — EX-06

CONTRACT-005's persistent-local identity surface replaces the old expectation
that attachment rotates passwords, clears expiry and regrants demo access. Update
`tests/test_truss_local_attach.py` and `tests/test_truss_persistent.py` accordingly;
old passing assertions for those behaviors are not desired-behavior evidence.
Preserve existing unrelated-role/database and reset ownership controls.

Use the owned isolated `External` PostgreSQL fixture in
`tests/test_truss_persistent.py`, with temporary credential files/source callbacks.
Do not read, attach, alter or reset a developer's personal server or
`~/.arras` credential files during testing. Keep Truss 0.0.45 and PostgreSQL 18.6;
no new dependency pin or managed-platform claim belongs in this slice.

| Scenario | Required observation |
| --- | --- |
| Two live hosts, shared source | A stays open while B attaches. A's original principal authenticates on a **new** connection after B starts, and both perform still-authorized operations. Password/expiry/login attributes and independent memberships are unchanged; existing open connections alone cannot prove preservation. |
| Restart and module reload | Persist a record, revoke a default grant and add an unrelated membership. Close/reopen/reload with the same source: credentials, record, revocation and unrelated membership survive; no reseed/default registrar or module regrant. |
| Missing/wrong/expired source | Existing managed-role lookup refuses without `ALTER ROLE`, `GRANT` or `REVOKE`; attributes/memberships/head/data remain unchanged. Missing source entries use `create=False` and do not change the credential file. Distinguish outage from auth refusal, scrub tokens/URLs/source exception text, and never repair expired or `NOLOGIN` roles implicitly. |
| Concurrent first creation | Two independent hosts/processes share a file and race the same absent role: stable credential/identity, one creator, no loser rotation/revocation. A deterministic duplicate-role countercontrol covers a creator outside the database-local lock scope, bounded rollback/reread and unchanged winner attributes. |
| File source | Temporary files prove atomic first creation/restart, cross-process locking and release on failure. Refuse malformed/duplicate-key/unknown-version/oversized/symlink/unsafe-permission/nonregular files without clobbering or blocking. An ancestor symlink followed by a missing child refuses before creating that child behind the link. Scope uses only credential-free cluster/installer identity; unrelated roles have independent secrets. Lookup-only mode never creates a missing entry/file. |
| Explicit role selection | Reuse a person created by another host. Reconcile the installer's direct known managed grants across hosts while preserving independent grantor rows, unrelated grants and inherited rights; repeated selection is idempotent. Assert the intended direct rows rather than infer exclusive effective privileges from a sandbox label. Native authorization still evaluates every applicable grant. Startup/reload never perform reconciliation. |
| Bootstrap/controls | New owned person/target roles receive intended initial grants once; existing roles retain current authority. Grant/revoke/expiry/reset remain explicit. Persistent `set_password`/`use_token` refuse; throwaway authentication, token-shaped binding tests and cleanup still work. |
| Composition/CLI | `TrussBox`/`devhost.build` forward `credential_source`; missing programmatic source refuses without file I/O. Check CLI/env/path precedence, default scope derivation, invalid option combinations and scrubbed startup errors. Only CLI composition constructs the default source. Stand-in parser tests remain separate from native proof. |

Run focused nonnative source/composition/file tests, module/host boundaries, Ruff
and Pyright, then Truss-marked local/persistent/binding tests with
`ARRAS_REQUIRE_TRUSS=1`. Default pytest excludes native tests. Record exact
commands/cohort/results/skips in the build plan; obtain Sol review before EX-04.
These are acceptance gates, not passing claims.

### Composed UI callback and packed provider — EX-04/EX-03

After EX-06 verification/review, EX-04 adds focused tests in `tests/test_ui.py`
using the existing ASGI helper and `tests/test_schema_surface.py` as the ordering
reference. Assert unchanged callback object/principal/parsed-module forwarding
for validate/register; `None` parity; 401 for no principal and 403 for nonoperators
before hook execution; malformed document 400 before hook; false 403 and exception
scrubbed 500 without library calls/revision/document/graph changes; true cannot
override a denied backend schema grant. With no operator hook, schema is absent
even if a schema callback exists. Include prefixed/root-path mounts and preserve
the existing action hook and public version-route behavior.

Run `uv run pytest tests/test_ui.py tests/test_schema_surface.py
tests/test_public_api.py tests/test_modules.py tests/test_boundary.py -q`, Ruff and
Pyright. This is in-process authorization composition, not new native behavior;
no browser or visual-baseline change is required for EX-04.

After EX-04 verification/review, EX-03 extends the existing
`ui/src/test/design-system.test.tsx`, `pack-manifest.test.ts` and boundary controls
where relevant, then tests a **packed** consumer. Build with `npm run build:lib`,
`npm run check:externals` and `npm run pack:wheel` from `ui/`. Install the resulting
tarball in an isolated temporary consumer using exact local artifacts and its
single React/ReactDOM peer pair, with scripts disabled and no private registry.
Compile a consumer TSX fixture against package-root imports of every advertised
value/type. Render a host replacement widget beneath the public provider with an
actual exported UI component; prove that root/browser/shell entrypoints do not
create separate design-system contexts. Assert partial/default fallback, nested
override and forwarded accessibility/disabled/busy/ref props using existing
component semantics. Source aliases or relative `../ds` imports cannot stand in
for the packed boundary. Keep installed dependency inspection and the custom
widget/context render as separate evidence; one does not prove the other.

Run `npm run check`, `npm run typecheck`,
`npm test -- src/test/design-system.test.tsx src/test/pack-manifest.test.ts
src/test/boundaries.test.ts`, the actual packed-consumer compile/render check and
the existing scoped-CSS check for the library build. Record the tarball digest,
consumer tool/dependency versions and exact commands in the plan. No publish or
visual-baseline regeneration is authorized or needed for this export-only fix.

### Schema administration

`session.schema()` and the surface over it are proven on the fakes, as the corpus does for every provider operation. The conformance corpus gains cases for validate-only registration (it changes no revision and no journal row, and reports the refusal `register` would raise) and for the `schema` grant (a `write` grant is not enough; `schema` allows both; a token is required), and the fakes, which implement the grant as a mode, pass them (corpus version 5; a Truss adapter must pass the same). `tests/test_schema_library.py` proves the library: a plan equals what registration then does (a property test over arbitrary compatible and incompatible edits), a stale `expected_revision` applies nothing, the administrative principal is refused, and an unplaced module is `Invalid` (`invalid_placement`) and a module that breaks another host rule is an `ok: false` plan. `tests/test_schema_surface.py` proves CONTRACT-011. `tests/test_devhost_roles.py` proves the sandbox's roles: the grants each implies, name rules, no administrator, replacement not accumulation, loopback only. The UI tests prove the import view (plan, refusal, conflict, hidden when not mounted) and export (byte-exact, only readable modules), and Playwright runs the whole-stack flow: as a `schema author` import an optional property with a preview, then as a `viewer` be refused, and export the module back (US-073 to US-076). The dev host (`python -m arras.devhost`) serves the console, and `tests/test_catalog_example.py` loads the example through the dev host's builder.

### Query area

`POST /query` is a read of `query` over the named module (CONTRACT-009). `tests/test_operate_query.py` proves it on the operate app over the fakes: the grid's columns, rows, freshness and revision for `latest` and `bulk`; a missing `module` refused; the limit bound and `truncated`, with a next page read by a keyset predicate in the statement and no cursor in the answer; a statement the backend cannot read, one for an unreadable module, a statement outside the named module, a construct the backend does not serve, an outage and an expired token each answered by type; two principals with different grants; the text absent from every error `message`, log and telemetry attribute; and `test_only_declared_actions_write` unchanged for writes. The UI tests prove the tab: the grid, `truncated` with no page control, the inserted `SELECT … ORDER BY x.<key> LIMIT 50`, error states and the session history (module, text and consistency; newest first, reuse, run again, clear, bounded, cleared when another person is chosen), and that nothing is written to `localStorage`, `sessionStorage`, IndexedDB, a cookie or a URL. Playwright runs one query end to end against the dev host (US-077, US-078).

### Latency benchmark harness

`tests/bench_latency.py` measures the four targets of US-044 at the host layer, the Arras interface the embedding host embeds, against a real Truss: 100 sequential singleton reads by key (p95 at most 20 ms), 100 invocations of a three-effect action including its change record (p95 at most 100 ms; `catalog.AssertCoverage` is a create and two links), 100 type enumerations (`describe`, p95 at most 20 ms), and the 30-record use case list (p95 at most 1 s). It is a script, not a test, so a default `pytest` never collects it; `tests/test_truss_bench.py` is `truss`-marked and runs it small on a throwaway PostgreSQL (it checks that the harness runs and that `--enforce` judges, never the targets themselves). Run it as a person who can read and write (the role `arrasdev_bench`, which holds the reader and writer role of every registered module and touches no other person):

```
uv run --extra truss python tests/bench_latency.py                  # the dev host's database
uv run --extra truss --group truss-test python tests/bench_latency.py --throwaway
uv run --extra truss python tests/bench_latency.py --http --repeat 2 --first-calls 4 --enforce
```

The database is the server `--url`, `ARRAS_TRUSS_DEV_URL` or `~/.arras/truss-dev.env` names (the dev host's own, the same way `python -m arras.devhost --truss` finds it), or a throwaway with the three samples seeded. The table has p50, p95, p99, maximum and mean for each operation after a warm-up (`--warmup`, 10; `--runs`, 100; the percentile is the nearest rank), the database round trips per call, the time spent waiting on the database and the process's own CPU time per call. `--statements` prints the statements of one call of each operation with the time and kilobytes each took; `--first-calls N` times the first call of each operation on a new Arras and a new connection; `--repeat` runs the set again; `--json` keeps the numbers. The machine's load average and its busiest processes are recorded before each run, and a series run above a load of 4 is labelled not quiet. `--enforce` exits 1 when an acceptance criterion's p95 misses its target; without it the exit is 0.

Series:

| Series | What it is | Judged |
|--------|------------|--------|
| in-process, warm | `Ontology` calls (`query` of the console's entity statement, `invoke`, `describe`) over one kept connection per person, as a pooling host supplies them | The four acceptance criteria |
| in-process, cold | The same, with a new connection for every call, as the dev host's own sources make them | No: it shows what a connection costs |
| http | The same operations over a running dev host (`--http`, default `http://127.0.0.1:8010`): the console's GraphQL and the operator surface, one connection kept to the host, one to the database per call | No: it adds the server, JSON and the host's per-call connection |

Extras beside each criterion: a read by key without the facts, a two-effect action (`AddSolution`), a one-effect update (`RenameUseCase`), a one-effect create (`pizza.AddCountry`), `modules`, the list with the facts and the whole list (limit 100). Every action is a distinct write (a key of the run's own), so none is a replay; the coverage assertions and solutions are retired afterwards and the renamed use case is renamed back (an aborted run's leftovers are swept at the next start), a write Truss answers `busy` is asked again and counted, and the countries of the create stay because no declared action deletes one (`--no-create` leaves them out).

What a run does not cover: the embedding host, a Databricks app's network round trip, Lakebase (its branch, its scale-to-zero resume, its connection pooling) and Unity Catalog. The database is a PostgreSQL 18.6 on the same machine, so the round trip is a loopback socket (0.1 ms for a trivial statement) and the numbers are a floor for a remote database. Results are in the Truss adapter plan (B6, and B7 after the one-catalog-read-per-call change, whose revocation tests are `tests/test_truss_call_scope.py`) and the traceability matrix (US-044).

### Truss tests on a local PostgreSQL

The `truss` tests run against a fresh local PostgreSQL 18.6 per run, with Truss installed by its own install and the module access granted as deployed (US-034). Only PostgreSQL 18.6, the version Truss runs on and Lakebase provides, is run; there is no second version to keep SQL portable across. They prove install-or-verify, grants and the adapter's behavior over Truss. A default `pytest` deselects them (`addopts = "-m 'not truss'"`); `pytest -m truss` selects them and exits 5 when none exist, so the CI job runs only where they do.

## Implementation Order

1. The conformance corpus and its runner, because the interface is validated by every adapter passing one corpus (ADR-013, CONTRACT-004).
2. The Truss adapter on a local PostgreSQL 18.6 (the `truss` marker): the corpus run against it, contract, access and grant tests.
3. The boundary check on public names and the startup tests for each failure case, which must exist before any merge that changes host startup (PRD, Risks).
4. The MCP binding tests over stdio, then the console tests.
6. The Ashlar adapter tests when Ashlar exists, and the replica and feed-position cases.
7. The host-level E2E journeys for the catalog; the inventory and a workflow client journeys follow.

## Infrastructure

| Requirement | Specification |
|-------------|---------------|
| CI Tool | GitHub Actions (`.github/workflows/ci.yml`): the `check` job syncs the extra `truss` so strict pyright covers the adapter, the `test` job runs the suite without Truss and with the pinned Weft parser (`weft-sql` 0.4.49, the version Truss pins), and the `truss` job (TR-04) syncs `--extra truss --group truss-test` and runs `pytest -m truss` with `ARRAS_REQUIRE_TRUSS=1` (60-minute timeout). The `truss` tests of the connection layer cover a lost backend, a quarantine flag set on a live connection and an aborted write transaction; Truss 0.0.45 has no deterministic trigger that quarantines a live connection, so the flag path is tested instead. Truss 0.0.45 also reports every `ValueError` inside an operation as one `invalid_transaction` message, so an operation outcome of that code is tested as the generic `unreachable` mapping and only the adoption step maps a profile refusal. Each repository runs the public-name boundary check (CONTRACT-005). |
| Test DB | A local PostgreSQL 18.6 through `pgserver-pg18`, fresh per run, a local role per test user, Truss's own install; a Lakebase branch for the benchmark |
| Services | A embedding host for E2E and the benchmark; the MCP process over stdio; a Databricks SQL warehouse on Unity Catalog and Ashlar, neither available yet |

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Ashlar is not built, so the replica side runs only against corpus positions and a test double | Replica behavior is unproven against the real store | Mark replica cases by backend kind; rerun the corpus on the real adapter when it exists |
| No measurement through the host exists, and resume latency is unmeasured | Latency targets cannot be claimed | Run the harness on a Lakebase branch; report the first request after suspend separately |
| How the embedding host hands a token to a running MCP process is open | End-to-end MCP token refresh cannot be tested against the real host | Test the token-file re-read in isolation (US-051-AC2); test the host path when decided |
| Truss's isolation by role membership is Truss's own behavior | Grant tests may not match deployed behavior | Run the grant tests on the local PostgreSQL first; confirm on Lakebase |
| Flaky or slow tests from a local PostgreSQL per run | Slow feedback (registration takes about 2 s, a write about 0.5 s) | A fresh instance per run, the `truss` marker, and only the tests that need Truss marked |

**Known Gaps**: no story test plans exist, so per-criterion rows are not yet authored; the test technology for the corpus runner, the harness and the Ashlar double is open; no line-coverage target is recorded; the security testing requirements beyond access tests are open.

## Build Handoff

**Commands**: `pytest` | coverage command not recorded. `ruff check`, `ruff format --check` and `pyright` run alongside; `uv sync` reproduces the environment (ADR-010). How each is invoked through `uv` is not recorded.
**Priority**: the order in Implementation Order.

**Blocking Gate**:

- `ruff check`, `ruff format --check` and `pyright` pass before a change lands (ADR-010).
- The Truss adapter passes every corpus case for the operations it declares (US-024).
- The public-name boundary check passes in each repository (US-033).
- The startup tests for each failure case pass before any merge that changes host startup (PRD).
- The latency targets are met on a Lakebase branch (PRD, Success Criteria).

## Open Questions

- [ ] What line-coverage target applies, if any? Ask Erik LaBianca.
- [ ] Which technology runs the conformance corpus, the benchmark harness and the Ashlar test double, and which CI tool runs them? Ask Erik LaBianca and the host integration owners.
- [ ] Who authors the story test plans, and in what order? Ask Erik LaBianca.
- [ ] How are the first request after suspend and Ashlar interactive reads budgeted? Ask the platform owner and the Ashlar project.

## Later 0.0.49 adoption and managed qualification gates

The separate adoption branch first verifies exact public Truss 0.0.49 artifact
identity and keeps Weft 0.4.51 fixed. Pure factory/lifecycle tests prove immutable
tuple forwarding on fresh installation, strict empty defaults, no stored-policy
update on reconnect, bounded named refusal, rollback and unchanged outer failure
precedence. Base imports remain SDK/I/O-free; public signatures/catalog stay in
parity. Historical 0.0.48 results and declared corpus limits are not relabelled
as 0.0.49 qualification.

The executable Lakebase harness uses only real public Arras/Truss operations and
independent native observations after an explicit target/authorization/fixture
handoff. Offline negative controls refuse absent or mismatched provider/resource
scope, credentials, hashes, symlink/alias paths, malformed manifests and incomplete
case membership before fixture/driver loading or connections. Synthetic controls
qualify only these gates. Safe original case receipts preserve failures,
uncertainty and cleanup separately; no credential, DSN or raw error prose is
persisted.

Required managed schedules follow Truss MP-01–06: populated durable state through
restart; original ended-session/lease refusal; actual managed role/ACL behavior;
complete feed/ACK independence; enforceable settings and uncertain outcomes;
and required extension correspondence. TLS/person-token/credential-refresh,
dry-run residue, caller work/savepoints and quarantine also require actual
target evidence. Caller-owned cases use public Truss directly and are not
advertised as Arras active-transaction support. Missing provider restart/refresh
controls or observation privileges remain blocked/not_run; no zero-case, skipped
or partial receipt can pass the full managed scope. Campaigns require separately
coordinated resource slots. The [local qualification](../04-build/evidence/truss049-adoption-20261023/local-qualification.json)
records source `40ed2481507f11a61ed81260fbfffbfc8ff91eba`: 199 local adapter
cases and two local strict-probe transaction-mode cases passed. The latter
characterize strict-install success and owned cleanup; they do not exercise a
managed platform-grant refusal. Fresh installed qualification and actual
Lakebase/MP-01–06 acceptance remain unrun in this tranche. Historical evidence
and the eight declared corpus limits remain unchanged.

### PR 9 execution and reusable identity setup

The human selected completion of the fresh installed 0.0.49 and actual Lakebase
gates before review, merge and publication. Source CI and local PostgreSQL
evidence cannot replace either gate. The managed campaign must pass all twelve
named cases and independently verified owned cleanup on the selected artifacts;
blocked, skipped, interrupted or partial campaigns do not pass.

Schema 2 permits an explicitly mixed authentication cohort. Its exact four-actor
map and `human_actor: writer` are repeated in target and authorization. One real,
ordinary human OAuth writer suffices for the human criterion; the other distinct
ordinary actors may use their explicitly declared profiles. The installer remains
separate. Original issuer/subject/resource facts, fresh SQL identity, real
credential expiry and refresh, denied credentials and membership revocation are
required. Service identities cannot supply human evidence.

The human also requires avoiding repeated admin activation. One-time identity
bootstrap may use the activated Databricks admin authority, with scope and custody
recorded. Subsequent campaigns must reuse securely referenced identities and
demonstrate credential renewal, owned role operations, provider controls and
cleanup through delegated permissions without account/workspace admin activation.
Do not claim this requirement complete from identity creation alone. Reusable
identity custody and disposable database cleanup are separate. The ordinary human
SQL role must hold no effective elevated role or owned schema/database authority;
broader human control-plane rights and unrelated resources remain unchanged.

Person and managed schedules run inside the original installation interval,
before cleanup. Cancellation stops later effects and retains failure evidence;
unverified person lifecycle or restoration prevents managed follow-up. All native
inventory rows stay in memory, including generated runtime secrets; only reviewed
closed projections enter receipts. Real transport interruption and independent
reconciliation are required for uncertain outcomes, without fabricated exceptions
or assertions that a client-side fault proves server COMMIT arrival.

The person schedule preserves the administrative/person boundary in
[CONTRACT-005](../02-design/contracts/CONTRACT-005-embedding-and-lifecycle.md)
and [CONTRACT-001](../02-design/contracts/CONTRACT-001-ontology-interface.md).
When registration has already been observed, the named administrative registrar's
`document()` call must return `Refused(no_access)` at the Arras boundary. The
ordinary reader must independently retrieve the registered document. A successful
administrative read fails the registrar-authority check; an unavailable or
unexpected result cannot count as the required refusal. A real in-memory Arras
host supplies the focused regression, while actual Lakebase retains the complete
registration, reader, writer, credential, membership and cleanup schedule.

For the exact selected Truss 0.0.49 CreateProbe validation schedule, successful
dry-run rollback preserves every durable graph/history/receipt/feed/recovery row
while PostgreSQL's nontransactional allocators may advance. Inventory and compare
all sequences; allow monotonic counter-only changes during that successful
validation alone for `id_seq`, `key_storage_row_seq`, `journal_seq`,
`runtime_object_transition_seq`, `request_receipt_row_seq` and
`runtime_feed_reservation_seq`. Preserve sequence definitions and report the
allocation-gap count/digest separately. Bind this narrow exception to the exact
0.0.49 wheel/native manifest and reviewed `groups.sql`, `operations.sql`,
`layout.sql` and `feed.sql` members. Unknown changes, decreasing counters or any
durable-row change fail. Invalid/denied/revoked and restored-state controls retain
exact sequence equality. This rule requires new source/behavior review for any
future selected runtime; version labels alone cannot carry it forward.

MP-06 uses the reviewed [exact-0.0.49 extension requirements](../04-build/evidence/truss049-adoption-20261023/extension-requirements.json)
as an input, separately from actual target qualification. Source and local
catalog closure require `plpgsql` 1.0 for this ordinary native profile; the
provider's `databricks_auth` OAuth bootstrap prerequisite is observed separately.
Inventory every required extension member and its actual ordinary-role privilege
vector. Internal language handlers are not application entrypoints: do not grant
them merely to satisfy an all-true predicate. Actual source-declared public
operations and denials establish ordinary behavior. Missing correspondence or
an unreviewed source inventory blocks the case.

MP-04 qualifies a bounded semantic replica for the selected public 0.0.49
CreateProbe schedule. Decode the exact `truss-native-feed/0.1` envelope and
source-bound runtime/layout pins, including the JSON layout-profile object.
Admit only the separately checked `truss-native-owned-create/0.1` and
`truss-native-scalar-create/0.2` history carriers; unknown profiles refuse.
Preserve complete journal, reservation, source, revision and prerequisite facts,
ownership/definition/version pins, property IDs/values and safe watermark. Drain
contiguous pages for the same consumer/source/registration through one genuine
terminal empty interval within explicit page/byte bounds. Persist semantic rows,
original bytes and both canonical body/page hashes atomically with a bound
receipt; replay is idempotent and reopening preserves the complete snapshot.
Compare the full replicated Probe multiset with an independently queried source
using schema-ID/pin-bound property mapping and explicit nontruncation. Verify
each page's original ACK/reconciliation through replay and restart. Saving opaque
page bytes alone does not qualify replication or a broader adapter.

Fresh installed managed consumers must expose the independently observed exact
Truss archive digest and native/migration manifests before mutation. Use a
content-hash-verified installation whose PEP 610 metadata retains the archive
SHA-256, then compare installed payload members against the selected public
wheel. A lockfile or expected digest alone cannot substitute for the observed
archive evidence; an installer that omits it leaves admission blocked. Keep
credential references outside these artifacts and capture failed attempts
without rewriting them as later passes.


The managed strict-empty-policy installation probe uses the same 60,000 ms
statement and operation bounds as Arras's existing installer path, including its
transaction-local statement timeout. Both are within the selected public Truss
0.0.49 host's 1–60,000 ms range. Deadline cancellation remains blocked and its original failed attempt is
retained; only the expected typed platform-grant refusal can qualify the probe.
The empty policy, exact refusal context, prior caller work/settings, detach,
rollback and complete native-state equality requirements remain mandatory.
Other operation, transport-fault and performance bounds remain unchanged; this
alignment does not waive any timing assertion or permit an unbounded installer.


PR 9 requires both complete campaigns against the exact final installed Arras
wheel bytes: actual Lakebase and fresh installed macOS. Retain the canonical
release-builder wheel before running them and bind its SHA-256 to both original
receipts. The final tagged build and public-download wheel must have that same
SHA-256. Any byte change, including packaging or metadata, requires both full
campaigns rebound and rerun. Payload correspondence, earlier CI, a partial run
or an isolated successful case cannot substitute for either complete campaign.

## Current Truss 0.0.50 adoption gates — 2026-10-24

The active 0.6.1 source pins public Truss 0.0.50 wheel
`7b0483bb0c624c98515cf38ec30bbbf1ca43c1250e8880e5d00d520b4b7eec00`, source
`a687d0a226dad5745cbd909377bf99c7c1cddc66`. The source-binding record at
`docs/helix/04-build/evidence/truss050-adoption-20261024/extension-source-binding.json`
records public archive/source correspondence and the reviewed carry-forward
basis for the extension requirement; it is not an installed or database test.
Its native manifest is unchanged, and its distinct migration manifest preserves
the former 0.0.49 manifest. Existing 0.0.49 tests and receipts remain scoped to
their original wheel and target.

Before merge/tag, the exact final Arras wheel still requires both complete gates:

- Fresh-installed macOS arm64 / CPython 3.11.9 (the selected hosted workflow
  tuple): all 72 applicable corpus cases,
  with 64 passes, eight unchanged declared limits, no failures, and independent
  cleanup.
- Actual Lakebase: all twelve required cases, their authorized person/provider
  identity and lifecycle controls, and independent owned-resource cleanup.
  Reuse the already-provisioned ordinary actors; no VM or repeated administrator
  provisioning is required.

Both receipts must bind to identical canonical Arras wheel bytes. Historical
0.0.49 receipts, source-local tests, source binding, and partial schedules do
not satisfy either current gate. The public artifact source comparison does not
imply a new target database observation or native execution result.
