---
ddx:
  id: implementation-plan-truss-adapter
  type: implementation-plan
  activity: build
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-21
  authoring:
    home: repo
  links:
    - id: FEAT-004
      kind: informed_by
    - id: FEAT-005
      kind: informed_by
    - id: FEAT-006
      kind: informed_by
    - id: ADR-006
      kind: informed_by
    - id: ADR-010
      kind: informed_by
    - id: ADR-012
      kind: informed_by
    - id: ADR-013
      kind: informed_by
    - id: ADR-014
      kind: informed_by
    - id: ADR-015
      kind: informed_by
    - id: ADR-017
      kind: informed_by
    - id: ADR-020
      kind: informed_by
    - id: ADR-026
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
    - id: CONTRACT-008
      kind: informed_by
    - id: CONTRACT-009
      kind: informed_by
    - id: CONTRACT-010
      kind: informed_by
    - id: CONTRACT-011
      kind: informed_by
    - id: TP-001
      kind: informed_by
    - id: TD-001
      kind: informed_by
---

# Build Plan: the Truss adapter

## Scope

Build the Truss adapter, a reader and a provider (CONTRACT-004), over Truss's public Python toolkit, and prove it by running the backend conformance corpus against a real Truss on PostgreSQL. A host registers it under a name it chooses and places modules on it (CONTRACT-005); nothing in `core` names Truss.

Done means: started with a per-person connection source, Arras registers a module, validates and registers changes under the person's `schema` grant, serves Weft statements through Truss, applies actions with preconditions, idempotency, dry-run and batches, imports records, answers `reached`, and returns the registered document, all through Truss and as the person, with the observable behavior the in-memory adapter gives.

Out of scope: the Ashlar adapter and the Truss-to-Ashlar feed; text search on Truss (declared `Unsupported`, CONTRACT-010); any change to Truss (asks are written generically in the requirements note).

This plan is a separate goal from the other plans in this directory (the Operator Console, schema administration, Weft delegation), which it builds on and does not edit.

**Pinned Truss**: `truss-toolkit==0.0.45` (native runtime `0.72`, manifest SHA-256 `71c4c3d4c05a2229c4cdec1643cabe0da7055965f0b0d23195e83ad780042a2e`, layout `1.0`, `weft-sql==0.4.49`, UMF core 0.10.0 source), psycopg 3.3.6 binary with libpq 18.6 on PostgreSQL 18.6, no Bun, Node or other process (Truss prepares a module in an embedded V8, `mini-racer` 0.14.1). Fresh installations only: Truss upgrades nothing.

**Governing Artifacts**:
- [FEAT-004](../01-frame/features/FEAT-004-backends.md), [FEAT-005](../01-frame/features/FEAT-005-access.md), [FEAT-006](../01-frame/features/FEAT-006-embedding-and-lifecycle.md)
- [ADR-006](../02-design/adr/ADR-006-embedded-library-on-psycopg-and-the-truss-toolkit.md), [ADR-012](../02-design/adr/ADR-012-own-postgres-database-lakebase-deployed-embedded-locally.md), [ADR-013](../02-design/adr/ADR-013-arras-is-an-ontology-interface-over-named-backends.md), [ADR-014](../02-design/adr/ADR-014-reads-state-their-consistency-and-freshness.md), [ADR-015](../02-design/adr/ADR-015-writes-are-umf-actions-applied-by-providers.md), [ADR-017](../02-design/adr/ADR-017-backends-are-reached-with-the-users-own-token.md), [ADR-020](../02-design/adr/ADR-020-contract-rules-are-checked-against-an-executable-model.md), [ADR-026](../02-design/adr/ADR-026-schema-administration-runs-as-the-person-on-a-surface-of-its-own.md)
- [CONTRACT-001](../02-design/contracts/CONTRACT-001-ontology-interface.md), [CONTRACT-002](../02-design/contracts/CONTRACT-002-type-registry-and-placement.md), [CONTRACT-003](../02-design/contracts/CONTRACT-003-actions.md), [CONTRACT-004](../02-design/contracts/CONTRACT-004-backend-contract.md), [CONTRACT-005](../02-design/contracts/CONTRACT-005-embedding-and-lifecycle.md), [CONTRACT-010](../02-design/contracts/CONTRACT-010-graph-browser-view-and-search.md), [CONTRACT-011](../02-design/contracts/CONTRACT-011-schema-administration-surface.md)
- Design notes: [truss-requirements](../02-design/truss-requirements.md), [truss-catalog-mapping](../02-design/truss-catalog-mapping.md), [truss-group-mapping](../02-design/truss-group-mapping.md), [ashlar-feed-position-question](../02-design/ashlar-feed-position-question.md). TR-05 rewrote the catalog mapping note and TR-07 the group mapping note to the `Provider` as built.
- Related plan: [implementation-plan-weft-delegation](implementation-plan-weft-delegation.md) (Arras passes Weft SQL to the backend)
- Test: [TP-001](../03-test/test-plan.md), [traceability](../03-test/traceability.md); [TD-001](../02-design/TD-001-contract-rules-formal-specification.md)
- Module boundaries: `tests/modules_check.py`, architecture.md Module Boundaries

## Design Decisions

These are made here so the slices do not reopen them. TR-01a writes D1 to D6 into the contracts and ADRs.

- **D1. Every receipt carries a token.** Truss returns a receipt token only after commit and a repeat of a keyed request, and never for a request with no key. The adapter therefore always supplies a request identity (the idempotency key's request id, or a fresh UUID when the caller gave none), commits, and repeats the request once in a new transaction to obtain the token. `Receipt.token` stays required, the corpus's keyless steps that save a token keep working, and an unknown commit is recoverable for a keyless invocation too. The cost is one extra short transaction per write (the measured replay is 0.02 s).
- **D2. `reached(principal, token)`.** Truss answers inside the person's transaction and authorizes the person, so `reached` takes the principal (CONTRACT-001, 004, `Backend`, the fakes, core `_await`). The corpus's `reached` steps name a person.
- **D3. The installer is not the registrar or the importer.** Truss refuses ordinary business calls from an elevated installer and its installer needs `CREATEROLE` and database `CREATE` with grant option. The factory takes two connection inputs: the per-person `ConnectionSource` and a separate trusted installing connection used only by `migrate`, the explicit upgrade, module-access configuration and the install-state read behind `status()` (Truss limits status to the installer and registrar; with no installing connection the backend is `not_configured`). A person registers under the `schema` grant, which on Truss is registrar membership, installation-wide, whereas Arras's grant is per module; that gap is a documented limit the corpus tags.
- **D4. `migrate` is install-or-verify; there is no upgrade.** `Arras.migrate()` runs the adapter's install-or-verify on the installing connection under a `pg_advisory_xact_lock` taken in the install transaction, so concurrent `migrate()` calls run one install; it verifies a present Truss and reports `unsupported_version` for another release, which is recreated (Truss refuses every upgrade). `start` does not install; a host that wants an install at start calls `migrate()` itself. `migrate` grants no module access: Truss refuses a whole grant batch for any module it has not accepted, and the installer cannot list accepted modules, so `configure_access` grants per module after registration. Alembic and the `arras` history schema leave ADR-006 and CONTRACT-005.
- **D5. A poisoned connection is closed by Arras.** `ConnectionSource` has no channel to tell the host's pool to drop a connection; the contract says Arras closes a connection Truss quarantined and the pool discards closed connections.
- **D6. The backend name is the host's.** `BackendInfo.name`, `Revision` and `Freshness` are keyed by the name the host registers; the factory takes it.
- **D7. Query rows.** Truss's query has no `limit`: it has `maximum_rows` (default 1,000, ceiling 10,000) and refuses with `limits` when a result, its bytes or its scan exceed a bound. The adapter passes `maximum_rows=10000`, caps rows at Arras's `limit` client-side to set `truncated`, and maps a Truss `limits` refusal to `Unsupported` as a declared bound of the backend. The scan bound (`maximum_scan_rows`, 10,000 at most, checked before filters and `LIMIT`) and the byte bound (`maximum_bytes`, 1 MiB by default) are Truss's too and surface as the same `limits`; a type with more than 10,000 rows is not queryable on Truss.
- **D8. A catalog cache grants nothing.** Core calls `catalog(principal)` on every operation and `describe` up to three times. On Truss that is a reader catalog, an accepted document and a parse, about 0.5 s. The adapter caches the parsed `ModuleInfo` per (document id, accepted digest, source catalog revision) and each person's last reader-catalog snapshot with Truss's validator (one for a read-only and one for a read-write call), and asks Truss, as the person, whether the catalog changed on each call; Truss re-answers the person's access every time and the cache never answers a question about access.

## Shared Constraints

- Python 3.11, `uv`, a committed `uv.lock`, no `requirements.txt` (ADR-010). Every slice keeps `uv run pytest`, `ruff check`, `ruff format --check` and `pyright` clean, with the adapter's dependencies installed for the type check.
- Every Truss call is made over a connection authenticated as the person; no service identity serves a user's read or write (ADR-017). The adapter holds no role map and no access decision (CONTRACT-004). A test asserts it by reading `session_user` inside each call.
- Truss is reached only through its public toolkit (`truss-toolkit`), pinned exactly with its driver tuple. The adapter imports no `truss._*` module.
- Truss, Ashlar and UMF documents never name Arras (CLAUDE.md); asks to Truss are written generically.
- The adapter belongs to a new group `adapters` (foundation, domain, contract, and the Truss toolkit). `core` never imports it. A host, or a binding that builds backends from configuration (`mcp`, `devhost`), constructs it and registers it with `Arras.start`. `ALLOWED` in `tests/modules_check.py` gains the `adapters` group and lets `mcp` and `devhost` import it. `tests/test_modules.py` caps a module at 926 lines: the adapter is several small modules.
- The base install does not require Truss or psycopg. Truss is the optional extra `truss`. Nothing on the machine beyond the wheels is needed: Truss prepares a module in an embedded V8 and spawns no process, so registration, `apply`, key lookups and imports work with no Bun, no Node and an empty `PATH`; the adapter passes no executable path to any of them.
- Adapter calls emit the existing telemetry events and attributes (CONTRACT-008, ADR-018): the backend name, the operation and the outcome class, never a credential or an input value.
- A capability is declared only when the adapter serves it (CONTRACT-004); an unsupported shape raises `Unsupported`. Arras does not synthesize a capability Truss lacks.
- Truss binds writes to the exact accepted source bytes of a document; the adapter passes them on every write and compares derived rows before registering, so a rewritten but equal document creates no Truss revision.
- Generated keys are derived deterministically from the request id and the effect index, because Truss's request fingerprint covers the whole input.
- Host-owned work this plan depends on and does not do: praxis supplies the per-person `ConnectionSource`, aligns its psycopg with 3.3.6, and provides the installing connection and the module roles.

## Implementation Slices

HELIX order: the test plan and the failing conformance case come first in each slice. Each slice is a commit that leaves the tree green. A slice marked *needs Truss* names the Truss behavior it uses and the fallback if it is absent.

| Slice | Story / Area | Governing Artifacts | Depends On | Validation Gate | Notes |
|-------|--------------|---------------------|------------|-----------------|-------|
| TR-00 | Bring the branch up to date with `main` (the corpus is at version 7, `Provider`, `query(Statement)`, named backends, `validate_register`); re-run the spike on Truss 0.0.2 and 0.0.3 | none | None | `uv run pytest` (1,633 passed), ruff, pyright; the spike's 25 observations match on 0.0.2 | The earlier plan was written against a stale branch. Evidence in Continuation Evidence. |
| TR-01a | Decisions D1 to D6 as contract text, no code: CONTRACT-001, 004 and 005 (the `reached` principal, a receipt always carries a token, the installer split and the factory's second connection, install-or-verify in `migrate()` and explicit upgrade, the closed-poisoned-connection clause, the backend name argument, the pinned driver tuple), and ADR-006, ADR-012 rewritten in place to the current design (Alembic and the `arras` history schema removed). CONTRACT-004's Truss adapter table is rewritten to the public toolkit (`group` apply, import, reader catalog, `query_in_transaction`, `reached_in_transaction`) | ADR-006, ADR-012, CONTRACT-001, 004, 005 | TR-00 | Contracts and ADRs rewritten to the current design, no change history in them; the fakes and tests unchanged; docs-only commit | Hard to change later, so first. |
| TR-01b | Code for D2 only: `reached(principal, token)` in `Backend`, the fakes, core `_await` and its callers, `operate/__init__.py` (lines near 123 and 165) and `operate/openapi.py` (near 328) with `ui/openapi.json` regenerated, `mcp/server.py`, `testing.py`, `devhost.py`; the conformance runner and corpus (the `reached` steps gain an `as`); the memory harnesses' `corpus_version` (7) and the corpus `version` bumped to 8 together; tests: `test_properties.py`, `test_routing.py`, `test_placement.py` (both override `reached`), `test_conformance.py`, `test_core.py`, `test_fakes.py`, `test_operate*.py`, `test_mcp.py`, `test_console.py`, `test_openapi_contract.py`, `test_telemetry.py`. `Receipt.token` and the UI are unchanged; bump `CONTRACT_VERSIONS["backend"]` to 4 and `tests/test_public_api.py` with it | CONTRACT-001, 004, 006, 009 | TR-01a | `uv run pytest`, `ruff`, `pyright`, `tests/test_openapi_contract.py` and the OpenAPI drift test; the executable model (`test_properties.py`) updated; `run_corpus` reports no `newer_corpus` | The wide edit is mechanical; the corpus bump needs both numbers moved in one commit or the harnesses report a newer corpus. |
| TR-02 | Test plan and traceability rows, then dependency and skeleton. The corpus cases the adapter needs that are missing (a rewritten-equal registration is unchanged; a non-member write is `Refused`; a non-member `reached` is `Refused`; a retry with generated keys matches; an undeterminable token is `Unavailable` already has `freshness.undeterminable-token-is-unavailable-not-false`, an outage, which TR-03's harness `outage` must produce on Truss); `truss-toolkit[native,query]==0.0.3` as the optional extra `truss` resolved from a committed find-links page (`tools/find-links/index.html`) whose anchors carry the releases' `SHA256SUMS` digests, so `uv.lock` hashes every toolkit and Weft file and `uv sync --locked --extra truss` verifies them; the `adapters` group and its `ALLOWED` entry with a negative control; a stub backend; the `truss` pytest marker registered with `addopts = "-m 'not truss'"`; CI: the `check` job syncs `--extra truss` so strict pyright covers the adapter; the test job's pinned Weft parser (`weft-sql 0.4.2`) is moved to the version Truss pins (`0.4.5`) so the memory adapter and Truss compile with one parser | TP-001, ADR-010 | TR-01b | `uv sync --locked` and `--extra truss` resolve from the lock on Linux x86_64 and macOS arm64 and Python 3.11 (3.12 and 3.13 only if the `pgserver-pg18` and Truss wheels exist for them; check before promising); `tests/test_modules.py` with the negative control; `uv build` and the wheel import smoke test with no Truss installed; default `pytest` collects no Truss test | *Distribution decision, recorded*: the host vendors the pinned wheels (or passes the find-links); the Truss and Weft wheels are on no package index and a release carries only the base dependencies. Praxis's vendor script already vendors locked wheels into the app build, so no mirror is built here. Recorded in CONTRACT-005 (Runtime) and ADR-010. A host may still choose a mirror later; the published wheel's extra metadata is the same either way. |
| TR-03 | Test harness: `tests/truss_harness.py`, a `Harness` over a local PostgreSQL 18.6 (`pgserver-pg18` through `truss-toolkit[local]` in a separate dependency group `truss-test`, never a plain dev dependency): Truss's own install, roles per person, module access grants, `foreign_token`, `outage`, `expire`; every corpus case fails for the stub | CONTRACT-004 (conformance corpus) | TR-02 | A test (not marked `truss`, so it runs wherever the `truss-test` group is synced and skips with the reason elsewhere; it fails instead when `ARRAS_REQUIRE_TRUSS=1`, which the TR-04 job sets) asserts the stub's corpus report has no case ok, covers exactly the 63 `store` and `reader` cases, and that every message names the stub; an always-on test shows a harness that cannot build its world passes no case; `uv run --extra truss --group truss-test pytest -m truss` runs the same corpus run and the harness self-tests | The harness installs through Truss directly; `migrate` comes in TR-13. |
| TR-04 | Connection layer. A per-principal connection source to a Truss assembly: `BEGIN ISOLATION LEVEL READ COMMITTED READ ONLY` or `... READ WRITE` as the call needs, `SET LOCAL statement_timeout` between 1 and 60,000 ms (Truss requires it before adoption; Truss's adoption does not check `SET ROLE`, so the adapter checks the session role is `none` itself, after `BEGIN` and before adopting, and never sets it), adopt, construct the assembly, detach and settle; a call with no token is `Refused` before any connection; a quarantined connection is closed (D5); the `truss` CI job is added here, running `uv sync --locked --extra truss --group truss-test` then `pytest -m truss`, because a job that selects no tests exits 5 | ADR-017, CONTRACT-005 | TR-03 | Unit tests with a recording connection; a Truss-marked test that a call runs as that person (`session_user`) and that a quarantined connection is closed; `Refused` before any connection with no token | One host and one assembly per call, not per pooled connection: the assembly binds one adopted connection and building host and assembly costs under 0.1 ms, so nothing is cached (the connection and the first catalog read are the cost). |
| TR-05 | Registry: `describe` (roles reader and provider, per-type `Capabilities`, `WeftSupport` from Truss's compile selection), `catalog`, `document`, `status`, `register`, `validate_register`, `attach` (not applicable). Reader catalog and accepted document; `register` with a request key from the document digest and derived-row equality checked first (an equal document returns unchanged without calling Truss); `validate_register` is a prepare and accept in a transaction the adapter rolls back, giving `changed`, `violations` and `report`; the schema grant is Truss registrar membership (installation-wide against Arras's per-module grant: a documented limit, D3); the catalog cache of D8; catalog failure codes mapped; update the two mapping notes to `Provider` | CONTRACT-002, 004, 011; ADR-026; truss-catalog-mapping | TR-04 | The registry and schema corpus cases pass on Truss; a rewritten-but-equal document creates no revision; a non-registrar is `Refused`; an ordinary reader sees exactly their modules; `validate_register` leaves no catalog row | *Needs Truss*: `expected_revision` checked in the same serialized step as acceptance (CONTRACT-004). Truss has no such parameter, so until it does the adapter compares the revision in the same transaction before `accept`, the corpus tags that case as a documented race, and the ask is in the requirements note. Evolution beyond new documents is `Unsupported` until Truss enables it. |
| TR-06 | `query`: pass `Statement(sql, params)` to Truss's `query_in_transaction` (Arras defines no dialect; Truss compiles with Weft and runs as the person, read-only). Select the `document_ids` that hold the module; pass `maximum_rows=10000` and cap rows to Arras's `limit` client-side with `truncated`, mapping a Truss `limits` refusal to `Unsupported` (D7); map parameters (Python `int` and `Decimal`; refuse floats); `Invalid(unknown_type)` for a module the person may not read, before any type-dependent step and without revealing existence; `Unsupported` for a statement that reads outside the module, for Weft's refusals (timestamp and binary filters, multi-hop relationships, optional grouped keys) and for `text` (no search); whole-entity rows carry the appended fact columns (`_version`, `_created_by`, `_created_at`, `_updated_by`, `_updated_at`, and for imports `_original_author`, `_original_at`, `_load_id`); `Freshness` from Truss's read position, stated as a conservative lower bound | CONTRACT-001, 004, 010; ADR-014; Weft delegation plan | TR-05 | The read corpus cases pass or are tagged to a declared Weft profile; a differential test runs the same statements on the memory adapter and on Truss and compares rows; a non-member's statement is `Invalid(unknown_type)` | *Verify first*: Truss has the eight fact columns as SQL functions; confirm that `alias.*` projects them. If not, the adapter reads them in the same transaction or the ask is filed. Truss authorizes per document, so a statement over one module of a multi-module document needs read authority for every module in it; the corpus marks that. Order is explicit: a statement with no `ORDER BY` has no order promise. A read of a module the person was shown is one operation: `query_with_catalog_in_transaction` (B9) |
| TR-07 | `apply`: plan to group (create, update, delete, link, unlink), the five precondition kinds, `asserted_origin` (`x-action`), request identity from the idempotency key, deterministic generated keys, the accepted-document handover, merged updates and a delete that removes the object's edges (Truss bumps a version per update operation and refuses to delete an object that has edges), result to `Receipt`, the failure map (`PreconditionFailed` with the caller's ids, `Conflict`, `Invalid`, `Refused`, `Unavailable`), commit and unknown-commit retry, D1's replay for the token; `expected_version` is never sent (no plan holds a version, and a version taken at lookup changes the input a keyed retry rebuilds); the group mapping note is written to `Provider` | CONTRACT-003, 004; truss-group-mapping | TR-05 | The action corpus cases pass; an idempotent retry after a lost commit returns the original receipt; a failed precondition leaves no row, journal row or receipt; a stale `expected_version` is mapped to `Conflict("version")` (no Arras plan can produce one) | `apply_in_transaction` returns a typed `UnauthorizedPerson` for a reader; the raw `42501` comes from `group_context_in_transaction`, the type and relationship reference lookups and the reads, which the adapter maps to `Refused`. *Needs Truss* (R13, R18.2): typed refusals from those calls. A group is at most 128 operations (Truss), a plan up to 1,000 (Arras): a larger plan is `Unsupported`. |
| TR-08 | `dry_run`, `apply_batch` (atomic: one group; non-atomic: a group and transaction per plan, request id `module.Action:key#index`), `stop_on_error` | CONTRACT-003, 004 | TR-07 | Dry-run and batch corpus cases pass; a dry-run leaves no data, journal row or request receipt; a non-atomic batch reports partial results | A deferred violation must surface inside the dry-run call; a corpus case compares it with the real apply. |
| TR-09 | `import_records`: object and relationship records, `load_id`, `initiated_by`, per-record created, skipped, rejected, provenance; edge-first imports resolve both endpoints in one transaction | CONTRACT-003 (bulk), 004 | TR-07 | The import corpus cases pass (identity, skipping, deleted stays deleted, provenance) | The importing principal is one TR-01a names; Truss's import needs the person's writer role. |
| TR-10 | `reached` and `at_least`: `reached_in_transaction` with typed results (`True`, `Invalid` for `invalid_token` and for a token over 16,384 characters, which Truss classifies as `resource` client-side; `Refused` for `authorization`, as CONTRACT-004 and the corpus require; `Unavailable` otherwise, including a `resource` reason from the backend); the token handling in `apply`; routing `at_least=token` to the record store | CONTRACT-001, 004; ADR-014 | TR-07, TR-01b | The freshness corpus cases pass on Truss; garbage is `Invalid`; an undeterminable token is `Unavailable`, never `False` | `False` comes only from the replica's feed path, outside this slice. The replica side (Ashlar publishing applied progress) is a separate plan. |
| TR-11 | Audit reads `changes` and `loads` from Truss's group and load audit pages, read as the person under Truss's own audit grant (separate from reading and writing); the mapping and its stated limits are CONTRACT-004's (observed time, no key or version, load discovery); `describe().audit` is true | CONTRACT-004, 009 | TR-07 | The journal corpus cases pass on Truss; the audit grant is not implied by reading or writing and a revoked auditor's next call is refused | B8. |
| TR-12 | Conformance and model. The full corpus passes on the Truss harness at the adapter's declared capabilities; the executable model (ADR-020) runs the Truss adapter in the differential property tests; hand-written mutants of the pure mapping tables (plan to operation, result to receipt, failure map), each run against the suite and all killed (no mutation tool is added); a Truss-marked test for a non-member with a garbage token (`Invalid` on Truss, `Refused` on memory) | ADR-020, TD-001 | TR-06 to TR-10 | `uv run pytest -m truss` green over the whole corpus; the property suite green; the mutants killed | The gate for calling the adapter conformant. |
| TR-13 | Lifecycle: a factory builds the adapter from a per-person `ConnectionSource`, a separate installing connection and the backend name (D3, D6); a host or binding registers it; `Arras.migrate` calls an optional adapter `migrate` (D4: install-or-verify under a `pg_advisory_xact_lock`; module access grants from the host's roles are the separate `configure_access`, one locked transaction per module, after registration; `migrate()` takes no principal, so the installing connection is the factory's); `upgrade` is a separate explicit call; `status` reports `not_configured`, `unsupported_version`, `unreachable`, `access_denied` and a failed install as `migration_failed`; the one install bound is `migrate`'s `timeout` (`start` has none); bump `CONTRACT_VERSIONS["lifecycle"]` to 2 and `tests/test_public_api.py` with it, because the lifecycle surface (D3, D4, D6) lands here | CONTRACT-005, FEAT-006 | TR-05 | Embedding tests: Truss absent, installed, wrong release, unreachable; two instances migrating together run once; `arras.boundary` host seam check passes | Install needs `CREATEROLE` and database `CREATE` with grant option; the roles are the platform's. `core.migrate` is a stub today and gains the optional call. |
| TR-14 | Bindings: the MCP process builds a Truss backend from its typed configuration (`arras.mcp.config`, ADR-019); the dev host and console run against a local PostgreSQL with Truss (the sandbox stays on the memory adapter) | ADR-016, ADR-019; CONTRACT-006, 007, 009 | TR-12, TR-13 | MCP, console and operate tests pass with a Truss backend; the dev UI browses a registered module from Truss | Reads the environment only in `arras.mcp.config` (twelve-factor). |
| TR-15 | Documentation and release: contracts, ADRs, PRD sketches, architecture and README match what was built (the extra, the driver requirements, the Lakebase caveat); the Truss requirements note at its final state; a release | all | all | CI green: lint, format, types, boundary, wheel smoke, the `truss` job; second-model review addressed | Cutting the release is the user's. |

**Cut order** (cut the first line first): TR-11 (audit reads); TR-09 (imports) if the first consumer does not import; the differential property run; the unchanged-registration corpus tags beyond the core cases. Never cut TR-00 to TR-08, TR-10 or TR-12.

## Execution Contract

The user authorizes implementation separately from plan readiness. Execute the ordered slices through their validation gates and the exit criteria; a slice is a reviewable commit, not a separately scheduled issue. Write the failing conformance case before the code. Stay within Scope. Stop for: a conflict between a contract and Truss's behavior that needs a decision, the Truss API changing under the pinned version, a missing platform privilege or role the host must supply, and a slice that would force a Truss change (write it as an ask, do not work around it silently).

Token and spending basis: unknown. The session has no metering for this work and no prior usage evidence for a comparable adapter; the user sets a total spending ceiling when authorizing execution, and reaching it requires a disposition of the remaining slices, not an automatic increase. The cost drivers are TR-01b (a signature change through core, bindings and UI), TR-07 (writes) and TR-12 (conformance and mutation checks).

Truss is experimental: pin it exactly, run the `truss` job on every change, and treat a failing job after a pin bump as a finding about Truss, not a reason to loosen the corpus.

## Continuation Evidence

On interruption, record the completed slice IDs with the test evidence, remaining slices, the Truss version pinned, open Truss asks and their state, and the next action, beside this plan. On resume, reconcile the record with the diff and with `uv run pytest -m truss` before continuing.

Open Truss asks (in the requirements note): typed refusal for a non-member on group and read calls (R13); a required property in an existing record's `umf.ddd` form (R16.5) and a nameless element refused at registration (R16.4); the relationship columns of a whole entity (R17.2) and replay by request identity (R18.3), which pin nine corpus cases; a set-based import (R19.5); validation of what an import stores (R19.1); a commit time or order, the key in an op and a discovery that lists relationships-only invocations for the audit pages (R20); an install state for a person enrolled in nothing (R22); a package index (R10); a managed-database installer.

## Optional Tracking

None selected. This plan is one tracked goal.

## Validation Plan

- [x] Failing conformance cases exist before each slice's implementation (each slice's row)
- [x] `uv run pytest`, `ruff check`, `ruff format --check`, `pyright` (with the `truss` extra installed) and the module boundary check pass (TR-15 run: 2,259 passed)
- [x] `uv run pytest -m truss` passes over the full corpus on the pinned Truss (178 passed in 576 s (9 min 36 s) at a load near 8 to 11 on 0.0.44, B8; the six corpus cases that truss-requirements R18.18 ended pass with no judgement of the adapter's own, B5)
- [ ] The base wheel installs and imports with no Truss or psycopg (owner: CI. The smoke in `ci.yml` and `release.yml` asserts it; it needs the UI build and has not run locally; the base import is checked in `tests/modules_check.py`)
- [ ] `uv sync --locked` resolves the extra on Linux x86_64 and macOS arm64, Python 3.11 to 3.13 (open: CI runs the `check` and `truss` jobs on ubuntu with the default Python and the developer's macOS arm64 ran it; no matrix. Accept and record, or add a matrix)
- [x] Behavior changes update the contracts, ADRs and PRD sketches (TR-01a to TR-15)

## Risks and Rollbacks

| Risk | Impact | Response | Rollback |
|------|--------|----------|----------|
| Truss's API changes between releases (it is `0.0.x`, experimental) | H | Pin exactly; the `truss` job and the corpus are the tripwire; map Truss's types in one module so a change lands in one place | Pin the previous release; the adapter is an optional extra |
| Registration cost: `prepare_catalog` takes about 0.5 to 0.9 s per registration in Truss's embedded V8, and `prepare_acceptance`, which a registration does not call, refuses a document whose report evidence passes Truss's caps (4 MiB of owner observations, 16 MiB of bridge output) with `PreparationRejected` (truss-registration-evidence-spec) | M | Owner: Truss, for the evidence size; declare `latency_class` honestly | If a module cannot register on Truss, it serves from the memory adapter and the dev host says so (an `Unsupported` that names the Truss reason); the other backends are unaffected |
| The Truss wheels are not on the package index (the release script walks only base `dependencies`, so an extra is invisible to it) | M | Decided in TR-02: the host vendors the pinned wheels; platform coverage checked (truss-toolkit is pure Python, weft-sql 0.4.5 has abi3 wheels for macOS and manylinux, `pgserver-pg18` only for `truss-test` on manylinux and macOS 14 arm64) | Hold the extra out of the published wheel's metadata until the host resolves it |
| Preconditions, evolution, `expected_revision` or non-member refusal do not behave as the contract assumes | M | The mapping notes list each; the corpus tags a Truss limit; asks are in the requirements note | `Unsupported` for the affected actions or modules, or a documented race |
| Per-person connections and a per-connection assembly cost more than a shared pool (ADR-017); a quarantined connection has no channel to the host's pool | M | Pool per principal in the host; measure assembly construction; Arras closes a poisoned connection and CONTRACT-005 says the pool discards it | A documented, measured limit on concurrent people |
| The installer, registrar and importer are one administrative principal in CONTRACT-005 but Truss refuses ordinary business calls from an elevated installer | M | TR-01a splits the principals; the harness builds each role | Run installation as a deploy step outside Arras |
| A database of another Truss release cannot be upgraded, but hosts may call `migrate` at every start | M | TR-01a: install-or-verify in `migrate()` reports `unsupported_version` | The host recreates the database; a dev host does it with `--truss-reset` |
| The pinned driver tuple (psycopg 3.3.6, libpq 18.6) conflicts with praxis's psycopg | M | Checked in TR-02: praxis locks psycopg 3.3.6 and jsonschema 4.26.0, the same tuple, so the risk is closed | Hold the extra until the host aligns |
| Truss authorizes per document, not per module (compiled queries and the accepted document need read authority for every module in the document) | M | Arras registers one module per document; the corpus covers a multi-module document | Refuse such a document at registration for the Truss backend |
| A byte-different equal document creates a Truss revision and breaks later writes | M | Compare derived rows before `accept`; pass the accepted bytes on every write; a corpus case | Re-fetch the accepted document and retry |
| The corpus moves under the adapter (version 10 here; Truss's own harness is pinned to an older one) | M | The adapter is held to the current corpus; Truss's pinned evidence is not ours | Pin the corpus version in the harness for a release |
| A slice forces a change to Truss | M | Write it as a generic ask in the requirements note; do not fork or patch Truss | Keep the capability undeclared |

## Exit Criteria

Plan readiness requires defined scope, ordered slices, shared constraints and explicit verification gates. These planning checks do not establish completion. Execution is complete only when:

- [x] Arras, started with a per-person connection source and the Truss backend registered under a name, registers a module, validates and registers a change under the person's schema grant, reads it back, applies an action with a precondition and an idempotency key, replays it, dry-runs it, imports records, and answers `reached`, all through Truss on PostgreSQL 18.6; a test asserts each call ran as the person (`session_user`) and never as a service identity.
- [x] The conformance corpus passes on Truss at the adapter's declared capabilities, with every skipped case tagged to a documented Truss limit (`TrussHarness.LIMITS`: nine cases).
- [ ] Every slice's validation gate and the final integration gate pass, and the `truss` CI job is green on the pinned release. (Slice gates pass locally. Open, owner the user: the `truss` job has never run on GitHub; record its duration when it first does, and split or shard the full-corpus test if it passes about 40 minutes of its 60.)
- [ ] Acceptance evidence is recorded in the pull request and in this plan's Continuation Evidence; no required step or material blocker remains, and open Truss asks are listed with their state. (Evidence is in the rows above; the open items are the `truss` GitHub job, which has not yet run (owner: the user, on push), and the PR-side evidence. The open Truss asks and their state are in the requirements note's status table: R13 non-member refusal, R16 `expected_revision` and evolution, R17 related keys, R18 group asks, R19 import, R20 group-scoped journal read, R21 install and upgrade, R22 install-state read, R10 a package index. Host-owned and outside this repository: the per-person `ConnectionSource`, the installing connection and module roles, psycopg 3.3.6, and vendoring the pinned Truss and Weft wheels.)
- [x] The contracts, ADRs, PRD sketches, README and the Truss notes match what was built (done in TR-15).
