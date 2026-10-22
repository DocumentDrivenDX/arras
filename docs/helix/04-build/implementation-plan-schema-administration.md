---
ddx:
  id: implementation-plan-schema-administration
  type: implementation-plan
  activity: build
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-010
      kind: informed_by
    - id: FEAT-002
      kind: informed_by
    - id: ADR-026
      kind: informed_by
    - id: CONTRACT-011
      kind: informed_by
    - id: implementation-plan
      kind: informed_by
---

# Build Plan: Schema administration, the console's sandbox and the Query area (FEAT-010 slices 3 and 4)

## Scope

Implement OPR-12 to OPR-15 (US-073 to US-076): validate-only and person-run registration in the library, the backend `schema` grant and `validate_register` on the fakes and the conformance corpus, the schema surface (CONTRACT-011), schema import and export in the console, role-and-name picking and sandbox controls in the development host's console, and the removal of the `arras.devui` page. A Truss adapter does not exist in this repository, so Truss's grant mapping and dry run are specified in CONTRACT-004 and proven only on the fakes and the corpus; the surface answers 501 for a record store with no dry run.

**Governing Artifacts**:
- [FEAT-010](../01-frame/features/FEAT-010-operator-console.md) OPR-12 to OPR-15; US-073 to US-076; [FEAT-002](../01-frame/features/FEAT-002-type-registry.md) REG-06; PRD FR-61, FR-62
- [ADR-026](../02-design/adr/ADR-026-schema-administration-runs-as-the-person-on-a-surface-of-its-own.md), ADR-017, ADR-021, ADR-015
- [CONTRACT-011](../02-design/contracts/CONTRACT-011-schema-administration-surface.md), CONTRACT-002 (`schema()`), CONTRACT-004 (`schema` grant, `validate_register`), CONTRACT-005, CONTRACT-009 (unchanged), CONTRACT-001
- Module boundaries: `tests/modules_check.py`, architecture.md

## Shared Constraints

- The invariants of the slice-1 plan hold: Python 3.11 with `uv`, `ruff` and `pyright` clean, `tests/test_modules.py` and its 926-line module cap, no credential or input in a URL, log or scrubbed error text, `ui/` imports nothing from Python, the wheel carries no UI assets, Truss, Ashlar and UMF documents never name Arras.
- CONTRACT-009 stays byte-for-byte compatible: its OpenAPI document gains nothing, and `tests/test_operate.py::test_only_declared_actions_write` still passes. Schema writes exist only in CONTRACT-011's app.
- Access is the backend's: no Arras role table, no hard-coded user, no administrator shortcut. The administrative principal is refused on `session.schema()`.
- `core.py` (822 lines), `operate/__init__.py` (656) and `fakes.py` (850) stay under the cap of 926 lines: new code goes in new modules, and a behaviour-preserving extraction precedes any addition to those files.
- Tests come first in each slice, and each slice leaves the tree green.

## Slice 4: the Query area (OPR-16, OPR-17; US-077, US-078)

| Slice | Content | Gate |
|-------|---------|------|
| Q-001 | `POST /query` on the operator app (CONTRACT-009): `session.query` with `module` (required), `sql` (at most 4,000 characters, and 16 KiB of bytes before it reaches a backend; Arras does not parse it), `params`, `consistency`, `at_least`, `limit`; no cursor in or out; `QueryResult` JSON by an explicit encoder (`jsonable` for values); OpenAPI and `ui/openapi.json` regenerated; `test_only_declared_actions_write` lists it as a read | `tests/test_operate_query.py` per US-077; the OpenAPI drift guards green |
| Q-002 | `ui/` Query tab: SQL editor (Ctrl or Cmd with Enter runs it), consistency choice, a grid (sticky header, typed cells, null, long text clipped with the full value on focus, row count, truncated notice, freshness and revision), no page control (a next page is a keyset predicate the operator writes), the type panel inserting `SELECT … FROM module.Type x ORDER BY x.<key> LIMIT 50`, errors as the library states them, and a session-only history held above the tab so it survives tab switches (50 entries with their module, newest first, same query listed once, reuse and run again, clear), keyed to the viewed person so choosing another empties it; no browser storage | unit and integration tiers; a storage test; Playwright against the dev host |

Cut order: the typed cell rendering falls back to plain text. Never cut the no-storage rule or the error states.

## Design decisions made here

1. **Library layout.** `session.schema()` returns a `Schema` (new module `arras/schema_admin.py`, group `core`; not `schema.py`, which would read as the `gqlschema` group). The checks `Registry._checked` runs move to `arras/registration.py` as `check_document(h, principal, catalogs, document)`, taking what they need from `Ontology` as arguments, so neither new module imports `core` at run time (`tests/test_modules.py` counts lazy imports as edges and rejects cycles; `core` is imported under `TYPE_CHECKING` only). `_revision` moves out of `core.py` with them. `Registry` and `Schema` differ only in the authority check (`require_admin` versus `require_user`). `Schema`, `SchemaPlan`, `SchemaChange` and `RegistrationCheck` are exported from `arras.__all__` (sorted).
2. **Grant first.** `Schema.validate` parses the document (unparsable: `Invalid`, since no module can be named), then calls the record store's `validate_register`, whose first act is the grant check, so a person without `schema` is `Refused` whatever the placement or readability of the document. Only then are the host-side checks (names, placement, cross-module readability, the servable GraphQL schema) merged with the backend's compatibility violations into one `SchemaPlan`. `changes` are diffed from the provider's `current` `ModuleInfo` and the parsed proposal, from declared structure only (never a value), so the diff needs no `read` grant.
3. **The provider's result is narrow.** `validate_register` returns `RegistrationCheck(revision, changed, violations, report, current)`; Arras builds the `SchemaPlan` (CONTRACT-004).
4. **Race.** `expected_revision` is passed into the provider's `register` and checked inside its serialized step (CONTRACT-004); core does not check it outside.
5. **Grant mode.** `schema` is a fourth `fakes.Mode` (`read`, `write`, `journal`, `schema`). `FakeAccess.allowed` already honours a `"*"` grant for every mode, so a `"*"` `schema` grant in the fakes means any module, a fake-only simplification; the corpus covers the grant on a held module only and never uses `"*"`; the right to create a module is tested on the fake directly (`tests/test_fakes_registry.py`) and by each provider's own tests, since a Truss harness would implement it as a database privilege.
6. **Versions.** `CONTRACT_VERSIONS["backend"]` is 3 (a provider has `validate_register`, `register` takes the `schema` grant, and `query` takes a module and a Weft `Statement`) and `["schema"]` is 1; core calls `validate_register` through `getattr` so a provider without it is `Unsupported` (501), never an `AttributeError`. Tests that pin the version dict are updated.
7. **Replica.** A registration by a person does not reach the replica by `attach` (the fake refuses a non-administrator). `MemoryReplica.feed()` carries the source's `modules` with its state, as `core.py` already assumes ("a replica learns of the module through its feed"), and `Registry.register`'s courtesy attach stays best-effort.
8. **Dev roles.** `Sandbox.person(name, role)` mints a principal with the role's modes granted on `"*"` (so a module a person creates is visible to them and to others of the same role), replacing that name's grants. Roles: `none`, `viewer` (read), `editor` (read, write), `schema author` (read, schema), `auditor` (read, journal), `maintainer` (read, write, journal, schema). A name is `[a-z][a-z0-9_-]{0,31}`; `root` and the four fixed people (`alice`, `carol`, `bob`, `dave`) are refused as custom names. `root` stays in `/api/people` and the picker as a fixed person, because the console's existing tests and the persona demo show it refused: `require_user` refuses the administrator on every surface, schema surface included, so naming it by header grants nothing, and a test proves each surface answers it 403. Minting happens under `serialized()`'s lock (the lock that guards the fakes), and `validate_register` joins `_LOCKED`. Tokens are minted by the fake access object, never taken from a header. `alice` is a maintainer and `root` is granted `schema`, so the sandbox's own registering path keeps working.
9. **Surface.** `create_schema_app` lives in `arras/operate/schema_app.py`, is re-exported from `arras.operate` (CONTRACT-011's name) and added to `boundary.PUBLIC_MODULE_NAMES["arras.operate"]`. The shared plumbing in `operate/__init__.py` (`_post_allowed`, `_cors`, `_as_viewer`, `_body`, the in-flight gate, bound to `MAX_BODY`, `MAX_PER_PRINCIPAL = 4` and `MAX_IN_FLIGHT = 16`) is extracted into a base class in `operate/wire.py` with those limits as constructor parameters, so the schema app runs with a 4 MiB body, a 1 MiB document and 2 and 4 in flight.
10. **Export.** No server work. The console exports from the catalog it holds, skips the catalog's "not shown" note entries (`schemaFormat: "json-schema"`) and says so; "Export all" writes the catalog's entries as `arras-schema-catalog.json`.
11. **The dev UI's routes.** Each maps to the console or the dev host: the raw SQL `query` box (with `consistency` and `at_least`) maps to the console's Query area (OPR-16, `POST /query` with a module), and GraphiQL (FEAT-007) and the Data area's filters remain; the library's `query` is unchanged. `/api/dev/control`'s `register` op (the administrator registering another module, used by the existing Playwright tests) stays.

## Implementation Slices

| Slice | Story / Area | Governing Artifacts | Depends On | Validation Gate | Notes |
|-------|---------------|---------------------|------------|-----------------|-------|
| C-000 | Test plan and traceability rows (written with the specs); this plan, reviewed | docs/helix/03-test | None | Docs only | HELIX order: tests before code |
| C-001 | Extraction, behaviour-preserving: `check_document` and `_revision` to `registration.py`; the `Operate` plumbing to `operate/wire.py` as a base class with the limits as parameters; `tests/modules_check.py` knows both (`registration` in `core`, `wire` in `operate`) | Shared Constraints | None | The existing suite, `ruff`, `pyright` and `tests/test_modules.py` unchanged and green | Nothing new is added until this lands; core stays under the cap of 926 lines (`tests/test_modules.py:65`) |
| C-002 | Backend grant and dry run on the fakes, with every fixture that registers moved to `schema`: `fakes.Mode` gains `schema`; `MemoryStore.register` checks `schema` and takes `expected_revision`; `validate_register` via a `_plan` shared with `register` (new `fakes_registry.py`, same `doubles` group, keeping `fakes.py` under the cap); `MemoryReplica.validate_register` raises `Unsupported` and `MemoryReplica.feed` carries the source's `modules`; `Provider` gains `validate_register`; `RegistrationCheck`, `SchemaPlan`, `SchemaChange` in `results.py`; the conformance harness gains a `validate_register` operation (with `edit` and `expected_revision` step options) and a corrected `grant` docstring, the corpus gains the cases (version 5, `corpus_version` bumped in `conformance/fakes.py`) and `store.registers-for-writers-only-and-never-attaches` becomes schema-grant-only; `CONTRACT_VERSIONS["backend"]` is 3. **Fixtures moved from `write` to `schema` for registering:** `sandbox.py:61`, `conformance/fakes.py:23`, `testing.py:54` and `InMemory.person`, `tests/test_core.py` (66, 291, 330, 566-567, 640), `test_fakes.py:48`, `test_placement.py` (111, 134, 164), `test_operate.py:1330`, `test_document.py:114`, `test_operator_library.py` (210, 276), `test_conformance.py:79` | CONTRACT-004, CONTRACT-002 | C-001 | Corpus cases: validate changes no revision and no journal row and reports what `register` raises; both are refused with `write` and allowed with `schema`, and refused without a token; a racing `expected_revision` applies once. After a person registers and `feed()` runs, a `bulk` read on the replica shows the new types. `test_fakes`, `test_conformance`, `test_core` green | The tree stays green because the fixture changes are in this slice |
| C-003 | Library: `Ontology.schema()`, `Schema.validate` and `Schema.register` per decisions 1 to 4; exports; `CONTRACT_VERSIONS["schema"]`; telemetry events `arras.schema.validate` and `arras.schema.register` with the module name only (added to `telemetry.EVENTS`) | ADR-026, CONTRACT-002 | C-002 | `tests/test_schema_library.py`: a plan equals what registration then does (a Hypothesis test over compatible and incompatible edits; a stateful test is enough, ADR-020's machine is optional); a plan changes nothing; a person with `write` only is `Refused` and learns nothing of placement; stale and racing `expected_revision` apply nothing or once; the administrative principal is refused; an unplaced module with the grant is `ok: false`; an unparsable document is `Invalid`; a provider without `validate_register` is `Unsupported`; `tests/test_telemetry.py` proves no document text reaches a sink | |
| C-004 | Surface: `operate/schema_app.py` per decision 9 (CONTRACT-011), `authorize_schema`, the status table, `GET /version`, `PUBLIC_MODULE_NAMES`, `modules_check` | CONTRACT-011 | C-003 | `tests/test_schema_surface.py` per CONTRACT-011's Testing paragraph: two principals (`schema` and `write` only) get the backend's answers; `authorize_schema` false is 403 with the library untouched; stale revision is 409; foreign origin 403; scrubbed errors; limits (a 1 MiB document in a 4 MiB body passes, over either is 413); the app absent when not mounted and `/api/operate/openapi.json` unchanged; a drift test compares the surface's `SchemaPlan` JSON with the shapes `ui/` writes by hand | |
| C-005 | Dev host roles per decision 8: `Sandbox.person`, name and role rules, `x-arras-role`, `/api/people` returning `{people, roles, default}`, `/api/schema` mounted, `validate_register` in `_LOCKED`, minting under the lock | ADR-026, US-076 | C-004 | `tests/test_devhost_roles.py` (grants per role, name rules, `root` and the fixed people refused as custom names, replacement not accumulation, a header naming `root` is refused by every surface (console, operate and schema), non-loopback Host refused, concurrent minting under load); `test_devhost_server.py` and the MCP sandbox switch (`ARRAS_DEV_USER`) still green | |
| C-006 | UI client and import: `schemaApi` (probes `GET /api/schema/version`; a 404 hides import), the `SchemaImport` view in the Schema area, types written by hand from CONTRACT-011 with a drift guard in `ui/src/integration` beside `drift.int.test.ts`, unit and integration tiers | OPR-12, OPR-13 | C-005 | `npm run typecheck`, `npm test`, `npm run test:integration` including: compatible import shows the plan and applies; incompatible shows the count and no Apply; `viewer` refused and Apply disabled with the reason; stale revision shows the conflict; not mounted, no control | `schemaBase` prop, default `/api/schema` |
| C-007 | UI export per decision 10 | OPR-14 | C-006 | Unit test: byte-exact text, only readable modules, none for an attached module, note entries never saved; Playwright proves the Blob download under the console's CSP | The CSP risk is measured, not assumed |
| C-008 | UI sandbox toolbar (standalone host only, not exported from `index.ts`): presets, "custom name + role", outage and mend, token expiry, run the feed; replaces the `main.tsx` person picker | OPR-15 | C-005 | Unit and integration tests; an export-list test asserting `index.ts` does not export the toolbar; `npm run build` | |
| C-009 | Retire the dev UI: delete `src/arras/devui/`; move the cases of `tests/test_devui.py` not covered elsewhere to `test_devhost_*`, then delete it; extract a `build()` in `arras.devhost` for `tests/test_catalog_example.py`; remove `devui` from `tests/modules_check.py` (including the `devhost` allowed set) and rewrite `test_mcp_does_not_reach_the_dev_ui` and `test_operate_may_not_reach_another_transport` against `devhost`; update `examples/catalog/README.md`, architecture.md's `operate` row (the schema app), `.github` steps if any, and the wheel-contents test | US-076-AC7 | C-005, C-006, C-008 | Full `uv run pytest`, `ruff`, `pyright`; `grep -rn devui` finds nothing in the tree; the wheel lists no HTML page | The dev UI's last unique feature (loading a schema file) is C-006 |
| C-010 | Whole-stack test (Playwright against the dev host): as a `schema author` import an optional property with a preview and see the new revision (and a `bulk` read agree); as a `viewer` be refused with the reason; export the module and re-validate it (nothing would change); the strict-CSP check still passes. Docs: `ui/README.md`, traceability rows from `gap` to `covered` with evidence | US-073 to US-076 | C-006 to C-009 | `npm run e2e` locally (the schema specs run against a second dev host on port 8124, since they register a revision of `catalog`); traceability updated; CI jobs green | |

**Cut order** (cut the first line first if time runs out): the Hypothesis plan-equals-registration test falls back to a table of examples; the toolbar's token-expiry and feed controls; Playwright in CI; "Export all" (which leaves US-075-AC2 uncovered, stated in the traceability row). Never cut C-001 to C-005, the stale-revision check, the `schema`-versus-`write` conformance cases, or the removal of the dev UI's last feature before C-009 runs.

## Execution Contract

Each slice is one commit on the branch with its tests first. Run `uv run ruff format --check`, `uv run ruff check`, `uv run pyright` and `uv run pytest` after every Python slice, and `npm run typecheck && npm test` in `ui/` after every UI slice. Do not weaken or delete a test to pass; the one removal is `tests/test_devui.py` in C-009 after its cases are moved or shown covered.

## Validation Plan

- Python: the suites named per slice; `tests/test_conformance.py` runs the current corpus against both fakes and any future adapter.
- UI: Vitest (unit and integration tiers), `npm run build`, Playwright whole-stack.
- Docs: `traceability.md` rows for US-073 to US-076 move from `gap` to `covered` only with a test named.

## Risks and Rollbacks

| Risk | Mitigation |
|------|-----------|
| A plan and the registration it previews diverge | One code path: `register` calls the same `_plan` as `validate_register`; a property test compares them |
| `schema` versus `write` confusion breaks the many fixtures that register with only `write` | C-002 lists and moves each of them in the same slice as the gate change, and bumps the corpus and backend versions |
| The extraction in C-001 changes behaviour | It is a pure move; the unchanged suite is the proof; no behaviour test is edited |
| A Blob download is blocked by the strict CSP | Measured in C-007 and C-010; fallback is a data-less `<a download>` from `Response.blob()` or serving `GET /api/operate/explorer/…` with `Content-Disposition`, whichever the CSP admits, noted in CONTRACT-009 if the latter |
| Truss offers no dry run or no `schema` grant | The surface answers 501 and the console hides import for that module; recorded as an open dependency in CONTRACT-004 |
| Removing the dev UI drops a use someone relies on | Every dev UI route maps to the console or the dev host (decision 11), the raw SQL `query` box to the Query area; checked in C-009 against its routes: state, query, validate, invoke, batch, register, control |

Rollback: slices C-001 to C-005 are additive to the library and revertible one by one; C-009 is the only deletion and is last.

## Exit Criteria

- US-073 to US-076 acceptance criteria are `covered` in the traceability matrix, with the Truss-only gaps stated.
- A person with the `schema` grant imports a compatible change from a file in the console with a preview; a person with only `write` is refused by the backend; the same document exports back byte for byte.
- No `arras.devui` module exists, and `uv run --extra devhost python -m arras.devhost`, which serves the console, is the one way to run the sandbox.
- CONTRACT-009's published description still lists no write other than declared actions.
